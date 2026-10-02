"""Run one document through the model and store what survives validation."""

import json
import logging
from datetime import UTC, datetime

from pydantic import ValidationError
from sqlalchemy.orm import Session

from anchor.config import Settings
from anchor.extraction.prompt import PROMPT_VERSION, SYSTEM, build_user_prompt
from anchor.extraction.schema import SCHEMA_VERSION, ExtractionOut, FactOut
from anchor.extraction.validator import validate
from anchor.llm import LLMClient, LLMError, cost_usd
from anchor.models import ExtractedFact, ExtractionRun, SourceDocument
from anchor.storage import RawStore
from anchor.text import TEXT_VERSION, html_to_text

logger = logging.getLogger(__name__)

# Longer documents are cut here; 8-K primary documents are far below this.
MAX_DOCUMENT_CHARS = 200_000


def parse_facts(payload: str) -> tuple[list[FactOut], int]:
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
            facts.append(FactOut.model_validate(item))
        except ValidationError as exc:
            logger.warning("dropped malformed fact %r: %s", item, exc.errors()[0]["msg"])
    return facts, len(items) - len(facts)


def extract_document(
    session: Session,
    document: SourceDocument,
    llm: LLMClient,
    store: RawStore,
    settings: Settings,
) -> ExtractionRun:
    text = html_to_text(store.get(document.raw_path))[:MAX_DOCUMENT_CHARS]
    run = ExtractionRun(
        document_id=document.id,
        model_name=llm.model_name,
        # Replaced by the provider-reported build once the call returns.
        model_version=llm.model_name,
        prompt_version=PROMPT_VERSION,
        schema_version=SCHEMA_VERSION,
        text_version=TEXT_VERSION,
        status="running",
    )
    session.add(run)
    session.commit()

    try:
        result = llm.generate_json(
            SYSTEM, build_user_prompt(text), ExtractionOut.model_json_schema()
        )
        run.model_version = result.model_version
        run.token_input = result.input_tokens
        run.token_output = result.output_tokens
        run.cost_usd = cost_usd(result, settings)
        facts, dropped = parse_facts(result.text)
    except (LLMError, ValueError) as exc:
        logger.error("extraction failed for %s: %s", document.external_id, exc)
        run.status = "failed"
        run.finished_at = datetime.now(UTC)
        session.commit()
        return run

    for fact in facts:
        checked = validate(fact, text)
        session.add(
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
    run.status = "succeeded"
    run.finished_at = datetime.now(UTC)
    session.commit()
    return run
