"""The fidelity auditor: did the words change? (docs/origin, §5.19 and §7.1)

"Did anything change?" is a question for a machine, not a model. Everything
here is deterministic:

- ``digest`` -- exact bytes, for passages that must not change at all;
- ``reading_text`` -- the words a reader reads, out of the Markdown, so a
  change of markup is not mistaken for a change of text;
- ``facts`` -- the numbers, dates, URLs, code and proper names in a text: the
  inventory that catches a model silently "fixing" a date;
- ``compare`` -- the two side by side, after a *declared* list of
  normalisations. Every normalisation has an id and a reason, and a report
  says how many times each one applied. A list that has to grow for a text to
  pass is a warning sign, not a fix.
"""

from __future__ import annotations

import difflib
import hashlib
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from markdown_it.tree import SyntaxTreeNode

from .markdown import is_comment, parse


def digest(text: str | bytes) -> str:
    raw = text.encode("utf-8") if isinstance(text, str) else text
    return hashlib.sha256(raw).hexdigest()


@dataclass(frozen=True)
class Normalization:
    id: str
    reason: str
    pattern: str
    replacement: str = ""

    def apply(self, line: str) -> tuple[str, int]:
        return re.subn(self.pattern, self.replacement, line)


def reading_lines(markdown: str) -> list[str]:
    """One line per paragraph, heading or list item: the text a reader reads.

    Markup is gone; editorial comments are gone; nothing else is touched.
    """

    lines: list[str] = []

    def inline_text(node: SyntaxTreeNode) -> str:
        if node.type in ("text", "code_inline"):
            return node.content
        if node.type in ("softbreak", "hardbreak"):
            return " "
        if is_comment(node):
            return ""
        return "".join(inline_text(child) for child in node.children)

    def walk(node: SyntaxTreeNode) -> None:
        if is_comment(node):
            return
        if node.type == "inline":
            text = " ".join(inline_text(node).split())
            if text:
                lines.append(text)
            return
        if node.type in ("fence", "code_block"):
            lines.extend(line for line in node.content.splitlines() if line.strip())
            return
        if node.type == "container_exercise" and node.info.strip():
            lines.append(" ".join(node.info.split()))
        for child in node.children:
            walk(child)

    walk(parse(markdown))
    return lines


_FACTS = {
    "url": re.compile(r"https?://[^\s)>\]]+"),
    "number": re.compile(r"(?<![\w.,])\d+(?:[.,]\d+)*(?![\w])"),
    "code": re.compile(r"`[^`]+`"),
    # A capitalised word that does not open a sentence: a name, or a term the
    # text chose to capitalise. Both are things a reviser must not change.
    "name": re.compile(r"(?<=[^.!?:—\s]\s)[A-ZÀ-Ý][\wÀ-ÿ]+(?:\s[A-ZÀ-Ý][\wÀ-ÿ]+)*"),
}


def facts(text: str) -> Counter:
    inventory: Counter = Counter()
    for kind, pattern in _FACTS.items():
        for match in pattern.findall(text):
            inventory[(kind, match.rstrip(".,;:"))] += 1
    return inventory


@dataclass
class FidelityReport:
    identical_bytes: bool
    identical_words: bool
    normalizations: dict[str, int] = field(default_factory=dict)
    word_differences: list[dict[str, Any]] = field(default_factory=list)
    facts_added: list[tuple[str, str, int]] = field(default_factory=list)
    facts_removed: list[tuple[str, str, int]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.identical_words and not self.facts_added and not self.facts_removed

    def public_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "identical_bytes": self.identical_bytes,
            "identical_words": self.identical_words,
            "normalizations": self.normalizations,
            "word_differences": self.word_differences,
            "facts_added": [list(f) for f in self.facts_added],
            "facts_removed": [list(f) for f in self.facts_removed],
        }


def _normalize(lines: list[str], rules: list[Normalization], counts: Counter) -> list[str]:
    out = []
    for line in lines:
        for rule in rules:
            line, applied = rule.apply(line)
            counts[rule.id] += applied
        line = " ".join(line.split())
        if line:
            out.append(line)
    return out


def compare(before: str, after: str, *, before_rules: list[Normalization] = (),
            after_rules: list[Normalization] = (), context: int = 6) -> FidelityReport:
    """Compare two Markdown texts as a reader would read them."""

    counts: Counter = Counter()
    old = _normalize(reading_lines(before), list(before_rules), counts)
    new = _normalize(reading_lines(after), list(after_rules), counts)
    old_words = " ".join(old).split()
    new_words = " ".join(new).split()
    differences = []
    matcher = difflib.SequenceMatcher(a=old_words, b=new_words, autojunk=False)
    for tag, a0, a1, b0, b1 in matcher.get_opcodes():
        if tag == "equal":
            continue
        differences.append({
            "change": tag,
            "before": " ".join(old_words[max(0, a0 - context):a1 + context]),
            "after": " ".join(new_words[max(0, b0 - context):b1 + context]),
            "removed": " ".join(old_words[a0:a1]),
            "added": " ".join(new_words[b0:b1]),
        })
    old_facts, new_facts = facts("\n".join(old)), facts("\n".join(new))
    added = sorted((k, v, n) for (k, v), n in (new_facts - old_facts).items())
    removed = sorted((k, v, n) for (k, v), n in (old_facts - new_facts).items())
    return FidelityReport(
        identical_bytes=before == after,
        identical_words=not differences,
        normalizations={k: v for k, v in sorted(counts.items()) if v},
        word_differences=differences,
        facts_added=added,
        facts_removed=removed,
    )


# ------------------------------------------------------------------ editions

def pdf_pages(path) -> list[str]:
    """The text of each page, whitespace collapsed (needs the build extra)."""

    from pypdf import PdfReader

    return [" ".join((page.extract_text() or "").split()) for page in PdfReader(str(path)).pages]


def compare_pdfs(before, after, *, context: int = 4) -> dict[str, Any]:
    """Two editions page by page: which pages read the same, and what differs.

    Typesetting transforms text (ligatures, hyphenation, quotes), so this is
    equivalence of extracted text, not of bytes -- the layer at which
    "ipsis litteris" can honestly be asked of a PDF (docs/origin, §7.1).
    """

    old, new = pdf_pages(before), pdf_pages(after)
    pages = []
    for number, (a, b) in enumerate(zip(old, new), start=1):
        if a == b:
            continue
        a_words, b_words = a.split(), b.split()
        matcher = difflib.SequenceMatcher(a=a_words, b=b_words, autojunk=False)
        changes = [{"removed": " ".join(a_words[a0:a1]), "added": " ".join(b_words[b0:b1])}
                   for tag, a0, a1, b0, b1 in matcher.get_opcodes() if tag != "equal"]
        pages.append({"page": number, "changes": changes})
    # Across the whole book, too: a line that moves to the next page is a
    # page difference but not a text difference.
    whole = difflib.SequenceMatcher(a=" ".join(old).split(), b=" ".join(new).split(), autojunk=False)
    text_changes = [{"removed": " ".join(whole.a[a0:a1]), "added": " ".join(whole.b[b0:b1])}
                    for tag, a0, a1, b0, b1 in whole.get_opcodes() if tag != "equal"]
    return {
        "pages_before": len(old),
        "pages_after": len(new),
        "identical_pages": min(len(old), len(new)) - len(pages),
        "differing_pages": pages,
        "text_changes": text_changes,
    }
