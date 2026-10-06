"""API privada para el diario de ánimo."""

from datetime import datetime
import uuid

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import MoodEntry
from app.db.postgres import get_db_session

router = APIRouter(prefix="/journal", tags=["Journal"])


class MoodEntryCreate(BaseModel):
    mood: int = Field(..., ge=1, le=5)
    note: str = Field(..., min_length=1, max_length=3000)


class MoodEntryResponse(BaseModel):
    id: str
    mood: int
    note: str
    created_at: datetime


def serialize(entry: MoodEntry) -> MoodEntryResponse:
    return MoodEntryResponse(
        id=str(entry.id),
        mood=entry.mood,
        note=entry.note,
        created_at=entry.created_at,
    )


@router.post("", response_model=MoodEntryResponse, status_code=status.HTTP_201_CREATED)
async def create_mood_entry(
    payload: MoodEntryCreate,
    db: AsyncSession = Depends(get_db_session),
) -> MoodEntryResponse:
    entry = MoodEntry(mood=payload.mood, note=payload.note.strip())
    db.add(entry)
    await db.flush()
    await db.refresh(entry)
    return serialize(entry)


@router.get("", response_model=list[MoodEntryResponse])
async def list_mood_entries(
    db: AsyncSession = Depends(get_db_session),
) -> list[MoodEntryResponse]:
    result = await db.execute(
        select(MoodEntry).order_by(MoodEntry.created_at.desc()).limit(12)
    )
    return [serialize(entry) for entry in result.scalars().all()]
