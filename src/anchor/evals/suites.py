"""The three eval suites. Each returns metrics, per-item details and latency/cost samples."""

import json
import logging
import time
from collections.abc import Callable
from dataclasses import asdict, dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from anchor.answer import AskConfig, ask
from anchor.cache import MemoryCache
from anchor.config import Settings
from anchor.embedding import Embedder
from anchor.evals.metrics import (
    contains_fact,
    first_relevant_rank,
    mean_reciprocal_rank,
    occurrences,
    overlaps,
    percentile,
    ratio,
    recall_at,
    values_match,
)
from anchor.llm import LLMClient
from anchor.models import ExtractedFact, ExtractionRun, SourceDocument
from anchor.rerank import NoReranker, Reranker
from anchor.retrieval import MODES, retrieve
from anchor.storage import RawStore
from anchor.text import html_to_text

logger = logging.getLogger(__name__)

GOLDEN = Path("evals/golden")


@dataclass
class SuiteResult:
    suite: str
    config: dict[str, Any]
    metrics: dict[str, Any]
    details: list[dict[str, Any]]
    latencies_ms: list[float] = field(default_factory=list)
    costs: list[Decimal] = field(default_factory=list)

    @property
    def p50_ms(self) -> float | None:
        return percentile(self.latencies_ms, 50)

    @property
    def p95_ms(self) -> float | None:
        return percentile(self.latencies_ms, 95)

    @property
    def avg_cost(self) -> Decimal | None:
        return sum(self.costs) / len(self.costs) if self.costs else None


def load(name: str) -> list[dict[str, Any]]:
    with (GOLDEN / name).open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


class Corpus:
    """Documents by external id, with their canonical text loaded on demand."""

    def __init__(self, session: Session, store: RawStore) -> None:
        self._session = session
        self._store = store
        self._texts: dict[str, str] = {}

    def document(self, external_id: str) -> SourceDocument | None:
        return self._session.scalar(
            select(SourceDocument).where(SourceDocument.external_id == external_id)
        )

    def text(self, external_id: str) -> str:
        if external_id not in self._texts:
            document = self.document(external_id)
            self._texts[external_id] = html_to_text(self._store.get(document.raw_path))
        return self._texts[external_id]

    def evidence_spans(self, evidence: list[dict[str, str]]) -> dict[str, list[tuple[int, int]]]:
        spans: dict[str, list[tuple[int, int]]] = {}
        for item in evidence:
            document = self.document(item["document"])
            if document is None:
                continue
            found = occurrences(self.text(item["document"]), item["quote"])
            spans.setdefault(str(document.id), []).extend(found)
        return spans


# --- extraction ---------------------------------------------------------------------


def run_extraction(session: Session, corpus: Corpus) -> SuiteResult:
    """Scores the facts already extracted (run `anchor.extract` first) against the gold set."""
    gold_docs = load("extraction.jsonl")
    details: list[dict[str, Any]] = []
    matched = provenance_ok = wrong_value = missing_docs = 0
    total_gold = 0
    statuses: dict[str, int] = {}
    latencies: list[float] = []
    costs: list[Decimal] = []
    models: set[str] = set()

    for gold in gold_docs:
        document = corpus.document(gold["document"])
        if document is None:
            missing_docs += 1
            total_gold += len(gold["facts"])
            continue
        text = corpus.text(gold["document"])
        current = session.scalars(
            select(ExtractedFact).where(
                ExtractedFact.document_id == document.id, ExtractedFact.is_current
            )
        ).all()
        for fact in current:
            statuses[fact.validation_status] = statuses.get(fact.validation_status, 0) + 1
        verified = [f for f in current if f.validation_status == "verified"]
        run = session.scalar(
            select(ExtractionRun)
            .where(ExtractionRun.document_id == document.id, ExtractionRun.status == "succeeded")
            .order_by(ExtractionRun.started_at.desc())
        )
        if run is not None:
            models.add(f"{run.model_name}/{run.prompt_version}")
            if run.finished_at is not None:
                latencies.append((run.finished_at - run.started_at).total_seconds() * 1000)
            if run.cost_usd is not None:
                costs.append(run.cost_usd)

        for expected in gold["facts"]:
            total_gold += 1
            same_field = [f for f in verified if f.field_name == expected["field"]]
            hit = next(
                (
                    f
                    for f in same_field
                    if values_match(expected["field"], expected["value"], f.value_normalized)
                ),
                None,
            )
            gold_spans = occurrences(text, expected["quote"])
            # Correct provenance: the value's span lies inside some occurrence of the gold quote.
            supported = hit is not None and any(
                overlaps((hit.span_start, hit.span_end), span) for span in gold_spans
            )
            matched += hit is not None
            provenance_ok += supported
            wrong_value += hit is None and bool(same_field)
            details.append(
                {
                    "document": gold["document"],
                    "field": expected["field"],
                    "expected": expected["value"],
                    "found": hit.value_normalized if hit else None,
                    "provenance_ok": supported,
                    "candidates": [f.value_normalized for f in same_field],
                }
            )

    all_facts = sum(statuses.values())
    metrics = {
        "documents": len(gold_docs) - missing_docs,
        "gold_fields": total_gold,
        "field_accuracy": ratio(matched, total_gold),
        "provenance_correctness": ratio(provenance_ok, matched),
        "wrong_value_rate": ratio(wrong_value, total_gold),
        "hallucination_rate": ratio(statuses.get("hallucinated", 0), all_facts),
        "status_counts": statuses,
        "missing_documents": missing_docs,
    }
    return SuiteResult("extraction", {"models": sorted(models)}, metrics, details, latencies, costs)


# --- retrieval ----------------------------------------------------------------------


@dataclass(frozen=True)
class RetrievalConfig:
    mode: str
    strategy: str
    reranker: str = "none"


def retrieval_configs(with_reranker: bool) -> list[RetrievalConfig]:
    configs = [
        RetrievalConfig(mode, strategy)
        for strategy in ("fixed", "sentence", "section")
        for mode in MODES
    ]
    if with_reranker:
        configs.append(RetrievalConfig("hybrid", "section", "cross-encoder"))
    return configs


def run_retrieval(
    session: Session,
    corpus: Corpus,
    embedder: Embedder,
    config: RetrievalConfig,
    reranker: Reranker | None = None,
) -> SuiteResult:
    questions = [q for q in load("questions.jsonl") if q["answerable"]]
    reranker = reranker or NoReranker()
    ranks: list[int | None] = []
    latencies: list[float] = []
    details: list[dict[str, Any]] = []
    for question in questions:
        spans = corpus.evidence_spans(question["evidence"])
        started = time.perf_counter()
        hits = retrieve(
            session, embedder, question["question"], mode=config.mode,
            strategy=config.strategy, k=30 if config.reranker != "none" else 10,
        )  # fmt: skip
        hits = reranker.rerank(question["question"], hits, 10)
        latencies.append((time.perf_counter() - started) * 1000)
        relevant = [
            any(overlaps((h.span_start, h.span_end), s) for s in spans.get(str(h.document_id), []))
            for h in hits
        ]
        rank = first_relevant_rank(relevant)
        ranks.append(rank)
        details.append({"id": question["id"], "rank": rank})
    metrics = {
        "questions": len(questions),
        "recall@5": round(recall_at(ranks, 5), 4),
        "recall@10": round(recall_at(ranks, 10), 4),
        "mrr": round(mean_reciprocal_rank(ranks), 4),
    }
    return SuiteResult(
        "retrieval", asdict(config) | {"embedder": embedder.model_name}, metrics, details,
        latencies,
    )  # fmt: skip


# --- answers ------------------------------------------------------------------------


def run_answers(
    session: Session,
    corpus: Corpus,
    *,
    embedder: Embedder,
    reranker: Reranker,
    llm: LLMClient,
    settings: Settings,
    config: AskConfig,
    pause_seconds: float = 0.0,
    sleep: Callable[[float], None] = time.sleep,
) -> SuiteResult:
    questions = load("questions.jsonl")
    details: list[dict[str, Any]] = []
    correct = answerable = refused_correctly = unanswerable = false_refusals = 0
    citations_ok = citations_total = errors = 0
    latencies: list[float] = []
    ttfts: list[float] = []
    costs: list[Decimal] = []
    for index, question in enumerate(questions):
        if index and pause_seconds:
            sleep(pause_seconds)  # free-tier rate limits
        result = ask(
            session, question["question"], embedder=embedder, reranker=reranker, llm=llm,
            cache=MemoryCache(), settings=settings, config=config,
        )  # fmt: skip
        errors += result["error"] is not None
        latencies.append(result["latency_total_ms"])
        if result["latency_ttft_ms"] is not None:
            ttfts.append(result["latency_ttft_ms"])
        costs.append(Decimal(result["cost_usd"]))
        outcome: dict[str, Any] = {"id": question["id"], "answer": result["answer"]}
        if question["answerable"]:
            answerable += 1
            spans = corpus.evidence_spans(question["evidence"])
            is_correct = not result["not_found"] and all(
                contains_fact(result["answer"], fact) for fact in question["key_facts"]
            )
            correct += is_correct
            false_refusals += result["not_found"]
            for claim in result["claims"]:
                citation = claim["citation"]
                citations_total += 1
                cited = (citation["span_start"], citation["span_end"])
                citations_ok += any(
                    overlaps(cited, span) for span in spans.get(citation["document_id"], [])
                )
            outcome |= {"correct": is_correct, "not_found": result["not_found"]}
        else:
            unanswerable += 1
            refused_correctly += result["not_found"]
            outcome |= {"refused": result["not_found"]}
        details.append(outcome)
        logger.info("%s %s", question["id"], outcome)
    metrics = {
        "questions": len(questions),
        "answer_accuracy": ratio(correct, answerable),
        "citation_correctness": ratio(citations_ok, citations_total),
        "refusal_rate_unanswerable": ratio(refused_correctly, unanswerable),
        "false_refusal_rate": ratio(false_refusals, answerable),
        "citations": citations_total,
        "errors": errors,
        "ttft_p50_ms": percentile(ttfts, 50),
        "ttft_p95_ms": percentile(ttfts, 95),
    }
    run_config = asdict(config) | {
        "embedder": embedder.model_name, "reranker": reranker.name, "llm": llm.model_name,
    }  # fmt: skip
    return SuiteResult("answer", run_config, metrics, details, latencies, costs)
