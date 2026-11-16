from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

from . import records, router
from .readers import iter_files, load_doc


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="extractor", description="Extract deadlines and to-dos from school files.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    ex = sub.add_parser("extract", help="extract items from files/folders")
    ex.add_argument("inputs", nargs="+", type=Path)
    ex.add_argument("--mode", choices=router.MODES, default="hybrid")
    ex.add_argument("--class", dest="cls", help="force the course code, e.g. CSCI498")
    ex.add_argument("--class-map", type=Path, help="JSON {alias: class} (Canvas course name -> folder class)")
    ex.add_argument("--ref-date", type=date.fromisoformat, help="override the file date (YYYY-MM-DD)")
    ex.add_argument("--out", type=Path, help="write records JSON here (default: stdout)")
    args = ap.parse_args(argv)

    cmap = json.loads(args.class_map.read_text()) if args.class_map else None
    pairs = iter_files(args.inputs)
    if not pairs:
        print("no supported files found (pdf, docx, txt, md)", file=sys.stderr)
        return 1
    docs = [load_doc(f, root, ref_date=args.ref_date, cls=args.cls, class_map=cmap) for f, root in pairs]
    items, report = router.run(docs, args.mode)
    payload = records.build(docs, items, str(pairs[0][1]), report)
    errs = records.validate(payload)
    if errs:
        print("schema errors:\n  " + "\n  ".join(errs), file=sys.stderr)
        return 2

    for it in items:
        print(f"{it.date}  {it.type:<8} {it.text:<28} [{it.origin} {it.confidence:.2f}] {', '.join(it.sources or [it.source])}"
              + (f"\n           note: {it.note}" if it.note else ""), file=sys.stderr)
    for w in report["warnings"]:
        print(f"warning: {w}", file=sys.stderr)
    for u in report["unscheduled"]:
        print(f"unscheduled (no date, no exam to anchor to): {u}", file=sys.stderr)
    for b in report["dropped_ungrounded"]:
        print(f"dropped (not grounded in source): {b}", file=sys.stderr)

    text = json.dumps(payload, indent=2, default=str)
    if args.out:
        args.out.write_text(text + "\n")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
