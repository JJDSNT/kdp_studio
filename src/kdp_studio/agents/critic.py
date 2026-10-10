"""The critic: someone who looks at the pages and says what they are worth.

The designer never sees what it draws; code can say a theme builds and has no
overfull box, not whether it is any good. The critic is shown the pages
themselves -- the cover, a part opening, a chapter opening, callouts, an
exercise, in colour and in black ink -- and judges them as a book designer
and as a reader would: whether the page has a point of view, whether its
decisions hold from the cover to an exercise, where the eye stumbles.

It is a critic, not a checker. It separates a *defect* (wrong whoever looks:
a label stranded at the foot of a page, text too faint to read in black ink)
from a *weakness* (a decision that does not earn its place) and from *taste*
(defensible, and not its own choice) -- and it does not praise by default.
Its criticism is advice: it never changes a theme, and taking a theme stays
the author's decision. Each criticism is kept
(`$XDG_DATA_HOME/kdp-studio/critiques/`) and shown in the gallery.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .. import gallery
from ..book import Book
from ..errors import NotFoundError
from ..jobs import Progress, kind
from ..model import Model, model_from_env
from ..state import Actor, now

AGENT = Actor("critic", "agent")
SEVERITIES = ("defect", "weakness", "taste")
SHOWN = (("part", "a part opening"), ("chapter", "a chapter opening"), ("callouts", "a page with callouts"),
         ("exercise", "an exercise with its prompt"))

SYSTEM = (
    "You are a critic of book design, exacting and well read in the history of the printed page. You are shown "
    "the pages of a THEME applied to a specimen text in Latin: judge the design, never the words. Look as a "
    "designer and as a reader holding the book.\n"
    "Judge its character first: does this page have a point of view, or is it a competent default? Is it one "
    "idea carried through — the cover, a part opening, a chapter opening, a callout, an exercise — or several "
    "ideas that met by accident? Does the cover belong to the interior? Name what it borrows and from where; "
    "borrowing well is craft, a recolour of another theme is not a theme.\n"
    "Then the craft: hierarchy (can the eye tell at once what is a label, a title, text), proportion and white "
    "space, the rhythm of a spread, the colour of the text block, alignment that is kept or broken without "
    "reason, weights that fight, accents spent too often to mean anything, things stranded (a label alone at "
    "the foot of a page, one line of a paragraph alone), collisions, and what survives in black ink: an accent "
    "that turns to a grey too pale to read is a defect of the theme, not of the printer.\n"
    "Be specific: say on which picture and where. Give each problem a severity — `defect`: wrong whoever looks; "
    "`weakness`: a decision that does not earn its place; `taste`: defensible, and you would have chosen "
    "otherwise — and a `fix` the designer can act on (the face, the size, the alignment, the rule, the colour by "
    "its role). Do not praise by default: a strength is something a designer would keep on purpose. If the "
    "brief is given, say plainly whether the theme answers it. `verdict` is `accept` only when no defect "
    "remains and the theme has a character of its own; otherwise `revise`. Write `overall` as a critic writes: "
    "a paragraph with a judgement in it, in the author's language."
)

SCHEMA = {
    "type": "object",
    "properties": {
        "overall": {"type": "string"},
        "character": {"type": "string"},
        "answers_the_brief": {"type": "string"},
        "strengths": {"type": "array", "items": {"type": "string"}},
        "problems": {"type": "array", "items": {"type": "object", "properties": {
            "where": {"type": "string"}, "what": {"type": "string"}, "why": {"type": "string"},
            "severity": {"type": "string", "enum": list(SEVERITIES)}, "fix": {"type": "string"}},
            "required": ["where", "what", "why", "severity", "fix"]}},
        "verdict": {"type": "string", "enum": ["accept", "revise"]},
    },
    "required": ["overall", "character", "answers_the_brief", "strengths", "problems", "verdict"],
}


def _store(theme: str) -> Path:
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "kdp-studio" / "critiques" / f"{theme}.json"


def critiques(theme: str) -> list[dict[str, Any]]:
    """Every criticism this theme received, oldest first."""

    path = _store(theme)
    if not path.is_file():
        return []
    try:
        found = json.loads(path.read_text("utf-8"))
    except ValueError:
        return []
    return found if isinstance(found, list) else []


def latest(theme: str) -> dict[str, Any] | None:
    found = critiques(theme)
    return found[-1] if found else None


def pictures(theme: str, language: str, book_root: Path | None = None) -> list[tuple[str, Path]]:
    """What the critic is shown: the colour render's key pages and cover, then the same pages in black ink."""

    shown: list[tuple[str, Path]] = []
    for ink, label in (("color", ""), ("black", " in black ink")):
        render = gallery.built(theme, language, book_root, ink) or gallery.build(theme, language, book_root, ink)
        folder = gallery.cache_dir() / render["key"]
        if ink == "color" and render["cover"]:
            shown.append(("the cover", folder / render["cover"]))
        for role, what in SHOWN:
            page = next((p for p in render["pages"] if p["role"] == role), None)
            # In black ink the chapter and the exercise say the most: where the accents were.
            if page and (ink == "color" or role in ("chapter", "exercise")):
                shown.append((what + label, folder / page["file"]))
    if not shown:
        raise NotFoundError(f"Theme {theme!r} has nothing to look at")
    return shown


def critique(book: Book, theme: str, *, language: str = "", brief: str = "", model: Model | None = None,
             progress=lambda message: None) -> dict[str, Any]:
    language = language or book.source_language
    found = {t["name"]: t for t in gallery.themes(book.root)}
    if theme not in found:
        raise NotFoundError(f"No theme named {theme!r}", available=sorted(found))
    brief = brief or str(found[theme].get("brief", ""))
    progress(f"Rendering {theme} to look at it")
    shown = pictures(theme, language, book.root)
    others = "\n".join(f"- {name}: {t['kinds'].get('print', {}).get('description', '')}"
                       for name, t in found.items() if name != theme)
    description = found[theme]["kinds"].get("print", {}).get("description", "")
    prompt = (f"The theme: {found[theme]['title']} ({theme}).\nWhat its designer says of it: {description or '—'}\n"
              f"The brief it was drawn from: {brief or '(none: a theme of the catalogue)'}\n"
              + (f"It was drawn over the theme {found[theme]['based_on']}: say whether it left it behind.\n"
                 if found[theme].get("based_on") else "")
              + f"\nThe other themes of the catalogue:\n{others or '(none)'}\n\n"
              "The pictures, in order:\n" + "\n".join(f"{i}. {what}" for i, (what, _) in enumerate(shown, start=1))
              + f"\n\nThe author reads {language}: write in that language.")
    progress(f"Looking at {len(shown)} pages")
    answer = (model or model_from_env()).ask(SYSTEM, prompt, SCHEMA, images=tuple(path for _, path in shown))
    record = {"theme": theme, "at": now(), "language": language, "shown": [what for what, _ in shown], **answer}
    record["defects"] = sum(1 for p in answer.get("problems") or [] if p.get("severity") == "defect")
    path = _store(theme)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps([*critiques(theme), record], ensure_ascii=False, indent=2), encoding="utf-8")
    progress(f"{answer['verdict']}: {record['defects']} defect(s), {len(answer.get('problems') or [])} problem(s)")
    return {**record, "summary": f"{theme}: {answer['verdict']} — " + str(answer["overall"])[:240]}


def as_instruction(record: dict[str, Any]) -> str:
    """A criticism as the designer reads it: what to change, most serious first."""

    order = {severity: index for index, severity in enumerate(SEVERITIES)}
    problems = sorted(record.get("problems") or [], key=lambda p: order.get(p.get("severity"), 9))
    lines = [f"A critic looked at the rendered pages. Its judgement: {record.get('overall', '')}",
             f"On character: {record.get('character', '')}", "What to change:"]
    lines += [f"- [{p['severity']}] {p['where']}: {p['what']} ({p['why']}) Fix: {p['fix']}" for p in problems]
    if record.get("strengths"):
        lines.append("Keep: " + "; ".join(record["strengths"]))
    return "\n".join(lines)


@kind("critique_theme", "Critic: look at a theme's rendered pages and judge them, as a book designer and a reader")
def critique_theme_job(book: Book, payload: dict[str, Any], actor: Actor, progress: Progress) -> dict[str, Any]:
    return critique(book, payload["theme"], language=payload.get("language", ""), progress=progress)
