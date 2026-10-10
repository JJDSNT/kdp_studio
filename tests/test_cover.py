"""Covers: the sheet a book and its publisher ask for, art without lettering, words set by code."""

import json
import shutil

import pytest

from kdp_studio import art
from kdp_studio.book import load_book
from kdp_studio.cover import publisher, title_lines, wrap
from kdp_studio.errors import ValidationError
from kdp_studio.state import Actor

AUTHOR = Actor("author")
needs_tex = pytest.mark.skipif(not (shutil.which("lualatex") and shutil.which("gs")),
                               reason="LuaLaTeX and Ghostscript build the cover")


def test_the_wrap_follows_the_trim_the_pages_and_the_paper(sample):
    rules = publisher(load_book(sample))
    sheet = wrap((6.0, 9.0), 156, "white", rules)
    assert sheet.spine == 0.3513 and (sheet.width, sheet.height) == (12.6013, 9.25)
    assert sheet.front_left == 6.4763 and sheet.barcode == (3.875, 0.375, 5.875, 1.575)
    # Another book: smaller, longer, on cream paper.
    pocket = wrap((5.0, 8.0), 300, "cream", rules)
    assert pocket.spine == 0.75 and (pocket.width, pocket.height) == (11.0, 8.25)
    with pytest.raises(ValidationError, match="no spine figure"):
        wrap((6.0, 9.0), 156, "groundwood", rules)


def test_a_book_brings_its_own_publisher_profile(sample):
    (sample / "publishers").mkdir()
    (sample / "publishers" / "offset.yaml").write_text(
        "title: An offset printer\nbleed: 0.197\nspine: {base: 0.04, per_page: {white: 0.0022}}\n"
        "spine_text: {min_pages: 80, margin: 0.08}\nbarcode: {size: [1.5, 1.0], from_spine: 0.4, from_foot: 0.4}\n"
        "ebook: {pixels: [1800, 2700]}\n")
    manifest = sample / "book.yaml"
    manifest.write_text(manifest.read_text().replace("cover: {template: nocturne}",
                                                     "cover: {template: nocturne, publisher: offset}"))
    rules = publisher(load_book(sample))
    assert rules.source == "book" and rules.ebook_pixels == (1800, 2700) and rules.spine_text_pages == 80
    sheet = wrap((6.0, 9.0), 100, "white", rules)
    assert sheet.spine == 0.26 and sheet.width == 12.654 and sheet.height == 9.394


def test_the_title_breaks_before_its_last_word_unless_the_book_says(sample):
    assert title_lines("A Era dos Agentes") == ["A Era dos", "Agentes"]
    assert title_lines("Agentes") == ["Agentes"]
    assert title_lines("A Era dos Agentes", ["A Era", "dos Agentes"]) == ["A Era", "dos Agentes"]


def picture(path, size=(900, 1400)):
    from PIL import Image

    Image.new("RGB", size, "#123456").save(path)
    return path


def test_art_is_recorded_with_how_it_was_made_and_never_replaced(sample, tmp_path):
    book = load_book(sample)
    found = art.add(book, picture(tmp_path / "a.png"), "horizon", actor=AUTHOR, purpose="cover",
                    prompt="a planet's edge at dawn, no text", model="some-model", seed=7)
    assert (found["width"], found["height"], found["lettering"], found["seed"]) == (900, 1400, "none", 7)
    assert (sample / "art" / "horizon.yaml").is_file() and not found["changed_since"]
    with pytest.raises(ValidationError, match="nothing is replaced"):
        art.add(book, picture(tmp_path / "b.png"), "horizon", actor=AUTHOR)
    picture(sample / "art" / "horizon.png", (800, 1200))
    picture(sample / "art" / "dropped.jpg")
    by_id = {a["id"]: a for a in art.records(book)}
    assert by_id["horizon"]["changed_since"] and not by_id["dropped"]["recorded"]


@needs_tex
def test_one_design_gives_the_ebook_cover_and_the_wrap(sample, tmp_path):
    from PIL import Image
    from pypdf import PdfReader

    from kdp_studio.build import build_ebook, build_print
    from kdp_studio.checks.run import run_checks
    from kdp_studio.cover import build_cover

    book = load_book(sample)
    art.add(book, picture(tmp_path / "a.png"), "plain", actor=AUTHOR, purpose="cover", lettering="baked")
    manifest = sample / "book.yaml"
    manifest.write_text(manifest.read_text().replace("cover: {template: nocturne}",
                                                     "cover: {template: nocturne, art: plain}"))
    book = load_book(sample)
    first = build_cover(book, "en")
    assert first.details["print"] == "" and Image.open(first.output).size == (1600, 2560)
    found = {f["id"]: f for f in run_checks(book, "en", "cover")["findings"]}
    assert found["wrap"]["verdict"] == "not_checked" and found["art-lettering"]["verdict"] == "warn"
    assert found["art-ebook"]["verdict"] == "warn"  # 875 px of a 900 px picture, for 1600

    interior = build_print(book, "en")
    pages = len(PdfReader(str(interior.output)).pages)
    built = build_cover(book, "en")
    box = PdfReader(str(built.output)).pages[0].mediabox
    sheet = wrap((6.0, 9.0), pages, "cream", publisher(book))
    assert abs(float(box.width) / 72 - sheet.width) < 0.01 and abs(float(box.height) / 72 - sheet.height) < 0.01
    found = {f["id"]: f for f in run_checks(book, "en", "cover")["findings"]}
    assert {found[k]["verdict"] for k in ("wrap-pages", "wrap-size", "wrap-fonts", "barcode", "spine-text")} == {"pass"}
    assert found["frozen"]["verdict"] == "warn" and found["art-print"]["verdict"] == "warn"
    # The ebook takes the built cover when the author supplied none.
    assert build_ebook(book, "en").details["cover"].endswith("-cover-ebook.jpg")
    # A wrap built for another page count is refused, whatever it looks like.
    report = sample / "builds" / "en" / "cover" / "cover.json"
    data = json.loads(report.read_text())
    data["print"]["wrap"]["pages"] = pages + 8
    report.write_text(json.dumps(data))
    found = {f["id"]: f for f in run_checks(book, "en", "cover")["findings"]}
    assert found["wrap-pages"]["verdict"] == "fail"


# ------------------------------------------------------------ providers

class Endpoint:
    """A RunPod endpoint that answers from a script and remembers what it was sent."""

    def __init__(self, output, polls=("IN_PROGRESS",)):
        self.output, self.polls, self.sent = output, list(polls), []

    def __call__(self, path, body):
        if body is not None:
            self.sent.append(body["input"])
            return {"id": "job-1", "status": "IN_QUEUE"}
        if self.polls:
            return {"status": self.polls.pop(0)}
        return {"status": "COMPLETED", "delayTime": 2000, "executionTime": 30000, "output": self.output}


def encoded(path):
    import base64

    return base64.b64encode(path.read_bytes()).decode()


@pytest.fixture
def configured(tmp_path, monkeypatch):
    import kdp_studio.providers.runpod as runpod

    workflow = tmp_path / "workflow.json"
    workflow.write_text(json.dumps({
        "3": {"class_type": "KSampler", "inputs": {"seed": 0}},
        "5": {"class_type": "EmptyLatentImage", "inputs": {"width": 512, "height": 512}},
        "6": {"class_type": "CLIPTextEncode", "inputs": {"text": ""}},
        "7": {"class_type": "CLIPTextEncode", "_meta": {"title": "Negative"}, "inputs": {"text": ""}}}))
    for name, value in (("RUNPOD_API_KEY", "k"), ("KDP_COMFYUI_ENDPOINT_ID", "comfy"),
                        ("KDP_COMFYUI_WORKFLOW", str(workflow)), ("RUNPOD_QWEN_ENDPOINT_ID", "qwen"),
                        ("XDG_STATE_HOME", str(tmp_path / "state")), ("XDG_CONFIG_HOME", str(tmp_path / "config"))):
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(runpod, "POLL_SECONDS", 0)


def test_a_request_is_planned_before_it_is_sent_and_says_what_is_missing(sample, monkeypatch, tmp_path):
    for name in ("RUNPOD_API_KEY", "KDP_COMFYUI_ENDPOINT_ID", "KDP_COMFYUI_WORKFLOW"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "config"))
    planned = art.plan(load_book(sample), "dawn", prompt="a planet's   edge at dawn", seed=3)
    assert planned["provider"] == "comfyui" and (planned["width"], planned["height"]) == (1024, 1536)
    assert planned["prompt"].startswith("a planet's edge at dawn No text, no letters")
    assert planned["missing"] == ["RUNPOD_API_KEY", "KDP_COMFYUI_ENDPOINT_ID", "KDP_COMFYUI_WORKFLOW"]
    assert planned["print_dpi"] == 167 and planned["estimate_usd"] > 0
    with pytest.raises(ValidationError, match="needs a prompt"):
        art.plan(load_book(sample), "dawn")
    with pytest.raises(ValidationError, match="repaints a picture"):
        art.plan(load_book(sample), "dawn", prompt="x", provider="qwen-edit")


def test_a_generated_picture_enters_the_book_with_how_it_was_made(sample, tmp_path, configured):
    from kdp_studio.providers.comfyui import ComfyUi

    book = load_book(sample)
    endpoint = Endpoint({"images": [{"data": encoded(picture(tmp_path / "made.png", (1024, 1536)))}]})
    planned = art.plan(book, "dawn", prompt="a planet's edge at dawn", seed=11)
    found = art.generate(book, planned, actor=Actor("assistant", "agent"), provider=ComfyUi(endpoint))
    graph = endpoint.sent[0]["workflow"]
    assert graph["6"]["inputs"]["text"].endswith("no signature anywhere in the image.")
    assert graph["7"]["inputs"]["text"].startswith("text, letters") and graph["3"]["inputs"]["seed"] == 11
    assert graph["5"]["inputs"] == {"width": 1024, "height": 1536}
    assert (found["seed"], found["provider"], found["lettering"]) == (11, "comfyui", "unchecked")
    assert found["provenance"]["seconds"] == 32.0 and found["provenance"]["job"] == "job-1"
    assert (sample / "art" / "dawn.png").is_file() and found["cost_usd"] > 0


def test_lettering_is_repainted_out_of_a_picture_the_book_has(sample, tmp_path, configured):
    from kdp_studio.providers.qwen_edit import QwenEdit

    book = load_book(sample)
    art.add(book, picture(tmp_path / "old.png", (1024, 1536)), "old-cover", actor=AUTHOR, purpose="cover",
            lettering="baked")
    endpoint = Endpoint({"image": encoded(picture(tmp_path / "clean.png", (1024, 1536)))})
    planned = art.plan(book, "clean-cover", derived_from="old-cover", remove_lettering=True, seed=5)
    assert planned["provider"] == "qwen-edit" and planned["prompt"].startswith("Remove every piece of text")
    found = art.generate(book, planned, actor=AUTHOR, provider=QwenEdit(endpoint))
    assert endpoint.sent[0]["seed"] == 5 and endpoint.sent[0]["image_base64"]
    assert found["derived_from"] == "old-cover" and found["model"] == "qwen-image-edit"


def test_paid_work_is_not_sent_twice(tmp_path, configured):
    from kdp_studio.providers import ProviderError
    from kdp_studio.providers.runpod import run_job

    state = tmp_path / "x.job.json"
    state.write_text(json.dumps({"endpoint": "e", "sha256": "another request", "status": "IN_QUEUE", "id": "j"}))
    endpoint = Endpoint({"image": "x"})
    with pytest.raises(ProviderError, match="different pending request"):
        run_job("e", {"prompt": "new"}, state_file=state, transport=endpoint)
    assert endpoint.sent == []


# --------------------------------------------------------------- themes

def test_a_theme_is_a_name_across_media_and_the_book_takes_it_by_one_command(sample):
    from kdp_studio import gallery
    from kdp_studio.commands import dispatch

    found = {t["name"]: t for t in gallery.themes(sample)}
    assert {"nocturne", "folio", "signal"} <= set(found)
    assert set(found["folio"]["kinds"]) == {"print", "ebook", "cover"}
    before = (sample / "book.yaml").read_text()
    result = dispatch(load_book(sample), "set_theme", {"theme": "folio", "reason": "quieter"}, AUTHOR)
    assert result["changed"] == ["print", "ebook", "cover"]
    assert (sample / "book.yaml").read_text() == before.replace("template: nocturne", "template: folio")
    assert gallery.in_use(load_book(sample)) == {"print": "folio", "ebook": "folio", "cover": "folio"}
    assert dispatch(load_book(sample), "set_theme", {"theme": "folio"}, AUTHOR)["changed"] == []
    with pytest.raises(Exception, match="No theme named"):
        dispatch(load_book(sample), "set_theme", {"theme": "nope"}, AUTHOR)


def test_a_theme_is_set_in_a_book_whose_editions_are_written_as_a_block(tmp_path, sample):
    from kdp_studio.gallery import apply_theme

    manifest = sample / "book.yaml"
    text = manifest.read_text()
    start = text.index("editions:")
    end = text.index("exercises:")
    manifest.write_text(text[:start] + "editions:\n  print:\n    template: nocturne\n    trim: 6x9\n    paper: cream\n"
                        "  ebook:\n    template: nocturne\n" + text[end:])
    result = apply_theme(load_book(sample), "signal", actor=AUTHOR)
    assert result["changed"] == ["print", "ebook"] and "    trim: 6x9\n" in manifest.read_text()
    assert manifest.read_text().count("template: signal") == 2


@needs_tex
def test_every_theme_renders_over_the_specimen(tmp_path, monkeypatch):
    from PIL import Image

    from kdp_studio import gallery

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    for theme in ("nocturne", "folio", "signal"):
        assert gallery.built(theme, "pt-BR") is None
        render = gallery.build(theme, "pt-BR")
        roles = [p["role"] for p in render["pages"] if p["role"]]
        assert roles == ["contents", "part", "chapter", "callouts", "exercise"], theme
        folder = gallery.cache_dir() / render["key"]
        assert Image.open(folder / render["cover"]).size == (1600, 2560) and (folder / "wrap.png").is_file()
        assert len(render["ebook"]) == 4 and gallery.built(theme, "pt-BR") == render
        page, kind = gallery.epub_file(render["key"], render["ebook"][-1])
        assert kind == "application/xhtml+xml" and b"Exercitium breve" in page
    with pytest.raises(Exception, match="No gallery file"):
        gallery.file(render["key"], "../../outside")


# ------------------------------------------------- black ink, the designer

def test_black_ink_turns_every_colour_into_a_grey(sample):
    from kdp_studio import catalog
    from kdp_studio.build import grey, print_colors

    assert grey("FFFFFF") == "FFFFFF" and grey("000000") == "000000" and grey("32D9E2") == "B6B6B6"
    template = catalog.get("print", "nocturne")
    mono = print_colors(load_book(sample), template, "black")
    assert all(value[0:2] == value[2:4] == value[4:6] for value in mono.values())
    assert print_colors(load_book(sample), template, "color")["cold"] == "32D9E2"
    with pytest.raises(ValidationError, match="Unknown ink"):
        print_colors(load_book(sample), template, "sepia")


@needs_tex
def test_an_interior_declared_black_is_measured_for_colour(sample):
    from kdp_studio.build import build_print
    from kdp_studio.checks.kdp_print import check_print, colour_pages

    coloured = build_print(load_book(sample), "en")
    assert colour_pages(coloured.output)
    found = {f.id: f for f in check_print(coloured.output, trim=(6, 9), bleed=True, paper="cream", ink="black")}
    assert found["ink"].verdict == "fail"
    black = build_print(load_book(sample), "en", ink="black")
    assert colour_pages(black.output) == []
    found = {f.id: f for f in check_print(black.output, trim=(6, 9), bleed=True, paper="cream", ink="black")}
    assert found["ink"].verdict == "pass"


class Drawer:
    """A model that answers with a theme: Folio's blocks under another name, then whatever it is told to."""

    name = "drawer"

    def __init__(self, name, spoil=None):
        from kdp_studio import catalog
        from kdp_studio.agents.designer import base_blocks

        blocks = base_blocks((catalog.get("print", "folio").path / "book.tex.j2").read_text())
        parts = blocks["parts"].split("\\aliaspagestyle")[0].split("parts\n", 1)[1]
        self.answer = {
            "title": "Almanac", "description": "A quiet page for a field guide.",
            "fonts": blocks["fonts"].split("fonts\n", 1)[1],
            "parts": parts, "chapter_style": blocks["chapter_style"].replace("folio", name)
            .replace("\\newcommand{\\kdpchapterlabel}{}\n", ""),
            "section_head": blocks["section_head"], "needs_bleed": False,
            "palette": dict(ink="111111", night="222222", deep="1A2B1A", cold="2E6B3A", cold_dark="1F4D28",
                            warm="B5651D", warm_dark="7A4312", shade="F1F4EC", shade_light="F8FAF5", grey="667066",
                            cream="FBFBF6", rule="D5DBCF"),
            "css_extra": "h1 { text-align: center; }",
            "cover_palette": dict(night="1F4D28", cream="FBFBF6", cold="E3C36A", warm="B5651D", grey="B9C2B4"),
            "cover_display_font": "TeX Gyre Schola", "cover_text_font": "TeX Gyre Schola",
            "references": [{"url": "https://example.org/a-template", "title": "A template", "license": "",
                            "taken": "the centred chapter head; no code"}],
            "notes": "ok"}
        self.spoil, self.asked = spoil or {}, []

    def available(self):
        return ""

    def ask(self, system, prompt, schema, *, web=False):
        self.asked.append({"prompt": prompt, "web": web})
        return {**self.answer, **self.spoil}


@needs_tex
def test_the_designer_s_theme_is_built_before_it_is_catalogued_and_travels_with_the_book(sample, tmp_path, monkeypatch):
    from kdp_studio import catalog, gallery
    from kdp_studio.agents.designer import design_theme
    from kdp_studio.commands import dispatch

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    model = Drawer("almanac")
    result = design_theme(load_book(sample), "almanac", "A field guide: calm, green, centred.", based_on="nocturne",
                          reference="https://example.org/a-template", model=model)
    assert model.asked[0]["web"] is True and "Installed font families" in model.asked[0]["prompt"]
    assert result["attempts"] == 1 and result["references"][0]["license"] == ""
    found = {t["name"]: t for t in gallery.themes(sample)}["almanac"]
    assert found["source"] == "yours" and found["designed_by"] == "designer" and found["based_on"] == "nocturne"
    assert found["inspired_by"][0]["taken"] == "the centred chapter head; no code"
    assert catalog.get("print", "almanac").meta["colors"]["cold"] == "2E6B3A"
    css = (catalog.get("ebook", "almanac").path / "style.css").read_text()
    assert "#2E6B3A" in css and "#32D9E2" not in css and "h1 { text-align: center; }" in css
    render = gallery.built("almanac", "en", sample)
    assert [p["role"] for p in render["pages"] if p["role"]][:2] == ["contents", "part"]
    # Taking it copies it into the book: a book builds from what it holds.
    taken = dispatch(load_book(sample), "set_theme", {"theme": "almanac"}, AUTHOR)
    assert taken["carried"] == ["templates/print/almanac", "templates/ebook/almanac", "templates/cover/almanac"]
    assert catalog.get("print", "almanac", sample).source == "book"
    with pytest.raises(ValidationError, match="nothing is replaced"):
        design_theme(load_book(sample), "almanac", "again", model=model)


def test_a_theme_that_runs_code_or_names_a_missing_font_is_never_catalogued(sample, tmp_path, monkeypatch):
    from kdp_studio import catalog
    from kdp_studio.agents.designer import design_theme

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    for spoil, why in (({"parts": "\\directlua{os.execute('true')}"}, "may not"),
                       ({"cover_display_font": "A Font Nobody Has"}, "not installed")):
        model = Drawer("almanac", spoil)
        with pytest.raises(ValidationError, match=why):
            design_theme(load_book(sample), "almanac", "A field guide.", model=model, attempts=2)
        assert len(model.asked) == 2 and "did not build" in model.asked[1]["prompt"]
        assert not (catalog.user_root() / "print" / "almanac").exists()


class Eye:
    """A critic that answers from a script and remembers what it was shown."""

    name = "eye"

    def __init__(self, *verdicts):
        self.verdicts, self.seen = list(verdicts), []

    def available(self):
        return ""

    def ask(self, system, prompt, schema, *, web=False, images=()):
        self.seen.append({"prompt": prompt, "images": [p.name for p in images]})
        verdict = self.verdicts.pop(0)
        problems = [] if verdict == "accept" else [
            {"where": "a chapter opening", "what": "the label is too faint", "why": "it vanishes in black ink",
             "severity": "defect", "owner": "designer", "fix": "set the label in cold_dark"},
            {"where": "an exercise", "what": "a label is stranded at the foot of the box", "why": "it says nothing",
             "severity": "defect", "owner": "template", "fix": "keep it with its list"},
            {"where": "the cover", "what": "it wants a picture", "why": "the ground is empty",
             "severity": "weakness", "owner": "art", "fix": "commission one"}]
        return {"overall": "Competent, and nobody's.", "character": "A default.", "answers_the_brief": "In part.",
                "strengths": ["the centre line holds"], "problems": problems, "verdict": verdict}


@needs_tex
def test_a_critic_looks_at_the_pages_and_the_designer_answers_it(sample, tmp_path, monkeypatch):
    from kdp_studio import gallery
    from kdp_studio.agents import critic
    from kdp_studio.agents.designer import design_theme, remove_theme, revise_theme

    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    book = load_book(sample)
    model, eye = Drawer("almanac"), Eye("revise", "accept")
    result = design_theme(book, "almanac", "A field guide: calm, green.", model=model, critic=eye, rounds=1)
    # The critic was shown pictures — the cover and pages, then pages in black ink — never a file to open.
    assert eye.seen[0]["images"][0] == "cover.jpg" and len(eye.seen[0]["images"]) == 7
    assert "in black ink" in eye.seen[0]["prompt"] and "A field guide" in eye.seen[0]["prompt"]
    # Its criticism went back to the designer, defects first, and the new drawing was looked at too.
    assert len(model.asked) == 2 and "[defect] a chapter opening: the label is too faint" in model.asked[1]["prompt"]
    assert "You already drew this theme" in model.asked[1]["prompt"] and model.asked[1]["web"] is False
    # What belongs to the template or to the art director is named as not the designer's, and is not counted.
    assert "Not yours to fix" in model.asked[1]["prompt"] and "a label is stranded" in model.asked[1]["prompt"]
    assert critic.critiques("almanac")[0]["defects"] == 1
    assert [c["verdict"] for c in result["critiques"]] == ["revise", "accept"] and result["drawings"] == 2
    assert critic.latest("almanac")["verdict"] == "accept" and len(critic.critiques("almanac")) == 2

    # The author asks for a change in their own words; a revision that does not build leaves the theme as it was.
    before = (gallery.catalog.user_root() / "print" / "almanac" / "book.tex.j2").read_text()
    with pytest.raises(ValidationError, match="stays as it was"):
        revise_theme(book, "almanac", "larger title", model=Drawer("almanac", {"parts": "\\directlua{x}"}))
    assert (gallery.catalog.user_root() / "print" / "almanac" / "book.tex.j2").read_text() == before
    again = Drawer("almanac")
    revise_theme(book, "almanac", "larger title", model=again)
    assert "larger title" in again.asked[0]["prompt"]
    with pytest.raises(ValidationError, match="not a theme the designer drew"):
        revise_theme(book, "folio", "x", model=again)
    # By default the work stops after one look: answering the critic is the author's call, not the designer's.
    quiet, once = Drawer("almanac"), Eye("revise")
    seen = revise_theme(book, "almanac", "smaller title", model=quiet, critic=once, look=True)
    assert len(quiet.asked) == 1 and len(once.seen) == 1 and seen["critiques"][0]["verdict"] == "revise"
    assert remove_theme("almanac")["removed"] == ["print", "ebook", "cover"]
    assert "almanac" not in {t["name"] for t in gallery.themes(sample)}
    with pytest.raises(ValidationError, match="cannot be removed"):
        remove_theme("nocturne")
