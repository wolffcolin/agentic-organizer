from datetime import date
from pathlib import Path

import pytest

from extractor import dates, records, router
from extractor.llm import ClaudeError, parse_items
from extractor.models import Item
from extractor.readers import infer_class, iter_files, load_doc
from extractor.retrieval import retrieve
from extractor.rules import extract_rules, label_key
from extractor.verify import is_grounded

FIX = Path(__file__).parent / "fixtures" / "semester"


@pytest.fixture(scope="module")
def docs():
    return [load_doc(f, root) for f, root in iter_files([FIX])]


def by_path(docs, name):
    return next(d for d in docs if d.path.endswith(name))


def run_rules(docs):
    return router.run(docs, "rules")


# ---------- dates ----------
def test_dates_formats():
    ref = date(2026, 9, 1)
    t = "Due Oct 14, 10/21, 2026-11-02, 5 December, Friday Sep 18"
    got = [h.date for h in dates.find_dates(t, ref)]
    assert sorted(got) == sorted([date(2026, 10, 14), date(2026, 10, 21), date(2026, 11, 2),
                                  date(2026, 12, 5), date(2026, 9, 18)])


def test_year_rolls_forward_for_spring_dates():
    assert dates.find_dates("Jan 20", date(2026, 11, 1))[0].date == date(2027, 1, 20)


def test_relative_dates_from_file_date():
    posted = date(2026, 11, 8)  # a Sunday
    assert dates.find_dates("due tomorrow", posted, posted)[0].date == date(2026, 11, 9)
    assert dates.find_dates("next Friday", posted, posted)[0].date == date(2026, 11, 13)
    assert dates.find_dates("in 2 weeks", posted, posted)[0].date == date(2026, 11, 22)


def test_time_parsing():
    h = dates.find_dates("Nov 13 by 11:59 pm", date(2026, 11, 1))[0]
    assert h.time == "23:59"


# ---------- retrieval ----------
def test_retrieval_prefers_deadline_chunks(docs):
    d = by_path(docs, "CSCI498/syllabus.txt")
    top = retrieve(d, top_k=2)
    assert any("due" in c.text.lower() for c in top)
    assert all("Late work" not in c.text or "due" in c.text.lower() or c.score > 0 for c in top)


# ---------- rules on the syllabus (example 2) ----------
def test_syllabus_all_deadlines(docs):
    items, _ = run_rules(docs)
    csci = {i.text: i for i in items if i.source == "CSCI498/syllabus.txt"}
    want = {"HW 1": "2026-09-04", "HW 2": "2026-09-18", "HW 3": "2026-10-02", "HW 4": "2026-10-09",
            "HW 5": "2026-10-30", "HW 6": "2026-11-13", "HW 7": "2026-11-20", "HW 8": "2026-12-04",
            "Midterm exam": "2026-10-14", "Final exam": "2026-12-10"}
    assert {k: v.date.isoformat() for k, v in csci.items()} == want
    assert csci["Midterm exam"].type == "exam" and csci["HW 6"].time == "23:59"


def test_lecture_topics_not_extracted(docs):
    items, _ = run_rules(docs)
    texts = " ".join(i.text.lower() for i in items)
    assert "introduction" not in texts and "linear models" not in texts


# ---------- notes with a buried to-do (example 3) ----------
def test_buried_todo_placed_before_midterm(docs):
    items, _ = run_rules(docs)
    todo = next(i for i in items if i.text == "study ch. 7")
    assert todo.type == "todo" and todo.date == date(2026, 10, 13)
    assert "CSCI498/Chapter 7 Study Guide.txt" in todo.sources and "CSCI498/syllabus.txt" in todo.sources
    assert "Midterm" in todo.note


def test_todo_without_exam_is_unscheduled(docs):
    only_notes = [by_path(docs, "Chapter 7 Study Guide.txt")]
    items, report = router.run(only_notes, "rules")
    assert not any(i.type == "todo" for i in items)
    assert any("study ch. 7" in u for u in report["unscheduled"])


# ---------- conflicting sources (example 5) ----------
def test_moved_deadline_cites_both_sources(docs):
    items, _ = run_rules(docs)
    hw4 = [i for i in items if label_key(i.text) == "hw4" and i.source.startswith("DSCI475")]
    assert len(hw4) == 1                                   # deduplicated
    it = hw4[0]
    assert it.date == date(2026, 11, 12)
    assert set(it.sources) == {"DSCI475/syllabus.txt", "DSCI475/announcement_nov8.txt"}
    assert "announcement" in it.note and "Nov 10" in it.note


def test_same_label_in_different_classes_not_merged(docs):
    items, _ = run_rules(docs)
    hw3 = {i.source: i.date for i in items if label_key(i.text) == "hw3"}
    assert hw3["CSCI498/syllabus.txt"] != hw3["DSCI475/syllabus.txt"]


# ---------- grounding: no invented deadlines ----------
def test_every_item_grounded_in_source(docs):
    items, report = run_rules(docs)
    by = {d.path: d for d in docs}
    assert report["dropped_ungrounded"] == []
    for it in items:
        assert is_grounded(it, by[it.source]) or it.derived


def test_invented_date_rejected(docs):
    d = by_path(docs, "CSCI498/syllabus.txt")
    fake = Item("deadline", "HW 9", date(2026, 12, 25), d.path, origin="rules")
    assert not is_grounded(fake, d)
    fake_llm = Item("deadline", "HW 1", date(2026, 9, 4), d.path, quote="HW 1 due Sep 5", origin="claude")
    assert not is_grounded(fake_llm, d)          # quote is not verbatim in the source


# ---------- Claude path (mocked) ----------
def test_hybrid_uses_claude_only_for_unlabeled_lines(tmp_path):
    f = tmp_path / "CSCI 498 notes.txt"
    f.write_text("CSCI 498 notes\nHW 1 due Sep 4\nThe guest speaker comes Oct 9 and slides are needed\n")
    d = load_doc(f, tmp_path, ref_date=date(2026, 9, 1))
    calls = []

    def fake(prompt):
        calls.append(prompt)
        return '{"items":[{"type":"todo","text":"Bring slides for the guest speaker","date":"2026-10-09",' \
               '"quote":"The guest speaker comes Oct 9","changed":false}]}'

    items, report = router.run([d], "hybrid", call=fake)
    assert len(calls) == 1
    assert "guest speaker" in calls[0]
    assert {i.text for i in items} == {"HW 1", "Bring slides for the guest speaker"}


def test_hallucinated_claude_item_dropped(tmp_path):
    f = tmp_path / "CSCI 498 notes.txt"
    f.write_text("CSCI 498 notes\nNothing is scheduled yet, maybe Oct 9?\n")
    d = load_doc(f, tmp_path, ref_date=date(2026, 9, 1))
    fake = lambda p: '{"items":[{"type":"exam","text":"Midterm","date":"2026-10-20","quote":"Midterm Oct 20"}]}'
    items, report = router.run([d], "hybrid", call=fake)
    assert items == [] and len(report["dropped_ungrounded"]) == 1


def test_claude_failure_falls_back_to_rules(tmp_path):
    f = tmp_path / "CSCI 498 notes.txt"
    f.write_text("HW 1 due Sep 4\nthe guest speaker is coming on Oct 9 so prepare\n")
    d = load_doc(f, tmp_path, ref_date=date(2026, 9, 1))

    def boom(prompt):
        raise ClaudeError("offline")

    items, report = router.run([d], "hybrid", call=boom)
    assert [i.text for i in items] == ["HW 1"] and report["warnings"]


def test_parse_items_extracts_json_from_chatty_reply():
    assert parse_items('Sure!\n{"items":[{"type":"todo"}]}\nDone')[0]["type"] == "todo"


# ---------- records / schema ----------
def test_output_validates_against_shared_schema(docs):
    items, report = run_rules(docs)
    payload = records.build(docs, items, str(FIX), report)
    assert records.validate(payload) == []
    assert all(r["proposed_name"] is None and r["proposed_folder"] is None for r in payload["records"])


def test_class_inference():
    assert infer_class("CSCI 498 syllabus.pdf", "") == "CSCI498"
    assert infer_class("x.pdf", "DSCI-475 Capstone") == "DSCI475"
    assert infer_class("x.pdf", "nothing") is None


# ---------- readers ----------
def test_docx_and_pdf_readers(tmp_path):
    import docx
    from reportlab.pdfgen import canvas
    d = docx.Document()
    d.add_paragraph("CSCI 498 Notes")
    t = d.add_table(rows=1, cols=2)
    t.rows[0].cells[0].text, t.rows[0].cells[1].text = "HW 2", "due Sep 18"
    d.save(tmp_path / "n.docx")
    c = canvas.Canvas(str(tmp_path / "s.pdf"))
    c.drawString(72, 720, "HW 1 due Sep 4")
    c.save()
    for name, want in (("n.docx", "HW 2"), ("s.pdf", "HW 1")):
        doc = load_doc(tmp_path / name, tmp_path, ref_date=date(2026, 9, 1))
        items, _ = extract_rules(doc)
        assert [i.text for i in items] == [want]


# ---------- regressions from real syllabi (synthetic text in the same shapes) ----------
REAL_SHAPES = """Semester Year: 08/24/2026 - 12/18/2026
Week 4 9/15/26 Career Day. Project check point #1 9/17/26 Final Project check point #1
Week 6 9/29/26 Lecture, Project presentation and discussion. 10/1/26 Lecture, Project presentation and discussion. Monthly homework due.
Week 11 11/3/26 Lecture, Project presentation and discussion. Monthly homework due. 11/5/26 Lecture, Project presentation and discussion.
Week 15 12/1/26 Lecture, Project presentation and discussion. 12/3/26 Final Project Presentation
Final project paper/report due: 12/16/2026.
Oct 6 Midterm Review (tentative)
Oct 8 Midterm (tentative)
Oct 20 TBD, Catchup, and/or Lab Day for Project 1
Dec 15 Finals Week (see the Registrar's exam schedule for time and location)
The code you write is small, but you may 10 or more hours on it
"""


def test_real_world_schedule_rows(tmp_path):
    f = tmp_path / "CSCI 561 syllabus.txt"
    f.write_text(REAL_SHAPES)
    d = load_doc(f, tmp_path, ref_date=date(2026, 8, 24))
    items, report = router.run([d], "rules")
    got = {(i.text, i.date.isoformat()) for i in items}
    assert got == {
        ("Project check point #1", "2026-09-15"), ("Final Project check point #1", "2026-09-17"),
        ("Monthly homework", "2026-10-01"), ("Monthly homework", "2026-11-03"),   # trailing "due." binds to its own row
        ("Final Project Presentation", "2026-12-03"), ("Final project paper/report", "2026-12-16"),
        ("Midterm", "2026-10-08"),
    }, got
    assert report["dropped_ungrounded"] == []
