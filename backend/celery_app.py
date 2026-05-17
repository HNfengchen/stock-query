import os
import logging

logger = logging.getLogger("stock_query")

celery_app = None
celery_enabled = False


def _load_celery_config():
    try:
        from scripts.core.config_loader import load_config
        cfg = load_config()
        return cfg.get("celery", {})
    except Exception:
        return {}


def init_celery():
    global celery_app, celery_enabled

    try:
        from celery import Celery
    except ImportError:
        logger.info("Celery 未安装，异步任务功能不可用")
        celery_enabled = False
        return None

    celery_cfg = _load_celery_config()

    if not celery_cfg.get("enabled", False):
        logger.info("Celery 未启用 (config: celery.enabled=false)")
        celery_enabled = False
        return None

    broker_url = celery_cfg.get("broker_url", "redis://localhost:6379/0")
    result_backend = celery_cfg.get("result_backend", "redis://localhost:6379/1")
    worker_concurrency = celery_cfg.get("worker_concurrency", 4)
    task_timeout = celery_cfg.get("task_timeout", 300)

    celery_app = Celery(
        "stock_query",
        broker=broker_url,
        backend=result_backend,
    )

    celery_app.conf.update(
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        timezone="Asia/Shanghai",
        enable_utc=True,
        task_track_started=True,
        task_time_limit=task_timeout,
        task_soft_time_limit=task_timeout - 30,
        worker_concurrency=worker_concurrency,
        worker_prefetch_multiplier=1,
        result_expires=3600,
        task_routes={
            "backend.tasks.analyze_stock_task": {"queue": "analysis"},
            "backend.tasks.batch_analyze_task": {"queue": "analysis"},
        },
    )

    celery_app.autodiscover_tasks(["backend"])

    celery_enabled = True
    logger.info(f"Celery 已初始化: broker={broker_url}, concurrency={worker_concurrency}")

    return celery_app


def get_celery_app():
    return celery_app


def is_celery_enabled():
    return celery_enabled
