#!/bin/bash
set -e

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
CURRENT_PATH="$PATH"

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
Environment=PATH=$CURRENT_PATH
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
Environment=PATH=$CURRENT_PATH
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
echo ""

echo "[1/4] 安装 Python 依赖..."
cd "$PROJECT_DIR"
pip install -r backend/requirements.txt 2>/dev/null || pip3 install -r backend/requirements.txt
pip install pyyaml pandas numpy akshare efinance 2>/dev/null || pip3 install pyyaml pandas numpy akshare efinance
echo "  完成"

echo ""
echo "[2/4] 安装前端依赖并构建..."
cd "$PROJECT_DIR/frontend"
npm install --silent 2>/dev/null
npm run build
echo "  完成"

echo ""
echo "[3/4] 配置 systemd 服务..."
echo "$BACKEND_SERVICE" | sudo tee /etc/systemd/system/stock-query-backend.service > /dev/null
echo "$FRONTEND_SERVICE" | sudo tee /etc/systemd/system/stock-query-frontend.service > /dev/null
sudo systemctl daemon-reload
echo "  完成"

echo ""
echo "[4/4] 启用开机自启动并启动服务..."
sudo systemctl enable stock-query-backend.service
sudo systemctl enable stock-query-frontend.service
sudo systemctl restart stock-query-backend.service
sleep 3
sudo systemctl restart stock-query-frontend.service
sleep 3
echo "  完成"

echo ""
echo "======================================"
echo "  部署完成！"
echo "======================================"
echo ""
sudo systemctl status stock-query-backend.service --no-pager -l 2>/dev/null | head -5
echo ""
sudo systemctl status stock-query-frontend.service --no-pager -l 2>/dev/null | head -5
echo ""
echo "常用命令:"
echo "  启动: sudo systemctl start stock-query-backend stock-query-frontend"
echo "  停止: sudo systemctl stop stock-query-backend stock-query-frontend"
echo "  重启: sudo systemctl restart stock-query-backend stock-query-frontend"
echo "  状态: sudo systemctl status stock-query-backend stock-query-frontend"
echo "  日志: journalctl -u stock-query-backend -f"
echo ""
echo "访问地址: http://localhost:5173"
