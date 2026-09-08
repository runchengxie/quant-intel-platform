"""Helpers for calling TuShare with retries and pacing."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")


@dataclass
class RateLimiter:
    min_interval: float
    last_call: float = 0.0

    def wait(self) -> None:
        if self.min_interval <= 0:
            return
        now = time.monotonic()
        elapsed = now - self.last_call
        if elapsed < self.min_interval:
            time.sleep(self.min_interval - elapsed)
        self.last_call = time.monotonic()


@dataclass
class FetchRunner:
    rate_limiter: RateLimiter
    retries: int = 6
    base_delay: float = 2.0
    max_delay: float = 60.0

    def call(self, label: str, fn: Callable[[], T]) -> T:
        for attempt in range(1, self.retries + 1):
            try:
                self.rate_limiter.wait()
                return fn()
            except Exception as exc:
                if attempt == self.retries:
                    raise
                delay = min(self.base_delay * 2 ** (attempt - 1), self.max_delay)
                print(
                    f"{label} failed (attempt {attempt}/{self.retries}): {exc}. "
                    f"Retrying in {delay:.1f}s..."
                )
                time.sleep(delay)
        raise RuntimeError("unreachable")
