"""Routes each file through rules and/or Claude, then grounds and merges.

modes:
  rules   offline; retrieval + regex/date rules only
  claude  Claude on the top retrieved chunks only
  hybrid  rules first; Claude only for lines the rules couldn't label, or when
          the rules found nothing. (Seam for a local model later.)
"""
from __future__ import annotations

from .llm import ClaudeError, call_claude, extract_claude
from .merge import merge_items, resolve_todos
from .models import Chunk, Doc, Item
from .retrieval import make_chunks, retrieve
from .rules import extract_rules
from .verify import filter_grounded

MODES = ("rules", "claude", "hybrid")
CLAUDE_TOP_K = 6


def _chunks_around(doc: Doc, line_nos: list[int], pad: int = 2) -> list[Chunk]:
    lines = doc.lines
    spans: list[list[int]] = []
    for i in sorted(set(line_nos)):
        s, e = max(0, i - pad), min(len(lines), i + pad + 1)
        if spans and s <= spans[-1][1]:
            spans[-1][1] = max(spans[-1][1], e)
        else:
            spans.append([s, e])
    return [Chunk(s, e, "\n".join(lines[s:e])) for s, e in spans]


def extract_doc(doc: Doc, mode: str, call=call_claude, report: dict | None = None) -> list[Item]:
    report = report if report is not None else {}
    items: list[Item] = []
    uncovered: list[int] = []
    if mode in ("rules", "hybrid"):
        items, uncovered = extract_rules(doc)
    if mode == "claude":
        chunks = retrieve(doc, top_k=CLAUDE_TOP_K)
    elif mode == "hybrid" and (uncovered or not items):
        chunks = _chunks_around(doc, uncovered) if uncovered else retrieve(doc, top_k=CLAUDE_TOP_K)
    else:
        chunks = []
    if chunks:
        try:
            items += extract_claude(doc, chunks, call=call)
            report.setdefault("claude_calls", []).append(doc.path)
        except ClaudeError as e:
            if mode == "claude":
                raise
            report.setdefault("warnings", []).append(f"{doc.path}: Claude unavailable, rules only ({e})")
    return items


def run(docs: list[Doc], mode: str = "hybrid", call=call_claude) -> tuple[list[Item], dict]:
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    report: dict = {"mode": mode, "warnings": [], "dropped_ungrounded": [], "unscheduled": []}
    by_path = {d.path: d for d in docs}
    classes = {d.path: d.cls for d in docs}
    raw: list[Item] = []
    for d in docs:
        raw += extract_doc(d, mode, call=call, report=report)
    grounded, bad = filter_grounded(raw, by_path)
    report["dropped_ungrounded"] = [f"{b.source}: {b.text} {b.date}" for b in bad]
    merged, warns = merge_items(grounded, classes)
    final, unscheduled = resolve_todos(merged, classes)
    report["warnings"] += warns
    report["unscheduled"] = [f"{u.source}: {u.text}" for u in unscheduled]
    final.sort(key=lambda i: (i.date, i.text))
    return final, report
