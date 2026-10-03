"""Run one document through the model and store what survives validation."""

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

from pydantic import ValidationError
from sqlalchemy.orm import Session

from anchor.config import Settings
from anchor.documents import load_text
from anchor.extraction.prompt import PROMPT_VERSION, build_system, build_user_prompt
from anchor.extraction.schema import FactOut, profile_for
from anchor.extraction.validator import validate
from anchor.extraction.versioning import (
    find_existing_run,
    link_amendment,
    reconcile_document,
    supersede_previous_runs,
)
from anchor.llm import LLMClient, LLMError, cost_usd
from anchor.models import ExtractedFact, ExtractionRun, ReviewQueue, SourceDocument
from anchor.storage import RawStore
from anchor.text import TEXT_VERSION

logger = logging.getLogger(__name__)

# One model call reads at most this much text (~10k tokens); longer documents are split.
WINDOW_CHARS = 40_000
# Hard ceiling for one document (~130 pages); the estimate warns before this is hit.
MAX_DOCUMENT_CHARS = 400_000


def parse_facts(payload: str, model: type[FactOut] = FactOut) -> tuple[list[FactOut], int]:
    """Parse the model's JSON fact by fact, so one malformed fact does not discard the rest.

    Returns the well-formed facts and the number that were dropped.
    """
    data = json.loads(payload)
    items = data.get("facts") if isinstance(data, dict) else None
    if not isinstance(items, list):
        raise ValueError('model output has no "facts" list')
    facts: list[FactOut] = []
    for item in items:
        try:
            facts.append(model.model_validate(item))
        except ValidationError as exc:
            logger.warning("dropped malformed fact %r: %s", item, exc.errors()[0]["msg"])
    return facts, len(items) - len(facts)


def windows(text: str, size: int = WINDOW_CHARS) -> list[str]:
    """Split text into pieces of at most `size` characters, at paragraph breaks where possible."""
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        if end < len(text):
            cut = text.rfind("\n\n", start + size // 2, end)
            end = cut if cut != -1 else end
        pieces.append(text[start:end])
        start = end
    return pieces


def extract_document(
    session: Session,
    document: SourceDocument,
    llm: LLMClient,
    store: RawStore,
    settings: Settings,
    *,
    progress: Callable[[int, int], None] | None = None,
) -> ExtractionRun:
    """Extract one document, or return the earlier run if this exact work was already done.

    The version key is document + model + prompt + schema + text version. To
    re-extract, change one of them; the old run and its facts are kept as history.
    """
    profile = profile_for(document.doc_type)
    existing = find_existing_run(
        session,
        document.id,
        model_name=llm.model_name,
        prompt_version=PROMPT_VERSION,
        schema_version=profile.version,
        text_version=TEXT_VERSION,
    )
    if existing is not None:
        return existing

    text = load_text(store, document)[:MAX_DOCUMENT_CHARS]
    link_amendment(session, document, text)
    run = ExtractionRun(
        document_id=document.id,
        model_name=llm.model_name,
        # Replaced by the provider-reported build once the call returns.
        model_version=llm.model_name,
        prompt_version=PROMPT_VERSION,
        schema_version=profile.version,
        text_version=TEXT_VERSION,
        status="running",
    )
    session.add(run)
    session.commit()

    system = build_system(profile)
    schema = profile.output_model.model_json_schema()
    pieces = windows(text)
    facts: list[FactOut] = []
    dropped = 0
    run.token_input = run.token_output = 0
    run.cost_usd = Decimal(0)
    try:
        for number, piece in enumerate(pieces, start=1):
            result = llm.generate_json(system, build_user_prompt(piece), schema)
            run.model_version = result.model_version
            run.token_input += result.input_tokens
            run.token_output += result.output_tokens
            run.cost_usd += cost_usd(result, settings)
            parsed, bad = parse_facts(result.text, profile.fact_model)
            facts.extend(parsed)
            dropped += bad
            if progress is not None:
                progress(number, len(pieces))
    except (LLMError, ValueError) as exc:
        logger.error("extraction failed for %s: %s", document.external_id or document.id, exc)
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        session.commit()
        return run

    stored: list[ExtractedFact] = []
    for fact in facts:
        # Quotes are located in the whole text, so a fact found in one window
        # still gets offsets relative to the full document.
        checked = validate(fact, text)
        stored.append(
            ExtractedFact(
                run_id=run.id,
                document_id=document.id,
                entity_id=checked.entity_id,
                field_name=checked.field_name,
                value_raw=checked.value_raw,
                value_normalized=checked.value_normalized,
                unit=checked.unit,
                span_start=checked.span_start,
                span_end=checked.span_end,
                source_excerpt=checked.source_excerpt,
                confidence=checked.confidence,
                validation_status=checked.validation_status,
                validation_reason=checked.reason,
            )
        )
    if dropped:
        logger.warning("%s: %d malformed facts dropped", document.external_id, dropped)
    session.add_all(stored)
    session.flush()
    session.add_all(
        ReviewQueue(fact_id=fact.id, reason=fact.validation_reason or "needs review")
        for fact in stored
        if fact.validation_status == "needs_review"
    )
    # The new facts, the retirement of the old ones and the run status change
    # commit together: readers never see two current versions of a fact.
    supersede_previous_runs(session, run)
    reconcile_document(session, document)
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    session.commit()
    return run
