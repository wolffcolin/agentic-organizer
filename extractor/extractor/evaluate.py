"""Score extraction against labelled dates.

gold.json: {"<path relative to the input folder>": [{"text": "HW 1", "date": "2026-09-04"}, ...]}
An entry may add "alternates": ["2026-09-06"] for slots the student can choose between.
Items match on (normalised label, date); any listed date of an entry counts. A merged item (e.g. a moved deadline) belongs to
the file that won the conflict.

  python -m extractor.evaluate gold.json private/ --mode rules
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from . import router
from .readers import iter_files, load_doc
from .rules import label_key


def _k(text: str, date: str) -> tuple[str, str]:
    return label_key(text) or re.sub(r"\W+", "", text.lower()), date


def score(items, gold: dict[str, list[dict]]) -> dict:
    pred: dict[str, set] = {}
    for it in items:
        pred.setdefault(it.source, set()).add(_k(it.text, it.date.isoformat()))
    out = {}
    for path in sorted(set(gold) | set(pred)):
        entries = [{_k(g["text"], d) for d in [g["date"], *g.get("alternates", [])]} for g in gold.get(path, [])]
        have = pred.get(path, set())
        accepted = set().union(*entries) if entries else set()
        hit = [e for e in entries if e & have]
        out[path] = {
            "precision": len(have & accepted) / len(have) if have else 1.0,
            "recall": len(hit) / len(entries) if entries else 1.0,
            "missed": sorted(min(e) for e in entries if not e & have),
            "extra": sorted(have - accepted),
        }
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="extractor.evaluate")
    ap.add_argument("gold", type=Path)
    ap.add_argument("inputs", nargs="+", type=Path)
    ap.add_argument("--mode", choices=router.MODES, default="rules")
    args = ap.parse_args(argv)
    gold = {k: v for k, v in json.loads(args.gold.read_text()).items() if not k.startswith("_")}
    docs = [load_doc(f, root) for f, root in iter_files(args.inputs)]
    items, _ = router.run(docs, args.mode)
    res = score(items, gold)
    for path, r in res.items():
        print(f"{path}: precision {r['precision']:.2f} recall {r['recall']:.2f}")
        for m in r["missed"]:
            print(f"   missed {m}")
        for e in r["extra"]:
            print(f"   extra  {e}")
    worst = min((min(r["precision"], r["recall"]) for r in res.values()), default=1.0)
    return 0 if worst == 1.0 else 1


if __name__ == "__main__":
    sys.exit(main())
