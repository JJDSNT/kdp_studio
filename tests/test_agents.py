"""Agents as manifests: what they may read, the two things they hand back, and the agent that writes them."""

import pytest

pytest.importorskip("langgraph")

from kdp_studio.agents import manifest as manifests  # noqa: E402
from kdp_studio.agents.meta import create_agent, remove_agent  # noqa: E402
from kdp_studio.book import load_book  # noqa: E402
from kdp_studio.errors import ValidationError  # noqa: E402
from kdp_studio.versions import version_report  # noqa: E402


class Answers:
    name = "answers"

    def __init__(self, *answers):
        self.answers, self.asked = list(answers), []

    def available(self):
        return ""

    def ask(self, system, prompt, schema, *, web=False, images=()):
        self.asked.append({"system": system, "prompt": prompt, "web": web})
        return self.answers.pop(0)


REPORT = {"summary": "diverges in its reader", "body": "The section speaks to an engineer.",
          "findings": [{"where": "“On 12 March 1998”", "what": "a date with no source", "why": "nobody can check it",
                        "severity": "problem", "suggestion": "name the source"}],
          "could_not": ["whether the workshop existed"]}


def test_the_catalogue_ships_the_agents_the_specification_names(sample):
    found = manifests.manifests(sample)
    assert {"interviewer", "fact-checker", "technical-reviewer", "experimenter", "continuity-reviser",
            "intention-guardian", "ingestor", "diagnostician", "mapper", "kdp-packager", "marketer", "art-director",
            "target-reader"} <= set(found)
    assert found["fact-checker"].web and found["continuity-reviser"].output == "edits"
    assert found["kdp-packager"].knowledge == ("kdp-listing",) and "4,000" in manifests.knowledge("kdp-listing")


def test_a_manifest_cannot_reach_past_the_readers_or_invent_an_output():
    good = {"id": "x-agent", "role": "r", "works_on": "section", "reads": ["section"], "output": "report",
            "system": "You are an agent. " * 8}
    assert manifests.parse(good).id == "x-agent"
    for change, why in (({"reads": ["section", "shell"]}, "no reader named shell"),
                        ({"output": "command"}, "output is one of"),
                        ({"output": "edits", "works_on": "book", "reads": ["plan"]}, "works on, and reads, one section"),
                        ({"works_on": "book"}, "reads one section"),
                        ({"system": "Be good."}, "must say who the agent is")):
        with pytest.raises(ValidationError, match=why):
            manifests.parse({**good, **change})


def test_a_report_is_kept_in_the_book_and_changes_nothing_else(sample):
    book = load_book(sample)
    before = (sample / "manuscript" / "en" / "01-first-light.md").read_text()
    model = Answers(REPORT)
    result = manifests.run(book, "intention-guardian", section="01-first-light", instruction="be strict", model=model)
    asked = model.asked[0]
    assert "On 12 March 1998" in asked["prompt"] and "be strict" in asked["prompt"] and "THIS SECTION" in asked["prompt"]
    assert "guardian of a book's intention" in asked["system"] and "You change nothing" in asked["system"]
    assert asked["web"] is False and result["problems"] == 1
    text = (sample / result["path"]).read_text()
    assert result["path"].startswith("reports/intention-guardian/") and "## Could not establish" in text
    assert "**problem** — “On 12 March 1998”: a date with no source" in text
    assert (sample / "manuscript" / "en" / "01-first-light.md").read_text() == before
    with pytest.raises(ValidationError, match="works on one section"):
        manifests.run(book, "intention-guardian", model=Answers(REPORT))


def test_edits_go_through_the_same_boundary_as_every_reviser(sample):
    book = load_book(sample)
    model = Answers({"edits": [{"find": "the workshop opened", "replace": "the workshop first opened",
                                "practice": "seam", "why": "said again in chapter 2"},
                               {"find": "title: First light", "replace": "title: X", "practice": "x", "why": "x"}],
                     "skipped": [], "summary": "One seam."})
    result = manifests.run(book, "continuity-reviser", section="01-first-light", model=model)
    assert result["applied"] == 1 and result["refused"][0]["reason"] == "touches a prompt, code or the frontmatter"
    found = version_report(book, result["version"])
    assert found["scope"] == "wording" and found["proposed_by"]["id"] == "continuity-reviser"
    assert "declared scope is `wording`" in model.asked[0]["system"]


DESIGNED = {"title": "Opening scene checker", "role": "Says whether a chapter opens with a scene or with an abstraction.",
            "works_on": "section", "reads": ["section", "plan"], "web": False, "output": "report", "scope": "content",
            "system": "You read the first page of a chapter. You say whether it opens in a scene — a person, a place, "
                      "something happening — or in an abstraction. You do not review the rest. Say what you could "
                      "not establish rather than guess.",
            "knowledge_note": "A scene has a person, a place and a moment.", "trial": "check the opening",
            "notes": "none of the existing agents looks at openings"}


def test_the_meta_agent_s_agent_is_tried_before_it_is_catalogued(sample):
    book = load_book(sample)
    model, trial = Answers(DESIGNED), Answers(REPORT)
    result = create_agent(book, "opening-scene", "Check every chapter opens with a scene.", model=model,
                          trial_model=trial)
    assert "- section: The section" in model.asked[0]["prompt"] and "intention-guardian" in model.asked[0]["prompt"]
    # The trial ran with the note it will read, on a real section, and left nothing in the book.
    assert "A scene has a person" in trial.asked[0]["prompt"] and result["trial"]["findings"] == 1
    assert not (sample / "reports").exists()
    made = manifests.get("opening-scene", sample)
    assert made.source == "yours" and made.origin["created_by"] == "meta-agent" and made.knowledge == ("opening-scene",)
    kept = manifests.run(book, "opening-scene", section="01-first-light", model=Answers(REPORT))
    assert kept["path"].startswith("reports/opening-scene/")
    with pytest.raises(ValidationError, match="nothing is replaced"):
        create_agent(book, "opening-scene", "again", model=Answers(DESIGNED))
    assert remove_agent("opening-scene") == {"agent": "opening-scene"}
    with pytest.raises(ValidationError, match="cannot be removed"):
        remove_agent("fact-checker")


def test_an_agent_that_asks_for_more_than_a_manifest_allows_is_never_catalogued(sample):
    wrong = {**DESIGNED, "output": "edits", "works_on": "book", "reads": ["plan"]}
    model = Answers(wrong, wrong)
    with pytest.raises(ValidationError, match="was not catalogued"):
        create_agent(load_book(sample), "rewriter", "Rewrite the whole book.", model=model)
    assert len(model.asked) == 2 and "was refused" in model.asked[1]["prompt"]
    assert "rewriter" not in manifests.manifests(sample)


def test_an_answer_that_fails_its_check_goes_back_to_the_agent_and_never_lands(sample):
    book = load_book(sample)
    lost = {"edits": [{"find": "a passage that is not there", "replace": "x", "practice": "seam", "why": "w"}],
            "skipped": [], "summary": "One."}
    moved = {"edits": [{"find": "12 March 1998", "replace": "13 March 1998", "practice": "seam", "why": "w"}],
             "skipped": [], "summary": "One."}
    good = {"edits": [{"find": "the workshop opened", "replace": "the workshop first opened", "practice": "seam",
                       "why": "w"}], "skipped": [], "summary": "One."}
    model = Answers(lost, good)
    result = manifests.run(book, "continuity-reviser", section="01-first-light", model=model)
    assert result["applied"] == 1 and "None of your edits could be applied" in model.asked[1]["prompt"]
    # Under a wording scope a changed date is refused before any version exists; with no answer left, nothing lands.
    model = Answers(moved, moved)
    with pytest.raises(ValidationError, match="change facts"):
        manifests.run(book, "continuity-reviser", section="01-first-light", model=model)
    from kdp_studio.versions import list_versions

    assert len(list_versions(book, "en", "01-first-light")) == 1


def test_the_author_can_always_have_work_critiqued_and_redone(sample, tmp_path, monkeypatch):
    from kdp_studio import jobs
    from kdp_studio.state import Actor

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    book = load_book(sample)
    review = {"overall": "Generic.", "verdict": "revise",
              "problems": [{"what": "no passage quoted", "why": "nobody can act on it", "fix": "quote each one"}]}
    model = Answers(REPORT, review, {**REPORT, "summary": "compatible"})
    monkeypatch.setattr("kdp_studio.agents.manifest.model_from_env", lambda: model)
    job = jobs.start(book, "run_agent", {"agent": "intention-guardian", "section": "01-first-light"},
                     Actor("author"), wait=True)
    # It landed, and the flow is held: nothing more happens until the author says so.
    assert job["state"] == "waiting" and job["waiting"]["reviewed"] is False and len(model.asked) == 1
    job = jobs.answer(book, job["id"], "critique", wait=True)
    assert job["state"] == "waiting" and job["waiting"]["verdict"] == "revise"
    assert "its critic, not its colleague" in model.asked[1]["system"]
    job = jobs.answer(book, job["id"], "redo", wait=True)
    assert "A reviewer read your answer" in model.asked[2]["prompt"] and "quote each one" in model.asked[2]["prompt"]
    assert job["result"]["summary"] == "compatible" and job["result"]["answers"] == 2
    job = jobs.answer(book, job["id"], "done", wait=True)
    assert job["state"] == "done" and len(list((sample / "reports" / "intention-guardian").glob("*.md"))) == 2
    with pytest.raises(ValidationError, match="not waiting"):
        jobs.answer(book, job["id"], "redo", wait=True)


def test_a_held_job_can_still_be_answered_after_the_runtime_restarts(sample, tmp_path, monkeypatch):
    from kdp_studio import jobs
    from kdp_studio.state import Actor

    monkeypatch.setenv("XDG_STATE_HOME", str(tmp_path / "state"))
    book = load_book(sample)
    review = {"overall": "Thin.", "verdict": "revise", "problems": [{"what": "w", "why": "y", "fix": "quote it"}]}
    model = Answers(REPORT, review, {**REPORT, "summary": "second answer"})
    monkeypatch.setattr("kdp_studio.agents.manifest.model_from_env", lambda: model)
    job = jobs.start(book, "run_agent", {"agent": "intention-guardian", "section": "01-first-light"},
                     Actor("author"), wait=True)
    assert job["state"] == "waiting"
    # The runtime stops: the flow it held in memory is gone, the job and its checkpoint are on disk.
    jobs.HELD.clear()
    monkeypatch.setattr(jobs, "FLOW_KINDS", dict(jobs.FLOW_KINDS))  # as a fresh process finds them: by importing
    jobs.reconcile(book)
    assert jobs.get_job(book, job["id"])["state"] == "waiting"
    job = jobs.answer(book, job["id"], "critique", wait=True)
    assert job["state"] == "waiting" and job["waiting"]["verdict"] == "revise"
    jobs.HELD.clear()
    job = jobs.answer(book, job["id"], "redo", wait=True)
    assert job["result"]["summary"] == "second answer" and "quote it" in model.asked[2]["prompt"]


def test_the_agents_written_in_code_run_on_the_same_flow(sample):
    from kdp_studio import jobs

    import kdp_studio.agents  # noqa: F401 - registers the kinds

    on_the_flow = {"research", "plan_book", "write_section", "revise_section", "revise_voice", "translate_section",
                   "design_theme", "revise_theme", "run_agent"}
    assert on_the_flow <= set(jobs.FLOW_KINDS)
    from kdp_studio.agents.architect import plan_complete
    from kdp_studio.agents.researcher import sources_cited
    from kdp_studio.agents.writer import manuscript_format

    assert manuscript_format("# A title\n\n<div>x</div>\n\nText.") and not manuscript_format("## A part\n\nText.")
    assert sources_cited({"sources": [{"url": "https://a.org", "title": "A"}],
                          "findings": [{"claim": "c", "sources": ["https://b.org"], "confidence": "verified"}]})
    assert plan_complete(load_book(sample), {"parts": [{"title": "P", "chapters": [
        {"title": "C", "synopsis": "s", "promise": "", "research": ["missing"]}]}]}) == [
        "“C” has no promise: what can the reader do after it?", "“C” names research that does not exist: missing"]
