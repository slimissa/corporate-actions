"""Tests for tools/rate_limit.TokenBucket."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))

from tools.rate_limit import TokenBucket


class TestConstruction:

    def test_default_capacity_is_rate(self):
        bucket = TokenBucket(rate=5.0)
        assert bucket.capacity == 5.0

    def test_explicit_capacity(self):
        bucket = TokenBucket(rate=5.0, capacity=20.0)
        assert bucket.capacity == 20.0

    def test_zero_rate_rejected(self):
        with pytest.raises(ValueError):
            TokenBucket(rate=0.0)

    def test_negative_rate_rejected(self):
        with pytest.raises(ValueError):
            TokenBucket(rate=-1.0)

    def test_zero_capacity_rejected(self):
        with pytest.raises(ValueError):
            TokenBucket(rate=5.0, capacity=0.0)

    def test_starts_full(self):
        bucket = TokenBucket(rate=10.0, capacity=10.0)
        # Consuming the full capacity should not block.
        start = time.monotonic()
        for _ in range(10):
            bucket.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05, f"full bucket should not block: {elapsed:.3f}s"


class TestAcquisition:

    def test_first_n_acquires_are_free(self):
        bucket = TokenBucket(rate=100.0, capacity=10.0)
        start = time.monotonic()
        for _ in range(10):
            bucket.acquire()
        elapsed = time.monotonic() - start
        assert elapsed < 0.05

    def test_eleventh_acquire_blocks(self):
        bucket = TokenBucket(rate=100.0, capacity=10.0)
        for _ in range(10):
            bucket.acquire()
        start = time.monotonic()
        bucket.acquire()
        elapsed = time.monotonic() - start
        # Rate is 100/sec, so 1 token needs 10ms.
        assert elapsed >= 0.005, f"expected to block ~10ms, blocked {elapsed:.4f}s"
        assert elapsed < 0.5, f"blocked too long: {elapsed:.4f}s"

    def test_sustained_rate(self):
        """20 acquires at 50/sec should take at least 0.2s."""
        bucket = TokenBucket(rate=50.0, capacity=5.0)
        start = time.monotonic()
        for _ in range(20):
            bucket.acquire()
        elapsed = time.monotonic() - start
        # 20 tokens, initial 5 free, remaining 15 at 50/sec = 0.3s.
        assert elapsed >= 0.25, f"too fast: {elapsed:.4f}s"
        assert elapsed < 0.7, f"too slow: {elapsed:.4f}s"

    def test_zero_tokens_rejected(self):
        bucket = TokenBucket(rate=5.0, capacity=10.0)
        with pytest.raises(ValueError):
            bucket.acquire(0)

    def test_negative_tokens_rejected(self):
        bucket = TokenBucket(rate=5.0, capacity=10.0)
        with pytest.raises(ValueError):
            bucket.acquire(-1)

    def test_tokens_exceeding_capacity_rejected(self):
        bucket = TokenBucket(rate=5.0, capacity=10.0)
        with pytest.raises(ValueError):
            bucket.acquire(11)


class TestRefill:

    def test_refills_after_sleep(self):
        bucket = TokenBucket(rate=20.0, capacity=5.0)
        for _ in range(5):
            bucket.acquire()
        # Bucket is empty. Sleep long enough to refill 4 tokens.
        time.sleep(0.22)
        start = time.monotonic()
        for _ in range(4):
            bucket.acquire()
        elapsed = time.monotonic() - start
        # 4 tokens already refilled, should be near-instant.
        assert elapsed < 0.1, f"expected refill, got {elapsed:.4f}s"

    def test_does_not_overfill(self):
        bucket = TokenBucket(rate=100.0, capacity=5.0)
        time.sleep(0.5)  # would refill 50 tokens if uncapped
        start = time.monotonic()
        for _ in range(5):
            bucket.acquire()
        elapsed = time.monotonic() - start
        # Should not have overfilled.
        assert elapsed < 0.05


class TestThreadSafety:

    def test_concurrent_acquires_are_paced(self):
        bucket = TokenBucket(rate=50.0, capacity=1.0)
        results = []

        def worker():
            bucket.acquire()
            results.append(time.monotonic())

        threads = [threading.Thread(target=worker) for _ in range(10)]
        start = time.monotonic()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.monotonic() - start
        # 10 acquires at 50/sec with capacity 1: first is free, remaining
        # 9 take 9/50 = 0.18s. Add tolerance.
        assert len(results) == 10
        assert elapsed >= 0.15, f"too fast for 10 acquires: {elapsed:.4f}s"
        assert elapsed < 0.6, f"too slow: {elapsed:.4f}s"


class TestMetrics:

    def test_acquired_counter(self):
        bucket = TokenBucket(rate=100.0, capacity=10.0)
        for _ in range(7):
            bucket.acquire()
        assert bucket.acquired == 7

    def test_waited_seconds_tracks_blocking(self):
        bucket = TokenBucket(rate=100.0, capacity=2.0)
        bucket.acquire()
        bucket.acquire()
        bucket.acquire()  # blocks ~10ms
        assert bucket.waited_seconds > 0
        assert bucket.waited_seconds < 0.5