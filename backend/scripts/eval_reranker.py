"""Compare local hybrid ranking with NVIDIA Nemotron reranking on the fixed eval set.

    cd backend
    python scripts/eval_reranker.py            # local ranking only (offline)
    python scripts/eval_reranker.py --nvidia   # also NVIDIA (needs NVIDIA_API_KEY; sends ONLY the
                                               # synthetic eval passages in tests/data, never your documents)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.evaluation import evaluate, format_report, local_ranker, nvidia_ranker  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--nvidia", action="store_true", help="also evaluate NVIDIA reranking (live API call)")
    ap.add_argument("--embedder", choices=["minilm", "hashing"], default="minilm")
    a = ap.parse_args()
    if a.embedder == "minilm":
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        fn = DefaultEmbeddingFunction()
        embed = lambda xs: [list(map(float, e)) for e in fn(list(xs))]  # noqa: E731
    else:
        from app.rag.vectorstore import hashing_embedder as embed

    results = [evaluate(f"local hybrid ({a.embedder})", local_ranker(embed))]
    if a.nvidia:
        from app.rag.nvidia_reranker import RerankUnavailable

        try:
            results.append(evaluate("NVIDIA nemotron-3.5-rerank-8b", nvidia_ranker()))
        except RerankUnavailable as exc:
            print(f"NVIDIA evaluation failed: {exc.reason} ({exc.code})", file=sys.stderr)
            return 1
    print(format_report(results))
    for m in results:
        misses = [(q, r) for q, r in m.per_question if r != 1]
        if misses:
            print(f"\n{m.name}: questions where the relevant passage was not ranked first")
            for q, r in misses:
                print(f"  rank {r}: {q}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
