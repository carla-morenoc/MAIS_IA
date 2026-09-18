"""
MAIS_IA — Motor Grafo Corrective RAG (CRAG).

Implementa la máquina de estados de CRAG de forma asíncrona:
- RETRIEVE: Recuperación híbrida + Re-Ranking.
- GRADE: Evaluación de relevancia contra un umbral (threshold=0.35).
- DECISION & REWRITE: Si es irrelevante, reescribe la query con LLM y reintenta.
- GENERATE: Genera respuesta final restrictiva con citas o retorna un mensaje seguro.
"""

import asyncio
import logging
import time
from typing import Any, Literal

from app.core.config import get_settings
from app.app_security.prompt_guard import INJECTION_BOUNDARY_INSTRUCTION, build_rag_context
from app.services.llm import get_llm_service
from app.services.reranker import get_reranker_service
from app.services.retrieval import hybrid_search

import re

def clean_search_query(query: str) -> str:
    """Elimina muletillas conversacionales en español para concentrar la búsqueda híbrida en la entidad clave."""
    fillers = [
        r"\bhablame de\b", r"\bháblame de\b", r"\bdime sobre\b", r"\bdime informacion de\b",
        r"\bdime información sobre\b", r"\bcuentame de\b", r"\bcuéntame de\b", r"\bque dice de\b",
        r"\bqué dice de\b", r"\bque habla de\b", r"\bqué habla de\b", r"\bexplicame\b",
        r"\bexplícame\b", r"\bbusca sobre\b", r"\binformacion de\b", r"\binformación sobre\b",
        r"\bque puedes decirme de\b", r"\bqué puedes decirme de\b", r"\bque sabes de\b", r"\bqué sabes de\b"
    ]
    cleaned = query
    for pattern in fillers:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)
    cleaned = cleaned.strip()
    return cleaned if len(cleaned) >= 2 else query


_MAIS_DOMAIN_TERMS = (
    "mais", "programa", "software", "aplicacion", "aplicación", "sistema",
    "factura", "facturacion", "facturación", "contabilidad", "contable",
    "venta", "ventas", "vendido", "vendidos", "artículo", "articulos",
    "artículos", "almacén", "almacen", "stock", "inventario", "usuario",
    "grid", "base de datos", "informe",
    "cierre", "caja", "verifactu", "ticket", "fichero", "documento", "manual",
    "video", "vídeo", "tutorial", "configur", "instal", "error", "pantalla",
    "boton", "botón", "campo", "api", "servidor", "copia de seguridad",
    "backup", "pdf", "youtube", "registro", "pedido", "albaran", "albarán",
)


def is_mais_scope_query(query: str, history: list[dict[str, str]] | None = None) -> bool:
    """Evita gastar recuperación/LLM en preguntas ajenas a los manuales de MAIS."""
    normalized_query = " ".join(query.lower().split())
    if any(term in normalized_query for term in _MAIS_DOMAIN_TERMS):
        return True

    # Permite preguntas de seguimiento como "¿y después?" dentro de un tema válido.
    if history:
        previous_user_turns = [
            turn.get("content", "")
            for turn in history
            if turn.get("role") == "user"
        ]
        return any(
            any(term in " ".join(content.lower().split()) for term in _MAIS_DOMAIN_TERMS)
            for content in previous_user_turns
        )
    return False

logger = logging.getLogger(__name__)
settings = get_settings()


class CRAGEngine:
    """Motor de orquestación del grafo de decisión Corrective RAG (CRAG)."""

    def __init__(self) -> None:
        self.llm = get_llm_service()
        self.reranker = get_reranker_service()
        self.threshold = settings.crag_relevance_threshold

    async def execute_query(
        self, 
        query: str, 
        document_ids: list[str] | None = None,
        history: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """
        Ejecuta el flujo completo de Corrective RAG (CRAG) midiendo latencias individuales
        e integrando memoria conversacional del historial previo.
        """
        start_total = time.perf_counter()
        latencies = {
            "retrieval": 0.0,
            "rewrite": 0.0,
            "generation": 0.0,
            "total": 0.0,
        }

        if not is_mais_scope_query(query, history):
            latencies["total"] = round((time.perf_counter() - start_total) * 1000, 2)
            return {
                "answer": (
                    "Solo puedo responder consultas relacionadas con los programas de MAIS, "
                    "informática, sus manuales y los videotutoriales seleccionados. "
                    "Formula la pregunta sobre una función, pantalla, configuración o procedimiento técnico."
                ),
                "sources": [],
                "crag_status": "NO_DATA_FOUND",
                "query_used": query,
                "latency_ms": latencies,
            }

        # ── 1. Nodo: RETRIEVE DUAL ──────────────────────────
        start_ret = time.perf_counter()
        
        # Ejecutar búsqueda por lenguaje natural completo y búsqueda por entidades en paralelo
        search_query = clean_search_query(query)
        logger.info("Consulta Natural: '%s' | Consulta Entidades: '%s' | Historial turnos: %d", query, search_query, len(history) if history else 0)

        task_orig = hybrid_search(query, document_ids=document_ids, top_k=30)
        
        if search_query.lower() != query.lower():
            task_entity = hybrid_search(search_query, document_ids=document_ids, top_k=30)
            res_orig, res_entity = await asyncio.gather(task_orig, task_entity)
        else:
            res_orig = await task_orig
            res_entity = []

        # Fusionar y deduplicar candidatos de ambas búsquedas por ID de chunk
        candidates_map = {c["id"]: c for c in res_orig}
        for c in res_entity:
            if c["id"] not in candidates_map:
                candidates_map[c["id"]] = c

        # Deduplicar por contenido de texto para eliminar redundancia de fragmentos de video en la base de datos
        seen_texts = set()
        unique_candidates = []
        for c in candidates_map.values():
            # Normalizar el texto (quitar espacios adicionales y pasar a minúsculas)
            norm_text = " ".join(c["text"].split()).lower()
            if norm_text not in seen_texts:
                seen_texts.add(norm_text)
                unique_candidates.append(c)
                
        all_candidates = unique_candidates
        logger.info(
            "Candidatos unificados de búsqueda dual (deduplicados por texto): %d fragmentos (de %d originales)", 
            len(all_candidates), 
            len(candidates_map)
        )

        top_chunks = await asyncio.to_thread(self.reranker.rerank, query, all_candidates, top_n=24)
        if top_chunks and all(chunk.get("type") == "youtube" for chunk in top_chunks):
            top_chunks = sorted(top_chunks, key=lambda chunk: chunk.get("page_number", 0))
        latencies["retrieval"] = round((time.perf_counter() - start_ret) * 1000, 2)

        # ── 2. Nodo: GRADE ─────────────────────────────────
        # Evaluamos si hay coincidencias literales de nombres propios o palabras clave de la query limpia
        query_terms = [w.lower().strip() for w in search_query.split() if len(w) >= 2]
        has_literal_match = False

        if top_chunks and query_terms:
            for chunk in top_chunks:
                chunk_lower = chunk["text"].lower()
                if any(term in chunk_lower for term in query_terms):
                    has_literal_match = True
                    break

        max_score = top_chunks[0]["rerank_score"] if top_chunks else 0.0
        # Si existe coincidencia literal o la consulta es una palabra corta/nombre propio, adaptar el umbral
        effective_threshold = 0.01 if has_literal_match else self.threshold

        logger.info(
            "Evaluación CRAG. Máximo score: %0.4f (Umbral efectivo: %0.2f, Coincidencia exacta: %s)",
            max_score,
            effective_threshold,
            has_literal_match,
        )

        crag_status: Literal["CORRECT", "AMBIGUOUS", "NO_DATA_FOUND"] = "CORRECT"
        final_chunks = top_chunks
        query_used = query

        # Si el score está por debajo del umbral efectivo y tampoco hay coincidencia exacta
        if max_score < effective_threshold and not has_literal_match:
            logger.warning(
                "Fragmentos por debajo del umbral (%0.4f < %0.2f). Iniciando reescritura de query.",
                max_score,
                effective_threshold,
            )
            
            # ── 3. Nodo: QUERY REWRITE & RETRY ─────────────
            start_rew = time.perf_counter()
            crag_status = "AMBIGUOUS"
            
            # Reescribir la query usando el LLM
            query_used = await self.llm.rewrite_query(query, history=history)
            
            # Reintentar búsqueda híbrida asíncrona con la query optimizada
            retry_candidates = await hybrid_search(query_used, document_ids=document_ids, top_k=25)
            retry_chunks = await asyncio.to_thread(self.reranker.rerank, query_used, retry_candidates, top_n=10)
            
            latencies["rewrite"] = round((time.perf_counter() - start_rew) * 1000, 2)

            # Re-evaluar score de la nueva búsqueda
            if not retry_chunks or (retry_chunks[0]["rerank_score"] < effective_threshold and not has_literal_match):
                # Si aún tras la reescritura no hay datos relevantes
                logger.warning("Búsqueda reintentada sin resultados suficientes. Estado: NO_DATA_FOUND.")
                crag_status = "NO_DATA_FOUND"
                final_chunks = []
            else:
                # Si el reintento funcionó, lo marcamos como corregido
                logger.info("Reintento de búsqueda híbrida exitoso.")
                final_chunks = retry_chunks

        # ── 4. Nodo: GENERATE ──────────────────────────────
        start_gen = time.perf_counter()
        
        if crag_status == "NO_DATA_FOUND":
            answer = (
                "¡Hola! Soy Maisito, el asistente oficial de MAIS. Lamentablemente no he encontrado información "
                "relevante en la documentación para responder a tu pregunta de manera precisa. "
                "¿Hay alguna otra consulta en la que te pueda asistir?"
            )
        else:
            # Construir contexto RAG con delimitadores XML estructurados
            # (mitiga Indirect Prompt Injection en PDFs maliciosos)
            context_str = build_rag_context(final_chunks)

            # Mapa de citas para que el LLM pueda referenciar las fuentes
            citation_map_lines = []
            for i, chunk in enumerate(final_chunks, start=1):
                clean_filename = chunk['filename'].replace('[', '(').replace(']', ')')
                if chunk.get("type") == "youtube":
                    raw_secs = chunk['page_number']
                    hrs = raw_secs // 3600
                    mins = (raw_secs % 3600) // 60
                    secs = raw_secs % 60
                    time_label = f"{hrs}:{mins:02d}:{secs:02d}" if hrs > 0 else f"{mins}:{secs:02d}"
                    citation_map_lines.append(f"chunk id={i} → [Video: {clean_filename}, min. {time_label}]")
                else:
                    citation_map_lines.append(f"chunk id={i} → [{clean_filename}, pág. {chunk['page_number']}]")
            citation_guide = "\n".join(citation_map_lines)

            # Formatear historial conversacional previo si existe
            history_str = ""
            if history:
                history_lines = []
                for turn in history[-4:]:
                    speaker = "Usuario" if turn.get("role") == "user" else "Maisito"
                    content = turn.get('content', '')
                    if len(content) > 400:
                        content = content[:400] + "..."
                    history_lines.append(f"{speaker}: {content}")
                history_str = f"Historial reciente de la conversación:\n" + "\n".join(history_lines) + "\n\n"

            source_fidelity_rule = (
                "\n8. FIDELIDAD A TODAS LAS FUENTES: Los PDFs y las transcripciones "
                "de vídeo tienen la misma validez. Usa literalmente sus hechos y pasos; "
                "puedes eliminar muletillas o reordenar para que se lea bien, pero no "
                "inventes, completes ni contradigas información."
                
            )

            system_prompt = (
                "Eres Maisito, el asistente virtual oficial, cercano y amigable de MAIS, una empresa de informática.\n"
                "Tu objetivo es guiar y ayudar a los clientes con dudas sobre nuestros programas, manuales y videotutoriales. Responde solo sobre ese ámbito. Mantén la continuidad si la pregunta hace referencia a lo hablado anteriormente.\n\n"
                "REGLAS ESTRICTAS DE FORMATO Y CITACIÓN:\n"
                "1. FUENTE DE VERDAD: El contexto recuperado es la única fuente de hechos y pasos. Tanto el PDF como la transcripción de vídeo son fuentes válidas. El historial solo sirve para resolver pronombres o el tema de seguimiento; nunca puede aportar, cambiar ni completar instrucciones. Prioriza el vídeo cuando responda directamente a la consulta, pero incorpora los pasos relevantes del PDF cuando complementen el mismo procedimiento.\n"
                "2. COBERTURA COMPLETA: Antes de responder, identifica internamente todas las acciones, menús, pantallas, botones, campos, confirmaciones y resultados distintos que aparezcan en los fragmentos relevantes. Inclúyelos todos una sola vez y en el orden en que se realizan. No descartes una acción porque parezca secundaria ni la reemplaces con un enlace.\n"
                "3. RESPUESTA PROCEDIMENTAL: Cuando el usuario pregunte cómo hacer, crear, emitir, configurar o resolver algo, no des un saludo ni una descripción general. Escribe el procedimiento paso a paso usando únicamente lo que dicen el vídeo o PDF. Cada paso debe ser concreto, fiel a la fuente y acabar con su cita. Si una parte necesaria no aparece en las fuentes, indícalo claramente en vez de inventarla.\n"
                "4. PÁRRAFOS Y PASOS: Para una consulta procedimental usa una lista numerada con todos los pasos respaldados por el contexto, aunque sean más de seis. Para una consulta no procedimental usa varios párrafos breves, uno por idea.\n"
                "5. CITAS DESPUÉS DEL CONTENIDO: La cita debe aparecer al final de cada párrafo o dato, después de la explicación, nunca como introducción. Para vídeo usa exactamente [Video: Nombre del video, min. M:SS] o [Video: Nombre, min. H:MM:SS] según el mapa. Para PDF usa [nombre_archivo.pdf, pág. X]. Está prohibido inventar marcas de tiempo, segundos o páginas.\n"
                "6. INTEGRACIÓN MULTIFUENTE: No mezcles datos de PDF y vídeo como si fueran una sola fuente. Cita cada afirmación según su origen y no atribuyas al vídeo algo que solo aparezca en el PDF.\n"
                "7. SIN REFERENCIAS NI RELLENO: No crees secciones finales de 'Referencias', 'Fuentes' o 'Bibliografía', no escribas 'Según la Fuente 1' y no repitas ideas. Toda afirmación debe estar respaldada por el contexto; si falta un dato, admítelo sin completarlo con conocimiento general."
                + source_fidelity_rule
                + INJECTION_BOUNDARY_INSTRUCTION
            )

            prompt = (
                f"{history_str}"
                f"Consulta actual del usuario: {query}\n\n"
                f"Mapa de citas obligatorio (usa exactamente este formato para cada fragmento citado):\n{citation_guide}\n\n"
                f"Contexto de referencia:\n{context_str}\n\n"
                f"Redacta la respuesta basándote primero en la transcripción del vídeo cuando exista. Pon cada cita al final del párrafo, copiándola literalmente del mapa de citas:"
            )

            try:
                answer = await self.llm.generate_response(prompt, system_prompt)
            except Exception as exc:
                logger.exception("Fallo durante la llamada al LLM para generación.")
                answer = f"Error interno en la generación de la respuesta: {exc}"

        latencies["generation"] = round((time.perf_counter() - start_gen) * 1000, 2)
        latencies["total"] = round((time.perf_counter() - start_total) * 1000, 2)

        # Dar formato final a las fuentes para la API
        sources = []
        for chunk in final_chunks:
            sources.append({
                "doc_id": chunk["doc_id"],
                "filename": chunk["filename"],
                "page_number": chunk["page_number"],
                "type": chunk.get("type", "pdf"),
                "video_id": chunk.get("video_id", None),
                "score": round(chunk["rerank_score"], 4),
                "snippet": chunk["text"],
            })

        return {
            "answer": answer,
            "sources": sources,
            "crag_status": crag_status,
            "query_used": query_used,
            "latency_ms": latencies,
        }


# Instancia singleton
crag_engine = CRAGEngine()


def get_crag_engine() -> CRAGEngine:
    """Retorna la instancia singleton de CRAGEngine."""
    return crag_engine
