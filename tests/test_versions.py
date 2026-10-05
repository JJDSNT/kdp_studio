import subprocess

import pytest

from kdp_studio.book import load_book
from kdp_studio.commands import dispatch
from kdp_studio.errors import ValidationError
from kdp_studio.state import Actor
from kdp_studio.versions import (adopt_version, propose_version, read_section, reject_version, save_section,
                                 version_report)

AUTHOR = Actor("author")
AGENT = Actor("assistant", "agent")


def chapter(sample):
    return (sample / "manuscript" / "en" / "01-first-light.md").read_text()


def test_a_candidate_never_touches_the_text(sample):
    book = load_book(sample)
    before = chapter(sample)
    version = propose_version(book, "en", "01-first-light", before.replace("Work", "Work").replace(
        "workshop opened", "workshop first opened"), actor=AGENT, scope="wording", rationale="rhythm")
    assert chapter(sample) == before
    report = version_report(book, version["id"])
    assert report["state"] == "candidate" and report["base_is_current"]
    assert {"op": "insert", "text": "first "} in report["diff"] or any(s["op"] == "insert" for s in report["diff"])
    assert not report["violations"]


def test_a_fact_changed_under_wording_is_a_violation(sample):
    book = load_book(sample)
    text = chapter(sample).replace("12 March 1998", "13 March 1998")
    version = propose_version(book, "en", "01-first-light", text, actor=AGENT, scope="wording", rationale="tidy")
    report = version_report(book, version["id"])
    assert report["violations"] == ["Facts changed under a wording-only scope"]
    assert ["number", "13", 1] in report["fidelity"]["facts_added"]


def test_adopting_writes_the_candidate_and_commits_why(sample):
    book = load_book(sample)
    new = chapter(sample).replace("Lisbon", "Lisbon, by the river")
    version = propose_version(book, "en", "01-first-light", new, actor=AGENT, scope="content", rationale="place")
    adopt_version(book, version["id"], actor=AUTHOR, rationale="yes, the river matters")
    assert chapter(sample) == new
    log = subprocess.run(["git", "log", "-1", "--format=%B"], cwd=sample, capture_output=True, text=True).stdout
    assert "yes, the river matters" in log and "Actor: author (human)" in log


def test_an_agent_cannot_adopt_and_a_rejection_needs_a_reason(sample):
    book = load_book(sample)
    version = propose_version(book, "en", "01-first-light", chapter(sample) + "\nMore.\n", actor=AGENT,
                              scope="content", rationale="more")
    with pytest.raises(ValidationError, match="Only a person"):
        adopt_version(book, version["id"], actor=AGENT)
    with pytest.raises(ValidationError, match="reason"):
        reject_version(book, version["id"], actor=AUTHOR, rationale="")
    reject_version(book, version["id"], actor=AUTHOR, rationale="not this")
    assert version_report(book, version["id"])["state"] == "rejected"


def test_a_stale_candidate_cannot_be_adopted(sample):
    book = load_book(sample)
    version = propose_version(book, "en", "01-first-light", chapter(sample) + "\nA.\n", actor=AGENT,
                              scope="content", rationale="a")
    current = read_section(book, "en", "01-first-light")
    save_section(book, "en", "01-first-light", current["text"] + "\nB.\n", expected_digest=current["digest"],
                 actor=AUTHOR, reason="my own line")
    with pytest.raises(ValidationError, match="changed since"):
        adopt_version(book, version["id"], actor=AUTHOR)


def test_an_edit_is_written_byte_for_byte_and_refused_when_stale(sample):
    book = load_book(sample)
    current = read_section(book, "en", "01-first-light")
    odd = current["text"].replace("\n", "\r\n") + "  \n"
    save_section(book, "en", "01-first-light", odd, expected_digest=current["digest"], actor=AUTHOR)
    assert (sample / "manuscript" / "en" / "01-first-light.md").read_bytes() == odd.encode()
    with pytest.raises(ValidationError, match="changed since it was opened"):
        save_section(book, "en", "01-first-light", "x", expected_digest=current["digest"], actor=AUTHOR)


def test_the_command_boundary_keeps_decisions_human(sample):
    book = load_book(sample)
    with pytest.raises(ValidationError, match="may not run"):
        dispatch(book, "decide_gate", {"gate_id": "x", "decision": "approved"}, AGENT)
    with pytest.raises(ValidationError, match="may not run"):
        dispatch(book, "save_section", {}, AGENT)
    gate = dispatch(book, "open_gate", {"kind": "intention"}, AGENT)
    assert gate["requested_by"] == {"id": "assistant", "kind": "agent"}
