"""Answer a question from retrieved chunks, emitting only claims whose citation checks out.

The model writes one JSON object per line (NDJSON): a claim, the source it relies
on and a verbatim quote. Each line is verified the moment it is complete and then
streamed, so verification does not delay the first visible token by more than one
claim. A claim is dropped when:

- it cites a source that was not provided,
- its quote is not in that source, or
- it states a number that its quote does not contain.

When no claim survives, the answer is "not found". Refusing is a measured
feature (see the eval harness), not a failure.
"""

import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from decimal import Decimal
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from anchor.cache import Cache
from anchor.config import Settings
from anchor.embedding import Embedder
from anchor.extraction.provenance import locate
from anchor.llm import LLMClient, LLMError, cost_usd
from anchor.models import Chunk, QueryLog, SourceDocument
from anchor.rerank import Reranker
from anchor.retrieval import Hit, Mode, retrieve

logger = logging.getLogger(__name__)

ANSWER_PROMPT_VERSION = "a1"
NOT_FOUND_TEXT = "Not found in the indexed documents."
_NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")

SYSTEM = """You answer questions about SEC filings using only the numbered sources given.

Output format: one JSON object per line, nothing else (no prose, no code fences).
Each line is one claim:
{"claim": "<one sentence of the answer>", "source": "S<n>", "quote": "<verbatim text>"}

Rules:
- "quote" must be copied character for character from the cited source and must
  contain every number, name and date the claim states.
- One fact per claim. Use several lines for several facts.
- Prefer sources not marked [SUPERSEDED]; those were replaced by an amendment.
- If the sources do not answer the question, output exactly one line:
{"not_found": true}"""


@dataclass(frozen=True)
class AskConfig:
    mode: Mode = "hybrid"
    strategy: str = "section"
    candidates: int = 30
    k: int = 6


@dataclass(frozen=True)
class Citation:
    document_id: str
    chunk_id: str
    external_id: str | None
    doc_type: str
    section: str | None
    span_start: int
    span_end: int
    quote: str


def _numbers(text: str) -> set[str]:
    return {match.replace(",", "") for match in _NUMBER.findall(text)}


def verify_claim(line: dict[str, Any], sources: dict[str, Hit]) -> Citation | str:
    """A citation for a supported claim, or the reason it is dropped."""
    claim, source_id, quote = line.get("claim"), line.get("source"), line.get("quote")
    if not (isinstance(claim, str) and isinstance(quote, str) and claim.strip()):
        return "malformed claim"
    hit = sources.get(str(source_id))
    if hit is None:
        return f"unknown source {source_id!r}"
    span = locate(hit.text, quote)
    if span is None:
        return "quote not found in source"
    found = hit.text[span.start : span.end]
    if not _numbers(claim) <= _numbers(found):
        return "claim states a number its quote does not contain"
    return Citation(
        document_id=str(hit.document_id),
        chunk_id=str(hit.chunk_id),
        external_id=hit.external_id,
        doc_type=hit.doc_type,
        section=hit.section,
        # Chunks are exact slices of the document text, so offsets add up.
        span_start=hit.span_start + span.start,
        span_end=hit.span_start + span.end,
        quote=found,
    )


def build_context(hits: list[Hit]) -> tuple[str, dict[str, Hit]]:
    sources: dict[str, Hit] = {}
    blocks: list[str] = []
    for number, hit in enumerate(hits, start=1):
        key = f"S{number}"
        sources[key] = hit
        date = hit.published_at.date().isoformat() if hit.published_at else "unknown date"
        flag = " [SUPERSEDED]" if hit.superseded else ""
        section = f", Item {hit.section}" if hit.section and hit.section[0].isdigit() else ""
        header = f"[{key}] {hit.publisher}, {hit.doc_type} filed {date}{section}{flag}"
        blocks.append(f"{header}\n{hit.text}")
    return "\n\n".join(blocks), sources


def _lines(pieces: Iterator[str]) -> Iterator[str]:
    buffer = ""
    for piece in pieces:
        buffer += piece
        while "\n" in buffer:
            line, buffer = buffer.split("\n", 1)
            yield line
    if buffer:
        yield buffer


def corpus_version(session: Session) -> str:
    """Changes whenever documents or chunks are added, which invalidates cached answers."""
    documents = session.scalar(select(func.count()).select_from(SourceDocument))
    chunks = session.scalar(select(func.count()).select_from(Chunk))
    return f"{documents}:{chunks}"


def cache_key(question: str, config: AskConfig, components: dict[str, str], corpus: str) -> str:
    material = json.dumps(
        {"q": " ".join(question.lower().split()), "config": asdict(config), **components,
         "corpus": corpus},
        sort_keys=True,
    )  # fmt: skip
    return hashlib.sha256(material.encode()).hexdigest()


def ask_stream(
    session: Session,
    question: str,
    *,
    embedder: Embedder,
    reranker: Reranker,
    llm: LLMClient,
    cache: Cache,
    settings: Settings,
    config: AskConfig | None = None,
) -> Iterator[dict[str, Any]]:
    """Yield events: `sources`, then `claim`* or `not_found`, then `done`."""
    config = config or AskConfig()
    started = time.perf_counter()

    def elapsed_ms() -> float:
        return round((time.perf_counter() - started) * 1000, 1)

    components = {
        "embedder": embedder.model_name,
        "reranker": reranker.name,
        "llm": llm.model_name,
        "prompt": ANSWER_PROMPT_VERSION,
    }
    key = cache_key(question, config, components, corpus_version(session))
    log_config = asdict(config) | components

    cached = cache.get(key)
    if cached is not None:
        yield from cached[:-1]
        done = cached[-1] | {"cache_hit": True, "latency_total_ms": elapsed_ms()}
        _log(session, question, log_config, cached, done, retrieval_ms=None, rerank_ms=None)
        yield done
        return

    events: list[dict[str, Any]] = []

    def emit(event: dict[str, Any]) -> dict[str, Any]:
        events.append(event)
        return event

    candidates = retrieve(
        session, embedder, question, mode=config.mode, strategy=config.strategy,
        k=config.candidates,
    )  # fmt: skip
    retrieval_ms = elapsed_ms()
    hits = reranker.rerank(question, candidates, config.k)
    rerank_ms = round(elapsed_ms() - retrieval_ms, 1)
    context, sources = build_context(hits)
    yield emit(
        {
            "event": "sources",
            "sources": [
                {"id": key, "chunk_id": str(hit.chunk_id), "document_id": str(hit.document_id),
                 "external_id": hit.external_id, "doc_type": hit.doc_type,
                 "section": hit.section, "superseded": hit.superseded}
                for key, hit in sources.items()
            ],
        }
    )  # fmt: skip

    claims = 0
    dropped = 0
    said_not_found = False
    ttft_ms: float | None = None
    error: str | None = None
    if hits:
        try:
            stream = llm.stream_text(SYSTEM, f"Question: {question}\n\nSources:\n\n{context}")
            for line in _lines(stream):
                line = line.strip()
                if not line.startswith("{"):
                    continue
                try:
                    parsed = json.loads(line)
                except json.JSONDecodeError:
                    dropped += 1
                    continue
                if parsed.get("not_found"):
                    said_not_found = True
                    continue
                verdict = verify_claim(parsed, sources)
                if isinstance(verdict, str):
                    dropped += 1
                    logger.info("dropped claim (%s): %s", verdict, parsed.get("claim"))
                    continue
                claims += 1
                ttft_ms = ttft_ms if ttft_ms is not None else elapsed_ms()
                yield emit({"event": "claim", "text": parsed["claim"].strip(),
                            "citation": asdict(verdict)})  # fmt: skip
        except LLMError as exc:
            error = str(exc)
            logger.error("answer generation failed: %s", exc)

    if claims == 0:
        ttft_ms = elapsed_ms()
        yield emit({"event": "not_found", "text": NOT_FOUND_TEXT})
    usage = llm.last_usage if hits else None
    done = {
        "event": "done",
        "not_found": claims == 0,
        "model_said_not_found": said_not_found,
        "claims": claims,
        "claims_dropped": dropped,
        "error": error,
        "latency_retrieval_ms": retrieval_ms,
        "latency_rerank_ms": rerank_ms,
        "latency_ttft_ms": ttft_ms,
        "latency_total_ms": elapsed_ms(),
        "cost_usd": str(cost_usd(usage, settings)) if usage else "0",
        "cache_hit": False,
    }
    events.append(done)
    # Failed generations are not cached: the next attempt should retry the model.
    if error is None:
        cache.set(key, events)
    _log(session, question, log_config, events, done, retrieval_ms=retrieval_ms,
         rerank_ms=rerank_ms)  # fmt: skip
    yield done


def _log(
    session: Session,
    question: str,
    config: dict[str, Any],
    events: list[dict[str, Any]],
    done: dict[str, Any],
    *,
    retrieval_ms: float | None,
    rerank_ms: float | None,
) -> None:
    claims = [event for event in events if event["event"] == "claim"]
    sources = next((event["sources"] for event in events if event["event"] == "sources"), [])
    session.add(
        QueryLog(
            question=question,
            config=config,
            retrieved_chunk_ids=[uuid.UUID(source["chunk_id"]) for source in sources],
            answer=" ".join(claim["text"] for claim in claims) or None,
            citations=[claim["citation"] for claim in claims],
            not_found=done["not_found"],
            claims_dropped=done["claims_dropped"],
            latency_retrieval_ms=retrieval_ms,
            latency_rerank_ms=rerank_ms,
            latency_ttft_ms=None if done["cache_hit"] else done["latency_ttft_ms"],
            latency_total_ms=done["latency_total_ms"],
            cost_usd=Decimal(0) if done["cache_hit"] else Decimal(done["cost_usd"]),
            cache_hit=done["cache_hit"],
        )
    )
    session.commit()


def ask(session: Session, question: str, **kwargs) -> dict[str, Any]:
    """Non-streaming convenience wrapper, used by the eval harness."""
    events = list(ask_stream(session, question, **kwargs))
    claims = [event for event in events if event["event"] == "claim"]
    return {
        "answer": " ".join(claim["text"] for claim in claims) or NOT_FOUND_TEXT,
        "claims": claims,
        "sources": events[0]["sources"],
        **{k: v for k, v in events[-1].items() if k != "event"},
    }
