"""Read PDF / DOCX / text files into a Doc."""
from __future__ import annotations

import re
from collections import Counter
from datetime import date, datetime
from pathlib import Path

from .dates import find_dates
from .models import Doc

SUPPORTED = {".pdf", ".docx", ".txt", ".md"}
COURSE_RE = re.compile(r"\b([A-Z]{2,4})[\s_-]?(\d{3})\b")
SEMESTER_RE = re.compile(r"\b(Fall|Spring|Summer|Winter)\s+(20\d\d)\b", re.I)
POSTED_RE = re.compile(r"^\s*(?:posted|date|sent|published|updated)\s*(?:on)?\s*[:\-]\s*(.+)$", re.I)
_SEM_START = {"spring": (2, 1), "summer": (6, 15), "fall": (9, 1), "winter": (1, 5)}


def read_text(path: Path) -> str:
    ext = path.suffix.lower()
    if ext == ".pdf":
        import logging
        from pypdf import PdfReader
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        return "\n".join((p.extract_text() or "") for p in PdfReader(str(path)).pages)
    if ext == ".docx":
        import docx
        d = docx.Document(str(path))
        out = [p.text for p in d.paragraphs]
        for t in d.tables:
            for row in t.rows:
                out.append(" | ".join(c.text.strip() for c in row.cells))
        return "\n".join(out)
    return path.read_text(encoding="utf-8", errors="replace")


def infer_class(rel_path: str, text: str, class_map: dict[str, str] | None = None) -> str | None:
    """Course code like CSCI498 from the file name first, then the text."""
    def norm(a: str, b: str) -> str:
        return f"{a.upper()}{b}"

    for src in (rel_path, "\n".join(text.splitlines()[:40])):
        found = Counter(norm(*m) for m in COURSE_RE.findall(src))
        if found:
            code = found.most_common(1)[0][0]
            return (class_map or {}).get(code, code)
    if class_map:
        low = text.lower()
        for alias, cls in class_map.items():
            if alias.lower() in low:
                return cls
    return None


def _posted_date(lines: list[str], fallback: date) -> date:
    for ln in lines[:15]:
        m = POSTED_RE.match(ln)
        if m:
            hits = find_dates(m.group(1), fallback)
            if hits:
                return hits[0].date
    return fallback


def load_doc(path: Path, root: Path, *, ref_date: date | None = None,
             cls: str | None = None, class_map: dict[str, str] | None = None) -> Doc:
    text = read_text(path)
    rel = path.relative_to(root).as_posix() if root in path.parents or root == path.parent else path.name
    mtime = datetime.fromtimestamp(path.stat().st_mtime).date()
    lines = text.splitlines()
    doc_date = ref_date or _posted_date(lines, mtime)
    anchor = doc_date
    sem = SEMESTER_RE.search("\n".join(lines[:40]))
    if sem and not ref_date:
        mo, dy = _SEM_START[sem.group(1).lower()]
        anchor = date(int(sem.group(2)), mo, dy)
    head = "\n".join(lines[:30]).lower()
    return Doc(path=rel, abs_path=str(path), text=text, doc_date=doc_date, ref_date=anchor,
               cls=cls or infer_class(rel, text, class_map),
               is_syllabus="syllabus" in rel.lower() or "syllabus" in head)


def iter_files(inputs: list[Path]) -> list[tuple[Path, Path]]:
    """(file, root) pairs for files and folders given on the command line."""
    out = []
    for p in inputs:
        if p.is_dir():
            for f in sorted(p.rglob("*")):
                if f.is_file() and f.suffix.lower() in SUPPORTED:
                    out.append((f, p))
        elif p.is_file():
            out.append((p, p.parent))
    return out
