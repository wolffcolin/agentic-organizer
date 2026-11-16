"""Build and validate handoff records (shared/handoff.schema.json)."""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path

from .models import Doc, Item

SCHEMA_PATH = Path(__file__).resolve().parents[2] / "shared" / "handoff.schema.json"


def _rid(path: str) -> str:
    return "f" + hashlib.sha1(path.encode()).hexdigest()[:8]


def _item_json(it: Item, rid: str) -> dict:
    slug = re.sub(r"[^a-z0-9]+", "-", it.text.lower()).strip("-")[:24]
    h = hashlib.sha1(f"{it.text}|{it.date}".encode()).hexdigest()[:4]
    out = {"id": f"{rid}-{slug}-{h}", "type": it.type, "text": it.text,
           "date": it.date.isoformat(), "sources": it.sources or [it.source]}
    if it.time:
        out["time"] = it.time
    if it.note:
        out["note"] = it.note
    return out


def build(docs: list[Doc], items: list[Item], root: str, report: dict | None = None) -> dict:
    by_file: dict[str, list[Item]] = {d.path: [] for d in docs}
    for it in items:
        by_file[it.source].append(it)
    records = []
    for d in docs:
        mine = by_file[d.path]
        rid = _rid(d.path)
        counts = {t: sum(1 for i in mine if i.type == t) for t in ("deadline", "exam", "todo")}
        summary = (f"{d.cls or 'Unclassified'} file: {counts['deadline']} deadlines, "
                   f"{counts['exam']} exams, {counts['todo']} to-dos.")
        conf = round(sum(i.confidence for i in mine) / len(mine), 2) if mine else 0.5
        records.append({
            "id": rid, "path": d.path, "class": d.cls,
            "proposed_name": None, "proposed_folder": None,   # Organizer fills these
            "confidence": conf, "needs_user": False, "summary": summary,
            "items": [_item_json(i, rid) for i in mine],
        })
    out = {"root": root, "scanned_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "records": records}
    if report:
        out["_extractor"] = report
    return out


def validate(payload: dict) -> list[str]:
    from jsonschema import Draft202012Validator
    schema = json.loads(SCHEMA_PATH.read_text())
    return [f"{'/'.join(map(str, e.absolute_path))}: {e.message}"
            for e in Draft202012Validator(schema).iter_errors(payload)]
