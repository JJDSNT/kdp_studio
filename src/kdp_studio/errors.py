from __future__ import annotations

from typing import Any


class KdpStudioError(Exception):
    """Base class for domain errors crossing an interface boundary.

    Every interface (CLI, HTTP, agent tool) reports the same ``code`` for the
    same failure, so callers can react without parsing messages.
    """

    code = "error"

    def __init__(self, message: str, **details: Any) -> None:
        super().__init__(message)
        self.message = message
        self.details = details

    def public_dict(self) -> dict[str, Any]:
        return {"error": {"code": self.code, "message": self.message, **self.details}}


class BookFormatError(KdpStudioError):
    """The book on disk does not follow the book format."""

    code = "book_format"


class ValidationError(KdpStudioError):
    """The requested intent is malformed or violates a domain rule."""

    code = "validation_failed"


class NotFoundError(KdpStudioError):
    """A referenced book, section, template or gate does not exist."""

    code = "not_found"


class RevisionConflictError(KdpStudioError):
    """Someone committed a newer revision than the caller expected."""

    code = "revision_conflict"

    def __init__(self, expected: int, actual: int) -> None:
        super().__init__(
            f"Expected revision {expected} but the book is at revision {actual}",
            expected_revision=expected,
            actual_revision=actual,
        )


class ToolUnavailableError(KdpStudioError):
    """A system tool or optional extra needed for this operation is missing."""

    code = "tool_unavailable"


class BuildError(KdpStudioError):
    """An edition failed to build."""

    code = "build_failed"
