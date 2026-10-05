import subprocess

import pytest

from kdp_studio.book import load_book
from kdp_studio.errors import RevisionConflictError, ValidationError
from kdp_studio.gates import decide_gate, gate_status, open_gate
from kdp_studio.state import Actor, read_state

AUTHOR = Actor("author")


def test_a_gate_records_who_decided_what_and_why(sample):
    book = load_book(sample)
    gate = open_gate(book, "intention", actor=AUTHOR)
    assert gate["state"] == "waiting"
    decided = decide_gate(book, gate["id"], "approved", actor=AUTHOR, rationale="It is mine")
    assert decided["decided_by"] == {"id": "author", "kind": "human"}
    state = read_state(sample)
    assert state["revision"] == 2
    assert [event["event"] for event in state["history"]] == ["gate_opened", "gate_decided"]
    log = subprocess.run(["git", "log", "--format=%s"], cwd=sample, capture_output=True, text=True).stdout
    assert f"Gate {gate['id']}: approved" in log


def test_an_agent_never_decides_a_gate(sample):
    book = load_book(sample)
    gate = open_gate(book, "intention", actor=AUTHOR)
    with pytest.raises(ValidationError, match="Only a person"):
        decide_gate(book, gate["id"], "approved", actor=Actor("coordinator", "agent"))


def test_asking_for_changes_needs_a_rationale(sample):
    book = load_book(sample)
    gate = open_gate(book, "voice", "01-first-light", actor=AUTHOR)
    with pytest.raises(ValidationError, match="rationale"):
        decide_gate(book, gate["id"], "changes_requested", actor=AUTHOR)


def test_an_approval_is_not_inherited_by_a_later_version(sample):
    book = load_book(sample)
    gate = open_gate(book, "voice", "01-first-light", actor=AUTHOR)
    decide_gate(book, gate["id"], "approved", actor=AUTHOR)
    assert not gate_status(book)[0]["changed_since"]
    chapter = sample / "manuscript" / "en" / "01-first-light.md"
    chapter.write_text(chapter.read_text() + "\nOne more sentence.\n")
    assert gate_status(book)[0]["changed_since"]


def test_a_decided_gate_is_never_rewritten(sample):
    book = load_book(sample)
    gate = open_gate(book, "intention", actor=AUTHOR)
    decide_gate(book, gate["id"], "approved", actor=AUTHOR)
    with pytest.raises(ValidationError, match="already decided"):
        decide_gate(book, gate["id"], "rejected", actor=AUTHOR, rationale="changed my mind")


def test_files_changed_while_waiting_cannot_be_approved(sample):
    book = load_book(sample)
    gate = open_gate(book, "intention", actor=AUTHOR)
    (sample / "intentions.md").write_text("Something else entirely.\n")
    with pytest.raises(ValidationError, match="changed after"):
        decide_gate(book, gate["id"], "approved", actor=AUTHOR)


def test_a_stale_revision_is_refused(sample):
    book = load_book(sample)
    gate = open_gate(book, "intention", actor=AUTHOR)
    with pytest.raises(RevisionConflictError):
        decide_gate(book, gate["id"], "approved", actor=AUTHOR, expected_revision=0)
