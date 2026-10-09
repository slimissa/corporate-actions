#!/usr/bin/env python3
"""A token bucket rate limiter.

Blocks a caller until a token is available. Tokens refill at a fixed
rate up to a maximum capacity. Useful for pacing outbound HTTP requests
to endpoints with a documented or observed throughput limit.

Usage:
    bucket = TokenBucket(rate=5.0, capacity=10)
    bucket.acquire()  # returns when a token is available
    ...               # do one unit of work
    bucket.acquire()  # blocks if the bucket is empty

Thread-safe. Uses a monotonic clock so wall-clock adjustments do not
distort the refill schedule.
"""

from __future__ import annotations

import threading
import time
from typing import Optional


class TokenBucket:
    """A thread-safe token bucket.

    Attributes:
        rate: Tokens added per second.
        capacity: Maximum tokens the bucket can hold.
    """

    def __init__(self, rate: float, capacity: Optional[float] = None):
        if rate <= 0:
            raise ValueError(f"rate must be positive, got {rate!r}")
        if capacity is None:
            capacity = max(1.0, rate)
        if capacity <= 0:
            raise ValueError(f"capacity must be positive, got {capacity!r}")

        self.rate = float(rate)
        self.capacity = float(capacity)

        self._tokens = float(capacity)  # start full
        self._last_refill = time.monotonic()
        self._lock = threading.Lock()

        # Metrics. Readable without the lock; increments are best-effort.
        self.acquired: int = 0
        self.waited_seconds: float = 0.0

    def _refill_locked(self) -> None:
        """Add tokens based on elapsed time. Caller must hold the lock."""
        now = time.monotonic()
        elapsed = now - self._last_refill
        if elapsed <= 0:
            return
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_refill = now

    def acquire(self, tokens: float = 1.0) -> None:
        """Block until `tokens` are available, then consume them.

        `tokens` must be at most `capacity`, otherwise the call would
        never return. Raises ValueError in that case.
        """
        if tokens <= 0:
            raise ValueError(f"tokens must be positive, got {tokens!r}")
        if tokens > self.capacity:
            raise ValueError(
                f"cannot acquire {tokens!r} tokens: capacity is {self.capacity}"
            )

        while True:
            with self._lock:
                self._refill_locked()
                if self._tokens >= tokens:
                    self._tokens -= tokens
                    self.acquired += 1
                    return
                # Compute the wait outside the lock so other callers can
                # also check the bucket state.
                deficit = tokens - self._tokens
                wait = deficit / self.rate

            self.waited_seconds += wait
            time.sleep(wait)
        