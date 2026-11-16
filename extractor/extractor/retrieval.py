"""RAG-style retrieval without an LLM: chunk a document, score chunks with
weighted keyword + date-pattern evidence (BM25-flavoured), return the best.

Used twice: the rules extractor only reads retrieved lines, and the Claude
path only sees retrieved chunks, which keeps prompts small and keeps most of
a private file's text on the machine.
"""
from __future__ import annotations

import math
import re
from collections import Counter

from .dates import find_dates
from .models import Chunk, Doc

# term -> weight. Rare, high-signal words weigh more (idf-like prior).
TERM_WEIGHTS = {
    "due": 3.0, "deadline": 3.0, "submit": 2.5, "submission": 2.5, "turn in": 2.5,
    "midterm": 3.0, "final": 2.5, "exam": 3.0, "quiz": 2.5, "test": 1.5,
    "hw": 2.5, "homework": 2.5, "assignment": 2.5, "project": 2.0, "lab": 1.5,
    "paper": 1.5, "report": 1.5, "presentation": 2.0, "proposal": 1.5,
    "schedule": 1.5, "calendar": 1.5, "todo": 3.0, "to-do": 3.0, "study": 2.0,
    "review": 1.2, "remember": 2.0, "don't forget": 3.0, "must": 1.0,
    "extended": 2.5, "moved": 2.5, "postponed": 2.5, "rescheduled": 2.5,
    "announcement": 1.5, "[ ]": 2.5, "☐": 2.5,
}
DATE_BONUS = 2.0
_TOKEN = re.compile(r"[a-z0-9\-\[\]☐']+")


def make_chunks(doc: Doc, size: int = 5, overlap: int = 2) -> list[Chunk]:
    lines = doc.lines
    step = max(1, size - overlap)
    chunks = []
    for s in range(0, max(1, len(lines)), step):
        e = min(len(lines), s + size)
        body = "\n".join(lines[s:e])
        if body.strip():
            chunks.append(Chunk(s, e, body))
        if e >= len(lines):
            break
    return chunks


def score_chunk(chunk: Chunk, doc: Doc) -> float:
    low = chunk.text.lower()
    toks = Counter(_TOKEN.findall(low))
    score = 0.0
    for term, w in TERM_WEIGHTS.items():
        tf = low.count(term) if " " in term else toks.get(term, 0)
        if tf:
            score += w * (tf / (tf + 1.2)) * 1.0          # saturating tf, as in BM25
    n_dates = len(find_dates(chunk.text, doc.ref_date, doc.doc_date))
    if n_dates:
        score += DATE_BONUS + math.log1p(n_dates)
    return score


def retrieve(doc: Doc, top_k: int | None = None, min_score: float = 2.0) -> list[Chunk]:
    """Highest-scoring chunks, in document order. top_k=None keeps every
    chunk above the threshold."""
    chunks = make_chunks(doc)
    for c in chunks:
        c.score = score_chunk(c, doc)
    keep = [c for c in chunks if c.score >= min_score]
    if top_k is not None:
        keep = sorted(keep, key=lambda c: -c.score)[:top_k]
    return sorted(keep, key=lambda c: c.start)


def line_numbers(chunks: list[Chunk]) -> list[int]:
    seen: set[int] = set()
    for c in chunks:
        seen.update(range(c.start, c.end))
    return sorted(seen)
