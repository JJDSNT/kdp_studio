"""Manuscript -> XHTML for EPUB 3, with semantic class names.

The class names are the ebook template contract (docs/templates.md); a
template is a stylesheet over them. Readers vary wildly, so the markup stays
plain: no layout depends on a background colour, and every distinction also
has a text label (docs/origin, §10).
"""

from __future__ import annotations

import html

from markdown_it.tree import SyntaxTreeNode

from ..book import Part, Section
from ..errors import BookFormatError
from ..markdown import callout, exercise_title, is_comment, parse, prompts
from . import RenderContext, roman


def x(text: str) -> str:
    return html.escape(text, quote=True)


class XhtmlRenderer:
    def __init__(self, context: RenderContext) -> None:
        self.context = context
        self._footnotes: dict[int, SyntaxTreeNode] = {}
        self._used: list[int] = []
        self._in_exercise = False
        # Inside a callout each source line stands on its own line.
        self._in_callout = False

    def part_page(self, part: Part) -> str:
        if part.kind == "part":
            label = f"{self.context.label('part')} {roman(part.number)}"
        else:
            label = self.context.label(part.kind)
        return (f'<section class="part-opening part-{part.kind}">'
                f'<p class="part-label">{x(label)}</p>'
                f'<hr class="part-rule" />'
                f'<h1 class="part-title">{x(part.title)}</h1></section>')

    def part_label(self, part: Part) -> str:
        if part.kind == "part":
            return f"{self.context.label('part')} {roman(part.number)} — {part.title}"
        return f"{self.context.label(part.kind)} — {part.title}"

    def section_label(self, section: Section) -> str:
        if section.kind == "chapter":
            return f"{self.context.label('chapter')} {section.number} — {section.toc_title}"
        return section.toc_title

    def section(self, section: Section) -> str:
        if section.kind == "chapter":
            label = f"{self.context.label('chapter')} {section.number}"
            head = (f'<p class="chapter-label">{x(label)}</p>'
                    f'<h1 class="chapter-title">{x(section.title)}</h1>')
        else:
            head = (f'<p class="front-label">{x(section.toc_title)}</p>'
                    f'<h1 class="chapter-title">{x(section.title)}</h1>')
        try:
            body = self.document(section.body)
        except BookFormatError as error:
            raise BookFormatError(f"{section.path.name}: {error.message}", **error.details) from error
        return f'<section class="{section.kind}">{head}<hr class="chapter-rule" />\n{body}</section>'

    def document(self, text: str) -> str:
        tree = parse(text)
        self._footnotes = {n.meta["id"]: n for n in tree.walk() if n.type == "footnote"}
        self._used = []
        body = self.blocks(tree.children)
        if self._used:
            notes = "".join(
                f'<li id="note-{n}">{self.blocks(self._footnotes[n].children)}'
                f' <a href="#ref-{n}">↩</a></li>' for n in self._used)
            body += (f'\n<section class="notes"><h2>{x(self.context.label("notes"))}</h2>'
                     f'<ol>{notes}</ol></section>')
        return body

    # -------------------------------------------------------------- blocks

    def blocks(self, nodes: list[SyntaxTreeNode]) -> str:
        return "\n".join(part for part in (self.block(n) for n in nodes) if part)

    def block(self, node: SyntaxTreeNode) -> str:
        kind = node.type
        if is_comment(node) or kind == "footnote_block":
            return ""
        if kind == "paragraph":
            return f"<p>{self.inline(node.children[0].children)}</p>"
        if kind == "heading":
            level = int(node.tag[1])
            text = self.inline(node.children[0].children)
            if self._in_exercise and level >= 4:
                return f'<p class="sublabel">{text}</p>'
            level = min(max(level, 2), 4)
            return f"<h{level}>{text}</h{level}>"
        if kind in ("bullet_list", "ordered_list"):
            tag = "ul" if kind == "bullet_list" else "ol"
            items = "".join(f"<li>{self.list_item(item)}</li>" for item in node.children)
            return f"<{tag}>{items}</{tag}>"
        if kind == "blockquote":
            return self.blockquote(node)
        if kind == "container_exercise":
            return self.exercise(node)
        if kind in ("fence", "code_block"):
            return f"<pre><code>{x(node.content.rstrip())}</code></pre>"
        if kind == "hr":
            return '<hr class="break" />'
        if kind == "table":
            return self.table(node)
        if kind == "html_block":
            raise BookFormatError("HTML is not part of the manuscript format", html=node.content.strip()[:80])
        raise BookFormatError(f"Unsupported block {kind!r}")

    def list_item(self, item: SyntaxTreeNode) -> str:
        # Tight list items hold a single paragraph; render it without <p>.
        if len(item.children) == 1 and item.children[0].type == "paragraph":
            return self.inline(item.children[0].children[0].children)
        return self.blocks(item.children)

    def blockquote(self, node: SyntaxTreeNode) -> str:
        found = callout(node)
        if found is None:
            return f"<blockquote>{self.blocks(node.children)}</blockquote>"
        if found.kind == "prompt":
            return self.prompt(found)
        if found.kind == "framework":
            head = f'<p class="callout-head"><span class="callout-label">{x(found.title)}</span></p>'
        else:
            head = (f'<p class="callout-head"><span class="callout-label">'
                    f'{x(self.context.callout_label(found.kind))}</span>'
                    + (f' <span class="callout-title">{x(found.title)}</span>' if found.title else "")
                    + "</p>")
        self._in_callout = True
        try:
            lead = f"<p>{self.inline(found.lead)}</p>" if found.lead else ""
            body = self.blocks(found.blocks)
        finally:
            self._in_callout = False
        return f'<div class="callout callout-{found.kind}">{head}{lead}{body}</div>'

    def prompt(self, found) -> str:
        exercise_id = found.title.strip()
        if not exercise_id:
            raise BookFormatError("A prompt callout needs the exercise id as its title")
        self.context.exercises.append(exercise_id)
        url = self.context.prompt_url(exercise_id)
        parts = ['<div class="prompt">',
                 f'<p class="prompt-head"><span class="prompt-label">'
                 f'{x(self.context.callout_label("prompt"))}</span> {x(exercise_id)}</p>']
        if url:
            qr = self.context.qr_path(exercise_id, url)
            shown = url.split("://", 1)[-1]
            parts.append('<div class="prompt-link">'
                         + (f'<img class="qr" src="{x(qr)}" alt="QR {x(exercise_id)}" />' if qr else "")
                         + f'<p class="prompt-url"><a href="{x(url)}"><code>{x(shown)}</code></a><br />'
                         f'<span class="prompt-hint">{x(self.context.label("prompt_hint"))}</span></p></div>')
        for item in prompts(found):
            if item.label:
                parts.append(f'<p class="prompt-name">{x(item.label)}</p>')
            parts.append(f'<p class="prompt-text">{x(item.text)}</p>')
        parts.append("</div>")
        return "\n".join(parts)

    def exercise(self, node: SyntaxTreeNode) -> str:
        self._in_exercise = True
        try:
            body = self.blocks(node.children)
        finally:
            self._in_exercise = False
        return (f'<section class="exercise"><p class="exercise-label">{x(self.context.label("exercise"))}</p>'
                f'<h2 class="exercise-title">{x(exercise_title(node))}</h2>\n{body}</section>')

    def table(self, node: SyntaxTreeNode) -> str:
        rows = []
        for group in node.children:
            cell_tag = "th" if group.type == "thead" else "td"
            for row in group.children:
                cells = "".join(
                    f"<{cell_tag}>{self.inline(cell.children[0].children) if cell.children else ''}</{cell_tag}>"
                    for cell in row.children)
                rows.append(f"<tr>{cells}</tr>")
        return f"<table>{''.join(rows)}</table>"

    # -------------------------------------------------------------- inline

    def inline(self, nodes: list[SyntaxTreeNode]) -> str:
        return "".join(self.span(n) for n in nodes)

    def span(self, node: SyntaxTreeNode) -> str:
        kind = node.type
        if kind == "text":
            return x(node.content)
        if kind == "strong":
            return f"<strong>{self.inline(node.children)}</strong>"
        if kind == "em":
            return f"<em>{self.inline(node.children)}</em>"
        if kind == "code_inline":
            return f"<code>{x(node.content)}</code>"
        if kind == "softbreak":
            return "<br />\n" if self._in_callout else "\n"
        if kind == "hardbreak":
            return "<br />"
        if kind == "link":
            return f'<a href="{x(str(node.attrs.get("href", "")))}">{self.inline(node.children)}</a>'
        if kind == "image":
            alt = "".join(c.content for c in node.children if c.type == "text")
            return f'<img src="{x(str(node.attrs.get("src", "")))}" alt="{x(alt)}" />'
        if kind == "footnote_ref":
            note = node.meta["id"]
            if note not in self._used:
                self._used.append(note)
            number = self._used.index(note) + 1
            return f'<sup><a href="#note-{note}" id="ref-{note}">{number}</a></sup>'
        if kind == "footnote_anchor" or is_comment(node):
            return ""
        if kind == "html_inline":
            raise BookFormatError("HTML is not part of the manuscript format", html=node.content[:80])
        raise BookFormatError(f"Unsupported inline {kind!r}")
