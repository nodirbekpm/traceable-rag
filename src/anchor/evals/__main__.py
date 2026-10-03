"""Eval harness.

    python -m anchor.evals prepare            # eval database: corpus, chunks, extraction
    python -m anchor.evals run --suite all    # score, store in eval_result, write reports
    python -m anchor.evals history            # earlier runs, to spot regressions

Runs against a separate database (`<name>_eval`) so the gold corpus is exactly
the documents listed in evals/corpus.json, nothing more.
"""

import argparse
import json
import logging
import os
import time
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import create_engine, make_url, select, text

from anchor.answer import AskConfig
from anchor.config import get_settings

logger = logging.getLogger("anchor.evals")
REPORTS = Path("evals/reports")


def use_eval_database() -> str:
    """Point every engine in this process at the eval database, creating it if needed."""
    from anchor import db

    base = make_url(os.environ.get("DATABASE_URL") or get_settings().database_url)
    eval_url = os.environ.get("EVAL_DATABASE_URL") or base.set(
        database=f"{base.database}_eval"
    ).render_as_string(hide_password=False)
    name = make_url(eval_url).database
    admin = create_engine(base, isolation_level="AUTOCOMMIT")
    with admin.connect() as connection:
        exists = connection.scalar(
            text("SELECT 1 FROM pg_database WHERE datname = :name"), {"name": name}
        )
        if not exists:
            connection.execute(text(f'CREATE DATABASE "{name}"'))
    admin.dispose()
    os.environ["DATABASE_URL"] = eval_url
    get_settings.cache_clear()
    db.get_engine.cache_clear()
    db.get_sessionmaker.cache_clear()
    return eval_url


def prepare(skip_extract: bool, pause: float) -> None:
    from alembic import command
    from alembic.config import Config

    from anchor.db import get_sessionmaker
    from anchor.edgar import EdgarClient
    from anchor.embedding import build_embedder
    from anchor.extraction.extractor import extract_document
    from anchor.indexing import index_document
    from anchor.ingest import ingest_filings
    from anchor.llm import build_llm
    from anchor.models import SourceDocument
    from anchor.storage import RawStore

    url = use_eval_database()
    alembic = Config("alembic.ini")
    alembic.attributes["database_url"] = url
    command.upgrade(alembic, "head")

    settings = get_settings()
    store = RawStore(settings.raw_storage_dir)
    corpus = json.loads(Path("evals/corpus.json").read_text(encoding="utf-8"))["documents"]
    by_cik: dict[int, set[str]] = {}
    for entry in corpus:
        by_cik.setdefault(entry["cik"], set()).add(entry["accession"])

    with get_sessionmaker()() as session, EdgarClient(settings.edgar_user_agent) as client:
        for cik, accessions in by_cik.items():
            result = ingest_filings(
                session, client, store, cik, accessions=accessions, with_exhibits=False
            )
            logger.info("ingest cik=%s stored=%d skipped=%d", cik, result.stored, result.skipped)
        documents = session.scalars(select(SourceDocument)).all()
        missing = {e["accession"] for e in corpus} - {d.external_id for d in documents}
        if missing:
            logger.warning("not found on EDGAR (too old for the recent-filings feed?): %s", missing)

        embedder = build_embedder(settings)
        for document in documents:
            index_document(session, document, store, embedder)
        logger.info("indexed %d documents", len(documents))

        if skip_extract:
            return
        llm = build_llm(settings)
        for number, document in enumerate(documents):
            run = extract_document(session, document, llm, store, settings)
            logger.info("extract %s %s", document.external_id, run.status)
            if number + 1 < len(documents) and pause:
                time.sleep(pause)


def _table(rows: list[dict], columns: list[str]) -> str:
    def cell(value) -> str:
        if isinstance(value, float):
            return f"{value:.3f}" if value <= 1 else f"{value:.1f}"
        return "—" if value is None else str(value)

    lines = ["| " + " | ".join(columns) + " |", "|" + "---|" * len(columns)]
    lines += ["| " + " | ".join(cell(row.get(c)) for c in columns) + " |" for row in rows]
    return "\n".join(lines)


def run(suites: list[str], pause: float, with_reranker: bool) -> None:
    from anchor.db import get_sessionmaker
    from anchor.embedding import build_embedder
    from anchor.evals.suites import Corpus, retrieval_configs, run_answers, run_extraction
    from anchor.evals.suites import run_retrieval as score_retrieval
    from anchor.llm import build_llm
    from anchor.models import EvalResult
    from anchor.rerank import cross_encoder
    from anchor.storage import RawStore

    use_eval_database()
    settings = get_settings()
    REPORTS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M")
    with get_sessionmaker()() as session:
        corpus = Corpus(session, RawStore(settings.raw_storage_dir))
        results = []
        if "extraction" in suites:
            results.append(run_extraction(session, corpus))
        if "retrieval" in suites:
            embedder = build_embedder(settings)
            for config in retrieval_configs(with_reranker):
                reranker = cross_encoder() if config.reranker != "none" else None
                results.append(score_retrieval(session, corpus, embedder, config, reranker))
        if "answer" in suites:
            results.append(
                run_answers(
                    session, corpus, embedder=build_embedder(settings),
                    reranker=cross_encoder(), llm=build_llm(settings), settings=settings,
                    config=AskConfig(), pause_seconds=pause,
                )
            )  # fmt: skip

        for result in results:
            session.add(
                EvalResult(
                    suite=result.suite, run_config=result.config, metrics=result.metrics,
                    details=result.details, avg_cost=result.avg_cost, p50_ms=result.p50_ms,
                    p95_ms=result.p95_ms,
                )
            )  # fmt: skip
        session.commit()

    sections = []
    retrieval_rows = [
        r.config | r.metrics | {"p50_ms": r.p50_ms, "p95_ms": r.p95_ms}
        for r in results
        if r.suite == "retrieval"
    ]
    if retrieval_rows:
        columns = ["mode", "strategy", "reranker", "recall@5", "recall@10", "mrr", "p50_ms",
                   "p95_ms"]  # fmt: skip
        sections.append("## Retrieval\n\n" + _table(retrieval_rows, columns))
    for result in results:
        if result.suite == "retrieval":
            continue
        metrics = {k: v for k, v in result.metrics.items() if not isinstance(v, dict)}
        cost = float(result.avg_cost) if result.avg_cost is not None else None
        extra = {"p50_ms": result.p50_ms, "p95_ms": result.p95_ms, "avg_cost_usd": cost}
        rows = [{"metric": k, "value": v} for k, v in (metrics | extra).items()]
        title = "Extraction" if result.suite == "extraction" else "Answers"
        sections.append(
            f"## {title}\n\nConfig: `{json.dumps(result.config)}`\n\n"
            + _table(rows, ["metric", "value"])
        )
    report = f"# Eval report {stamp}\n\n" + "\n\n".join(sections) + "\n"
    (REPORTS / f"{stamp}.md").write_text(report, encoding="utf-8")
    (REPORTS / "latest.md").write_text(report, encoding="utf-8")
    print(report)


def history(suite: str | None) -> None:
    from anchor.db import get_sessionmaker
    from anchor.models import EvalResult

    use_eval_database()
    with get_sessionmaker()() as session:
        query = select(EvalResult).order_by(EvalResult.executed_at.desc()).limit(40)
        if suite:
            query = query.where(EvalResult.suite == suite)
        for row in session.scalars(query):
            print(row.executed_at.isoformat(timespec="minutes"), row.suite,
                  json.dumps(row.run_config), json.dumps(row.metrics))  # fmt: skip


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("--skip-extract", action="store_true")
    prep.add_argument("--pause", type=float, default=6.0, help="seconds between LLM calls")
    runner = commands.add_parser("run")
    runner.add_argument(
        "--suite", choices=["extraction", "retrieval", "answer", "all"], default="all"
    )
    runner.add_argument("--pause", type=float, default=6.0, help="seconds between LLM calls")
    runner.add_argument("--no-reranker", action="store_true")
    hist = commands.add_parser("history")
    hist.add_argument("--suite", choices=["extraction", "retrieval", "answer"])
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    if args.command == "prepare":
        prepare(args.skip_extract, args.pause)
    elif args.command == "run":
        suites = ["extraction", "retrieval", "answer"] if args.suite == "all" else [args.suite]
        run(suites, args.pause, not args.no_reranker)
    else:
        history(args.suite)


if __name__ == "__main__":
    main()
