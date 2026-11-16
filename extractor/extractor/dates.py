"""Deterministic date finding. No LLM, no network."""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, timedelta

MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6, "jul": 7,
    "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
WEEKDAYS = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}

_MON = (r"(?P<mon>Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|"
        r"Aug(?:ust)?|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\.?")
_WD = (r"(?:(?P<wd>Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|Thu(?:r(?:s(?:day)?)?)?|"
       r"Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\.?,?\s+)?")

RE_MONTH_DAY = re.compile(
    _WD + _MON + r"\s+(?P<day>\d{1,2})(?!\d)(?:st|nd|rd|th)?(?:,?\s+(?P<year>20\d\d)(?!\d))?",
    re.I)
RE_DAY_MONTH = re.compile(
    _WD + r"(?P<day>\d{1,2})(?:st|nd|rd|th)?\s+(?:of\s+)?" + _MON + r"(?:,?\s+(?P<year>20\d\d)(?!\d))?",
    re.I)
RE_ISO = re.compile(r"(?<!\d)(?P<year>20\d\d)-(?P<m>\d{2})-(?P<d>\d{2})(?!\d)")
RE_NUMERIC = re.compile(
    _WD + r"(?<![\d/])(?P<m>\d{1,2})/(?P<d>\d{1,2})(?:/(?P<year>\d{4}|\d{2}))?(?![\d/])", re.I)
RE_REL_WD = re.compile(
    r"\b(?P<which>next|this|coming)\s+(?P<wd>Mon(?:day)?|Tue(?:s(?:day)?)?|Wed(?:nesday)?|"
    r"Thu(?:r(?:s(?:day)?)?)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)\b", re.I)
RE_TOMORROW = re.compile(r"\btomorrow\b", re.I)
RE_IN_N = re.compile(r"\bin\s+(?P<n>\d{1,2})\s+(?P<unit>day|week)s?\b", re.I)
RE_TIME = re.compile(r"(?<![\d:-])(?P<h>\d{1,2})(?::(?P<min>\d{2}))?\s*(?P<ap>[ap])\.?m\.?(?![a-z])", re.I)


@dataclass
class DateHit:
    start: int
    end: int
    date: date
    time: str | None
    kind: str        # abs | rel
    text: str


def _valid(y: int, m: int, d: int) -> date | None:
    try:
        return date(y, m, d)
    except ValueError:
        return None


def _infer_year(m: int, d: int, ref: date, wd: int | None) -> date | None:
    """Pick the year for a month/day with no year, anchored on `ref`.

    Among plausible years (within ~5 months before / 7 months after `ref`), a
    weekday name ("Wednesday, Oct 14") picks the year it matches, if any.
    """
    cands = [c for y in (ref.year - 1, ref.year, ref.year + 1) if (c := _valid(y, m, d))]
    if not cands:
        return None
    lo, hi = ref - timedelta(days=150), ref + timedelta(days=215)
    pool = [c for c in cands if lo <= c <= hi] or cands
    if wd is not None:
        match = [c for c in pool if c.weekday() == wd]
        if match:     # a mismatching weekday is usually a typo; fall through to the window
            pool = match
    return min(pool, key=lambda c: abs((c - ref).days))


def _time_after(text: str, end: int) -> str | None:
    m = RE_TIME.search(text, end, min(len(text), end + 30))
    if not m:
        return None
    h = int(m.group("h"))
    if not 1 <= h <= 12:
        return None
    mins = int(m.group("min") or 0)
    if mins > 59:
        return None
    h = h % 12 + (12 if m.group("ap").lower() == "p" else 0)
    return f"{h:02d}:{mins:02d}"


def _wd_idx(s: str | None) -> int | None:
    return WEEKDAYS[s[:3].lower()] if s else None


def find_dates(text: str, ref: date, doc_date: date | None = None) -> list[DateHit]:
    """All dates in `text`. `ref` anchors missing years; `doc_date` resolves
    relative phrases ("next Friday")."""
    doc_date = doc_date or ref
    hits: list[DateHit] = []
    taken: list[tuple[int, int]] = []

    def free(s: int, e: int) -> bool:
        return all(e <= a or s >= b for a, b in taken)

    def add(s: int, e: int, d: date | None, kind: str):
        if d is None or not free(s, e):
            return
        taken.append((s, e))
        hits.append(DateHit(s, e, d, _time_after(text, e), kind, text[s:e]))

    for m in RE_ISO.finditer(text):
        add(m.start(), m.end(), _valid(int(m["year"]), int(m["m"]), int(m["d"])), "abs")

    for rx in (RE_MONTH_DAY, RE_DAY_MONTH):
        for m in rx.finditer(text):
            if m["mon"] == "may":          # the verb ("you may 10 ..."), not the month
                continue
            mon = MONTHS[m["mon"][:3].lower()]
            day = int(m["day"])
            if m["year"]:
                d = _valid(int(m["year"]), mon, day)
            else:
                d = _infer_year(mon, day, ref, _wd_idx(m["wd"]))
            add(m.start(), m.end(), d, "abs")

    for m in RE_NUMERIC.finditer(text):
        mon, day = int(m["m"]), int(m["d"])
        if not (1 <= mon <= 12 and 1 <= day <= 31):
            continue
        if m["year"]:
            y = int(m["year"])
            y = y + 2000 if y < 100 else y
            d = _valid(y, mon, day)
        else:
            d = _infer_year(mon, day, ref, _wd_idx(m["wd"]))
        add(m.start(), m.end(), d, "abs")

    for m in RE_REL_WD.finditer(text):
        target = _wd_idx(m["wd"])
        ahead = (target - doc_date.weekday()) % 7 or 7
        d = doc_date + timedelta(days=ahead)
        if m["which"].lower() == "next" and d.isocalendar()[:2] == doc_date.isocalendar()[:2]:
            d += timedelta(days=7)
        add(m.start(), m.end(), d, "rel")
    for m in RE_TOMORROW.finditer(text):
        add(m.start(), m.end(), doc_date + timedelta(days=1), "rel")
    for m in RE_IN_N.finditer(text):
        n = int(m["n"]) * (7 if m["unit"].lower() == "week" else 1)
        add(m.start(), m.end(), doc_date + timedelta(days=n), "rel")

    hits.sort(key=lambda h: h.start)
    return hits
