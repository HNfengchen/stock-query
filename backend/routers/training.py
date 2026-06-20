import asyncio
import json
import logging
import os
import re
import shutil
import threading
from datetime import datetime


from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from backend.logging import log_system

router = APIRouter()

logger = logging.getLogger("stock_query.training")

PYTHON_BIN = os.path.expanduser("~/miniconda3/bin/python")
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
MODELS_DIR = os.path.join(PROJECT_ROOT, "models")
TRAINING_TIMEOUT = 600  # 10分钟

_training_lock = threading.Lock()
_training_status = {"running": False, "mode": None, "started_at": None, "pid": None}


class TrainingRequest(BaseModel):
    mode: str = "incremental"  # incremental / force / hmm_only


def _parse_log_level(line: str) -> str:
    """根据日志行内容推断级别"""
    lower = line.lower()
    if "error" in lower or "exception" in lower or "traceback" in lower:
        return "error"
    if "warning" in lower or "warn" in lower:
        return "warning"
    return "info"


def _parse_stock_progress(line: str):
    """从训练日志中提取股票进度信息"""
    # 匹配类似 [601898] 训练完成 / 模型已存在，跳过训练 / 训练失败
    m = re.match(r".*\[(\d{6})\].*(训练完成|成功)", line)
    if m:
        return m.group(1), "success"
    m = re.match(r".*\[(\d{6})\].*(跳过|skipped)", line)
    if m:
        return m.group(1), "skipped"
    m = re.match(r".*\[(\d{6})\].*(失败|failed|error)", line)
    if m:
        return m.group(1), "failed"
    return None, None


@router.post("/training/start")
async def start_training(req: TrainingRequest):
    logger.info(f"[training] 收到训练请求: mode={req.mode}")
    if req.mode not in ("incremental", "force", "hmm_only"):
        logger.warning(f"[training] 无效训练模式: {req.mode}")
        return JSONResponse(status_code=400, content={"detail": f"无效的训练模式: {req.mode}"})

    with _training_lock:
        if _training_status["running"]:
            logger.warning(f"[training] 拒绝请求: 已有训练任务正在运行 (mode={_training_status['mode']})")
            return JSONResponse(status_code=409, content={"detail": "已有训练任务正在运行"})
        _training_status["running"] = True
        _training_status["mode"] = req.mode
        _training_status["started_at"] = datetime.now().isoformat()
        _training_status["pid"] = None
        logger.info(f"[training] 训练状态已设置: mode={req.mode}, started_at={_training_status['started_at']}")

    async def event_generator():

        log_system("training", f"开始训练: mode={req.mode}")

        success_count = 0
        failed_count = 0
        skipped_count = 0

        try:
            # 构建训练命令
            if req.mode == "force":
                # 先删除 models/ 目录
                if os.path.exists(MODELS_DIR):
                    logger.info(f"[training] force模式: 清除 models/ 目录: {MODELS_DIR}")
                    shutil.rmtree(MODELS_DIR)
                    yield {"event": "log", "data": json.dumps({"message": "已清除 models/ 目录", "level": "info"}, ensure_ascii=False)}
                    log_system("training", "已清除 models/ 目录")
                else:
                    logger.info("[training] force模式: models/ 目录不存在，无需清除")

                cmd_args = [
                    PYTHON_BIN, "-m", "scripts.train_model",
                    "--watchlist",
                    "--config", os.path.join(PROJECT_ROOT, "config", "config.yaml"),
                ]
            elif req.mode == "incremental":
                cmd_args = [
                    PYTHON_BIN, "-m", "scripts.train_model",
                    "--watchlist", "--skip-existing",
                    "--config", os.path.join(PROJECT_ROOT, "config", "config.yaml"),
                ]
            else:  # hmm_only
                cmd_args = [
                    PYTHON_BIN, "-m", "scripts.train_hmm",
                    "--config", os.path.join(PROJECT_ROOT, "config", "config.yaml"),
                ]

            logger.info(f"[training] 执行命令: {' '.join(cmd_args)}, cwd={PROJECT_ROOT}")
            yield {"event": "log", "data": json.dumps({"message": f"执行命令: {' '.join(cmd_args)}", "level": "info"}, ensure_ascii=False)}

            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
                cwd=PROJECT_ROOT,
            )
            logger.info(f"[training] 子进程启动: pid={proc.pid}, cmd={' '.join(cmd_args)}")

            with _training_lock:
                _training_status["pid"] = proc.pid

            try:
                while True:
                    line_bytes = await asyncio.wait_for(proc.stdout.readline(), timeout=TRAINING_TIMEOUT)
                    if not line_bytes:
                        logger.info("[training] 子进程stdout已关闭")
                        break
                    line = line_bytes.decode("utf-8", errors="replace").rstrip()
                    if not line:
                        continue

                    level = _parse_log_level(line)
                    yield {"event": "log", "data": json.dumps({"message": line, "level": level}, ensure_ascii=False)}

                    stock_code, status = _parse_stock_progress(line)
                    if stock_code and status:
                        yield {"event": "progress", "data": json.dumps({"stock": stock_code, "status": status}, ensure_ascii=False)}
                        if status == "success":
                            success_count += 1
                        elif status == "failed":
                            failed_count += 1
                        elif status == "skipped":
                            skipped_count += 1

                await asyncio.wait_for(proc.wait(), timeout=30)
                logger.info(f"[training] 子进程退出: returncode={proc.returncode}")
            except asyncio.TimeoutError:
                proc.kill()
                logger.error("[training] 训练超时，已终止子进程")
                yield {"event": "error", "data": json.dumps({"message": "训练超时，已终止"}, ensure_ascii=False)}
                log_system("training", "训练超时，已终止")
                return

            if proc.returncode != 0:
                logger.error(f"[training] 训练进程异常退出: returncode={proc.returncode}")
                yield {"event": "error", "data": json.dumps({"message": f"训练进程退出码: {proc.returncode}"}, ensure_ascii=False)}

            # hmm_only 模式已训练全局 HMM；incremental/force 模式下按需补充全局 HMM
            if req.mode in ("incremental", "force"):
                hmm_model_path = os.path.join(MODELS_DIR, "hmm_regime.pkl")
                should_train_hmm = req.mode == "force" or not os.path.exists(hmm_model_path)
                logger.info(f"[training] HMM检查: path={hmm_model_path}, exists={os.path.exists(hmm_model_path)}, should_train={should_train_hmm}")
                if should_train_hmm:
                    yield {"event": "log", "data": json.dumps({"message": "开始训练全局HMM模型...", "level": "info"}, ensure_ascii=False)}
                    hmm_args = [
                        PYTHON_BIN, "-m", "scripts.train_hmm",
                        "--config", os.path.join(PROJECT_ROOT, "config", "config.yaml"),
                    ]
                    logger.info(f"[training] HMM命令: {' '.join(hmm_args)}")
                    hmm_proc = await asyncio.create_subprocess_exec(
                        *hmm_args,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.STDOUT,
                        cwd=PROJECT_ROOT,
                    )
                    try:
                        while True:
                            line_bytes = await asyncio.wait_for(hmm_proc.stdout.readline(), timeout=TRAINING_TIMEOUT)
                            if not line_bytes:
                                break
                            hmm_line = line_bytes.decode("utf-8", errors="replace").rstrip()
                            if hmm_line:
                                level = _parse_log_level(hmm_line)
                                yield {"event": "log", "data": json.dumps({"message": hmm_line, "level": level}, ensure_ascii=False)}
                        await asyncio.wait_for(hmm_proc.wait(), timeout=30)
                        logger.info(f"[training] 全局HMM训练完成: returncode={hmm_proc.returncode}")
                    except asyncio.TimeoutError:
                        hmm_proc.kill()
                        logger.error("[training] 全局HMM训练超时，已终止")
                        yield {"event": "error", "data": json.dumps({"message": "全局HMM训练超时，已终止"}, ensure_ascii=False)}

            # 触发个股 HMM 训练（hmm_only / incremental / force）
            if req.mode in ("hmm_only", "incremental", "force"):
                yield {"event": "log", "data": json.dumps({"message": "开始训练个股HMM模型...", "level": "info"}, ensure_ascii=False)}
                hmm_stock_args = [
                    PYTHON_BIN, "-m", "scripts.train_hmm",
                    "--all-watchlist",
                    "--config", os.path.join(PROJECT_ROOT, "config", "config.yaml"),
                ]
                if req.mode == "incremental":
                    hmm_stock_args.append("--skip-existing")
                logger.info(f"[training] 个股HMM命令: {' '.join(hmm_stock_args)}")
                hmm_stock_proc = await asyncio.create_subprocess_exec(
                    *hmm_stock_args,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=PROJECT_ROOT,
                )
                try:
                    while True:
                        line_bytes = await asyncio.wait_for(hmm_stock_proc.stdout.readline(), timeout=TRAINING_TIMEOUT)
                        if not line_bytes:
                            break
                        hmm_stock_line = line_bytes.decode("utf-8", errors="replace").rstrip()
                        if hmm_stock_line:
                            level = _parse_log_level(hmm_stock_line)
                            yield {"event": "log", "data": json.dumps({"message": hmm_stock_line, "level": level}, ensure_ascii=False)}
                            stock_code, status = _parse_stock_progress(hmm_stock_line)
                            if stock_code and status:
                                yield {"event": "progress", "data": json.dumps({"stock": stock_code, "status": status}, ensure_ascii=False)}
                                if status == "success":
                                    success_count += 1
                                elif status == "failed":
                                    failed_count += 1
                                elif status == "skipped":
                                    skipped_count += 1
                    await asyncio.wait_for(hmm_stock_proc.wait(), timeout=30)
                    logger.info(f"[training] 个股HMM训练完成: returncode={hmm_stock_proc.returncode}")
                except asyncio.TimeoutError:
                    hmm_stock_proc.kill()
                    logger.error("[training] 个股HMM训练超时，已终止")
                    yield {"event": "error", "data": json.dumps({"message": "个股HMM训练超时，已终止"}, ensure_ascii=False)}

            yield {"event": "complete", "data": json.dumps({
                "success_count": success_count,
                "failed_count": failed_count,
                "skipped_count": skipped_count,
            }, ensure_ascii=False)}

            logger.info(f"[training] 训练完成: success={success_count}, failed={failed_count}, skipped={skipped_count}")
            log_system("training", f"训练完成: success={success_count}, failed={failed_count}, skipped={skipped_count}")

        except Exception as e:
            logger.error(f"训练异常: {e}", exc_info=True)
            yield {"event": "error", "data": json.dumps({"message": str(e)}, ensure_ascii=False)}
            log_system("training", f"训练异常: {e}")
        finally:
            with _training_lock:
                _training_status["running"] = False
                _training_status["mode"] = None
                _training_status["started_at"] = None
                _training_status["pid"] = None

    return EventSourceResponse(event_generator())


@router.get("/training/status")
async def get_training_status():
    with _training_lock:
        status = {
            "running": _training_status["running"],
            "mode": _training_status["mode"],
            "started_at": _training_status["started_at"],
            "pid": _training_status["pid"],
        }
    logger.debug(f"[training] 状态查询: {status}")
    return status


@router.get("/training/models")
async def list_models():
    models = []
    hmm_info = {"exists": False, "trained_at": None}

    logger.info(f"[list_models] 扫描模型目录: {MODELS_DIR}, 存在={os.path.exists(MODELS_DIR)}")

    if not os.path.exists(MODELS_DIR):
        logger.warning(f"[list_models] 模型目录不存在: {MODELS_DIR}")
        return {"models": models, "hmm": hmm_info, "total": 0}

    entries = os.listdir(MODELS_DIR)
    logger.info(f"[list_models] 目录条目数: {len(entries)}, 条目: {entries}")

    # 扫描模型目录
    for entry in sorted(entries):
        model_path = os.path.join(MODELS_DIR, entry)
        if not os.path.isdir(model_path):
            logger.debug(f"[list_models] 跳过非目录项: {entry}")
            continue

        # 跳过HMM模型目录和非股票代码目录
        if not re.match(r"^\d{6}$", entry):
            logger.debug(f"[list_models] 跳过非股票代码目录: {entry}")
            continue

        # 检查是否存在模型文件: 任意 .txt (LightGBM booster) 或 meta.joblib
        txt_files = [f for f in os.listdir(model_path) if f.endswith(".txt")]
        has_meta = os.path.exists(os.path.join(model_path, "meta.joblib"))
        if not txt_files and not has_meta:
            logger.warning(f"[list_models] 目录 {entry} 无有效模型文件(txt={txt_files}, meta={has_meta})")
            continue

        # 取最新的模型文件修改时间
        mtimes = []
        for f in os.listdir(model_path):
            fp = os.path.join(model_path, f)
            if os.path.isfile(fp):
                mtimes.append(os.path.getmtime(fp))
        trained_at = datetime.fromtimestamp(max(mtimes)).isoformat() if mtimes else None

        # 从 meta.joblib 读取特征信息
        feature_names = []
        n_features = 0
        meta_path = os.path.join(model_path, "meta.joblib")
        if os.path.exists(meta_path):
            try:
                import joblib
                meta = joblib.load(meta_path)
                feature_names = meta.get("feature_names", [])
                n_features = len(feature_names)
                logger.info(f"[list_models] {entry}: 从meta读取 {n_features} 个特征")
            except Exception as e:
                logger.warning(f"[list_models] {entry}: 读取meta失败: {e}")
        else:
            logger.warning(f"[list_models] {entry}: 无meta.joblib，特征数未知")

        models.append({
            "stock_code": entry,
            "trained_at": trained_at,
            "n_features": n_features,
            "feature_names": feature_names,
        })
        logger.info(f"[list_models] 发现模型: {entry}, trained_at={trained_at}, n_features={n_features}")

    # 检查HMM模型
    hmm_path = os.path.join(MODELS_DIR, "hmm_regime.pkl")
    if os.path.exists(hmm_path):
        hmm_info["exists"] = True
        hmm_info["trained_at"] = datetime.fromtimestamp(os.path.getmtime(hmm_path)).isoformat()
        logger.info(f"[list_models] HMM模型存在: trained_at={hmm_info['trained_at']}")
    else:
        logger.info("[list_models] HMM模型不存在")

    logger.info(f"[list_models] 汇总: 个股模型={len(models)}, HMM={hmm_info['exists']}")
    return {"models": models, "hmm": hmm_info, "total": len(models)}


@router.delete("/training/models/{stock_code}")
async def delete_model(stock_code: str):
    logger.info(f"[training] 收到删除模型请求: {stock_code}")
    if not re.match(r"^\d{6}$", stock_code):
        logger.warning(f"[training] 无效股票代码: {stock_code}")
        return JSONResponse(status_code=400, content={"detail": "无效的股票代码"})

    model_path = os.path.join(MODELS_DIR, stock_code)
    if not os.path.exists(model_path):
        logger.warning(f"[training] 模型不存在: {stock_code}")
        return JSONResponse(status_code=404, content={"detail": f"模型不存在: {stock_code}"})

    shutil.rmtree(model_path)
    logger.info(f"[training] 已删除模型: {stock_code}")
    log_system("training", f"已删除模型: {stock_code}")
    return {"detail": f"已删除模型: {stock_code}"}
