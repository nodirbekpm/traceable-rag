"""Idempotency, supersession and history. Nothing here deletes a row.

- A document is not re-extracted when a successful run with the same version key exists.
- A newer run of the same document replaces the older run's facts as the current view.
- An amendment (8-K/A) replaces the matching facts of the filing it amends.

"Replaces" always means: the old fact stays, `is_current` becomes false and
`superseded_by` points at the fact that took its place.
"""

import logging
import re
import uuid
from collections import defaultdict
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.models import ExtractedFact, ExtractionRun, SourceDocument

logger = logging.getLogger(__name__)

_MONTHS = "January|February|March|April|May|June|July|August|September|October|November|December"
_DATE = re.compile(rf"\b(?:{_MONTHS})\s+\d{{1,2}},\s+\d{{4}}\b")


def find_existing_run(
    session: Session,
    document_id: uuid.UUID,
    *,
    model_name: str,
    prompt_version: str,
    schema_version: str,
    text_version: str,
) -> ExtractionRun | None:
    """The successful run with this exact version key, if the work was already done."""
    return session.scalar(
        select(ExtractionRun).where(
            ExtractionRun.document_id == document_id,
            ExtractionRun.model_name == model_name,
            ExtractionRun.prompt_version == prompt_version,
            ExtractionRun.schema_version == schema_version,
            ExtractionRun.text_version == text_version,
            ExtractionRun.status == "succeeded",
        )
    )


def _pair(
    old: list[ExtractedFact], new: list[ExtractedFact]
) -> list[tuple[ExtractedFact, ExtractedFact | None]]:
    """Match old facts to their replacements by (field, entity), then by value.

    A field that occurs once on both sides is paired even if the value changed --
    that is exactly the correction we want to record. With several occurrences
    (e.g. several Items) only equal values are paired; the rest get no successor.
    """
    groups: dict[tuple[str, str | None], list[ExtractedFact]] = defaultdict(list)
    for fact in new:
        groups[(fact.field_name, fact.entity_id)].append(fact)
    old_counts: dict[tuple[str, str | None], int] = defaultdict(int)
    for fact in old:
        old_counts[(fact.field_name, fact.entity_id)] += 1

    pairs: list[tuple[ExtractedFact, ExtractedFact | None]] = []
    for fact in old:
        key = (fact.field_name, fact.entity_id)
        candidates = groups.get(key, [])
        if len(candidates) == 1 and old_counts[key] == 1:
            pairs.append((fact, candidates[0]))
            continue
        same = [c for c in candidates if c.value_normalized == fact.value_normalized]
        pairs.append((fact, same[0] if same else None))
    return pairs


def supersede_previous_runs(session: Session, run: ExtractionRun) -> int:
    """Make `run` the current view of its document. Returns how many facts were retired."""
    new = list(session.scalars(select(ExtractedFact).where(ExtractedFact.run_id == run.id)))
    old = list(
        session.scalars(
            select(ExtractedFact).where(
                ExtractedFact.document_id == run.document_id,
                ExtractedFact.run_id != run.id,
                ExtractedFact.is_current,
            )
        )
    )
    for fact, successor in _pair(old, new):
        fact.is_current = False
        # A fact already replaced by an amendment keeps that link.
        if fact.superseded_by is None and successor is not None:
            fact.superseded_by = successor.id
    return len(old)


def reconcile_amendment(session: Session, original_id: uuid.UUID, amendment_id: uuid.UUID) -> int:
    """Retire the original's facts that the amendment restates. Safe to call repeatedly.

    Only verified amendment facts count: an unverified value must not displace a
    verified one. Facts the amendment does not mention stay current.
    """
    amended = list(
        session.scalars(
            select(ExtractedFact).where(
                ExtractedFact.document_id == amendment_id,
                ExtractedFact.is_current,
                ExtractedFact.validation_status == "verified",
            )
        )
    )
    original = list(
        session.scalars(
            select(ExtractedFact).where(
                ExtractedFact.document_id == original_id, ExtractedFact.is_current
            )
        )
    )
    retired = 0
    for fact, successor in _pair(original, amended):
        if successor is not None:
            fact.is_current = False
            fact.superseded_by = successor.id
            retired += 1
    return retired


def link_amendment(session: Session, amendment: SourceDocument, text: str) -> SourceDocument | None:
    """Find the filing an 8-K/A amends and record it in `supersedes_id`.

    Amendments name the original by its filing date ("...the Current Report on
    Form 8-K filed on April 21, 2026"). We take the same filer's 8-K whose filing
    date is mentioned in the amendment (the most recent one if several match).
    No date match means no link: a wrong link would retire correct facts.
    """
    if not amendment.doc_type.endswith("/A") or amendment.published_at is None:
        return None
    if amendment.supersedes_id is not None:
        return session.get(SourceDocument, amendment.supersedes_id)

    mentioned = set()
    for match in _DATE.findall(text):
        mentioned.add(datetime.strptime(" ".join(match.split()), "%B %d, %Y").date())
    candidates = session.scalars(
        select(SourceDocument)
        .where(
            SourceDocument.publisher_id == amendment.publisher_id,
            SourceDocument.doc_type == amendment.doc_type.removesuffix("/A"),
            SourceDocument.published_at < amendment.published_at,
        )
        .order_by(SourceDocument.published_at.desc())
    ).all()
    # Filing timestamps are UTC while the text uses US dates, hence the one-day tolerance.
    day = timedelta(days=1)
    dated = [c for c in candidates if any(abs(c.published_at.date() - d) <= day for d in mentioned)]
    if not dated:
        logger.warning("%s: no original filing found for amendment", amendment.external_id)
        return None
    amendment.supersedes_id = dated[0].id
    return dated[0]


def reconcile_document(session: Session, document: SourceDocument) -> int:
    """Apply amendment supersession in whichever order the two filings were extracted."""
    retired = 0
    if document.supersedes_id is not None:
        retired += reconcile_amendment(session, document.supersedes_id, document.id)
    amendments = session.scalars(
        select(SourceDocument.id).where(SourceDocument.supersedes_id == document.id)
    ).all()
    for amendment_id in amendments:
        retired += reconcile_amendment(session, document.id, amendment_id)
    return retired


def fact_history(session: Session, fact_id: uuid.UUID) -> list[ExtractedFact]:
    """The chain of facts that led to `fact_id`, newest first, starting with the fact itself."""
    chain: list[ExtractedFact] = []
    frontier = [fact_id]
    first = session.get(ExtractedFact, fact_id)
    if first is None:
        return chain
    chain.append(first)
    seen = {fact_id}
    while frontier:
        previous = session.scalars(
            select(ExtractedFact)
            .where(ExtractedFact.superseded_by.in_(frontier))
            .order_by(ExtractedFact.created_at.desc())
        ).all()
        frontier = [f.id for f in previous if f.id not in seen]
        seen.update(frontier)
        chain.extend(f for f in previous if f.id in frontier)
    return chain
