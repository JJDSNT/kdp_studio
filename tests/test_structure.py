import subprocess

import pytest

from kdp_studio.book import load_book
from kdp_studio.commands import dispatch
from kdp_studio.errors import ValidationError
from kdp_studio.gates import chapter_status
from kdp_studio.state import Actor
from kdp_studio.structure import move

AUTHOR = Actor("author")


def numbers(book):
    return {s.id: s.number for s in book.sections("en") if s.number}


def test_moving_a_section_renumbers_and_keeps_the_rest_of_book_yaml(sample):
    before = (sample / "book.yaml").read_text()
    result = move(load_book(sample), actor=AUTHOR, reason="the workshop first",
                  section="02-the-workshop", before="01-first-light")
    after = (sample / "book.yaml").read_text()
    assert after.startswith("# A tiny book")
    assert before.split("editions:")[1] == after.split("editions:")[1]
    assert numbers(load_book(sample)) == {"02-the-workshop": 1, "01-first-light": 2, "03-what-remains": 3}
    assert result["impact"]["en"]["renumbered"]["02-the-workshop"] == {"from": 2, "to": 1}
    log = subprocess.run(["git", "log", "-1", "--format=%s"], cwd=sample, capture_output=True, text=True).stdout
    assert log.strip() == "Structure: the workshop first"


def test_a_reference_by_number_that_changed_target_is_reported(sample):
    chapter = sample / "manuscript" / "en" / "03-what-remains.md"
    chapter.write_text(chapter.read_text() + "\nAs chapter 2 showed, work happens.\n")
    result = move(load_book(sample), actor=AUTHOR, reason="swap", section="02-the-workshop", before="01-first-light")
    reference = result["impact"]["en"]["references"][0]
    assert reference["says"] == "chapter 2" and reference["meant"] == "02-the-workshop"
    assert reference["now"] == "chapter 1"


def test_a_section_moves_into_another_part_and_a_part_moves(sample):
    book = load_book(sample)
    move(book, actor=AUTHOR, reason="close on the workshop", section="02-the-workshop", into="epilogue")
    parts = load_book(sample).manifest["contents"]
    assert parts[2]["sections"] == ["03-what-remains", "02-the-workshop"]
    move(load_book(sample), actor=AUTHOR, reason="epilogue first", part="epilogue", before="1")
    assert load_book(sample).manifest["contents"][1]["part"] == "epilogue"


def test_a_move_needs_a_reason_and_a_place(sample):
    with pytest.raises(ValidationError, match="why"):
        move(load_book(sample), actor=AUTHOR, reason="", section="02-the-workshop", before="01-first-light")
    with pytest.raises(ValidationError, match="where"):
        move(load_book(sample), actor=AUTHOR, reason="x", section="02-the-workshop")


def test_a_chapter_is_approved_as_it_reads_and_shows_when_it_changes(sample):
    book = load_book(sample)
    dispatch(book, "approve_chapter", {"section": "01-first-light"}, AUTHOR)
    assert chapter_status(book)["01-first-light"]["state"] == "approved"
    assert not chapter_status(book)["01-first-light"]["changed_since"]
    chapter = sample / "manuscript" / "en" / "01-first-light.md"
    chapter.write_text(chapter.read_text() + "\nNew.\n")
    assert chapter_status(book)["01-first-light"]["changed_since"]
    with pytest.raises(ValidationError, match="may not run"):
        dispatch(book, "approve_chapter", {"section": "01-first-light"}, Actor("assistant", "agent"))


def test_the_voice_gate_judges_the_book_not_a_chapter(sample):
    (sample / "style.yaml").write_text("guide: [intentions.md]\n")
    gate = dispatch(load_book(sample), "open_gate", {"kind": "voice"}, AUTHOR)
    assert gate["subject"] == ""
