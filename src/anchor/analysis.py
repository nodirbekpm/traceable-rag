"""Background analysis of an uploaded document: extract facts, then index for questions.

Job state lives in memory: the API runs as one process, and everything durable
(runs, facts, chunks) is in the database, so a restart loses only the progress bar.
"""

import logging
import threading
import time
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anchor.config import Settings
from anchor.embedding import Embedder
from anchor.extraction.extractor import extract_document
from anchor.indexing import index_document
from anchor.llm import LLMClient
from anchor.models import Chunk, ExtractionRun, SourceDocument
from anchor.storage import RawStore

logger = logging.getLogger(__name__)

# Uploads are indexed with the strategy questions use by default.
UPLOAD_STRATEGIES = ("section",)

_jobs: dict[uuid.UUID, dict[str, Any]] = {}
_lock = threading.Lock()


def _update(document_id: uuid.UUID, **fields: Any) -> None:
    with _lock:
        _jobs.setdefault(document_id, {}).update(fields)


def status(session: Session, document_id: uuid.UUID) -> dict[str, Any]:
    with _lock:
        job = dict(_jobs.get(document_id, {}))
    if job.get("state") in {"queued", "extracting", "indexing", "failed"}:
        return job
    succeeded = session.scalar(
        select(func.count()).where(
            ExtractionRun.document_id == document_id, ExtractionRun.status == "succeeded"
        )
    )
    chunks = session.scalar(select(func.count()).where(Chunk.document_id == document_id))
    if succeeded and chunks:
        return job | {"state": "ready", "chunks": chunks}
    return {"state": "new"}


def start(document_id: uuid.UUID) -> bool:
    """Mark a job as queued; False when it is already running."""
    with _lock:
        if _jobs.get(document_id, {}).get("state") in {"queued", "extracting", "indexing"}:
            return False
        _jobs[document_id] = {"state": "queued", "progress": 0.0, "started_at": time.time()}
        return True


def run(
    session_factory: Callable[[], AbstractContextManager[Session]],
    document_id: uuid.UUID,
    *,
    llm: LLMClient,
    embedder: Embedder,
    store: RawStore,
    settings: Settings,
) -> None:
    started = time.time()
    try:
        with session_factory() as session:
            document = session.get(SourceDocument, document_id)
            _update(document_id, state="extracting", step="Reading the document with the model")

            def progress(done: int, total: int) -> None:
                _update(document_id, progress=round(0.8 * done / total, 3),
                        step=f"Reading part {done} of {total}")  # fmt: skip

            extraction = extract_document(
                session, document, llm, store, settings, progress=progress
            )
            if extraction.status != "succeeded":
                raise RuntimeError("the model call failed; see the server log")
            _update(document_id, state="indexing", progress=0.85, step="Indexing for questions")
            index_document(session, document, store, embedder, UPLOAD_STRATEGIES)
        _update(document_id, state="ready", progress=1.0, step="Done",
                seconds=round(time.time() - started, 1))  # fmt: skip
    except Exception as exc:  # a background job must report, not crash silently
        logger.exception("analysis of %s failed", document_id)
        _update(document_id, state="failed", error=str(exc))
