#!/bin/bash
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
BACKEND_PORT=${BACKEND_PORT:-8002}
FRONTEND_PORT=${FRONTEND_PORT:-5173}
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$PROJECT_DIR/logs"

mkdir -p "$PID_DIR" "$LOG_DIR"

check_backend() {
    if [ -f "$PID_DIR/backend.pid" ]; then
        pid=$(cat "$PID_DIR/backend.pid")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

check_frontend() {
    if [ -f "$PID_DIR/frontend.pid" ]; then
        pid=$(cat "$PID_DIR/frontend.pid")
        if kill -0 "$pid" 2>/dev/null; then
            return 0
        fi
    fi
    return 1
}

start_backend() {
    if check_backend; then
        echo "[后端] 已在运行 (PID: $(cat "$PID_DIR/backend.pid"))"
        return 0
    fi

    echo "[后端] 正在启动..."
    cd "$PROJECT_DIR"

    nohup python -m uvicorn backend.app:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --workers 1 \
        > "$LOG_DIR/backend.log" 2>&1 &

    echo $! > "$PID_DIR/backend.pid"

    for i in $(seq 1 15); do
        if curl -s "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
            echo "[后端] 启动成功 (PID: $(cat "$PID_DIR/backend.pid"), 端口: $BACKEND_PORT)"
            return 0
        fi
        sleep 1
    done

    echo "[后端] 启动超时，请检查日志: $LOG_DIR/backend.log"
    return 1
}

start_frontend() {
    if check_frontend; then
        echo "[前端] 已在运行 (PID: $(cat "$PID_DIR/frontend.pid"))"
        return 0
    fi

    echo "[前端] 正在启动..."
    cd "$PROJECT_DIR/frontend"

    if [ ! -d "dist" ]; then
        echo "[前端] 构建前端..."
        if [ ! -d "node_modules" ]; then
            npm install --production=false > "$LOG_DIR/npm_install.log" 2>&1
        fi
        npm run build > "$LOG_DIR/frontend_build.log" 2>&1
    fi

    export BACKEND_URL="http://127.0.0.1:$BACKEND_PORT"
    export FRONTEND_PORT="$FRONTEND_PORT"
    nohup python3 serve.py \
        > "$LOG_DIR/frontend.log" 2>&1 &

    echo $! > "$PID_DIR/frontend.pid"

    for i in $(seq 1 15); do
        if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
            echo "[前端] 启动成功 (PID: $(cat "$PID_DIR/frontend.pid"), 端口: $FRONTEND_PORT)"
            return 0
        fi
        sleep 1
    done

    echo "[前端] 启动超时，请检查日志: $LOG_DIR/frontend.log"
    return 1
}

stop_backend() {
    if check_backend; then
        pid=$(cat "$PID_DIR/backend.pid")
        echo "[后端] 正在停止 (PID: $pid)..."
        kill "$pid" 2>/dev/null
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
        rm -f "$PID_DIR/backend.pid"
        echo "[后端] 已停止"
    else
        echo "[后端] 未运行"
    fi
}

stop_frontend() {
    if check_frontend; then
        pid=$(cat "$PID_DIR/frontend.pid")
        echo "[前端] 正在停止 (PID: $pid)..."
        kill "$pid" 2>/dev/null
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null
        fi
        rm -f "$PID_DIR/frontend.pid"
        echo "[前端] 已停止"
    else
        echo "[前端] 未运行"
    fi
}

show_status() {
    echo "======================================"
    echo "  Stock Query 服务状态"
    echo "======================================"
    if check_backend; then
        echo "  后端: 运行中 (PID: $(cat "$PID_DIR/backend.pid"), 端口: $BACKEND_PORT)"
    else
        echo "  后端: 未运行"
    fi
    if check_frontend; then
        echo "  前端: 运行中 (PID: $(cat "$PID_DIR/frontend.pid"), 端口: $FRONTEND_PORT)"
    else
        echo "  前端: 未运行"
    fi
    echo "======================================"
}

case "${1:-}" in
    start)
        start_backend
        start_frontend
        echo ""
        show_status
        echo ""
        echo "访问地址: http://localhost:$FRONTEND_PORT"
        ;;
    stop)
        stop_frontend
        stop_backend
        ;;
    restart)
        stop_frontend
        stop_backend
        sleep 2
        start_backend
        start_frontend
        echo ""
        show_status
        ;;
    status)
        show_status
        ;;
    backend)
        start_backend
        ;;
    frontend)
        start_frontend
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status|backend|frontend}"
        echo ""
        echo "  start     - 启动前后端服务"
        echo "  stop      - 停止前后端服务"
        echo "  restart   - 重启前后端服务"
        echo "  status    - 查看服务状态"
        echo "  backend   - 仅启动后端"
        echo "  frontend  - 仅启动前端"
        echo ""
        echo "环境变量:"
        echo "  BACKEND_PORT  - 后端端口 (默认: 8002)"
        echo "  FRONTEND_PORT - 前端端口 (默认: 5173)"
        exit 1
        ;;
esac
