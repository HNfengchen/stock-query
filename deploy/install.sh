#!/bin/bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DEPLOY_DIR="$PROJECT_DIR/deploy"

PYTHON_PATH=$(which python3 2>/dev/null || which python 2>/dev/null || echo "")
if [ -z "$PYTHON_PATH" ]; then
    echo "[错误] 未找到 Python"
    exit 1
fi

NPM_PATH=$(which npm 2>/dev/null || echo "")
if [ -z "$NPM_PATH" ]; then
    echo "[错误] 未找到 npm"
    exit 1
fi

CURRENT_USER=$(whoami)

CLEAN_PATH="$PYTHON_PATH"
BIN_DIR=$(dirname "$PYTHON_PATH")
CLEAN_PATH="$BIN_DIR:/usr/local/bin:/usr/bin:/bin"

IS_WSL=false
if grep -qi microsoft /proc/version 2>/dev/null; then
    IS_WSL=true
    echo "[检测] WSL2 环境"
fi

HAS_SUDO=false
if command -v sudo &>/dev/null && sudo -n true 2>/dev/null; then
    HAS_SUDO=true
elif command -v sudo &>/dev/null && [ "$(id -u)" -ne 0 ]; then
    echo "[提示] sudo 需要密码，将在需要时提示"
    HAS_SUDO=true
fi

HAS_SYSTEMD=false
if systemctl is-system-running &>/dev/null; then
    HAS_SYSTEMD=true
    echo "[检测] systemd 可用"
elif [ "$IS_WSL" = true ]; then
    echo "[警告] WSL2 中 systemd 未启用，将使用 nohup 方式管理服务"
fi

BACKEND_SERVICE="[Unit]
Description=Stock Query Backend (FastAPI)
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR
ExecStart=$PYTHON_PATH -m uvicorn backend.app:app --host 0.0.0.0 --port 8002 --workers 1
Restart=always
RestartSec=5
Environment=PYTHONPATH=$PROJECT_DIR
Environment=PATH=$CLEAN_PATH
Environment=CORS_ORIGINS=http://localhost:5173,http://127.0.0.1:5173
Environment=HOME=/home/$CURRENT_USER

[Install]
WantedBy=multi-user.target"

FRONTEND_SERVICE="[Unit]
Description=Stock Query Frontend (Static Server + API Proxy)
After=network.target stock-query-backend.service

[Service]
Type=simple
User=$CURRENT_USER
WorkingDirectory=$PROJECT_DIR/frontend
ExecStart=$PYTHON_PATH serve.py
Restart=always
RestartSec=5
Environment=PATH=$CLEAN_PATH
Environment=HOME=/home/$CURRENT_USER
Environment=BACKEND_URL=http://127.0.0.1:8002
Environment=FRONTEND_PORT=5173

[Install]
WantedBy=multi-user.target"

echo "======================================"
echo "  Stock Query 部署脚本"
echo "======================================"
echo ""
echo "项目目录: $PROJECT_DIR"
echo "Python:   $PYTHON_PATH"
echo "npm:      $NPM_PATH"
echo "用户:     $CURRENT_USER"
echo "WSL2:     $IS_WSL"
echo "systemd:  $HAS_SYSTEMD"
echo ""

echo "[1/5] 安装 Python 依赖..."
cd "$PROJECT_DIR"

PIP_CMD="pip3"
if ! command -v pip3 &>/dev/null; then
    PIP_CMD="pip"
fi

$PIP_CMD install --quiet -r "$PROJECT_DIR/requirements.txt"
echo "  核心依赖安装完成"

echo "  检查可选依赖..."
for pkg in lightgbm hmmlearn celery redis; do
    if $PIP_CMD show "$pkg" &>/dev/null; then
        echo "    ✅ $pkg 已安装"
    else
        echo "    ⚠️  $pkg 未安装（可选，不影响核心功能）"
    fi
done

echo ""
echo "[2/5] 安装前端依赖并构建..."
cd "$PROJECT_DIR/frontend"
if [ ! -d "node_modules" ]; then
    npm install
else
    echo "  node_modules 已存在，跳过安装"
fi

if [ ! -d "dist" ]; then
    npm run build
    echo "  前端构建完成"
else
    echo "  dist 已存在，跳过构建（如需重建请删除 dist 目录后重新运行）"
fi

echo ""
echo "[3/5] 停止旧服务..."
PID_DIR="$PROJECT_DIR/.pids"
mkdir -p "$PID_DIR"

if [ "$HAS_SYSTEMD" = true ]; then
    $PIP_CMD show systemd &>/dev/null || true
    if [ "$HAS_SUDO" = true ]; then
        sudo systemctl stop stock-query-backend.service 2>/dev/null || true
        sudo systemctl stop stock-query-frontend.service 2>/dev/null || true
    else
        systemctl --user stop stock-query-backend.service 2>/dev/null || true
        systemctl --user stop stock-query-frontend.service 2>/dev/null || true
    fi
fi

for svc in backend frontend; do
    if [ -f "$PID_DIR/$svc.pid" ]; then
        pid=$(cat "$PID_DIR/$svc.pid")
        if kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_DIR/$svc.pid"
    fi
done
echo "  旧服务已停止"

echo ""
echo "[4/5] 配置服务..."

if [ "$HAS_SYSTEMD" = true ] && [ "$HAS_SUDO" = true ]; then
    echo "  写入 systemd 服务文件..."
    echo "$BACKEND_SERVICE" | sudo tee /etc/systemd/system/stock-query-backend.service > /dev/null
    echo "$FRONTEND_SERVICE" | sudo tee /etc/systemd/system/stock-query-frontend.service > /dev/null
    sudo systemctl daemon-reload
    echo "  systemd 服务配置完成"
elif [ "$HAS_SYSTEMD" = true ]; then
    echo "  写入用户级 systemd 服务文件..."
    mkdir -p ~/.config/systemd/user
    echo "$BACKEND_SERVICE" > ~/.config/systemd/user/stock-query-backend.service
    echo "$FRONTEND_SERVICE" > ~/.config/systemd/user/stock-query-frontend.service
    systemctl --user daemon-reload
    echo "  用户级 systemd 服务配置完成"
else
    echo "  systemd 不可用，将使用 nohup 方式启动"
fi

echo ""
echo "[5/5] 启动服务..."

BACKEND_PORT=${BACKEND_PORT:-8002}
FRONTEND_PORT=${FRONTEND_PORT:-5173}
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$LOG_DIR"

if [ "$HAS_SYSTEMD" = true ] && [ "$HAS_SUDO" = true ]; then
    sudo systemctl enable stock-query-backend.service
    sudo systemctl enable stock-query-frontend.service
    sudo systemctl start stock-query-backend.service
    sleep 3
    sudo systemctl start stock-query-frontend.service
    sleep 3
    echo "  systemd 服务已启动"
elif [ "$HAS_SYSTEMD" = true ]; then
    systemctl --user enable stock-query-backend.service
    systemctl --user enable stock-query-frontend.service
    systemctl --user start stock-query-backend.service
    sleep 3
    systemctl --user start stock-query-frontend.service
    sleep 3
    echo "  用户级 systemd 服务已启动"
fi

if [ "$HAS_SYSTEMD" != true ] || [ "$HAS_SUDO" != true ]; then
    echo "  使用 nohup 启动后端..."
    cd "$PROJECT_DIR"
    nohup $PYTHON_PATH -m uvicorn backend.app:app \
        --host 0.0.0.0 \
        --port "$BACKEND_PORT" \
        --workers 1 \
        > "$LOG_DIR/backend.log" 2>&1 &
    echo $! > "$PID_DIR/backend.pid"

    for i in $(seq 1 15); do
        if curl -s "http://localhost:$BACKEND_PORT/health" > /dev/null 2>&1; then
            echo "  后端启动成功 (PID: $(cat "$PID_DIR/backend.pid"), 端口: $BACKEND_PORT)"
            break
        fi
        sleep 1
    done

    echo "  使用 nohup 启动前端..."
    cd "$PROJECT_DIR/frontend"
    BACKEND_URL="http://127.0.0.1:$BACKEND_PORT" FRONTEND_PORT="$FRONTEND_PORT" \
        nohup $PYTHON_PATH serve.py \
        > "$LOG_DIR/frontend.log" 2>&1 &
    echo $! > "$PID_DIR/frontend.pid"

    for i in $(seq 1 15); do
        if curl -s "http://localhost:$FRONTEND_PORT" > /dev/null 2>&1; then
            echo "  前端启动成功 (PID: $(cat "$PID_DIR/frontend.pid"), 端口: $FRONTEND_PORT)"
            break
        fi
        sleep 1
    done
fi

echo ""
echo "======================================"
echo "  部署完成！"
echo "======================================"
echo ""

if [ "$HAS_SYSTEMD" = true ] && [ "$HAS_SUDO" = true ]; then
    sudo systemctl status stock-query-backend.service --no-pager -l 2>/dev/null | head -5
    echo ""
    sudo systemctl status stock-query-frontend.service --no-pager -l 2>/dev/null | head -5
elif [ "$HAS_SYSTEMD" = true ]; then
    systemctl --user status stock-query-backend.service --no-pager -l 2>/dev/null | head -5
    echo ""
    systemctl --user status stock-query-frontend.service --no-pager -l 2>/dev/null | head -5
else
    if [ -f "$PID_DIR/backend.pid" ]; then
        echo "  后端 PID: $(cat "$PID_DIR/backend.pid")"
    fi
    if [ -f "$PID_DIR/frontend.pid" ]; then
        echo "  前端 PID: $(cat "$PID_DIR/frontend.pid")"
    fi
fi

echo ""
echo "常用命令:"
if [ "$HAS_SYSTEMD" = true ] && [ "$HAS_SUDO" = true ]; then
    echo "  启动: sudo systemctl start stock-query-backend stock-query-frontend"
    echo "  停止: sudo systemctl stop stock-query-backend stock-query-frontend"
    echo "  重启: sudo systemctl restart stock-query-backend stock-query-frontend"
    echo "  状态: sudo systemctl status stock-query-backend stock-query-frontend"
    echo "  日志: journalctl -u stock-query-backend -f"
elif [ "$HAS_SYSTEMD" = true ]; then
    echo "  启动: systemctl --user start stock-query-backend stock-query-frontend"
    echo "  停止: systemctl --user stop stock-query-backend stock-query-frontend"
    echo "  重启: systemctl --user restart stock-query-backend stock-query-frontend"
    echo "  状态: systemctl --user status stock-query-backend stock-query-frontend"
    echo "  日志: journalctl --user -u stock-query-backend -f"
else
    echo "  启动: $PROJECT_DIR/start.sh start"
    echo "  停止: $PROJECT_DIR/start.sh stop"
    echo "  状态: $PROJECT_DIR/start.sh status"
fi
echo ""
echo "访问地址: http://localhost:$FRONTEND_PORT"
