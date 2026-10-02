import uuid
from datetime import datetime
from decimal import Decimal
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from anchor import __version__
from anchor.db import get_session
from anchor.extraction.review import ReviewError, open_reviews, resolve
from anchor.extraction.versioning import fact_history
from anchor.models import ExtractedFact, SourceDocument

app = FastAPI(title="Anchor", version=__version__)

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
