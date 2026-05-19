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
SUDO_OK=false
if command -v sudo &>/dev/null; then
    if sudo -n true 2>/dev/null; then
        HAS_SUDO=true
        SUDO_OK=true
    elif [ "$(id -u)" -ne 0 ]; then
        echo "[提示] sudo 需要密码，将在需要时提示"
        HAS_SUDO=true
        if echo "" | sudo -S true 2>/dev/null; then
            SUDO_OK=true
        fi
    fi
fi

HAS_SYSTEMD=false
SYSTEMD_SCOPE=""
if systemctl is-system-running &>/dev/null; then
    HAS_SYSTEMD=true
    SYSTEMD_SCOPE="system"
    echo "[检测] systemd 可用"
elif systemctl is-system-running 2>/dev/null | grep -qE '^(degraded|maintenance)'; then
    HAS_SYSTEMD=true
    SYSTEMD_SCOPE="system"
    echo "[检测] systemd 可用（状态: $(systemctl is-system-running 2>/dev/null)）"
elif pidof systemd &>/dev/null; then
    HAS_SYSTEMD=true
    SYSTEMD_SCOPE="system"
    echo "[检测] systemd 进程存在"
elif [ "$IS_WSL" = true ]; then
    echo "[警告] WSL2 中 systemd 未启用，将使用 nohup 方式管理服务"
fi

if [ "$HAS_SYSTEMD" = true ] && [ "$SUDO_OK" = false ]; then
    if systemctl --user is-system-running &>/dev/null || systemctl --user list-units &>/dev/null 2>&1; then
        SYSTEMD_SCOPE="user"
        echo "[检测] 使用用户级 systemd"
    else
        HAS_SYSTEMD=false
        echo "[警告] 用户级 systemd 不可用，将使用 nohup 方式管理服务"
    fi
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

BACKEND_PORT=${BACKEND_PORT:-8002}
FRONTEND_PORT=${FRONTEND_PORT:-5173}

echo "======================================"
echo "  Stock Query 部署脚本"
echo "======================================"
echo ""
echo "项目目录: $PROJECT_DIR"
echo "Python:   $PYTHON_PATH"
echo "npm:      $NPM_PATH"
echo "用户:     $CURRENT_USER"
echo "WSL2:     $IS_WSL"
echo "systemd:  $HAS_SYSTEMD ($SYSTEMD_SCOPE)"
echo ""

echo "[1/7] 安装 Python 依赖..."
cd "$PROJECT_DIR"
rm -rf logs

PIP_CMD="pip3"
if ! command -v pip3 &>/dev/null; then
    PIP_CMD="pip"
fi

$PIP_CMD install --quiet -r "$PROJECT_DIR/requirements.txt" || {
    echo "  [错误] Python 依赖安装失败，请检查 requirements.txt 和网络连接"
    exit 1
}
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
echo "[2/7] 安装前端依赖并构建..."
cd "$PROJECT_DIR/frontend"
npm install || {
    echo "  [错误] npm install 失败"
    exit 1
}
rm -rf dist
npm run build || {
    echo "  [错误] 前端构建失败"
    exit 1
}
echo "  前端构建完成"

echo ""
echo "[3/7] 停止旧服务（所有启动方式）..."
PID_DIR="$PROJECT_DIR/.pids"
LOG_DIR="$PROJECT_DIR/logs"
mkdir -p "$PID_DIR" "$LOG_DIR"

echo "  停止系统级 systemd 服务..."
sudo systemctl stop stock-query-backend.service 2>/dev/null || true
sudo systemctl stop stock-query-frontend.service 2>/dev/null || true

echo "  停止用户级 systemd 服务..."
systemctl --user stop stock-query-backend.service 2>/dev/null || true
systemctl --user stop stock-query-frontend.service 2>/dev/null || true

echo "  停止 nohup 进程..."
for svc in backend frontend; do
    if [ -f "$PID_DIR/$svc.pid" ]; then
        pid=$(cat "$PID_DIR/$svc.pid") || pid=""
        if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
            kill "$pid" 2>/dev/null || true
            sleep 1
            kill -9 "$pid" 2>/dev/null || true
        fi
        rm -f "$PID_DIR/$svc.pid"
    fi
done

echo "  清理残留进程（按端口匹配）..."
for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    pid=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | head -1) || pid=""
    if [ -n "$pid" ]; then
        echo "    端口 $port 仍有进程 $pid，终止..."
        kill "$pid" 2>/dev/null || true
        sleep 1
        kill -9 "$pid" 2>/dev/null || true
    fi
done

echo "  旧服务已停止"

echo ""
echo "[4/7] 检查并释放端口..."

_wait_for_port() {
    local port=$1
    local max_wait=10
    local waited=0
    while ss -tlnp 2>/dev/null | grep -q ":${port} " && [ $waited -lt $max_wait ]; do
        sleep 1
        waited=$((waited + 1))
    done
    if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
        return 1
    fi
    return 0
}

for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
    pid=$(ss -tlnp 2>/dev/null | grep ":${port} " | grep -oP 'pid=\K[0-9]+' | head -1) || pid=""
    if [ -n "$pid" ]; then
        echo "  端口 $port 被进程 $pid 占用，正在终止..."
        kill "$pid" 2>/dev/null || true
        sleep 2
        if kill -0 "$pid" 2>/dev/null; then
            kill -9 "$pid" 2>/dev/null || true
            sleep 1
        fi
        if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            echo "  [警告] 端口 $port 仍被占用，尝试 fuser..."
            fuser -k "${port}/tcp" 2>/dev/null || true
            sleep 1
        fi
        if ! _wait_for_port "$port"; then
            echo "  [错误] 无法释放端口 $port，请手动处理"
            exit 1
        fi
        echo "  端口 $port 已释放"
    else
        echo "  端口 $port 可用"
    fi
done

echo ""
echo "[5/7] 配置服务..."

if [ "$HAS_SYSTEMD" = true ]; then
    if [ "$SYSTEMD_SCOPE" = "system" ] && [ "$SUDO_OK" = true ]; then
        echo "  写入系统级 systemd 服务文件..."
        if echo "$BACKEND_SERVICE" | sudo tee /etc/systemd/system/stock-query-backend.service > /dev/null 2>&1 && \
           echo "$FRONTEND_SERVICE" | sudo tee /etc/systemd/system/stock-query-frontend.service > /dev/null 2>&1 && \
           sudo systemctl daemon-reload 2>/dev/null; then
            echo "  系统级 systemd 服务配置完成"
            echo "  禁用用户级 systemd 服务（互斥）..."
            systemctl --user disable stock-query-backend.service 2>/dev/null || true
            systemctl --user disable stock-query-frontend.service 2>/dev/null || true
            rm -f ~/.config/systemd/user/stock-query-backend.service 2>/dev/null || true
            rm -f ~/.config/systemd/user/stock-query-frontend.service 2>/dev/null || true
            systemctl --user daemon-reload 2>/dev/null || true
        else
            echo "  [警告] sudo 写入失败，切换到用户级 systemd"
            SUDO_OK=false
            HAS_SUDO=false
            SYSTEMD_SCOPE="user"
        fi
    fi

    if [ "$SYSTEMD_SCOPE" = "user" ]; then
        echo "  写入用户级 systemd 服务文件..."
        if mkdir -p ~/.config/systemd/user 2>/dev/null && \
           echo "$BACKEND_SERVICE" > ~/.config/systemd/user/stock-query-backend.service 2>/dev/null && \
           echo "$FRONTEND_SERVICE" > ~/.config/systemd/user/stock-query-frontend.service 2>/dev/null && \
           systemctl --user daemon-reload 2>/dev/null; then
            echo "  用户级 systemd 服务配置完成"
            echo "  禁用系统级 systemd 服务（互斥）..."
            sudo systemctl disable stock-query-backend.service 2>/dev/null || true
            sudo systemctl disable stock-query-frontend.service 2>/dev/null || true
        else
            echo "  [警告] 用户级 systemd 失败，将使用 nohup 方式"
            HAS_SYSTEMD=false
        fi
    fi
fi

if [ "$HAS_SYSTEMD" = false ]; then
    echo "  禁用所有 systemd 服务（使用 nohup 模式）..."
    sudo systemctl disable stock-query-backend.service 2>/dev/null || true
    sudo systemctl disable stock-query-frontend.service 2>/dev/null || true
    systemctl --user disable stock-query-backend.service 2>/dev/null || true
    systemctl --user disable stock-query-frontend.service 2>/dev/null || true
    rm -f ~/.config/systemd/user/stock-query-backend.service 2>/dev/null || true
    rm -f ~/.config/systemd/user/stock-query-frontend.service 2>/dev/null || true
    systemctl --user daemon-reload 2>/dev/null || true
    echo "  systemd 服务已禁用，将使用 nohup"
fi

echo ""
echo "[6/7] 启动服务..."

if [ "$HAS_SYSTEMD" = true ]; then
    if [ "$SYSTEMD_SCOPE" = "system" ] && [ "$SUDO_OK" = true ]; then
        sudo systemctl enable stock-query-backend.service 2>/dev/null || true
        sudo systemctl enable stock-query-frontend.service 2>/dev/null || true
        if sudo systemctl start stock-query-backend.service 2>/dev/null; then
            sleep 3
            sudo systemctl start stock-query-frontend.service 2>/dev/null || echo "  [警告] start frontend 失败"
            sleep 3
            echo "  systemd 服务已启动"
        else
            echo "  [警告] sudo systemctl start 失败，切换到 nohup"
            HAS_SYSTEMD=false
        fi
    elif [ "$SYSTEMD_SCOPE" = "user" ]; then
        systemctl --user enable stock-query-backend.service 2>/dev/null || true
        systemctl --user enable stock-query-frontend.service 2>/dev/null || true
        if systemctl --user start stock-query-backend.service 2>/dev/null; then
            sleep 3
            systemctl --user start stock-query-frontend.service 2>/dev/null || echo "  [警告] start frontend 失败"
            sleep 3
            echo "  用户级 systemd 服务已启动"
        else
            echo "  [警告] 用户级 systemctl start 失败，切换到 nohup"
            HAS_SYSTEMD=false
        fi
    fi
fi

if [ "$HAS_SYSTEMD" = false ]; then
    echo "  使用 nohup 启动服务..."

    for port in "$BACKEND_PORT" "$FRONTEND_PORT"; do
        if ss -tlnp 2>/dev/null | grep -q ":${port} "; then
            echo "  [错误] 端口 $port 仍被占用，无法启动"
            exit 1
        fi
    done

    cd "$PROJECT_DIR"
    nohup "$PYTHON_PATH" -m uvicorn backend.app:app --host 0.0.0.0 --port "$BACKEND_PORT" --workers 1 \
        >> "$LOG_DIR/backend.log" 2>&1 &
    BACKEND_PID=$!
    echo "$BACKEND_PID" > "$PID_DIR/backend.pid"
    echo "  后端已启动 (PID: $BACKEND_PID, 端口: $BACKEND_PORT)"

    sleep 3

    if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
        echo "  [错误] 后端进程启动后立即退出，请检查日志: $LOG_DIR/backend.log"
        cat "$LOG_DIR/backend.log" | tail -20
        exit 1
    fi

    cd "$PROJECT_DIR/frontend"
    nohup "$PYTHON_PATH" serve.py \
        >> "$LOG_DIR/frontend.log" 2>&1 &
    FRONTEND_PID=$!
    echo "$FRONTEND_PID" > "$PID_DIR/frontend.pid"
    echo "  前端已启动 (PID: $FRONTEND_PID, 端口: $FRONTEND_PORT)"

    sleep 2

    if ! kill -0 "$FRONTEND_PID" 2>/dev/null; then
        echo "  [错误] 前端进程启动后立即退出，请检查日志: $LOG_DIR/frontend.log"
        cat "$LOG_DIR/frontend.log" | tail -20
        exit 1
    fi

    echo "  nohup 服务已启动"
fi

echo ""
echo "[7/7] 验证服务..."

sleep 2

BACKEND_OK=false
FRONTEND_OK=false

if curl -sf "http://127.0.0.1:$BACKEND_PORT/api/health" > /dev/null 2>&1; then
    BACKEND_OK=true
    echo "  ✅ 后端健康检查通过 (http://127.0.0.1:$BACKEND_PORT)"
else
    if curl -sf "http://127.0.0.1:$BACKEND_PORT/" > /dev/null 2>&1; then
        BACKEND_OK=true
        echo "  ✅ 后端响应正常 (http://127.0.0.1:$BACKEND_PORT)"
    else
        echo "  ⚠️  后端未响应 (http://127.0.0.1:$BACKEND_PORT)，可能仍在启动中"
    fi
fi

if curl -sf "http://127.0.0.1:$FRONTEND_PORT/" > /dev/null 2>&1; then
    FRONTEND_OK=true
    echo "  ✅ 前端响应正常 (http://127.0.0.1:$FRONTEND_PORT)"
else
    echo "  ⚠️  前端未响应 (http://127.0.0.1:$FRONTEND_PORT)，可能仍在启动中"
fi

echo ""
echo "======================================"
echo "  部署完成！"
echo "======================================"
echo ""

if [ "$HAS_SYSTEMD" = true ]; then
    if [ "$SYSTEMD_SCOPE" = "system" ] && [ "$SUDO_OK" = true ]; then
        sudo systemctl status stock-query-backend.service --no-pager -l 2>/dev/null | head -5 || true
        echo ""
        sudo systemctl status stock-query-frontend.service --no-pager -l 2>/dev/null | head -5 || true
    elif [ "$SYSTEMD_SCOPE" = "user" ]; then
        systemctl --user status stock-query-backend.service --no-pager -l 2>/dev/null | head -5 || true
        echo ""
        systemctl --user status stock-query-frontend.service --no-pager -l 2>/dev/null | head -5 || true
    fi
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
if [ "$HAS_SYSTEMD" = true ]; then
    if [ "$SYSTEMD_SCOPE" = "system" ] && [ "$SUDO_OK" = true ]; then
        echo "  启动: sudo systemctl start stock-query-backend stock-query-frontend"
        echo "  停止: sudo systemctl stop stock-query-backend stock-query-frontend"
        echo "  重启: sudo systemctl restart stock-query-backend stock-query-frontend"
        echo "  状态: sudo systemctl status stock-query-backend stock-query-frontend"
        echo "  日志: journalctl -u stock-query-backend -f"
    else
        echo "  启动: systemctl --user start stock-query-backend stock-query-frontend"
        echo "  停止: systemctl --user stop stock-query-backend stock-query-frontend"
        echo "  重启: systemctl --user restart stock-query-backend stock-query-frontend"
        echo "  状态: systemctl --user status stock-query-backend stock-query-frontend"
        echo "  日志: journalctl --user -u stock-query-backend -f"
    fi
else
    echo "  启动: bash $DEPLOY_DIR/install.sh"
    echo "  停止: kill \$(cat $PID_DIR/backend.pid) \$(cat $PID_DIR/frontend.pid)"
    echo "  日志: tail -f $LOG_DIR/backend.log"
fi
echo ""
echo "访问地址: http://localhost:$FRONTEND_PORT"
