from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass
class Doc:
    path: str                 # path relative to the scanned root, forward slashes
    abs_path: str
    text: str
    doc_date: date            # when the file was written/posted (header > mtime)
    ref_date: date            # anchor used to infer missing years
    cls: str | None = None
    is_syllabus: bool = False

    @property
    def lines(self) -> list[str]:
        return self.text.splitlines()


@dataclass
class Chunk:
    start: int                # 0-based first line
    end: int                  # exclusive
    text: str
    score: float = 0.0


@dataclass
class Item:
    type: str                 # deadline | exam | todo
    text: str
    date: date | None         # None => undated to-do, resolved later via anchor
    source: str               # file path (relative)
    quote: str = ""           # exact source text that supports the item
    time: str | None = None
    confidence: float = 0.8
    origin: str = "rules"     # rules | claude
    override_hint: bool = False   # source says the date was moved/changed
    anchor: str | None = None     # for undated to-dos: midterm | final | exam
    doc_date: date | None = None
    note: str | None = None
    sources: list[str] = field(default_factory=list)
    derived: bool = False     # date computed from an anchor, not found in text
