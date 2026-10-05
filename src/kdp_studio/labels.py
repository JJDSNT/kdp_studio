"""The labels an edition prints, per language, with the book's overrides."""

from __future__ import annotations

from importlib import resources
from typing import Any

import yaml

from .errors import NotFoundError


def available() -> list[str]:
    return sorted(p.name.removesuffix(".yaml") for p in resources.files(__package__).joinpath("locales").iterdir()
                  if p.name.endswith(".yaml"))


def labels(language: str, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
    base_language = language if language in available() else language.split("-")[0]
    if base_language not in available():
        raise NotFoundError(f"No labels for language {language!r}", available=available())
    path = resources.files(__package__).joinpath("locales", f"{base_language}.yaml")
    merged: dict[str, Any] = yaml.safe_load(path.read_text("utf-8"))
    for key, value in (overrides or {}).items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = {**merged[key], **value}
        else:
            merged[key] = value
    return merged
