"""Ranking evaluation: compare the local hybrid ranking with NVIDIA reranking on a
fixed set of questions with known relevant passages (tests/data/rerank_eval.json).

The local ranker reproduces the retriever's hybrid formula (0.7 cosine + 0.3 lexical)
over the full passage set. The NVIDIA ranker reranks the same passages. Metrics:
hit@1, recall@3, MRR.
"""
from __future__ import annotations

import json
import math
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from .retriever import _lexical, tokenize

EVAL_PATH = Path(__file__).resolve().parents[2] / "tests" / "data" / "rerank_eval.json"
Ranker = Callable[[str, list[dict]], list[str]]  # (question, passages) -> passage ids, best first


def load_eval(path: Path = EVAL_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _cos(a: Sequence[float], b: Sequence[float]) -> float:
    na = math.sqrt(sum(x * x for x in a)) or 1.0
    nb = math.sqrt(sum(x * x for x in b)) or 1.0
    return sum(x * y for x, y in zip(a, b)) / (na * nb)


def local_ranker(embed: Callable[[Sequence[str]], list[list[float]]]) -> Ranker:
    cache: dict[str, list[float]] = {}

    def rank(q: str, passages: list[dict]) -> list[str]:
        missing = [p["text"] for p in passages if p["text"] not in cache]
        if missing:
            for t, e in zip(missing, embed(missing)):
                cache[t] = e
        qe = embed([q])[0]
        qt = tokenize(q)
        scored = [(0.7 * max(0.0, _cos(qe, cache[p["text"]])) + 0.3 * _lexical(qt, p["text"]), p["id"])
                  for p in passages]
        return [pid for _, pid in sorted(scored, key=lambda x: x[0], reverse=True)]

    return rank


def nvidia_ranker() -> Ranker:
    from . import nvidia_reranker

    def rank(q: str, passages: list[dict]) -> list[str]:
        scores = nvidia_reranker.rerank(q, [p["text"] for p in passages])
        ranked = [passages[s.index]["id"] for s in scores]
        return ranked + [p["id"] for p in passages if p["id"] not in ranked]

    return rank


@dataclass
class Metrics:
    name: str
    hit_at_1: float
    recall_at_3: float
    mrr: float
    per_question: list[tuple[str, int | None]]  # (question, rank of first relevant, 1-based)


def evaluate(name: str, ranker: Ranker, data: dict | None = None) -> Metrics:
    data = data or load_eval()
    passages = data["passages"]
    hits1 = rec3 = rr = 0.0
    per: list[tuple[str, int | None]] = []
    for item in data["questions"]:
        order = ranker(item["q"], passages)
        rel = set(item["relevant"])
        first = next((i + 1 for i, pid in enumerate(order) if pid in rel), None)
        per.append((item["q"], first))
        hits1 += 1.0 if first == 1 else 0.0
        rec3 += len(rel & set(order[:3])) / len(rel)
        rr += 1.0 / first if first else 0.0
    n = len(data["questions"])
    return Metrics(name, round(hits1 / n, 3), round(rec3 / n, 3), round(rr / n, 3), per)


def format_report(results: list[Metrics]) -> str:
    lines = ["| Ranker | hit@1 | recall@3 | MRR |", "|---|---|---|---|"]
    lines += [f"| {m.name} | {m.hit_at_1:.2f} | {m.recall_at_3:.2f} | {m.mrr:.2f} |" for m in results]
    return "\n".join(lines)
