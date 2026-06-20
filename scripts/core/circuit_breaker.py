import time
import threading
from typing import Dict, List, Optional

from scripts.logger import get_logger

logger = get_logger("circuit_breaker")


class CircuitBreaker:
    def __init__(self, timeout: int = 300, source_priority: Optional[List[str]] = None, health_check_interval: int = 60):
        self._timeout = timeout
        self._source_priority = source_priority or []
        self._unhealthy: Dict[str, dict] = {}
        self._lock = threading.Lock()
        self._health_check_interval = health_check_interval
        self._health_check_timer = None
        self._health_check_running = False
        self._health_check_callback = None

    def mark_unhealthy(self, source: str, reason: str) -> None:
        with self._lock:
            self._unhealthy[source] = {
                "reason": reason,
                "marked_at": time.time(),
            }
            logger.warning("数据源 [%s] 标记为不健康: %s", source, reason)

    def mark_healthy(self, source: str) -> None:
        with self._lock:
            if source in self._unhealthy:
                del self._unhealthy[source]
                logger.info("数据源 [%s] 健康检查通过，主动恢复", source)

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

    def set_health_check_callback(self, callback):
        self._health_check_callback = callback

    def start_health_check(self):
        if self._health_check_running:
            return
        self._health_check_running = True
        self._schedule_health_check()
        logger.info("熔断器健康检查已启动 (间隔: %ds)", self._health_check_interval)

    def stop_health_check(self):
        self._health_check_running = False
        if self._health_check_timer:
            self._health_check_timer.cancel()
            self._health_check_timer = None

    def _schedule_health_check(self):
        if not self._health_check_running:
            return
        self._health_check_timer = threading.Timer(self._health_check_interval, self._run_health_check)
        self._health_check_timer.daemon = True
        self._health_check_timer.start()

    def _run_health_check(self):
        if not self._health_check_running:
            return
        try:
            if self._health_check_callback:
                for source in list(self._source_priority):
                    try:
                        is_healthy = self._health_check_callback(source)
                        if is_healthy:
                            if source in self._unhealthy:
                                self.mark_healthy(source)
                        else:
                            self.mark_unhealthy(source, "健康检查失败")
                    except Exception as e:
                        logger.error("健康检查异常 [%s]: %s", source, e)
                        self.mark_unhealthy(source, f"健康检查异常: {e}")
        except Exception as e:
            logger.error("健康检查运行错误: %s", e)
        finally:
            self._schedule_health_check()

    def health_check(self) -> Dict[str, bool]:
        results = {}
        if self._health_check_callback:
            for source in self._source_priority:
                try:
                    results[source] = self._health_check_callback(source)
                except Exception:
                    logger.warning(f"数据源{source}健康检查异常", exc_info=True)
                    results[source] = False
        return results
