"""
MAIS_IA — Controlador de Chat, Memoria Conversacional y Consultas.

Expone endpoints para:
- POST /api/v1/chat/query: Consulta inteligente CRAG con memoria y guardado en PostgreSQL.
- GET /api/v1/chat/history/{session_id}: Recuperación del historial completo de la sesión.
- DELETE /api/v1/chat/history/{session_id}: Limpieza y reinicio de la sesión de chat.
- GET /api/v1/chat/popular-questions: Consultas frecuentes para popups/sugerencias.
"""

import logging
import uuid
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.postgres import get_db_session
from app.services.chat_service import (
    delete_session_history,
    get_or_create_session,
    get_popular_queries,
    get_recent_history_context,
    get_session_messages,
    save_chat_message,
)
from app.services.crag_engine import CRAGEngine, get_crag_engine

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/chat", tags=["Chat"])


# ── Modelos de Petición y Respuesta ────────────────────────


class ChatQueryRequest(BaseModel):
    """Esquema de entrada para una consulta de chat con sesión."""

    query: str = Field(
        ..., 
        min_length=1, 
        max_length=1000, 
        description="Consulta del usuario a responder sobre los documentos"
    )
    document_ids: list[str] = Field(
        default_factory=list, 
        description="Lista de IDs de documentos para filtrar el contexto, si está vacía busca en todos"
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Identificador único de la sesión del usuario para mantener la memoria",
    )


class SourceDocument(BaseModel):
    """Esquema de detalles de un fragmento de origen utilizado."""

    doc_id: str = Field(..., description="ID del documento en la base de datos")
    filename: str = Field(..., description="Nombre original del archivo PDF o Vídeo")
    page_number: int = Field(..., description="Número de página o segundo del chunk")
    score: float = Field(..., description="Puntaje de relevancia final del Reranker")
    snippet: str = Field(..., description="Texto del fragmento de origen")
    type: Optional[str] = Field(default="pdf", description="Tipo de documento: 'pdf' o 'youtube'")
    video_id: Optional[str] = Field(default=None, description="ID del vídeo de YouTube si aplica")


class LatencyBreakdown(BaseModel):
    """Esquema detallado de tiempos de procesamiento en milisegundos."""

    retrieval: float = Field(..., description="Tiempo en recuperar y reordenar fragmentos")
    rewrite: float = Field(..., description="Tiempo en reescribir la query (0 si no aplica)")
    generation: float = Field(..., description="Tiempo en llamada al LLM para responder")
    total: float = Field(..., description="Latencia total de extremo a extremo")


class ChatQueryResponse(BaseModel):
    """Esquema de salida final del endpoint de consulta RAG."""

    answer: str = Field(..., description="Respuesta sintetizada generada por el LLM")
    sources: list[SourceDocument] = Field(..., description="Fuentes utilizadas para responder")
    crag_status: str = Field(..., description="Estado del flujo CRAG (CORRECT | AMBIGUOUS | NO_DATA_FOUND)")
    latency_ms: LatencyBreakdown = Field(..., description="Desglose de latencia")
    session_id: str = Field(..., description="ID de sesión persistente")


class MessageItem(BaseModel):
    """Esquema de un mensaje individual en el historial."""

    id: str
    session_id: str
    role: str
    content: str
    sources: Optional[list[dict]] = None
    latency_ms: Optional[dict] = None
    crag_status: Optional[str] = None
    created_at: Any


# ── Endpoints ──────────────────────────────────────────────


@router.post(
    "/query",
    response_model=ChatQueryResponse,
    status_code=status.HTTP_200_OK,
    summary="Realizar una consulta inteligente (CRAG con Memoria)",
    description=(
        "Envía una pregunta sobre el contenido indexado. "
        "Mantiene la memoria de la conversación asociada a session_id, "
        "reordena fragmentos, genera la respuesta y persiste el diálogo."
    ),
)
async def query_chat(
    payload: ChatQueryRequest,
    engine: CRAGEngine = Depends(get_crag_engine),
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Ejecuta una consulta inteligente RAG con memoria conversacional."""
    session_id = payload.session_id or str(uuid.uuid4())
    logger.info("Recibida consulta de chat (sesión %s): '%s'", session_id, payload.query)

    try:
        # 1. Asegurar sesión en base de datos y obtener historial previo
        await get_or_create_session(db, session_id)
        history = await get_recent_history_context(db, session_id, limit=6)

        # 2. Guardar mensaje del usuario en PostgreSQL
        await save_chat_message(
            db=db,
            session_id=session_id,
            role="user",
            content=payload.query,
        )

        # 3. Ejecutar pipeline CRAG con contexto histórico
        result = await engine.execute_query(
            query=payload.query, 
            document_ids=payload.document_ids,
            history=history,
        )

        # 4. Guardar respuesta del asistente en PostgreSQL
        await save_chat_message(
            db=db,
            session_id=session_id,
            role="assistant",
            content=result.get("answer", ""),
            sources=result.get("sources"),
            latency_ms=result.get("latency_ms"),
            crag_status=result.get("crag_status"),
        )

        # 5. Añadir session_id al resultado final
        result["session_id"] = session_id
        return result

    except Exception as exc:
        logger.exception("Fallo catastrófico al procesar la query de chat: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Fallo interno en el motor de consulta CRAG: {exc}",
        )


@router.get(
    "/history/{session_id}",
    response_model=list[MessageItem],
    status_code=status.HTTP_200_OK,
    summary="Obtener historial de una conversación",
)
async def get_history(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> list[dict]:
    """Retorna todos los mensajes previos de una sesión para restaurar el chat."""
    messages = await get_session_messages(db, session_id)
    return [
        {
            "id": str(m.id),
            "session_id": m.session_id,
            "role": m.role,
            "content": m.content,
            "sources": m.sources,
            "latency_ms": m.latency_ms,
            "crag_status": m.crag_status,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        }
        for m in messages
    ]


@router.delete(
    "/history/{session_id}",
    status_code=status.HTTP_200_OK,
    summary="Limpiar historial y reiniciar sesión",
)
async def clear_history(
    session_id: str,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    """Borra el historial de una sesión permitiendo iniciar un tema nuevo."""
    await delete_session_history(db, session_id)
    return {"message": f"Sesión {session_id} limpiada exitosamente"}


@router.get(
    "/popular-questions",
    response_model=list[str],
    status_code=status.HTTP_200_OK,
    summary="Obtener preguntas frecuentes para sugerencias y popups",
)
async def popular_questions(
    db: AsyncSession = Depends(get_db_session),
) -> list[str]:
    """Devuelve las preguntas más consultadas por los usuarios."""
    return await get_popular_queries(db, limit=5)
