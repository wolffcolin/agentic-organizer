"""Claude via `claude -p`. Only retrieved chunks are sent."""
from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from datetime import date

from .dates import find_dates
from .models import Chunk, Doc, Item
from .rules import ANCHOR_RE

PROMPT = """You extract deadlines, exams and to-dos from a student's school file.

File: {path}
Course: {cls}
File date (use to resolve relative dates like "next Friday" and missing years): {doc_date}

Rules:
- Only report items that are explicitly in the excerpts below. Never invent dates.
- type is one of: deadline (assignment/project due), exam (exam/midterm/final/quiz), todo (a task for the student).
- date is YYYY-MM-DD, or null for a to-do with no date. time is HH:MM (24h) or null.
- "quote" must be an exact, verbatim substring of the excerpts containing the date (or the to-do).
- If a line says a date was moved/extended/changed, report the NEW date and set "changed": true.
- For an undated to-do tied to an exam ("study ch. 7 before the midterm"), set "anchor" to midterm, final or exam.
- Skip lecture topics, office hours and anything that is not something the student must do or attend.

Reply with ONLY JSON: {{"items":[{{"type":"","text":"","date":null,"time":null,"quote":"","changed":false,"anchor":null}}]}}

Excerpts (line numbers shown for reference only):
{excerpts}
"""


class ClaudeError(RuntimeError):
    pass


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().lower()


def build_prompt(doc: Doc, chunks: list[Chunk]) -> str:
    ex = "\n---\n".join(
        "\n".join(f"{c.start + j + 1}: {ln}" for j, ln in enumerate(c.text.splitlines())) for c in chunks)
    return PROMPT.format(path=doc.path, cls=doc.cls or "unknown", doc_date=doc.doc_date.isoformat(), excerpts=ex)


def call_claude(prompt: str, model: str | None = None, timeout: int = 120, retries: int = 1) -> str:
    cmd = ["claude", "-p", "--output-format", "json", "--tools", "", "--no-session-persistence"]
    model = model or os.environ.get("EXTRACTOR_CLAUDE_MODEL")
    if model:
        cmd += ["--model", model]
    last = None
    for _ in range(retries + 1):
        try:
            with tempfile.TemporaryDirectory() as cwd:   # keep project context out of the call
                r = subprocess.run(cmd, input=prompt, capture_output=True, text=True,
                                   timeout=timeout, cwd=cwd)
            if r.returncode != 0:
                last = ClaudeError(r.stderr.strip()[:300] or f"claude exited {r.returncode}")
                continue
            return json.loads(r.stdout)["result"]
        except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError) as e:
            last = ClaudeError(f"claude call failed: {e}")
    raise last or ClaudeError("claude call failed")


def parse_items(raw: str) -> list[dict]:
    m = re.search(r"\{.*\}", raw, re.S)
    if not m:
        raise ClaudeError("no JSON in Claude reply")
    data = json.loads(m.group(0))
    return [x for x in data.get("items", []) if isinstance(x, dict)]


def to_items(raw_items: list[dict], doc: Doc) -> list[Item]:
    out: list[Item] = []
    for x in raw_items:
        typ = x.get("type")
        text = (x.get("text") or "").strip()
        if typ not in ("deadline", "exam", "todo") or not text:
            continue
        d = None
        if x.get("date"):
            try:
                d = date.fromisoformat(x["date"])
            except ValueError:
                continue
        t = x.get("time")
        if t and not re.fullmatch(r"\d{2}:\d{2}", t):
            t = None
        anchor = x.get("anchor")
        quote = (x.get("quote") or "").strip()
        if anchor not in ("midterm", "final", "exam"):
            m = ANCHOR_RE.search(quote)
            anchor = m.group("a").lower() if m else None
        out.append(Item(typ, text, d, doc.path, quote=quote, time=t, confidence=0.7, origin="claude",
                        override_hint=bool(x.get("changed")), anchor=anchor, doc_date=doc.doc_date))
    return out


def extract_claude(doc: Doc, chunks: list[Chunk], call=call_claude) -> list[Item]:
    if not chunks:
        return []
    raw = call(build_prompt(doc, chunks))
    return to_items(parse_items(raw), doc)


def quote_in_doc(quote: str, doc: Doc) -> bool:
    return bool(quote) and _norm(quote) in _norm(doc.text)


__all__ = ["extract_claude", "call_claude", "build_prompt", "parse_items", "to_items", "quote_in_doc",
           "ClaudeError", "find_dates"]
