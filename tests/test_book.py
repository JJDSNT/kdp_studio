import pytest

from kdp_studio.book import Part, load_book
from kdp_studio.errors import BookFormatError


def test_contents_number_chapters_and_parts(sample):
    book = load_book(sample)
    entries = book.contents("en")
    assert entries[0].kind == "front" and entries[0].number == 0
    part = entries[1]
    assert isinstance(part, Part) and part.number == 1 and part.title == "Making things"
    assert [s.number for s in part.sections] == [1, 2]
    epilogue = entries[2]
    assert epilogue.kind == "epilogue" and epilogue.number == 0 and epilogue.sections[0].number == 3


def test_a_section_in_the_contents_must_exist(sample):
    (sample / "manuscript" / "en" / "02-the-workshop.md").unlink()
    with pytest.raises(BookFormatError, match="02-the-workshop"):
        load_book(sample).contents("en")


def test_a_part_needs_a_title_in_the_language(sample):
    meta = sample / "manuscript" / "en" / "meta.yaml"
    meta.write_text(meta.read_text().replace("  1: Making things\n", ""))
    with pytest.raises(BookFormatError, match="no title"):
        load_book(sample).contents("en")


def test_comments_do_not_count_as_words(sample):
    section = load_book(sample).sections("en")[1]
    assert "editorial" not in section.body.split("<!--")[0]
    assert section.words < len(section.body.split())
