"""The manuscript dialect: CommonMark plus three book constructs.

- Callouts, written as GitHub-style alerts: ``> [!concept] Title``.
- Exercises, written as containers: ``::: exercise Title`` ... ``:::``.
- Prompts, a callout kind whose title is the exercise id
  (``> [!prompt] EX-04-01``); ``---`` separates several prompts, and a line
  in bold alone labels the prompt that follows it.

HTML comments are editorial notes: they stay in the manuscript and never reach
an edition. See docs/book-format.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from markdown_it import MarkdownIt
from markdown_it.tree import SyntaxTreeNode
from mdit_py_plugins.container import container_plugin
from mdit_py_plugins.footnote import footnote_plugin

CALLOUT_KINDS = ("concept", "warning", "practice", "challenge", "framework", "note", "prompt")

_CALLOUT = re.compile(r"^\[!([a-z-]+)\]\s*(.*)$")


def _parser() -> MarkdownIt:
    md = MarkdownIt("commonmark", {"html": True}).enable("table")
    md.use(container_plugin, name="exercise")
    md.use(footnote_plugin)
    return md


_MD = _parser()


def parse(text: str) -> SyntaxTreeNode:
    return SyntaxTreeNode(_MD.parse(text))


@dataclass
class Callout:
    kind: str
    title: str
    #: Inline nodes that followed the title line in the same paragraph.
    lead: list[SyntaxTreeNode]
    #: Block nodes after the first paragraph.
    blocks: list[SyntaxTreeNode]


def callout(node: SyntaxTreeNode) -> Callout | None:
    """The callout a blockquote declares, or None for a plain quotation."""

    if node.type != "blockquote" or not node.children:
        return None
    first = node.children[0]
    if first.type != "paragraph" or not first.children:
        return None
    inline = first.children[0].children
    if not inline or inline[0].type != "text":
        return None
    match = _CALLOUT.match(inline[0].content)
    if not match:
        return None
    rest = inline[1:]
    title_parts = [match.group(2)]
    while rest and rest[0].type not in ("softbreak", "hardbreak"):
        title_parts.append(plain_text(rest[0]))
        rest = rest[1:]
    lead = rest[1:] if rest else []
    return Callout(match.group(1), "".join(title_parts).strip(), lead, list(node.children[1:]))


def exercise_title(node: SyntaxTreeNode) -> str:
    return node.info.strip().removeprefix("exercise").strip()


def plain_text(node: SyntaxTreeNode) -> str:
    if node.type in ("text", "code_inline"):
        return node.content
    if node.type in ("softbreak", "hardbreak"):
        return " "
    return "".join(plain_text(child) for child in node.children)


def is_comment(node: SyntaxTreeNode) -> bool:
    return node.type in ("html_block", "html_inline") and node.content.strip().startswith("<!--")


@dataclass
class Prompt:
    label: str
    text: str


def prompts(callout_: Callout) -> list[Prompt]:
    """The prompts inside a prompt callout, split on ``---``."""

    chunks: list[list[SyntaxTreeNode]] = [[]]
    for block in callout_.blocks:
        if block.type == "hr":
            chunks.append([])
        else:
            chunks[-1].append(block)
    found: list[Prompt] = []
    for chunk in chunks:
        paragraphs = [b for b in chunk if b.type == "paragraph"]
        if not paragraphs:
            continue
        label = ""
        head = paragraphs[0].children[0].children
        lines = _lines(head)
        if lines and len(lines[0]) == 1 and lines[0][0].type == "strong":
            label = plain_text(lines[0][0])
            lines = lines[1:]
        text = " ".join(" ".join(plain_text(n) for n in line).strip() for line in lines).strip()
        rest = " ".join(plain_text(p) for p in paragraphs[1:]).strip()
        found.append(Prompt(label, " ".join(t for t in (text, rest) if t)))
    return found


def _lines(inline: list[SyntaxTreeNode]) -> list[list[SyntaxTreeNode]]:
    lines: list[list[SyntaxTreeNode]] = [[]]
    for node in inline:
        if node.type in ("softbreak", "hardbreak"):
            lines.append([])
        elif not (node.type == "text" and not node.content.strip()):
            lines[-1].append(node)
    return [line for line in lines if line]
