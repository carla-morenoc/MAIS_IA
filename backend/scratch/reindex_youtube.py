"""Reencola todos los videotutoriales para regenerar sus chunks y vectores."""

import os
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db.models import Document, DocumentStatus
from app.db.postgres import sync_session_factory
from app.workers.ingestion import process_youtube_video_task


def reindex_youtube_videos() -> None:
    with sync_session_factory() as session:
        documents = (
            session.query(Document)
            .filter(Document.document_type == "youtube")
            .all()
        )

        if not documents:
            print("No hay videotutoriales para reindexar.")
            return

        for document in documents:
            document.status = DocumentStatus.PENDING
            document.error_message = None
            document.total_chunks = None

        session.commit()
        document_ids = [str(document.id) for document in documents]

    for document_id in document_ids:
        process_youtube_video_task.delay(document_id)

    print(f"Reindexados {len(document_ids)} videotutoriales.")


if __name__ == "__main__":
    reindex_youtube_videos()
