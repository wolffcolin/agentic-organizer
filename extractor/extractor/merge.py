"""Cross-file dedupe, conflict resolution and to-do scheduling."""
from __future__ import annotations

import re
from datetime import date, timedelta

from .models import Item
from .rules import canon_label, find_labels, label_key


def _key(it: Item, cls: str | None) -> tuple:
    if it.type == "todo":
        return (cls, "todo", re.sub(r"[^a-z0-9]+", "", it.text.lower()))
    return (cls, label_key(it.text))


def _fmt(d) -> str:
    return d.strftime("%b %-d")


def _pick_winner(group: list[Item]) -> Item:
    # An explicit "moved/extended" statement beats everything; otherwise the
    # newer source wins; ties fall back to confidence, then first seen.
    return max(group, key=lambda i: (i.override_hint, i.doc_date or i.date, i.confidence, -group.index(i)))


SLOT_WINDOW_DAYS = 5     # slots sit within a class week (Tue->Thu is 2 days, Thu->next Tue is 5)
SLOT_MAX_DATES = 3       # a label on many dates is a recurring item (weekly quiz), not a set of slots


def _slot_clusters(seen: dict[tuple, dict[str, set]]) -> dict[tuple, date]:
    """(key, source, date) -> earliest date of its slot group.

    A file that lists one label on 2+ dates within a few days ("Checkpoint 1: Sep 15 or Sep 17")
    is offering slots to choose from, not several deadlines.
    """
    out: dict[tuple, date] = {}
    for key, per_source in seen.items():
        for src, ds in per_source.items():
            days = sorted(ds)
            if len(days) < 2 or len(days) > SLOT_MAX_DATES:
                continue
            clusters: list[list[date]] = []
            for d in days:
                if clusters and (d - clusters[-1][0]).days <= SLOT_WINDOW_DAYS:
                    clusters[-1].append(d)
                else:
                    clusters.append([d])
            for c in clusters:
                if len(c) > 1:
                    for d in c:
                        out[(key, src, d)] = c[0]
    return out


def merge_items(items: list[Item], classes: dict[str, str | None]) -> tuple[list[Item], list[str]]:
    """Returns (items, warnings). Undated to-dos pass through untouched."""
    # a file that lists the same label on several dates ("Monthly homework due" x3) has distinct
    # occurrences, not a conflict, so those keys also include the date
    seen: dict[tuple, dict[str, set]] = {}
    for it in items:
        if it.date is not None:
            seen.setdefault(_key(it, classes.get(it.source)), {}).setdefault(it.source, set()).add(it.date)
    multi = {k for k, per in seen.items() if any(len(ds) > 1 for ds in per.values())}

    slots = _slot_clusters(seen)
    slot_keys: set[tuple] = set()
    groups: dict[tuple, list[Item]] = {}
    order: list[tuple] = []
    for it in items:
        k = _key(it, classes.get(it.source))
        if it.date is not None and (k, it.source, it.date) in slots:
            k = k + ("slot", slots[(k, it.source, it.date)])
            slot_keys.add(k)
        elif k in multi and it.date is not None:
            k = k + (it.date,)
        if k not in groups:
            order.append(k)
        groups.setdefault(k, []).append(it)

    out: list[Item] = []
    warnings: list[str] = []
    for k in order:
        g = groups[k]
        dated = [i for i in g if i.date is not None]
        undated = [i for i in g if i.date is None]
        if not dated:
            out.append(max(undated, key=lambda i: i.confidence))
            continue
        if k in slot_keys and len({i.date for i in dated}) > 1:
            first = min(dated, key=lambda i: (i.date, -i.confidence))
            first.alternates = sorted({i.date for i in dated} - {first.date})
            first.sources = list(dict.fromkeys(i.source for i in dated))
            first.confidence = max(i.confidence for i in dated)
            lbs = find_labels(first.text)
            if lbs and first.type != "todo":
                first.text = canon_label(lbs[0].text)
            first.note = ("Several slots are listed (" + ", ".join(_fmt(d) for d in [first.date] + first.alternates)
                          + "); you only need one. Dated at the earliest.")
            out.append(first)
            continue
        winner = _pick_winner(dated)
        if winner.type != "todo":
            lbs = find_labels(winner.text)
            if lbs:
                winner.text = canon_label(lbs[0].text)
        losers = [i for i in dated if i.date != winner.date]
        all_sources = [winner.source] + [s for i in sorted(dated, key=lambda i: i.doc_date or i.date, reverse=True)
                                         for s in [i.source] if s != winner.source]
        winner.sources = list(dict.fromkeys(all_sources))
        winner.confidence = max(i.confidence for i in dated if i.date == winner.date)
        if losers:
            other_files = {i.source for i in losers}
            cross = other_files - {winner.source}
            if cross:
                lo = losers[0]
                if winner.override_hint:
                    why = f"{winner.source} says the date moved"
                else:
                    why = f"{winner.source} is newer"
                winner.note = (f"Using {_fmt(winner.date)} ({why}); "
                               f"{lo.source} had {_fmt(lo.date)}.")
            else:
                warnings.append(f"{winner.source}: '{winner.text}' appears with several dates "
                                f"({', '.join(sorted({_fmt(i.date) for i in dated}))}); kept {_fmt(winner.date)}")
        out.append(winner)
    return out, warnings


def resolve_todos(items: list[Item], classes: dict[str, str | None]) -> tuple[list[Item], list[Item]]:
    """Give undated to-dos a date: the day before the next matching exam.
    Returns (items, unscheduled)."""
    exams = [i for i in items if i.type == "exam" and i.date]
    resolved, unscheduled = [], []
    for it in items:
        if it.type != "todo" or it.date is not None:
            resolved.append(it)
            continue
        cls = classes.get(it.source)
        pool = [e for e in exams if classes.get(e.source) == cls or cls is None]
        if it.anchor in ("midterm", "final"):
            pool = [e for e in pool if it.anchor in label_key(e.text)]
        floor = it.doc_date
        pool = [e for e in pool if floor is None or e.date >= floor]
        if not pool:
            unscheduled.append(it)
            continue
        target = min(pool, key=lambda e: e.date)
        it.date = target.date - timedelta(days=1)
        it.derived = True
        it.sources = list(dict.fromkeys([it.source, target.source]))
        it.note = f"No date in the source; scheduled the day before {target.text} ({_fmt(target.date)})."
        resolved.append(it)
    return resolved, unscheduled
