from kdp_studio.book import load_book
from kdp_studio.labels import labels
from kdp_studio.render import RenderContext
from kdp_studio.render.latex import LatexRenderer
from kdp_studio.render.xhtml import XhtmlRenderer


def context():
    return RenderContext("en", labels("en"), prompt_url=lambda i: f"https://x.org/{i}",
                         qr_path=lambda i, u: f"qr/{i}.png")


def test_latex_uses_the_template_contract(sample):
    book = load_book(sample)
    body = "\n".join(LatexRenderer(context()).entry(e) for e in book.contents("en"))
    assert r"\kdppart{Part I}{Making things}" in body
    assert r"\kdpunnumberedpart{Epilogue}{Afterwards}" in body
    assert r"\kdpchapter{Chapter 1}{First light}" in body
    assert r"\begin{kdpcallout}{concept}{Concept}{A callout}" in body
    assert r"\begin{kdpcallout}{framework}{Three questions}{}" in body
    assert r"\begin{kdpexercise}{Try it}{Make something}" in body
    assert r"\kdpprompt{Get the prompt}{EX-01-01}{x.org/EX-01-01}{qr/EX-01-01.png}" in body
    assert r"\kdppromptlabel{Second prompt}" in body
    assert r"\footnote{A footnote" in body
    assert "editorial note" not in body


def test_xhtml_is_semantic_and_keeps_comments_out(sample):
    book = load_book(sample)
    ctx = context()
    renderer = XhtmlRenderer(ctx)
    html = "".join(renderer.section(s) for s in book.sections("en"))
    assert '<div class="callout callout-concept">' in html
    assert '<section class="exercise"><p class="exercise-label">Try it</p>' in html
    assert '<p class="prompt-name">First prompt</p>' in html
    assert 'class="notes"' in html
    assert "editorial note" not in html
    assert ctx.exercises == ["EX-01-01"]


def test_a_book_overrides_labels(sample):
    ctx = RenderContext("en", labels("en", {"exercise": "Your turn", "callouts": {"concept": "Idea"}}))
    assert ctx.label("exercise") == "Your turn"
    assert ctx.callout_label("concept") == "Idea"
    assert ctx.callout_label("warning") == "Watch out"
