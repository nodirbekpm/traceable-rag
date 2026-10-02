"""Human review of facts the pipeline was not confident enough to accept on its own."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.models import ExtractedFact, ReviewQueue


class ReviewError(ValueError):
    pass


def open_reviews(session: Session) -> list[ReviewQueue]:
    return list(
        session.scalars(
            select(ReviewQueue)
            .where(ReviewQueue.resolved_at.is_(None))
            .order_by(ReviewQueue.created_at)
        )
    )


def resolve(session: Session, review_id: uuid.UUID, *, accept: bool) -> ReviewQueue:
    """Record a reviewer's decision. The fact keeps its span either way."""
    review = session.get(ReviewQueue, review_id)
    if review is None:
        raise ReviewError("review item not found")
    if review.resolved_at is not None:
        raise ReviewError("review item is already resolved")
    fact = session.get(ExtractedFact, review.fact_id)
    fact.validation_status = "verified" if accept else "rejected"
    fact.validation_reason = "accepted by reviewer" if accept else "rejected by reviewer"
    review.resolved_at = datetime.now(UTC)
    review.resolution = "accepted" if accept else "rejected"
    session.commit()
    return review
