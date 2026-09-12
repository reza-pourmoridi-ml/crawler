"""Lightweight progress reporting from an isolated job process."""

from collections.abc import Callable


_reporter: Callable[[], None] | None = None


def set_progress_reporter(reporter: Callable[[], None] | None) -> None:
    global _reporter
    _reporter = reporter


def report_progress() -> None:
    if _reporter is not None:
        _reporter()
