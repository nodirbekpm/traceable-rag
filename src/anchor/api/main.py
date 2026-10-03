import json
import uuid
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import datetime
from decimal import Decimal
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any, Literal

from fastapi import (
    BackgroundTasks,
    Depends,
    FastAPI,
    File,
    HTTPException,
    Query,
    Response,
    UploadFile,
    status,
)
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from anchor import __version__, analysis
from anchor.answer import AskConfig, ask_stream
from anchor.cache import RedisCache
from anchor.config import get_settings
from anchor.db import get_session, get_sessionmaker
from anchor.documents import UploadError, load_text, store_upload
from anchor.embedding import build_embedder
from anchor.estimate import estimate_analysis
from anchor.extraction.review import ReviewError, open_reviews, resolve
from anchor.extraction.versioning import fact_history
from anchor.llm import LLMError, build_llm
from anchor.models import ExtractedFact, ExtractionRun, SourceDocument
from anchor.rerank import LLMReranker, NoReranker, cross_encoder
from anchor.retrieval import Mode
from anchor.storage import RawStore
from anchor.text import TEXT_VERSION

app = FastAPI(title="Anchor", version=__version__)

VIEWER = Path(__file__).parent / "static" / "viewer.html"

SessionDep = Annotated[Session, Depends(get_session)]


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    doc_type: str
    external_id: str | None
    publisher: str
    published_at: datetime | None
    source_url: str
    content_hash: str
    supersedes_id: uuid.UUID | None
    title: str | None
    media_type: str


class FactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    run_id: uuid.UUID
    field_name: str
    entity_id: str | None
    value_raw: str | None
    value_normalized: str | None
    unit: str | None
    span_start: int | None
    span_end: int | None
    source_excerpt: str | None
    confidence: Decimal | None
    validation_status: str
    validation_reason: str | None
    is_current: bool
    superseded_by: uuid.UUID | None
    created_at: datetime


class ReviewOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    fact_id: uuid.UUID
    reason: str
    created_at: datetime
    resolved_at: datetime | None
    resolution: str | None


class ReviewDecision(BaseModel):
    accept: bool


@app.get("/health")
def health(session: SessionDep, response: Response) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except SQLAlchemyError:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "degraded", "database": "unreachable", "version": __version__}
    return {"status": "ok", "database": "ok", "version": __version__}


class RunOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    document_id: uuid.UUID
    model_name: str
    model_version: str
    prompt_version: str
    schema_version: str
    text_version: str
    status: str
    started_at: datetime
    finished_at: datetime | None
    token_input: int | None
    token_output: int | None
    cost_usd: Decimal | None


@app.get("/", include_in_schema=False)
def viewer() -> FileResponse:
    return FileResponse(VIEWER, media_type="text/html")


@app.get("/documents/{document_id}/text")
def document_text(document_id: uuid.UUID, session: SessionDep) -> dict[str, str]:
    """The canonical text that every span offset refers to."""
    document = session.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    store = RawStore(get_settings().raw_storage_dir)
    return {"text": load_text(store, document), "text_version": TEXT_VERSION}


@app.get("/runs/{run_id}", response_model=RunOut)
def get_run(run_id: uuid.UUID, session: SessionDep) -> ExtractionRun:
    run = session.get(ExtractionRun, run_id)
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "run not found")
    return run


@app.get("/documents", response_model=list[DocumentOut])
def list_documents(session: SessionDep) -> list[SourceDocument]:
    return list(
        session.scalars(select(SourceDocument).order_by(SourceDocument.published_at.desc()))
    )


@app.get("/documents/{document_id}/facts", response_model=list[FactOut])
def list_facts(
    document_id: uuid.UUID, session: SessionDep, current: bool = True
) -> list[ExtractedFact]:
    """Facts of a document. `current=false` returns the full history, superseded rows included."""
    query = select(ExtractedFact).where(ExtractedFact.document_id == document_id)
    if current:
        query = query.where(ExtractedFact.is_current)
    return list(session.scalars(query.order_by(ExtractedFact.span_start.nulls_last())))


@app.get("/facts/{fact_id}/history", response_model=list[FactOut])
def get_fact_history(fact_id: uuid.UUID, session: SessionDep) -> list[ExtractedFact]:
    """The fact followed by every earlier value it replaced, newest first."""
    chain = fact_history(session, fact_id)
    if not chain:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "fact not found")
    return chain


@app.get("/review", response_model=list[ReviewOut])
def list_open_reviews(session: SessionDep) -> list:
    return open_reviews(session)


@app.post("/review/{review_id}/resolve", response_model=ReviewOut)
def resolve_review(review_id: uuid.UUID, decision: ReviewDecision, session: SessionDep):
    try:
        return resolve(session, review_id, accept=decision.accept)
    except ReviewError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


RerankChoice = Literal["cross-encoder", "llm", "none"]


def get_session_factory() -> Callable[[], AbstractContextManager[Session]]:
    """Streaming responses outlive request-scoped dependencies, so they open their own session."""
    return get_sessionmaker()


@lru_cache
def _redis_cache() -> RedisCache:
    return RedisCache(get_settings().redis_url)


def get_ask_components(rerank: RerankChoice = "cross-encoder") -> dict[str, Any]:
    settings = get_settings()
    try:
        llm = build_llm(settings)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    rerankers = {
        "cross-encoder": cross_encoder,
        "llm": lambda: LLMReranker(llm),
        "none": NoReranker,
    }
    return {
        "embedder": build_embedder(settings),
        "reranker": rerankers[rerank](),
        "llm": llm,
        "cache": _redis_cache(),
        "settings": settings,
    }


@app.get("/ask")
def ask_endpoint(
    q: Annotated[str, Query(min_length=3, max_length=500)],
    session_factory: Annotated[
        Callable[[], AbstractContextManager[Session]], Depends(get_session_factory)
    ],
    components: Annotated[dict[str, Any], Depends(get_ask_components)],
    mode: Mode = "hybrid",
    strategy: Literal["fixed", "sentence", "section"] = "section",
    document_id: uuid.UUID | None = None,
) -> StreamingResponse:
    """Server-sent events: `sources`, then `claim`* or `not_found`, then `done`."""
    config = AskConfig(
        mode=mode,
        strategy=strategy,
        document_id=str(document_id) if document_id else None,
    )

    def events():
        with session_factory() as session:
            for event in ask_stream(session, q, config=config, **components):
                yield f"event: {event['event']}\ndata: {json.dumps(event)}\n\n"

    return StreamingResponse(events(), media_type="text/event-stream")


# --- uploads: any document, estimated before it is analysed -------------------------


def _estimate(session: Session, document: SourceDocument) -> dict[str, Any]:
    settings = get_settings()
    store = RawStore(settings.raw_storage_dir)
    pages = None
    if document.media_type == "application/pdf":
        from io import BytesIO

        from pypdf import PdfReader

        pages = len(PdfReader(BytesIO(store.get(document.raw_path))).pages)
    return estimate_analysis(session, load_text(store, document), settings, pages=pages).as_dict()


@app.post("/documents", status_code=status.HTTP_201_CREATED)
async def upload_document(file: Annotated[UploadFile, File()], session: SessionDep) -> dict:
    """Store a file (PDF, DOCX, HTML, TXT, MD) and say what analysing it would take."""
    content = await file.read()
    store = RawStore(get_settings().raw_storage_dir)
    try:
        document, duplicate = store_upload(
            session, store, file.filename or "document", content, file.content_type
        )
    except UploadError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {
        "document": DocumentOut.model_validate(document).model_dump(mode="json"),
        "duplicate": duplicate,
        "estimate": _estimate(session, document),
        "status": analysis.status(session, document.id),
    }


@app.get("/documents/{document_id}/estimate")
def get_estimate(document_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    document = session.get(SourceDocument, document_id)
    if document is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    return _estimate(session, document)


def get_analysis_components() -> dict[str, Any]:
    settings = get_settings()
    try:
        llm = build_llm(settings)
    except LLMError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    return {
        "llm": llm,
        "embedder": build_embedder(settings),
        "store": RawStore(settings.raw_storage_dir),
        "settings": settings,
    }


@app.post("/documents/{document_id}/analyze", status_code=status.HTTP_202_ACCEPTED)
def analyze_document(
    document_id: uuid.UUID,
    background: BackgroundTasks,
    session: SessionDep,
    components: Annotated[dict[str, Any], Depends(get_analysis_components)],
    session_factory: Annotated[
        Callable[[], AbstractContextManager[Session]], Depends(get_session_factory)
    ],
) -> dict[str, Any]:
    """Start extraction and indexing in the background; poll `/status` for progress."""
    if session.get(SourceDocument, document_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "document not found")
    if analysis.start(document_id):
        background.add_task(analysis.run, session_factory, document_id, **components)
    return analysis.status(session, document_id)


@app.get("/documents/{document_id}/status")
def document_status(document_id: uuid.UUID, session: SessionDep) -> dict[str, Any]:
    return analysis.status(session, document_id)
