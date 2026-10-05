"""Checks: measured verdicts, never opinions.

Every check reports what it measured, what is required, and a verdict. A
check that could not run says ``not_checked`` and why; it never reports a pass
it did not measure.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

PASS, FAIL, WARN, NOT_CHECKED, INFO = "pass", "fail", "warn", "not_checked", "info"


@dataclass(frozen=True)
class Finding:
    id: str
    item: str
    verdict: str
    measured: str = ""
    required: str = ""
    detail: str = ""

    def public_dict(self) -> dict[str, Any]:
        return {"id": self.id, "item": self.item, "verdict": self.verdict, "measured": self.measured,
                "required": self.required, "detail": self.detail}


def summary(findings: list[Finding]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for finding in findings:
        counts[finding.verdict] = counts.get(finding.verdict, 0) + 1
    return counts
