"""Manuscript -> LaTeX body, in the template contract's macros.

The contract (docs/templates.md) is the only thing a print template must
implement: ``\\kdppart``, ``\\kdpunnumberedpart``, ``\\kdpchapter``,
``\\kdpfrontsection``, the ``kdpcallout`` and ``kdpexercise`` environments,
``\\kdpsublabel`` and ``\\kdpprompt``.
"""

from __future__ import annotations


from markdown_it.tree import SyntaxTreeNode

from ..book import Part, Section
from ..errors import BookFormatError
from ..markdown import callout, exercise_title, is_comment, parse, prompts
from . import RenderContext, roman

_ESCAPES = {"&": r"\&", "%": r"\%", "$": r"\$", "#": r"\#", "_": r"\_",
            "{": r"\{", "}": r"\}", "~": r"\textasciitilde{}", "^": r"\textasciicircum{}"}


def escape(text: str) -> str:
    out = text.replace("\\", r"\textbackslash{}")
    for char, replacement in _ESCAPES.items():
        out = out.replace(char, replacement)
    return out


def typeset(text: str) -> str:
    """Escape, then the typographic conventions of running text."""

    out = escape(text)
    out = out.replace(" — ", "~— ").replace("...", r"\dots{}")
    return out


class LatexRenderer:
    def __init__(self, context: RenderContext) -> None:
        self.context = context
        self._footnotes: dict[int, SyntaxTreeNode] = {}
        self._in_exercise = False
        # Inside a callout each source line is its own paragraph: a framework
        # sets a question on one line and its answer on the next.
        self._in_callout = False

    # ---------------------------------------------------------------- book

    def entry(self, entry: Part | Section) -> str:
        if isinstance(entry, Part):
            if entry.kind == "part":
                label = f"{self.context.label('part')} {roman(entry.number)}"
                head = rf"\kdppart{{{escape(label)}}}{{{typeset(entry.title)}}}"
            else:
                label = self.context.label(entry.kind)
                head = rf"\kdpunnumberedpart{{{escape(label)}}}{{{typeset(entry.title)}}}"
            return "\n\n".join([head, *(self.section(s) for s in entry.sections)])
        return self.section(entry)

    def section(self, section: Section) -> str:
        if section.kind == "chapter":
            label = f"{self.context.label('chapter')} {section.number}"
            head = rf"\kdpchapter{{{escape(label)}}}{{{typeset(section.title)}}}{{{typeset(section.toc_title)}}}"
        else:
            head = rf"\kdpfrontsection{{{typeset(section.toc_title)}}}{{{typeset(section.title)}}}"
        try:
            return head + "\n\n" + self.document(section.body)
        except BookFormatError as error:
            raise BookFormatError(f"{section.path.name}: {error.message}", **error.details) from error

    def document(self, text: str) -> str:
        tree = parse(text)
        self._footnotes = {}
        for node in tree.walk():
            if node.type == "footnote":
                self._footnotes[node.meta["id"]] = node
        return self.blocks(tree.children)

    # -------------------------------------------------------------- blocks

    def blocks(self, nodes: list[SyntaxTreeNode]) -> str:
        return "\n\n".join(part for part in (self.block(n) for n in nodes) if part)

    def block(self, node: SyntaxTreeNode) -> str:
        kind = node.type
        if is_comment(node) or kind == "footnote_block":
            return ""
        if kind == "paragraph":
            return self.inline(node.children[0].children)
        if kind == "heading":
            return self.heading(node)
        if kind == "bullet_list":
            return self.list(node, "itemize")
        if kind == "ordered_list":
            return self.list(node, "enumerate")
        if kind == "blockquote":
            return self.blockquote(node)
        if kind == "container_exercise":
            return self.exercise(node)
        if kind in ("fence", "code_block"):
            return "\\begin{verbatim}\n" + node.content.rstrip("\n") + "\n\\end{verbatim}"
        if kind == "hr":
            return r"\kdpbreak"
        if kind == "table":
            return self.table(node)
        if kind == "html_block":
            raise BookFormatError("HTML is not part of the manuscript format", html=node.content.strip()[:80])
        raise BookFormatError(f"Unsupported block {kind!r}")

    def heading(self, node: SyntaxTreeNode) -> str:
        text = self.inline(node.children[0].children)
        level = int(node.tag[1])
        if self._in_exercise and level >= 4:
            return rf"\kdpsublabel{{{text}}}"
        command = {1: "section", 2: "section", 3: "subsection"}.get(level, "subsubsection")
        return rf"\{command}{{{text}}}"

    def list(self, node: SyntaxTreeNode, environment: str) -> str:
        items = []
        for item in node.children:
            items.append(r"\item " + self.blocks(item.children))
        return f"\\begin{{{environment}}}\n" + "\n".join(items) + f"\n\\end{{{environment}}}"

    def blockquote(self, node: SyntaxTreeNode) -> str:
        found = callout(node)
        if found is None:
            return "\\begin{quote}\n" + self.blocks(node.children) + "\n\\end{quote}"
        if found.kind == "prompt":
            return self.prompt(found)
        body = []
        self._in_callout = True
        try:
            if found.lead:
                body.append(self.inline(found.lead))
            body.append(self.blocks(found.blocks))
        finally:
            self._in_callout = False
        label = found.title if found.kind == "framework" else self.context.callout_label(found.kind)
        title = "" if found.kind == "framework" else found.title
        return (
            rf"\begin{{kdpcallout}}{{{found.kind}}}{{{escape(label)}}}{{{typeset(title)}}}" + "\n"
            + "\n\n".join(b for b in body if b) + "\n\\end{kdpcallout}"
        )

    def prompt(self, found) -> str:
        exercise_id = found.title.strip()
        if not exercise_id:
            raise BookFormatError("A prompt callout needs the exercise id as its title")
        self.context.exercises.append(exercise_id)
        url = self.context.prompt_url(exercise_id)
        qr = self.context.qr_path(exercise_id, url) if url else ""
        shown = url.split("://", 1)[-1]
        parts = []
        for item in prompts(found):
            parts.append(rf"\kdppromptlabel{{{escape(item.label)}}}" if item.label else r"\kdppromptsep")
            parts.append(rf"\kdpprompttext{{{escape(item.text)}}}")
        return (
            rf"\kdpprompt{{{escape(self.context.callout_label('prompt'))}}}{{{escape(exercise_id)}}}"
            rf"{{{escape(shown)}}}{{{qr}}}{{" + "\n".join(parts) + "}"
        )

    def exercise(self, node: SyntaxTreeNode) -> str:
        self._in_exercise = True
        try:
            body = self.blocks(node.children)
        finally:
            self._in_exercise = False
        label = escape(self.context.label("exercise"))
        return (rf"\begin{{kdpexercise}}{{{label}}}{{{typeset(exercise_title(node))}}}" + "\n"
                + body + "\n\\end{kdpexercise}")

    def table(self, node: SyntaxTreeNode) -> str:
        rows = []
        for group in node.children:
            for row in group.children:
                cells = [self.inline(cell.children[0].children) if cell.children else "" for cell in row.children]
                rows.append(" & ".join(cells) + r" \\")
                if group.type == "thead":
                    rows.append(r"\hline")
        columns = len(node.children[0].children[0].children) if node.children else 1
        return ("\\begin{kdptable}{" + "l" * columns + "}\n" + "\n".join(rows) + "\n\\end{kdptable}")

    # -------------------------------------------------------------- inline

    def inline(self, nodes: list[SyntaxTreeNode]) -> str:
        return "".join(self.span(n) for n in nodes)

    def span(self, node: SyntaxTreeNode) -> str:
        kind = node.type
        if kind == "text":
            return typeset(node.content)
        if kind == "strong":
            return rf"\textbf{{{self.inline(node.children)}}}"
        if kind == "em":
            return rf"\emph{{{self.inline(node.children)}}}"
        if kind == "code_inline":
            return rf"\texttt{{{escape(node.content)}}}"
        if kind == "softbreak":
            return "\n\n" if self._in_callout else "\n"
        if kind == "hardbreak":
            return r"\\" + "\n"
        if kind == "link":
            return self.inline(node.children)
        if kind == "image":
            return rf"\kdpimage{{{escape(str(node.attrs.get('src', '')))}}}"
        if kind == "footnote_ref":
            note = self._footnotes.get(node.meta["id"])
            text = self.blocks([c for c in note.children]) if note else ""
            return rf"\footnote{{{text.strip()}}}"
        if kind == "footnote_anchor" or is_comment(node):
            return ""
        if kind == "html_inline":
            raise BookFormatError("HTML is not part of the manuscript format", html=node.content[:80])
        raise BookFormatError(f"Unsupported inline {kind!r}")
