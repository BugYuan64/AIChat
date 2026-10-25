"""进程内滑动窗口限流（v1 单实例；多实例需替换为共享存储）。"""

import time

from aichat.core.errors import rate_limited


class SlidingWindowLimiter:
    def __init__(self) -> None:
        self._hits: dict[str, list[float]] = {}

    def check(self, key: str, limit: int, window_seconds: float = 60.0) -> None:
        now = time.monotonic()
        hits = [t for t in self._hits.get(key, []) if now - t < window_seconds]
        if len(hits) >= limit:
            wait_ms = int((window_seconds - (now - hits[0])) * 1000) + 50
            raise rate_limited(max(wait_ms, 100))
        hits.append(now)
        self._hits[key] = hits
        if len(self._hits) > 10000:  # 防泄漏
            cutoff = now - window_seconds
            self._hits = {k: v for k, v in self._hits.items() if v and v[-1] > cutoff}
