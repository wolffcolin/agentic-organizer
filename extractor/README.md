# Extractor (Colin)

Pulls deadlines, exams and to-dos out of school files (PDF / DOCX / TXT / MD)
and emits them in the shared handoff format (`../shared/handoff.schema.json`).
The extractor fills `class`, `summary`, `confidence` and `items`; it leaves
`proposed_name` / `proposed_folder` null for the Organizer.

## Run
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python -m extractor extract <file-or-folder>... --mode hybrid --out records.json
.venv/bin/python -m pytest
```
Modes: `rules` (offline, no model), `claude` (`claude -p` on the top retrieved chunks), `hybrid` (default: rules first, Claude only for prose lines the rules can't label or files where they found nothing; falls back to rules if Claude fails). Options: `--class CSCI498`, `--class-map map.json`, `--ref-date YYYY-MM-DD`.
Put your own real files in `extractor/private/` (gitignored) and point the CLI at them.

## Scoring against your own labels
Write `gold.json` (kept private, next to your files): `{"syllabus.pdf": [{"text": "Midterm", "date": "2026-10-08"}]}`, then
`.venv/bin/python -m extractor.evaluate gold.json private/ --mode rules` prints precision/recall per file plus what was missed or extra.
`tests/fixtures/gold.json` is the committed example; `tests/test_properties.py` also recovers 300 randomly generated syllabi exactly.

## Pipeline
read → chunk → **retrieve** (keyword/date-weighted scoring, no LLM) → extract (regex/date rules, and/or Claude) → **ground check** (every date must appear in its source; Claude items must quote the source verbatim) → **merge** across files → records + schema validation.

- Missing years are inferred from the semester header ("Fall 2026"), else the file's posted date / mtime; a weekday name ("Wednesday, Oct 14") picks the matching year.
- Relative dates ("next Friday") resolve from a `Posted:` header, else the file mtime.
- Conflicts: an explicit "moved/extended" statement wins, else the newer file; `sources` lists every file and `note` says why.
- Undated to-dos ("TODO: study ch. 7 before the midterm") get the day before the next matching exam in the same class, citing the exam's file; if no exam is known they are listed as `unscheduled` in `_extractor` rather than given an invented date.
- `_extractor` (extra top-level key) carries warnings, dropped-ungrounded items and unscheduled to-dos.

## Not yet
Local model (the `router.py` seam is where it plugs in), image/OCR files, Canvas ingestion, `.ics` export (Gunnar's app has one).
