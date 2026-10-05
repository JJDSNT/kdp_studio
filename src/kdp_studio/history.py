"""The book's history: one git commit per committed decision or edit.

When the book is a git repository, every write KDP Studio makes is committed
with the paths it touched -- and only those, so the author's own uncommitted
work is never swept into a commit -- with the reason and the actor in the
message. `git log` then answers "who changed this chapter, when and why".
"""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .state import Actor


def is_repository(root: Path) -> bool:
    return (root / ".git").exists()


def commit(root: Path, paths: list[Path], message: str, actor: Actor) -> str:
    """Commit exactly these paths; return the commit id, or "" outside git."""

    if not is_repository(root):
        return ""
    relative = [str(p.relative_to(root)) for p in paths]
    subprocess.run(["git", "add", "--", *relative], cwd=root, capture_output=True)
    run = subprocess.run(["git", "commit", "-q", "-m", f"{message}\n\nActor: {actor.id} ({actor.kind})",
                          "--", *relative], cwd=root, capture_output=True, text=True)
    if run.returncode != 0:
        return ""
    head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True, text=True)
    return head.stdout.strip()


def log(root: Path, path: Path, limit: int = 30) -> list[dict[str, Any]]:
    """The commits that touched one file, newest first."""

    if not is_repository(root):
        return []
    run = subprocess.run(["git", "log", f"-{limit}", "--format=%h%x1f%aI%x1f%s%x1f%b%x1e", "--",
                          str(path.relative_to(root))], cwd=root, capture_output=True, text=True)
    entries = []
    for record in run.stdout.split("\x1e"):
        fields = record.strip().split("\x1f")
        if len(fields) >= 3:
            body = fields[3] if len(fields) > 3 else ""
            actor = next((line.removeprefix("Actor: ") for line in body.splitlines() if line.startswith("Actor: ")), "")
            entries.append({"commit": fields[0], "at": fields[1], "message": fields[2], "actor": actor})
    return entries
