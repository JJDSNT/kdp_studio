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
