"""Stable failures raised by the subprocess agent boundary."""

from __future__ import annotations


class AgentRuntimeError(RuntimeError):
    """Fail-closed runtime error with a stable machine-readable code."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
