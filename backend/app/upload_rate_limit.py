"""Bounded per-process sliding-window limits for plan uploads."""
from __future__ import annotations

from collections import OrderedDict, deque
from math import ceil
from time import monotonic
from typing import Callable


class UploadRateLimiter:
    def __init__(
        self,
        *,
        window_seconds: float = 60.0,
        max_clients: int = 4096,
        max_events: int = 100_000,
        clock: Callable[[], float] = monotonic,
    ) -> None:
        self._window_seconds = window_seconds
        self._max_clients = max_clients
        self._max_events = max_events
        self._clock = clock
        self._events: OrderedDict[str, deque[float]] = OrderedDict()
        self._event_count = 0

    def check(self, client_address: str, limit: int) -> int | None:
        """Record an allowed request or return seconds until retry is safe."""
        now = self._clock()
        cutoff = now - self._window_seconds
        for address, timestamps in list(self._events.items()):
            while timestamps and timestamps[0] <= cutoff:
                timestamps.popleft()
                self._event_count -= 1
            if not timestamps:
                del self._events[address]

        timestamps = self._events.get(client_address)
        if timestamps is not None and len(timestamps) >= limit:
            return max(1, ceil(timestamps[0] + self._window_seconds - now))

        if timestamps is None:
            if len(self._events) >= self._max_clients:
                return self._retry_after_oldest(now)
            timestamps = deque()
            self._events[client_address] = timestamps
        else:
            self._events.move_to_end(client_address)

        if self._event_count >= self._max_events:
            return self._retry_after_oldest(now)

        timestamps.append(now)
        self._event_count += 1
        return None

    def _retry_after_oldest(self, now: float) -> int:
        oldest = min(timestamps[0] for timestamps in self._events.values())
        return max(1, ceil(oldest + self._window_seconds - now))