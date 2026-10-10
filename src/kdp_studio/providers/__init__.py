"""Art providers: the services that make or repaint a picture, behind one narrow interface.

Generating a picture is slow, paid and done on someone else's machine, so a
provider is an adapter (as the model is, model.py): KDP Studio plans the
request -- prompt, size, seed, an estimate of the cost -- shows it, and only
then sends it. What comes back enters the book as art with its record
(art.py). Pattern and wire formats measured in Cine Toaster's providers.

Credentials and endpoint ids are read from the environment, or from
`$XDG_CONFIG_HOME/kdp-studio/providers.env`; never from a book, which is a
repository someone may publish, and never printed.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from ..errors import KdpStudioError


class ProviderError(KdpStudioError):
    """A provider failed, or refused the request."""

    code = "provider_failed"


class ProviderNotConfigured(ProviderError):
    """A credential or an endpoint is missing for this provider."""

    code = "provider_not_configured"


def config_file() -> Path:
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / "kdp-studio" / "providers.env"


def load_settings() -> None:
    """Read providers.env into the environment, without ever returning or logging a value."""

    path = config_file()
    if not path.is_file():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def setting(name: str) -> str:
    load_settings()
    return os.environ.get(name, "").strip()


@dataclass(frozen=True)
class ArtRequest:
    """Everything that will be sent, known before anything is."""

    prompt: str
    negative: str
    width: int
    height: int
    seed: int
    #: The picture to repaint, for a provider that edits.
    source: Path | None = None


@dataclass(frozen=True)
class ArtResult:
    path: Path
    provider: str
    model: str
    seed: int
    seconds: float = 0.0
    cost_usd: float = 0.0
    #: The provider's own account of the job, kept without interpreting it.
    provenance: dict[str, Any] = field(default_factory=dict)


class ArtProvider(Protocol):
    id: str
    model: str
    #: "generate" from words alone, or "edit" a picture the book already has.
    mode: str
    #: The longest side it is asked for, in pixels.
    max_side: int

    def missing(self) -> list[str]:
        """The settings it still needs, by name; empty when it can run."""
        ...

    def estimate_usd(self) -> float: ...

    def run(self, request: ArtRequest, output: Path, state_file: Path) -> ArtResult: ...


def providers() -> dict[str, ArtProvider]:
    from .comfyui import ComfyUi
    from .qwen_edit import QwenEdit

    found: list[ArtProvider] = [ComfyUi(), QwenEdit()]
    return {provider.id: provider for provider in found}


def get(name: str) -> ArtProvider:
    found = providers()
    if name not in found:
        raise ProviderError(f"No art provider named {name!r}", available=sorted(found))
    return found[name]
