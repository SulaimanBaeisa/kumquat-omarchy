"""Shared LibreOffice helper: one isolated user profile per run.

Concurrent ``soffice`` invocations that share the default user profile
fail with "another instance is running" (LibreOffice takes a lock on the
profile directory). Conversions must be able to run in parallel — a user
converting two files at once, or the test suite alongside a job — so
every invocation gets its own ``-env:UserInstallation`` directory.
"""

from __future__ import annotations

from pathlib import Path


def profile_args(tmp: str | Path) -> list[str]:
    """ffice args that point this run at its own throwaway profile."""
    return [f"-env:UserInstallation=file://{Path(tmp) / 'lo-profile'}"]
