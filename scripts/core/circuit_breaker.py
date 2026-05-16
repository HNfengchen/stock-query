import time
import threading
import logging
from typing import Dict, List, Optional

logger = logging.getLogger("CircuitBreaker")


class CircuitBreaker:
    def __init__(self, timeout: int = 300, source_priority: Optional[List[str]] = None):
        self._timeout = timeout
        self._source_priority = source_priority or []
        self._unhealthy: Dict[str, dict] = {}
        self._lock = threading.Lock()

    def mark_unhealthy(self, source: str, reason: str) -> None:
        with self._lock:
            self._unhealthy[source] = {
                "reason": reason,
                "marked_at": time.time(),
            }
            logger.warning("数据源 [%s] 标记为不健康: %s", source, reason)

    def is_healthy(self, source: str) -> bool:
        with self._lock:
            if source not in self._unhealthy:
                return True
            elapsed = time.time() - self._unhealthy[source]["marked_at"]
            if elapsed >= self._timeout:
                del self._unhealthy[source]
                logger.info("数据源 [%s] 超时恢复 (等待了 %ds)", source, int(elapsed))
                return True
            return False

    def get_healthy_sources(self) -> list:
        with self._lock:
            all_sources = list(self._source_priority)
            for source in self._unhealthy:
                if source not in all_sources:
                    all_sources.append(source)

        healthy = []
        for source in all_sources:
            if self.is_healthy(source):
                healthy.append(source)
        return healthy

    def get_status(self) -> dict:
        with self._lock:
            now = time.time()
            status = {}
            for source in self._source_priority:
                if source in self._unhealthy:
                    elapsed = now - self._unhealthy[source]["marked_at"]
                    status[source] = {
                        "healthy": elapsed >= self._timeout,
                        "reason": self._unhealthy[source]["reason"],
                        "marked_at": self._unhealthy[source]["marked_at"],
                        "remaining_timeout": max(0, self._timeout - elapsed),
                    }
                else:
                    status[source] = {"healthy": True, "reason": None, "marked_at": None, "remaining_timeout": 0}

            for source in self._unhealthy:
                if source not in status:
                    elapsed = now - self._unhealthy[source]["marked_at"]
                    status[source] = {
                        "healthy": elapsed >= self._timeout,
                        "reason": self._unhealthy[source]["reason"],
                        "marked_at": self._unhealthy[source]["marked_at"],
                        "remaining_timeout": max(0, self._timeout - elapsed),
                    }
            return status
