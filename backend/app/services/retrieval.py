"""
MAIS_IA — Servicio de Búsqueda Híbrida y Recuperación.

Ejecuta búsquedas combinadas (densa + esparsa) en Qdrant
y aplica Reciprocal Rank Fusion (RRF) de forma nativa en la base de datos
para obtener los candidatos más relevantes.
"""

import asyncio
import logging
import re
import unicodedata

from qdrant_client import models

from app.core.config import get_settings
from app.db.qdrant import get_async_qdrant_client
from app.services.vector_store import (
    generate_dense_embeddings,
    generate_sparse_embeddings,
)

from sqlalchemy import select
from app.db.postgres import async_session_factory
from app.db.models import Document

logger = logging.getLogger(__name__)
settings = get_settings()


async def hybrid_search(
    query: str, 
    document_ids: list[str] | None = None, 
    top_k: int = 30,
    source_type: str | None = None,
) -> list[dict]:
    """
    Ejecuta una búsqueda híbrida nativa en Qdrant con fusión RRF de forma asíncrona.

    Args:
        query: Consulta del usuario en lenguaje natural.
        document_ids: Opcional, lista de IDs de documentos para filtrar el contexto.
        top_k: Número de candidatos a recuperar antes del re-ranking.
        source_type: Opcional, limita la búsqueda a una fuente (por ejemplo,
            ``youtube``) para evitar que un PDF desplace una transcripción.

    Returns:
        Lista de fragmentos en formato diccionario con su payload y score de fusión.
    """
    client = get_async_qdrant_client()
    collection_name = settings.qdrant_collection

    logger.info(
        "Búsqueda híbrida en colección '%s'. Query: '%s' (filter_docs=%s)",
        collection_name,
        query,
        document_ids,
    )

    # ── 1. Generar vectores de la consulta ─────────────────
    # Generar vector denso de forma no bloqueante (CPU/I/O local en hilo)
    dense_vector_list = await asyncio.to_thread(generate_dense_embeddings, [query])
    dense_vector = dense_vector_list[0]
    
    # Generar vector esparso de forma no bloqueante (CPU/I/O local en hilo)
    sparse_emb_list = await asyncio.to_thread(generate_sparse_embeddings, [query])
    sparse_emb = sparse_emb_list[0]
    sparse_vector = models.SparseVector(
        indices=sparse_emb["indices"],
        values=sparse_emb["values"]
    )

    # ── 2. Configurar filtros opcionales ───────────────────
    # Obtener documentos inactivos para excluirlos de la búsqueda
    inactive_ids = []
    try:
        async with async_session_factory() as db_session:
            stmt = select(Document.id).where(Document.is_active == False)
            res = await db_session.execute(stmt)
            inactive_ids = [str(r[0]) for r in res.all()]
    except Exception as exc:
        logger.error("Error al obtener documentos inactivos de la base de datos: %s", exc)

    must_conditions = []
    must_not_conditions = []

    if document_ids:
        must_conditions.append(
            models.FieldCondition(
                key="doc_id",
                match=models.MatchAny(any=document_ids)
            )
        )

    if source_type:
        must_conditions.append(
            models.FieldCondition(
                key="type",
                match=models.MatchValue(value=source_type),
            )
        )

    if inactive_ids:
        must_not_conditions.append(
            models.FieldCondition(
                key="doc_id",
                match=models.MatchAny(any=inactive_ids)
            )
        )

    filter_cond = None
    if must_conditions or must_not_conditions:
        filter_cond = models.Filter(
            must=must_conditions if must_conditions else None,
            must_not=must_not_conditions if must_not_conditions else None
        )

    # ── 3. Ejecutar consulta híbrida con fusión RRF ────────
    # Usamos query_points con prefetch para recuperar por ambos caminos
    # y FusionQuery para unificarlos en la base de datos de manera asíncrona.
    try:
        response = await client.query_points(
            collection_name=collection_name,
            prefetch=[
                # Búsqueda Densa (Semántica)
                models.Prefetch(
                    query=dense_vector,
                    using="dense",
                    limit=top_k,
                    filter=filter_cond,
                ),
                # Búsqueda Esparsa (Keywords / SPLADE)
                models.Prefetch(
                    query=sparse_vector,
                    using="sparse",
                    limit=top_k,
                    filter=filter_cond,
                ),
            ],
            # Fusión por Reciprocal Rank Fusion (RRF)
            query=models.FusionQuery(fusion=models.Fusion.RRF),
            limit=top_k,
        )
    except Exception as exc:
        logger.error("Fallo al ejecutar búsqueda híbrida en Qdrant: %s", exc)
        raise

    # ── 4. Formatear resultados ────────────────────────────
    results = []
    for point in response.points:
        payload = point.payload or {}
        results.append({
            "id": point.id,
            "score": point.score,  # Score de RRF
            "text": payload.get("text", ""),
            "doc_id": payload.get("doc_id", ""),
            "filename": payload.get("filename", ""),
            "page_number": payload.get("page_number", 0),
            "chunk_index": payload.get("chunk_index", 0),
            "type": payload.get("type", "pdf"),
            "video_id": payload.get("video_id", None),
        })

    logger.info(
        "Búsqueda híbrida completada. Recuperados %d candidatos.",
        len(results)
    )
    return results


_QUERY_STOP_WORDS = {
    "a", "al", "como", "con", "cual", "cuales", "de", "del", "el", "en",
    "es", "hacer", "hago", "la", "las", "lo", "los", "me", "para", "por",
    "que", "se", "un", "una", "y", "crear", "creo", "crea", "crear", "crear",
    "dime", "explica", "explicame", "necesito", "quiero", "puedo", "puedes",
    "realizar", "realizo", "realiza", "usar", "uso", "utilizar", "utilizo",
}

_VIDEO_TERM_ALIASES = {
    "albaran": {"albaran", "albaranes"},
    "albaranes": {"albaran", "albaranes"},
    "backup": {"backup", "copia", "seguridad"},
    "copia": {"copia", "backup", "seguridad"},
    "crear": {"crear", "nuevo", "nueva", "generar", "emitir", "facturar"},
    "emitir": {"emitir", "emision", "emitida", "facturar", "facturacion"},
    "factura": {"factura", "facturas", "facturar", "facturarlo", "facturacion"},
    "facturas": {"factura", "facturas", "facturar", "facturarlo", "facturacion"},
    "facturo": {"factura", "facturas", "facturar", "facturarlo", "facturacion"},
    "facturar": {"factura", "facturas", "facturar", "facturarlo", "facturacion"},
    "hoy": {"hoy", "dia", "diario", "fecha", "jornada", "actual"},
    "seguridad": {"seguridad", "copia", "backup"},
    "todo": {"todo", "total", "resumen", "listado", "informe"},
    "vendido": {"vendido", "vender", "venta", "ventas", "facturacion", "informe", "listado", "resumen"},
    "vender": {"vendido", "vender", "venta", "ventas", "facturacion", "informe", "listado", "resumen"},
    "ventas": {"vendido", "vender", "venta", "ventas", "facturacion", "informe", "listado", "resumen"},
    "ver": {"ver", "consultar", "visualizar", "listado", "informe", "resumen"},
}


def _normalise_terms(value: str) -> set[str]:
    """Normaliza español para coincidencias literales en transcripciones."""
    ascii_value = "".join(
        char
        for char in unicodedata.normalize("NFD", value.lower())
        if unicodedata.category(char) != "Mn"
    )
    return set(re.findall(r"[a-z0-9]+", ascii_value))


async def lexical_video_search(
    query: str,
    document_ids: list[str] | None = None,
    top_k: int = 16,
) -> list[dict]:
    """Busca términos literales en las transcripciones de vídeo seleccionadas.

    Los modelos dense/SPLADE instalados son principalmente ingleses. En español
    pueden devolver un tutorial que parece semánticamente cercano pero no trata
    la acción pedida. Esta pasada ligera lee los payloads de vídeo y premia las
    palabras que realmente aparecen en su texto o título.
    """
    query_terms = _normalise_terms(query) - _QUERY_STOP_WORDS
    if not query_terms:
        return []

    expanded_terms = set(query_terms)
    for term in query_terms:
        expanded_terms.update(_VIDEO_TERM_ALIASES.get(term, set()))
        # Singular simple para "facturas" / "albaranes" y casos similares.
        if len(term) > 4 and term.endswith("s"):
            expanded_terms.add(term[:-1])

    must_conditions = [
        models.FieldCondition(
            key="type",
            match=models.MatchValue(value="youtube"),
        )
    ]
    if document_ids:
        must_conditions.append(
            models.FieldCondition(
                key="doc_id",
                match=models.MatchAny(any=document_ids),
            )
        )

    client = get_async_qdrant_client()
    scroll_filter = models.Filter(must=must_conditions)
    offset = None
    matches: list[dict] = []
    document_terms: dict[str, dict[str, set[str] | int]] = {}
    # Las transcripciones de los vídeos activos caben holgadamente aquí; el
    # límite protege la API si se importaran miles de vídeos en el futuro.
    for _ in range(10):
        points, offset = await client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=scroll_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            text = payload.get("text", "")
            text_terms = _normalise_terms(text)
            title_terms = _normalise_terms(payload.get("filename", ""))
            exact_matches = query_terms & text_terms
            alias_matches = (expanded_terms - query_terms) & text_terms
            title_matches = expanded_terms & title_terms
            # Se exige al menos una palabra específica del usuario, una de sus
            # variantes o una coincidencia en el título del tutorial.
            score = len(exact_matches) * 4 + len(alias_matches) + len(title_matches) * 2
            if score:
                doc_id = payload.get("doc_id", "")
                coverage = document_terms.setdefault(
                    doc_id,
                    {"exact": set(), "alias": set(), "title": set(), "exact_chunks": 0},
                )
                coverage["exact"].update(exact_matches)
                coverage["alias"].update(alias_matches)
                coverage["title"].update(title_matches)
                if exact_matches:
                    coverage["exact_chunks"] += 1
                matches.append({
                    "id": point.id,
                    "score": 0.0,
                    "text": text,
                    "doc_id": payload.get("doc_id", ""),
                    "filename": payload.get("filename", ""),
                    "page_number": payload.get("page_number", 0),
                    "chunk_index": payload.get("chunk_index", 0),
                    "type": payload.get("type", "youtube"),
                    "video_id": payload.get("video_id"),
                    "chunk_match_score": score,
                    "lexical_score": score,
                })
        if offset is None:
            break

    # Para una pregunta con varios conceptos, el vídeo correcto puede mencionar
    # "factura" y "albarán" en chunks diferentes. Elegir solo el mejor chunk
    # premiaba un vídeo que repetía una única palabra. Sumamos cobertura por
    # documento y luego mantenemos los mejores tramos de ese documento.
    for chunk in matches:
        coverage = document_terms[chunk["doc_id"]]
        exact_terms = coverage["exact"]
        title_terms = coverage["title"]
        exact_chunks = coverage["exact_chunks"]
        if not isinstance(exact_terms, set) or not isinstance(title_terms, set) or not isinstance(exact_chunks, int):
            continue
        chunk["video_title_score"] = len(title_terms)
        # No se puede escoger un tutorial entero porque una palabra aparezca
        # una sola vez fuera de contexto. Debe estar en el título o repetirse
        # en varios tramos de la transcripción.
        if not title_terms and exact_chunks < 2:
            chunk["video_score"] = 0
            continue
        document_score = (
            len(exact_terms) * 8
            + len(coverage["alias"]) * 2
            # Un término en el título identifica el tutorial completo y es
            # más fiable que una mención aislada en cualquier transcripción.
            + len(title_terms) * 12
            + exact_chunks * 2
        )
        chunk["lexical_score"] += document_score
        chunk["video_score"] = document_score

    matches.sort(key=lambda chunk: (chunk["lexical_score"], -chunk["chunk_index"]), reverse=True)
    logger.info(
        "Búsqueda literal en vídeos: %d coincidencias para términos %s.",
        len(matches),
        sorted(expanded_terms),
    )
    return matches[:top_k]


async def get_video_transcript_chunks(doc_id: str) -> list[dict]:
    """Recupera la transcripción completa de un único vídeo en orden temporal."""
    client = get_async_qdrant_client()
    scroll_filter = models.Filter(
        must=[
            models.FieldCondition(
                key="doc_id",
                match=models.MatchValue(value=str(doc_id)),
            ),
            models.FieldCondition(
                key="type",
                match=models.MatchValue(value="youtube"),
            ),
        ]
    )
    offset = None
    chunks: list[dict] = []
    while True:
        points, offset = await client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=scroll_filter,
            limit=256,
            offset=offset,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            chunks.append({
                "id": point.id,
                "score": 0.0,
                "text": payload.get("text", ""),
                "doc_id": payload.get("doc_id", ""),
                "filename": payload.get("filename", ""),
                "page_number": payload.get("page_number", 0),
                "chunk_index": payload.get("chunk_index", 0),
                "type": payload.get("type", "youtube"),
                "video_id": payload.get("video_id"),
            })
        if offset is None:
            break

    chunks.sort(key=lambda chunk: chunk["chunk_index"])
    logger.info("Transcripción completa recuperada: %d fragmentos del vídeo %s.", len(chunks), doc_id)
    return chunks


async def get_video_neighbour_chunks(
    doc_id: str,
    center_chunk_indexes: list[int],
    radius: int = 2,
    limit: int = 18,
) -> list[dict]:
    """Obtiene los tramos contiguos de una transcripción ya recuperada.

    La búsqueda vectorial encuentra el instante que contiene las palabras de la
    pregunta, pero un procedimiento suele empezar unos segundos antes o acabar
    justo después. Este complemento no hace otra búsqueda semántica: lee los
    chunks vecinos del mismo vídeo para que el LLM reciba el procedimiento en
    orden y no una colección de frases aisladas.
    """
    if not center_chunk_indexes:
        return []

    client = get_async_qdrant_client()
    ranges = [
        models.Filter(
            must=[
                models.FieldCondition(
                    key="doc_id",
                    match=models.MatchValue(value=str(doc_id)),
                ),
                models.FieldCondition(
                    key="chunk_index",
                    range=models.Range(
                        gte=max(0, index - radius),
                        lte=index + radius,
                    ),
                ),
            ]
        )
        for index in sorted(set(center_chunk_indexes))[:4]
    ]

    by_id: dict[str, dict] = {}
    for scroll_filter in ranges:
        points, _ = await client.scroll(
            collection_name=settings.qdrant_collection,
            scroll_filter=scroll_filter,
            limit=limit,
            with_payload=True,
            with_vectors=False,
        )
        for point in points:
            payload = point.payload or {}
            by_id[str(point.id)] = {
                "id": point.id,
                "score": 0.0,
                "text": payload.get("text", ""),
                "doc_id": payload.get("doc_id", ""),
                "filename": payload.get("filename", ""),
                "page_number": payload.get("page_number", 0),
                "chunk_index": payload.get("chunk_index", 0),
                "type": payload.get("type", "youtube"),
                "video_id": payload.get("video_id"),
                # El score se conserva solo para que la respuesta API tenga un
                # formato homogéneo; estos chunks llegan por continuidad.
                "rerank_score": 0.0,
            }

    return sorted(by_id.values(), key=lambda chunk: chunk["chunk_index"])

