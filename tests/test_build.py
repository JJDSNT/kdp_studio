import shutil
import zipfile

import pytest

from kdp_studio.book import load_book
from kdp_studio.build import build_ebook, build_print
from kdp_studio.checks import FAIL
from kdp_studio.checks.epub import check_epub
from kdp_studio.checks.kdp_print import check_print, required_gutter


def test_the_ebook_builds_and_passes_its_structural_checks(sample):
    result = build_ebook(load_book(sample), "en")
    with zipfile.ZipFile(result.output) as epub:
        assert epub.namelist()[0] == "mimetype"
        assert "OEBPS/qr/EX-01-01.png" in epub.namelist()
    findings = {f.id: f.verdict for f in check_epub(result.output)}
    assert FAIL not in findings.values()


def test_the_gutter_grows_with_the_page_count():
    assert required_gutter(148) == 0.375
    assert required_gutter(156) == 0.5
    assert required_gutter(301) == 0.625


@pytest.mark.skipif(not (shutil.which("lualatex") and shutil.which("gs")), reason="needs LuaLaTeX and Ghostscript")
def test_the_print_interior_is_measured_not_estimated(sample):
    result = build_print(load_book(sample), "en")
    assert result.details["overfull"] == 0 and result.details["underfull"] == 0
    findings = {f.id: f for f in check_print(result.output, trim=(6, 9), bleed=True, paper="cream")}
    assert findings["page-size"].verdict == "pass"
    # The sample is shorter than KDP accepts, and the check says so.
    assert findings["page-count"].verdict == FAIL
    assert findings["fonts-embedded"].verdict == "pass"
    assert findings["full-bleed"].measured.startswith("2 ")
