"""Edge cases for date parsing and rule extraction."""
from datetime import date

import pytest

from extractor import dates, router
from extractor.models import Doc
from extractor.rules import extract_rules


def mk(text: str, ref=date(2026, 8, 24), name="CSCI 498 syllabus.txt", cls="CSCI498") -> Doc:
    return Doc(path=name, abs_path=name, text=text, doc_date=ref, ref_date=ref, cls=cls, is_syllabus=True)


def got(text: str, **kw):
    items, _ = router.run([mk(text, **kw)], "rules")
    return {(i.text, i.date.isoformat()) for i in items}


# ---------- dates ----------
@pytest.mark.parametrize("text,want", [
    ("Sept. 15", date(2026, 9, 15)),
    ("September 15th, 2026", date(2026, 9, 15)),
    ("15 Sep", date(2026, 9, 15)),
    ("9/15/26", date(2026, 9, 15)),
    ("9/15/2026", date(2026, 9, 15)),
    ("9/15", date(2026, 9, 15)),
    ("2026-09-15", date(2026, 9, 15)),
    ("Tue, Sep 15", date(2026, 9, 15)),
    ("Tuesday, September 15", date(2026, 9, 15)),
    ("Dec 1", date(2026, 12, 1)),
])
def test_date_formats(text, want):
    assert [h.date for h in dates.find_dates(text, date(2026, 8, 24))] == [want]


@pytest.mark.parametrize("text", ["Feb 30", "13/45", "0/5", "Sep 31", "see Section 4", "version 2.3", "May need", "you may 10"])
def test_non_dates_ignored(text):
    assert dates.find_dates(text, date(2026, 8, 24)) == []


def test_may_capitalised_is_a_month():
    assert dates.find_dates("May 3", date(2026, 1, 20))[0].date == date(2026, 5, 3)


def test_year_rollover_spring_semester():
    ref = date(2027, 2, 1)   # Spring 2027 syllabus
    assert dates.find_dates("Feb 10", ref)[0].date == date(2027, 2, 10)
    assert dates.find_dates("May 5", ref)[0].date == date(2027, 5, 5)


def test_fall_semester_january_final_rolls_to_next_year():
    assert dates.find_dates("Jan 12", date(2026, 9, 1))[0].date == date(2027, 1, 12)


def test_weekday_typo_does_not_flip_year():
    # Oct 14 2026 is a Wednesday; "Thursday" is a typo, we must not jump to 2027
    assert dates.find_dates("Thursday, Oct 14", date(2026, 9, 1))[0].date == date(2026, 10, 14)


def test_weekday_picks_matching_year_when_plausible():
    # Jan 1 2027 is a Friday; Jan 1 2026 is a Thursday. Ref in late Dec: both are plausible.
    assert dates.find_dates("Friday, Jan 1", date(2026, 12, 20))[0].date == date(2027, 1, 1)


def test_two_dates_in_a_row_are_both_found():
    assert [h.date for h in dates.find_dates("8/25/26 First Day. 8/27/26 Lecture", date(2026, 8, 24))] == \
        [date(2026, 8, 25), date(2026, 8, 27)]


@pytest.mark.parametrize("text,want", [
    ("due 5pm", "17:00"), ("Oct 5 at 11:59 pm", "23:59"), ("Oct 5, 9 a.m.", "09:00"),
    ("Oct 5 12:00 am", "00:00"), ("Oct 5 12:30 pm", "12:30")])
def test_times(text, want):
    text = text if "Oct" in text else "Oct 5 " + text
    assert dates.find_dates(text, date(2026, 9, 1))[0].time == want


def test_time_range_not_taken_as_due_time():
    assert dates.find_dates("Final exam: Dec 10, 7:00-9:00 pm", date(2026, 9, 1))[0].time is None


def test_relative_next_weekday_rules():
    posted = date(2026, 11, 11)   # Wednesday
    f = lambda t: dates.find_dates(t, posted, posted)[0].date
    assert f("this Friday") == date(2026, 11, 13)
    assert f("next Friday") == date(2026, 11, 20)    # same ISO week -> following week
    assert f("next Monday") == date(2026, 11, 16)


# ---------- rules ----------
@pytest.mark.parametrize("line,want", [
    ("Homework #3 due Oct 12", {("Homework #3", "2026-10-12")}),
    ("Problem Set 2 due Friday, Oct 9 at 5pm", {("Problem Set 2", "2026-10-09")}),
    ("Quiz 1 - Sep 20", {("Quiz 1", "2026-09-20")}),
    ("Exam 2: Nov 4", {("Exam 2", "2026-11-04")}),
    ("Assignment 3 (due 10/12)", {("Assignment 3", "2026-10-12")}),
    ("Oct 14 | Midterm", {("Midterm", "2026-10-14")}),
    ("Midterm | Oct 14", {("Midterm", "2026-10-14")}),
    ("HW 1 due Sep 4, HW 2 due Sep 18", {("HW 1", "2026-09-04"), ("HW 2", "2026-09-18")}),
    ("HW 4 due Nov 12 (was Nov 10)", {("HW 4", "2026-11-12")}),
    ("HW 4 due Nov 3, extended from Nov 10", {("HW 4", "2026-11-03")}),
])
def test_label_date_pairs(line, want):
    assert got(line) == want


@pytest.mark.parametrize("line", [
    "No class Oct 13",
    "Aug 24 | Course introduction",
    "Office hours moved to Thursday, Oct 8",
    "Homework is worth 3/4 of your grade",
    "Midterm Review Oct 6",
    "See the Registrar's exam schedule (published Oct 1)",
    "Lecture, Project presentation and discussion. 10/6/26",
    "Late homework loses 10% per day",
])
def test_no_item_for_non_deadlines(line):
    assert got(line) == set(), line


def test_label_on_previous_line_for_wrapped_rows():
    items, _ = router.run([mk("Homework 5\nSep 25")], "rules")
    assert [(i.text, i.date.isoformat()) for i in items] == [("Homework 5", "2026-09-25")]


def test_same_homework_listed_twice_same_date_deduped():
    items, _ = router.run([mk("HW 1 due Sep 4\nSummary: HW 1 due Sep 4")], "rules")
    assert len(items) == 1


def test_same_label_on_two_dates_in_one_file_kept_as_occurrences():
    items, report = router.run([mk("Monthly homework due Oct 1\nMonthly homework due Nov 3")], "rules")
    assert sorted(i.date.isoformat() for i in items) == ["2026-10-01", "2026-11-03"]
    assert report["warnings"] == []


def test_checkbox_and_todo_markers():
    d = mk("TODO: read chapter 4 by Sep 10\n[ ] email the TA\n- [ ] finish lab 2 before the midterm\nMidterm: Oct 14", ref=date(2026, 9, 1))
    d.is_syllabus = False
    items, _ = router.run([d], "rules")
    by = {i.text: i for i in items}
    assert by["read chapter 4"].date == date(2026, 9, 10)
    assert by["finish lab 2"].date == date(2026, 10, 13)      # before the midterm
    assert by["email the TA"].date == date(2026, 10, 13)        # undated -> day before the next exam


def test_undated_todo_without_anchor_goes_before_next_exam_or_unscheduled():
    d = mk("[ ] email the TA\nFinal exam: Dec 10", ref=date(2026, 9, 1))
    d.is_syllabus = False
    items, _ = router.run([d], "rules")
    assert any(i.text == "email the TA" and i.date == date(2026, 12, 9) for i in items)


def test_todo_not_scheduled_before_a_past_exam():
    d = mk("TODO: study ch. 7 before the midterm\nMidterm: Oct 14", ref=date(2026, 10, 20))
    d.is_syllabus = False
    items, report = router.run([d], "rules")
    assert not any(i.type == "todo" for i in items) and report["unscheduled"]


def test_prose_todo_phrases_ignored_in_syllabus():
    assert got("You will need to bring a laptop to every class.\nDon't forget to check Canvas.") == set()


def test_empty_and_dateless_docs():
    assert router.run([mk("")], "rules")[0] == []
    assert router.run([mk("Course description. Grading policy: HW 40%, Midterm 25%.")], "rules")[0] == []


def test_date_does_not_swallow_year_from_next_line():
    hits = dates.find_dates("HW 2 due November 21\n2026-09-25 | Lecture", date(2026, 8, 24))
    assert [h.date for h in hits] == [date(2026, 11, 21), date(2026, 9, 25)]


def test_time_never_taken_from_next_line():
    assert dates.find_dates("HW 2 due Oct 5\n9 am lecture", date(2026, 8, 24))[0].time is None


# ---------- shapes from a real PL syllabus (spring 2025) and a calendar-grid schedule ----------
PL_REF = date(2025, 1, 6)


def test_review_session_is_not_the_exam():
    assert got("Feb 27 Q&A for midterm", ref=PL_REF) == set()
    assert got("Feb 27 Review for the midterm", ref=PL_REF) == set()
    assert got("Mar 4 Midterm Exam", ref=PL_REF) == {("Midterm Exam", "2025-03-04")}


def test_exam_row_after_review_row_has_no_conflict():
    d = mk("8 Feb 25 Lab 4 +10: Mutability\n Feb 27 Q&A for midterm\n9 Mar 4 Midterm Exam", ref=PL_REF)
    items, report = router.run([d], "rules")
    assert [(i.text, i.date.isoformat()) for i in items] == [("Midterm Exam", "2025-03-04")]
    assert report["warnings"] == []


@pytest.mark.parametrize("line", [
    "5 Feb 4 Lab 2 Day - HoF",
    " Jan 16 03: Linux and Git (Lab 0 Day)",
    "8 Feb 25 Lab 4 +10: Mutability",
    "11 Mar 18 Spring Break (no class)",
    "17 Apr 29 Final Review Q&A",
    "18 May 7 Finals Week",
    "4 Jan 28 Career Day (no class)",
])
def test_class_session_rows_are_not_deadlines(line):
    assert got(line, ref=PL_REF) == set(), line


def test_tentative_items_are_marked():
    d = mk("Oct 8 Midterm (tentative)", ref=date(2026, 8, 24))
    items, _ = router.run([d], "rules")
    assert items[0].note == "Marked tentative in the source."


def test_calendar_grid_gives_warning_not_wrong_dates():
    text = ("Tuesday Detailed Course Schedule - Spring 2023:\n"
            "Week Monday Tuesday Wednesday Thursday Friday\n"
            "1 January 9 January 10 January 11 January 12 January 13\n"
            "Class meets Read Ch. 1\n"
            "Research Project 1 -\n"
            "Individual Submission Feb 13\n")
    items, report = router.run([mk(text, ref=date(2023, 1, 9))], "rules")
    assert items == []
    assert any("calendar-grid" in w for w in report["warnings"])


def test_grid_documents_are_not_sent_to_claude_in_hybrid():
    text = "Week Monday Tuesday Wednesday Thursday Friday\n1 January 9 January 10 January 11 January 12 January 13\n"
    calls = []
    router.run([mk(text, ref=date(2023, 1, 9))], "hybrid", call=lambda p: calls.append(p) or '{"items":[]}')
    assert calls == []


# ---------- slot groups: several days offered for one item, you only need one ----------
def _items(text, ref=date(2026, 8, 24)):
    return router.run([mk(text, ref=ref)], "rules")


def test_slots_become_one_item_at_the_earliest_date():
    items, report = _items("Checkpoint 1 (Due Sept 15)\n9/15/26 Project check point #1 9/17/26 Final Project check point #1")
    assert len(items) == 1
    it = items[0]
    assert it.date == date(2026, 9, 15) and it.alternates == [date(2026, 9, 17)]
    assert "Sep 15" in it.note and "Sep 17" in it.note and "one" in it.note
    assert report["warnings"] == []                      # not reported as a conflict


def test_slots_from_two_sections_of_one_file_merge():
    items, _ = _items("Week 12 11/10/26 Project check point #3 11/12/26 Project check point #3\n"
                      "3. Checkpoint 3: Progress Update Presentation (Due Nov 10)")
    assert len(items) == 1 and items[0].date == date(2026, 11, 10) and items[0].alternates == [date(2026, 11, 12)]


def test_monthly_recurring_items_are_not_slots():
    items, _ = _items("Monthly homework due Oct 1\nMonthly homework due Nov 3\nMonthly homework due Nov 24")
    assert sorted(i.date.isoformat() for i in items) == ["2026-10-01", "2026-11-03", "2026-11-24"]
    assert all(not i.alternates for i in items)


def test_weekly_items_a_week_apart_are_not_slots():
    items, _ = _items("Quiz due Sep 8\nQuiz due Sep 15\nQuiz due Sep 22")
    assert len(items) == 3 and all(not i.alternates for i in items)


def test_frequent_recurring_item_is_not_collapsed_into_pairs():
    lines = "\n".join(f"Reading response due {d}" for d in ("Sep 1", "Sep 3", "Sep 8", "Sep 10", "Sep 15", "Sep 17"))
    items, _ = _items(lines)
    assert len(items) == 6


def test_slots_do_not_hide_a_real_cross_file_move():
    syl = mk("Checkpoint 1: Sep 15 or Sep 17", name="syllabus.txt")
    ann = Doc("ann.txt", "ann.txt", "Posted: Sep 10, 2026\nCheckpoint 1 has been moved to Sep 22.",
              date(2026, 9, 10), date(2026, 8, 24), "CSCI498", False)
    items, _ = router.run([syl, ann], "rules")
    cp = [i for i in items if "heckpoint" in i.text]
    assert len(cp) == 1 and cp[0].date == date(2026, 9, 22) and set(cp[0].sources) == {"ann.txt", "syllabus.txt"}
