"""Randomised recovery test: generated syllabi in many shapes with known answers,
plus distractor lines that must not become items."""
import json
import random
from datetime import date, timedelta
from pathlib import Path

from extractor import cli, evaluate, router
from extractor.models import Doc
from extractor.readers import iter_files, load_doc
from extractor.rules import label_key
from extractor.verify import is_grounded

FIX = Path(__file__).parent / "fixtures"
MONTH = ["", "January", "February", "March", "April", "May", "June", "July", "August", "September",
         "October", "November", "December"]


def fmt(d: date, rng: random.Random) -> str:
    style = rng.choice(["short", "long", "dotted", "us", "us2", "us4", "iso", "wd"])
    mon = MONTH[d.month]
    return {
        "short": f"{mon[:3]} {d.day}", "long": f"{mon} {d.day}",
        "dotted": f"{mon[:3]}. {d.day}" if d.month != 9 else f"Sept. {d.day}",
        "us": f"{d.month}/{d.day}", "us2": f"{d.month}/{d.day}/{d.year % 100}",
        "us4": f"{d.month}/{d.day}/{d.year}", "iso": d.isoformat(),
        "wd": f"{d.strftime('%a')}, {mon[:3]} {d.day}",
    }[style]


HW_TEMPLATES = [
    "HW {n} due {D}", "Homework {n}: {D}", "{D} | HW {n} due", "Assignment {n} (due {D})",
    "Week {w} | {X} | Topic {w} | HW {n} due {D}", "{X} Lecture {w}. HW {n} due {D}",
]
DISTRACTORS = [
    "{X} | Lecture on topic {w}", "No class {X}", "Office hours Tuesdays 2-4 pm", "Late work loses 10% per day",
    "Homework is worth 3/4 of your grade", "Course description and learning objectives", "Week {w} | {X} | Review of chapter {w}",
    "Instructor: Dr. Example (example@mines.edu)", "Room 305, building 12",
    "{w} {X} Q&A for midterm", "{w} {X} Lab 2 Day - HoF", "{X} Spring Break (no class)",
    "{X} Final Review Q&A", "{X} Career Day (no class)",
]


def make_doc(seed: int):
    rng = random.Random(seed)
    start = date(2026, 8, 31)
    lines, expected = ["CSCI 498 Syllabus - Fall 2026"], set()
    for n in range(1, rng.randint(3, 9)):
        due = start + timedelta(days=rng.randint(7, 100))
        topic = start + timedelta(days=rng.randint(0, 100))
        lines.append(rng.choice(HW_TEMPLATES).format(n=n, w=rng.randint(1, 15), D=fmt(due, rng), X=fmt(topic, rng)))
        expected.add((f"hw{n}", due.isoformat()))
        if rng.random() < 0.6:
            lines.append(rng.choice(DISTRACTORS).format(w=rng.randint(1, 15), X=fmt(start + timedelta(days=rng.randint(0, 100)), rng)))
    for name, key in (("Midterm exam", "midterm"), ("Final exam", "final")):
        if rng.random() < 0.8:
            d = start + timedelta(days=rng.randint(30, 105))
            lines.append(f"{name}: {fmt(d, rng)}")
            expected.add((key, d.isoformat()))
    rng.shuffle(lines[1:])
    return "\n".join(lines), expected


def test_random_syllabi_recovered_exactly():
    bad = []
    for seed in range(300):
        text, expected = make_doc(seed)
        d = Doc("CSCI 498 syllabus.txt", "x", text, date(2026, 8, 24), date(2026, 8, 24), "CSCI498", True)
        items, report = router.run([d], "rules")
        got = {(label_key(i.text), i.date.isoformat()) for i in items}
        if got != expected:
            bad.append((seed, sorted(expected - got), sorted(got - expected)))
        assert report["dropped_ungrounded"] == []
        assert all(is_grounded(i, d) for i in items)
    assert not bad, f"{len(bad)}/300 docs wrong, first: {bad[:3]}"


def test_scoring_tool_on_fixtures_is_perfect():
    gold = json.loads((FIX / "gold.json").read_text())
    docs = [load_doc(f, root) for f, root in iter_files([FIX / "semester"])]
    items, _ = router.run(docs, "rules")
    res = evaluate.score(items, gold)
    for path, r in res.items():
        assert r["missed"] == [] and r["extra"] == [], (path, r)


def test_score_flags_a_wrong_date():
    from extractor.models import Item
    gold = {"a.txt": [{"text": "HW 1", "date": "2026-09-04"}]}
    r = evaluate.score([Item("deadline", "HW 1", date(2026, 9, 5), "a.txt")], gold)["a.txt"]
    assert r["recall"] == 0 and r["precision"] == 0


# ---------- CLI end to end ----------
def test_cli_writes_valid_schema_json(tmp_path):
    out = tmp_path / "r.json"
    assert cli.main(["extract", str(FIX / "semester"), "--mode", "rules", "--out", str(out)]) == 0
    data = json.loads(out.read_text())
    assert len(data["records"]) == 4 and data["_extractor"]["mode"] == "rules"
    ids = [i["id"] for r in data["records"] for i in r["items"]]
    assert len(ids) == len(set(ids))


def test_cli_no_supported_files(tmp_path):
    (tmp_path / "x.png").write_bytes(b"")
    assert cli.main(["extract", str(tmp_path), "--mode", "rules"]) == 1


def test_cli_class_override_and_ref_date(tmp_path):
    f = tmp_path / "notes.txt"
    f.write_text("HW 1 due Jan 20\n")
    out = tmp_path / "r.json"
    cli.main(["extract", str(f), "--mode", "rules", "--class", "MATH101", "--ref-date", "2027-01-05", "--out", str(out)])
    rec = json.loads(out.read_text())["records"][0]
    assert rec["class"] == "MATH101" and rec["items"][0]["date"] == "2027-01-20"


def test_score_accepts_any_listed_slot_and_does_not_penalise_it():
    from extractor.models import Item
    gold = {"a.txt": [{"text": "Checkpoint 1", "date": "2026-09-15", "alternates": ["2026-09-17"]}]}
    for d in (date(2026, 9, 15), date(2026, 9, 17)):
        r = evaluate.score([Item("deadline", "Checkpoint 1", d, "a.txt")], gold)["a.txt"]
        assert r["recall"] == 1 and r["precision"] == 1 and r["extra"] == []
    r = evaluate.score([Item("deadline", "Checkpoint 1", date(2026, 9, 20), "a.txt")], gold)["a.txt"]
    assert r["recall"] == 0 and r["precision"] == 0
