"""Grounding check: no invented deadlines.

Every dated item must have its date findable in its source text (any common
written form, or a resolvable relative phrase). Claude items must also quote
the source verbatim. Items whose date was derived from an exam anchor are
checked against the anchor instead (see merge.resolve_todos).
"""
from __future__ import annotations

from .dates import find_dates
from .llm import quote_in_doc
from .models import Doc, Item


def date_in_source(item: Item, doc: Doc) -> bool:
    if item.date is None:
        return True
    return any(h.date == item.date for h in find_dates(doc.text, doc.ref_date, doc.doc_date))


def is_grounded(item: Item, doc: Doc) -> bool:
    if item.derived:
        return True
    if item.origin == "claude" and not quote_in_doc(item.quote, doc):
        return False
    return date_in_source(item, doc)


def filter_grounded(items: list[Item], docs: dict[str, Doc]) -> tuple[list[Item], list[Item]]:
    ok, bad = [], []
    for it in items:
        (ok if is_grounded(it, docs[it.source]) else bad).append(it)
    return ok, bad
