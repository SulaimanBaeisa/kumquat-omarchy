"""Run one conversion off the GTK main thread.

The GUI injects a `post` that schedules callbacks on the GLib main loop;
tests inject a synchronous `post`. This module never imports GTK.
"""
from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from .progress import Progress, ProgressCallback

Post = Callable[..., Any]
DoneCallback = Callable[[Any, BaseException | None], None]


class Job:
    """A single background job with progress and completion callbacks."""

    def __init__(self, work: Callable[[ProgressCallback], Any], *,
                 on_progress: ProgressCallback, on_done: DoneCallback,
                 post: Post) -> None:
        self._work = work
        self._on_progress = on_progress
        self._on_done = on_done
        self._post = post
        self._thread = threading.Thread(target=self._run, daemon=True)

    @property
    def running(self) -> bool:
        return self._thread.is_alive()

    def start(self) -> None:
        self._thread.start()

    def join(self, timeout: float | None = None) -> None:
        self._thread.join(timeout)

    def _report(self, update: Progress) -> None:
        self._post(self._on_progress, update)

    def _run(self) -> None:
        try:
            result = self._work(self._report)
        except BaseException as exc:  # noqa: BLE001 - surfaced to the UI, never lost
            self._post(self._on_done, None, exc)
            return
        self._post(self._on_done, result, None)
