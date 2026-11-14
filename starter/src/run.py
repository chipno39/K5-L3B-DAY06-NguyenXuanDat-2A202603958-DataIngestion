"""Day 06 Data Ingestion Engineering pipeline orchestration and benchmark evaluation."""
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import statistics
import time
from typing import Any
from dotenv import load_dotenv

from .chunking import by_paragraph, fixed_size
from .embeddings import MyEmbedder
from .evaluation import evaluate_query, summarize
from .ingestion import load_pdf
from .models import Chunk, DocumentPage
from .store import PgVectorStore


def _resolve_paths() -> tuple[Path, Path, list[Path]]:
    """Locate PDF corpus, benchmark file, and output directories whether run from root or starter/."""
    cwd = Path.cwd()
    if (cwd / "starter").exists():
        repo_root = cwd
    elif cwd.name == "starter":
        repo_root = cwd.parent
    else:
        repo_root = Path(__file__).resolve().parents[2]

    dotenv_candidates = [repo_root / "starter" / ".env", repo_root / ".env"]
    for env_path in dotenv_candidates:
        if env_path.exists():
            load_dotenv(env_path)
            break

    pdf_candidates = [
        repo_root / "data" / "2026_So-tay-TSV_compressed.pdf",
        repo_root / "starter" / "data" / "2026_So-tay-TSV_compressed.pdf",
    ]
    pdf_path = next((p for p in pdf_candidates if p.exists()), pdf_candidates[0])

    bench_candidates = [
        repo_root / "benchmark" / "questions.json",
        repo_root / "starter" / "data" / "benchmark.json",
    ]
    bench_path = next((p for p in bench_candidates if p.exists()), bench_candidates[0])

    out_dirs = [repo_root / "results", repo_root / "starter" / "results"]
    for d in out_dirs:
        d.mkdir(parents=True, exist_ok=True)

    return pdf_path, bench_path, out_dirs


def _compute_chunk_stats(chunks: list[Chunk]) -> dict[str, Any]:
    lengths = [len(c.text) for c in chunks]
    if not lengths:
        return {
            "chunk_count": 0,
            "total_chars": 0,
            "approx_tokens": 0,
            "min_len": 0,
            "max_len": 0,
            "mean_len": 0.0,
            "median_len": 0.0,
        }
    total_chars = sum(lengths)
    return {
        "chunk_count": len(lengths),
        "total_chars": total_chars,
        "approx_tokens": int(round(total_chars / 4.0)),
        "min_len": min(lengths),
        "max_len": max(lengths),
        "mean_len": round(statistics.mean(lengths), 1),
        "median_len": round(statistics.median(lengths), 1),
    }


def _build_strategy_chunks(
    strategy: str, pages: list[DocumentPage]
) -> tuple[list[Chunk], dict[str, Any]]:
    valid_pages = [p for p in pages if p.metadata.get("is_valid_content", False)]
    chunks: list[Chunk] = []

    if strategy == "A":
        params = {
            "chunking": "fixed_size",
            "chunk_size": 500,
            "overlap": 50,
            "metadata_fields": ["document_id", "source", "page", "section", "document_type", "language"],
            "use_metadata_filter": False,
        }
        for page in valid_pages:
            chunks.extend(fixed_size(page, size=500, overlap=50))
    elif strategy in ("B", "C"):
        params = {
            "chunking": "by_paragraph",
            "max_size": 850,
            "overlap": 0,
            "metadata_fields": ["document_id", "source", "page", "section", "document_type", "language"],
            "use_metadata_filter": strategy == "C",
        }
        for page in valid_pages:
            chunks.extend(by_paragraph(page, max_size=850))
    else:
        raise ValueError(f"Unknown strategy: {strategy}")

    return chunks, params


def main() -> None:
    pdf_path, bench_path, out_dirs = _resolve_paths()
    database_url = os.getenv(
        "DATABASE_URL", "postgresql://day6:day6_local_only@127.0.0.1:55433/day6_lab"
    )

    print(f"[1/5] Loading corpus from: {pdf_path}")
    pages = load_pdf(
        path=pdf_path,
        document_id="fptu-handbook-2026",
        source="data/2026_So-tay-TSV_compressed.pdf",
    )
    valid_pages = [p for p in pages if p.metadata.get("is_valid_content", False)]
    excluded_pages = [p for p in pages if not p.metadata.get("is_valid_content", False)]

    if len(valid_pages) < 30:
        raise RuntimeError(
            f"Corpus validation failed: only {len(valid_pages)} valid content pages (< 30 required)."
        )

    print(
        f"      Physical pages: {len(pages)} | Valid content pages: {len(valid_pages)} (>= 30 required) | Excluded pages: {len(excluded_pages)}"
    )

    benchmark_data = json.loads(bench_path.read_text(encoding="utf-8"))
    questions: list[dict[str, Any]] = benchmark_data["questions"]
    if len(questions) < 20:
        raise RuntimeError(f"Benchmark validation failed: only {len(questions)} questions (< 20 required).")

    print(f"[2/5] Initializing local embedding model & PostgreSQL + pgvector store...")
    embedder = MyEmbedder()
    store = PgVectorStore(database_url=database_url, dimensions=embedder.dimensions)
    store.create_schema()
    print(f"      Model: {embedder.model_name} (dim={embedder.dimensions})")

    strategy_stats: dict[str, Any] = {}
    all_traces: list[dict[str, Any]] = []
    chunks_by_strategy: dict[str, list[Chunk]] = {}

    for strategy in ("A", "B", "C"):
        print(f"[3/5] Running ingestion & indexing for Strategy {strategy}...")
        t0 = time.perf_counter()
        chunks, params = _build_strategy_chunks(strategy, pages)
        chunks_by_strategy[strategy] = chunks

        texts = [c.text for c in chunks]
        vectors = embedder.embed_documents(texts)
        store.upsert(strategy=strategy, chunks=chunks, vectors=vectors)
        ingest_seconds = round(time.perf_counter() - t0, 3)

        count_before_reingest = store.count_chunks(strategy)
        # Re-ingest same batch to verify idempotency (no duplicate rows)
        store.upsert(strategy=strategy, chunks=chunks, vectors=vectors)
        count_after_reingest = store.count_chunks(strategy)
        idempotent_ok = count_before_reingest == count_after_reingest == len(chunks)

        cstats = _compute_chunk_stats(chunks)
        strategy_stats[strategy] = {
            "strategy": strategy,
            "parameters": params,
            "chunk_stats": cstats,
            "ingest_time_seconds": ingest_seconds,
            "cost_usd": 0.0,
            "stored_count_before_reingest": count_before_reingest,
            "stored_count_after_reingest": count_after_reingest,
            "idempotency_verified": idempotent_ok,
        }
        print(
            f"      Strategy {strategy}: {cstats['chunk_count']} chunks | "
            f"mean_len={cstats['mean_len']} chars | ingest={ingest_seconds}s | "
            f"idempotent={idempotent_ok} ({count_before_reingest}->{count_after_reingest})"
        )

    print(f"[4/5] Running benchmark queries ({len(questions)} questions x 3 strategies)...")
    for strategy in ("A", "B", "C"):
        use_filter = strategy_stats[strategy]["parameters"]["use_metadata_filter"]
        q_start = time.perf_counter()
        for q in questions:
            q_vec = embedder.embed_query(q["question"])
            applied_filter = q.get("filter") if (use_filter and q.get("filter")) else None
            hits = store.search(
                strategy=strategy,
                query_vector=q_vec,
                top_k=3,
                filters=applied_filter,
            )
            trace = evaluate_query(
                question=q,
                hits=hits,
                strategy=strategy,
                applied_filter=applied_filter,
            )
            all_traces.append(trace)
        strategy_stats[strategy]["query_time_seconds"] = round(time.perf_counter() - q_start, 3)

    metrics_summary = summarize(all_traces)

    ingestion_log = {
        "run_timestamp": datetime.now(timezone.utc).isoformat(),
        "corpus_source_id": "fptu-handbook-2026",
        "source_path": "data/2026_So-tay-TSV_compressed.pdf",
        "total_physical_pages": len(pages),
        "valid_content_pages_count": len(valid_pages),
        "excluded_pages_count": len(excluded_pages),
        "excluded_pages_detail": [
            {
                "page": p.page,
                "section": p.metadata.get("section"),
                "reason": p.metadata.get("status"),
                "raw_chars": p.metadata.get("raw_chars"),
                "normalized_chars": p.metadata.get("normalized_chars"),
            }
            for p in excluded_pages
        ],
        "embedding_model": embedder.model_name,
        "embedding_dimensions": embedder.dimensions,
        "vector_store": "PostgreSQL 16.16 + pgvector 0.8.7 (exact cosine distance <=>)",
        "cost_usd": 0.0,
    }

    print("[5/5] Saving traces, metrics, and logs to results/...")
    for out_dir in out_dirs:
        (out_dir / "ingestion_log.json").write_text(
            json.dumps(ingestion_log, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "strategy_stats.json").write_text(
            json.dumps(strategy_stats, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "metrics_summary.json").write_text(
            json.dumps(metrics_summary, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        (out_dir / "traces.json").write_text(
            json.dumps(all_traces, ensure_ascii=False, indent=2), encoding="utf-8"
        )

    print("\n=== BENCHMARK SUMMARY (Hit@1 & Evidence Hit@3) ===")
    for strat in ("A", "B", "C"):
        dev_m = metrics_summary[strat]["dev"]
        test_m = metrics_summary[strat]["test"]
        print(
            f"Strategy {strat} | "
            f"DEV: Hit@1={dev_m['hit_at_1_fraction']} ({dev_m['hit_at_1_pct']}%), "
            f"Hit@3={dev_m['evidence_hit_at_3_fraction']} ({dev_m['evidence_hit_at_3_pct']}%), "
            f"Filter={dev_m['filter_compliance_fraction']} | "
            f"TEST: Hit@1={test_m['hit_at_1_fraction']} ({test_m['hit_at_1_pct']}%), "
            f"Hit@3={test_m['evidence_hit_at_3_fraction']} ({test_m['evidence_hit_at_3_pct']}%), "
            f"Filter={test_m['filter_compliance_fraction']}"
        )


if __name__ == "__main__":
    main()
