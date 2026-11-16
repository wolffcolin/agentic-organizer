"""Rules-based extraction over retrieved lines. Fully offline."""
from __future__ import annotations

import re
from dataclasses import dataclass

from .dates import DateHit, find_dates
from .models import Doc, Item
from .retrieval import line_numbers, retrieve

# ---------------------------------------------------------------- labels
_STRONG = r"(?:HW|Homework|Assignment|Asgn|PS|Problem\s+Set|Quiz|Midterm|Final|Exam|Test|Check\s?point)"
_WEAK = r"(?:Project|Proj|Lab|Paper|Report|Presentation|Reading|Essay|Milestone|Proposal)"
_PREFIX = r"(?:Final|Midterm|Group|Team|Term|Capstone|Monthly|Weekly|Bi-?weekly|Written|Programming|Take-?home)"
LABEL_RE = re.compile(
    rf"\b(?:(?P<pre>{_PREFIX})\s+)?(?:(?P<strong>{_STRONG})|{_WEAK})(?:\s*#?\s*\d+)?"
    r"(?:\s+(?:Proposal|Report|Presentation|Draft|Paper|Exam))?\b", re.I)
_MERGE_GAP = re.compile(r"^(?:[\s/&-]|and)*$", re.I)
# a label followed by one of these is prose, not an item ("Midterm Review", "exam schedule")
SKIP_AFTER = re.compile(r"^\s*(review|schedule|policy|policies|information|day\b|week|grade|grading|weight|%)", re.I)

EXAM_WORDS = re.compile(r"\b(midterm|final|exam|test|quiz)\b", re.I)
NOT_EXAM = re.compile(r"\b(project|presentation|paper|report|proposal)\b", re.I)
CUE_WORDS = re.compile(r"\b(due|deadline|submit|submitted|turn in|by)\b", re.I)
SPAN_CUE = re.compile(r"\b(due|deadline|submit|submitted|turn in|check\s?point)\b", re.I)
_GAP_VOCAB = {"is", "are", "will", "be", "has", "have", "been", "now", "due", "by", "on", "deadline",
              "moved", "extended", "pushed", "back", "postponed", "rescheduled", "changed", "to",
              "for", "date", "new", "the", "at"}
_GAP_CUES = {"due", "by", "on", "deadline", "moved", "extended", "pushed", "postponed", "rescheduled",
             "changed", "to"}
CHANGE_WORD = re.compile(r"\b(moved|extended|postponed|rescheduled|pushed back|changed|new due date)\b", re.I)
STALE_CUE = re.compile(r"(from|was|originally|previously|instead of|rather than|not)\s*:?\s*\(?\s*$", re.I)

TODO_MARK = re.compile(
    r"^\s*(?:[-*•]\s*)?(?:(?:to-?do|task|action(?:\s+item)?)\s*[:\-]\s*|(?:\[\s?\]|☐|□)\s*)(?P<t>.+)$", re.I)
TODO_PHRASE = re.compile(r"\b(?:don'?t forget(?:\s+to)?|remember\s+to|need\s+to|make sure\s+to)\s+(?P<t>.+)", re.I)
TODO_VERB = re.compile(r"^\s*(?:[-*•]\s*)?(?P<t>(?:study|review|finish|complete|practice|revise)\b.+)$", re.I)
ANCHOR_RE = re.compile(r"\bbefore\s+(?:the\s+)?(?P<a>midterm|final|exam|quiz|test)\b", re.I)


@dataclass
class Label:
    start: int
    end: int
    text: str
    strong: bool      # reliable on its own; weak labels (project, lab...) need a due-cue


def find_labels(s: str) -> list[Label]:
    out: list[Label] = []
    for m in LABEL_RE.finditer(s):
        strong = bool(m.group("strong") or m.group("pre"))
        if out and _MERGE_GAP.match(s[out[-1].end:m.start()]):
            prev = out[-1]
            out[-1] = Label(prev.start, m.end(), s[prev.start:m.end()], prev.strong or strong)
        else:
            out.append(Label(m.start(), m.end(), m.group(0), strong))
    return [lb for lb in out if not SKIP_AFTER.match(s[lb.end:lb.end + 14])]


def canon_label(label: str) -> str:
    return re.sub(r"\s+", " ", label.strip()).strip(" .,:;-–—|")


def label_key(label: str) -> str:
    """Dedupe key: homework/assignment/problem set all become 'hw'."""
    lbs = find_labels(label)
    k = re.sub(r"\s+", " ", (lbs[0].text if lbs else label).lower()).strip()
    k = re.sub(r"\b(homework|assignment|asgn|problem set|ps)\b", "hw", k)
    k = re.sub(r"\b(midterm|final)\s+exam\b", r"\1", k)
    k = re.sub(r"\b(?:final\s+)?project\s+(?=check)", "", k)
    k = re.sub(r"\bfinal project (?=paper|report)", "final ", k)
    k = re.sub(r"hw\s*#?\s*(\d+)", r"hw\1", k)
    return re.sub(r"[^a-z0-9]+", "", k)


def _item_type(label: str) -> str:
    if EXAM_WORDS.search(label) and not NOT_EXAM.search(label):
        return "exam"
    if re.match(r"\s*reading", label, re.I):
        return "todo"
    return "deadline"


def _clean(line: str, hits: list[DateHit]) -> str:
    out = line
    for h in sorted(hits, key=lambda h: -h.start):
        out = out[:h.start] + " " + out[h.end:]
    out = re.sub(r"\b(due|by|on|deadline|moved to|now due)\b[:\s]*", " ", out, flags=re.I)
    out = re.sub(r"[|\t]+", " ", out)
    out = re.sub(r"\s+", " ", out).strip(" .,:;-–—|()[]")
    return out[:90]


def _live_hits(line: str, hits: list[DateHit]) -> list[DateHit]:
    """Drop dates introduced as the old value ("was Nov 10", "instead of ...")."""
    return [h for h in hits if not STALE_CUE.search(line[max(0, h.start - 22):h.start])]


def _gap_is_cue(gap: str) -> tuple[bool, bool]:
    """(is a 'due-cue' gap, says the date changed)."""
    if re.search(r"[.;!?]\s", gap):
        return False, False
    words = re.findall(r"[a-z]+", gap.lower())
    if gap.rstrip().endswith(":") and not words:
        return True, False
    if words and all(w in _GAP_VOCAB for w in words) and any(w in _GAP_CUES for w in words):
        return True, bool(CHANGE_WORD.search(gap))
    return False, False


def _bind(labels: list[Label], hits: list[DateHit], line: str) -> dict[int, list[tuple[Label, bool, bool]]]:
    """hit index -> [(label, direct_cue, says_changed)].

    1. "HW 4 due Nov 12" / "Final exam: Dec 10": a label followed by a due-cue then a date.
    2. Schedule rows "Sep 15 Career Day. Project check point #1": the nearest date before it.
    3. Otherwise the next date after it.
    """
    bound: dict[int, list[tuple[Label, bool, bool]]] = {}
    for lb in labels:
        fi = next((i for i, h in enumerate(hits) if h.start >= lb.end), None)
        pi = next((i for i in range(len(hits) - 1, -1, -1) if hits[i].end <= lb.start), None)
        pick = None
        if fi is not None:
            direct, changed = _gap_is_cue(line[lb.end:hits[fi].start])
            if direct:
                pick = (fi, True, changed)
        if pick is None and pi is not None:
            pick = (pi, False, False)
        if pick is None and fi is not None:
            pick = (fi, False, False)
        if pick:
            bound.setdefault(pick[0], []).append((lb, pick[1], pick[2]))
    return bound


def _window(line: str, hits: list[DateHit], lb: Label) -> str:
    """Text between the dates on either side of a label (its own 'cell' in a row)."""
    lo = max((h.end for h in hits if h.end <= lb.start), default=0)
    hi = min((h.start for h in hits if h.start >= lb.end), default=len(line))
    return line[lo:hi]


def _cue_in_sentence(span: str, label_text: str) -> bool:
    for sent in re.split(r"(?<=[.;!?])\s+", span):
        if label_text.lower() in sent.lower() and SPAN_CUE.search(sent):
            return True
    return False


def _todo_from_line(line: str, doc: Doc) -> str | None:
    m = TODO_MARK.match(line)
    if not m and not doc.is_syllabus:
        m = TODO_PHRASE.search(line) or TODO_VERB.match(line)
    return m.group("t") if m else None


def extract_rules(doc: Doc, top_k: int | None = None) -> tuple[list[Item], list[int]]:
    """Returns (items, uncovered_line_numbers). Uncovered lines are dated prose
    the rules couldn't label: candidates to hand to Claude in hybrid mode."""
    lines = doc.lines
    items: list[Item] = []
    uncovered: list[int] = []
    for i in line_numbers(retrieve(doc, top_k=top_k)):
        line = lines[i]
        if not line.strip():
            continue
        hits = find_dates(line, doc.ref_date, doc.doc_date)
        live = _live_hits(line, hits)

        todo = _todo_from_line(line, doc)
        if todo:
            am = ANCHOR_RE.search(line)
            anchor = am.group("a").lower() if am else None
            first = live[0] if live else None
            text = re.sub(ANCHOR_RE, "", _clean(todo, hits)).strip(" .,:;-–—")
            if text:
                items.append(Item("todo", text, first.date if first else None, doc.path, quote=line.strip(),
                                  time=first.time if first else None,
                                  confidence=0.75 if first else 0.65, anchor=anchor, doc_date=doc.doc_date))
                continue

        if not live:
            continue
        labels = find_labels(line)
        if labels:
            bound = _bind(labels, live, line)
            for hi, cands in sorted(bound.items()):
                h = live[hi]
                span = line[(live[hi - 1].end if hi else 0):(live[hi + 1].start if hi + 1 < len(live) else len(line))]
                ok = [c for c in cands if c[0].strong or _cue_in_sentence(_window(line, live, c[0]), c[0].text)]
                if not ok:
                    continue
                lb, direct, changed = max(ok, key=lambda c: (c[0].strong, c[1]))
                label = canon_label(lb.text)
                items.append(Item(_item_type(label), label, h.date, doc.path, quote=line.strip(), time=h.time,
                                  confidence=0.9 if direct or lb.strong else 0.8, doc_date=doc.doc_date,
                                  override_hint=changed or bool(CHANGE_WORD.search(span))))
            continue

        # no recognised label on this line
        h = live[0]
        label_text, conf = None, 0.9
        if i > 0 and find_labels(lines[i - 1]) and not find_dates(lines[i - 1], doc.ref_date):
            label_text, conf = canon_label(find_labels(lines[i - 1])[0].text), 0.6
        elif CUE_WORDS.search(line) and len(_clean(line, hits)) >= 3:
            label_text, conf = _clean(line, hits), 0.55
        if label_text:
            items.append(Item(_item_type(label_text), label_text, h.date, doc.path, quote=line.strip(),
                              time=h.time, confidence=conf, doc_date=doc.doc_date,
                              override_hint=bool(CHANGE_WORD.search(line))))
        elif len(_clean(line, hits).split()) >= 5 and (not doc.is_syllabus or CUE_WORDS.search(line)):
            uncovered.append(i)     # prose with a date: worth asking Claude about
    return items, uncovered
