"""Outbound redaction / DLP.

This is the ONLY mitigation for in-context exfiltration (the capability fence
stops cross-namespace reads, but cannot stop an agent from emitting data it
legitimately retrieved). It is best-effort — market it as such, not as a hard
guarantee. Rules are intentionally simple/regex-based for the MVP; a deployer
ports their own (e.g. salary / equity / cap-table patterns).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

DEFAULT_PATTERNS: list[str] = [
    r"\bsk-[A-Za-z0-9_\-]{16,}\b",  # API keys
    r"\bxox[baprs]-[A-Za-z0-9\-]{10,}\b",  # Slack tokens
    r"\b\d{3}-\d{2}-\d{4}\b",  # US SSN-shaped
    r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b",  # emails (example; tune per deploy)
]


@dataclass(slots=True)
class Redactor:
    enabled: bool = True
    patterns: list[str] = field(default_factory=lambda: list(DEFAULT_PATTERNS))
    placeholder: str = "[redacted]"
    _compiled: list = field(default_factory=list, init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        self._compiled = [re.compile(p) for p in self.patterns]

    def redact(self, text: str) -> tuple[str, int]:
        """Return (clean_text, num_redactions)."""
        if not self.enabled or not text:
            return text, 0
        count = 0
        out = text
        for rx in self._compiled:
            out, n = rx.subn(self.placeholder, out)
            count += n
        return out, count
