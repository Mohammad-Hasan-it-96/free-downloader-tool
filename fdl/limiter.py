"""A speed limit that several download threads share."""

import threading
import time


class RateLimiter:
    """Lets through at most `bytes_per_second`, shared by all threads.

    It works like a bucket that refills over time. A thread asks for the
    bytes it is about to read; if the bucket is empty, it waits.
    `bytes_per_second` of 0 or less means no limit at all.
    """

    def __init__(self, bytes_per_second=0, burst_seconds=1.0):
        self.rate = max(0, int(bytes_per_second or 0))
        self.capacity = max(1, int(self.rate * burst_seconds)) if self.rate else 0
        self._tokens = float(self.capacity)
        self._updated = time.monotonic()
        self._lock = threading.Lock()

    @property
    def unlimited(self):
        return self.rate <= 0

    def chunk_size(self, wanted):
        """Never ask for more bytes at once than the bucket can hold."""
        if self.unlimited:
            return wanted
        return max(1024, min(wanted, self.capacity))

    def take(self, amount):
        """Wait until `amount` bytes are allowed, then return."""
        if self.unlimited or amount <= 0:
            return
        while True:
            with self._lock:
                now = time.monotonic()
                self._tokens = min(
                    float(self.capacity),
                    self._tokens + (now - self._updated) * self.rate)
                self._updated = now
                if self._tokens >= amount:
                    self._tokens -= amount
                    return
                missing = amount - self._tokens
                wait = missing / self.rate
            time.sleep(min(wait, 0.25))


NO_LIMIT = RateLimiter(0)
