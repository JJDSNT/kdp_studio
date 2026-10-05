from kdp_studio.fidelity import Normalization, compare, digest

TEXT = """On 12 March 1998 the workshop opened at 7 Rua Augusta.

> [!concept] A callout
> See https://example.org/a for the source.
"""


def test_markup_changes_are_not_word_changes():
    restyled = TEXT.replace("> [!concept] A callout", "> **CONCEPT — A callout**")
    report = compare(TEXT, restyled,
                     before_rules=[Normalization("marker", "markup", r"^\[![a-z]+\]\s*")],
                     after_rules=[Normalization("label", "generated label", r"^CONCEPT — ")])
    assert report.ok and not report.identical_bytes
    assert report.normalizations == {"label": 1, "marker": 1}


def test_a_silently_changed_date_is_caught_even_if_correct():
    revised = TEXT.replace("12 March 1998", "13 March 1998")
    report = compare(TEXT, revised)
    assert not report.ok
    assert ("number", "12", 1) in report.facts_removed
    assert ("number", "13", 1) in report.facts_added


def test_a_changed_url_and_name_are_facts():
    report = compare(TEXT, TEXT.replace("example.org/a", "example.org/b").replace("Rua Augusta", "Rua Garrett"))
    kinds = {kind for kind, _, _ in report.facts_added}
    assert {"url", "name"} <= kinds


def test_an_untouchable_block_is_checked_by_bytes():
    block = "> [!prompt] EX-01-01\n>\n> Make a list.\n"
    assert digest(block) == digest(block)
    assert digest(block) != digest(block.replace("list", "List"))


def test_editorial_comments_are_not_reader_text():
    assert compare(TEXT, TEXT + "\n<!-- a note -->\n").ok
