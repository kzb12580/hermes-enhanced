#!/bin/bash
# Hermes Desktop - 本地构建脚本
# 用法: ./build.sh [platform]
# platform: win, mac, linux (默认当前平台)

set -e

PLATFORM=${1:-""}
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=========================================="
echo "Hermes Desktop 构建脚本"
echo "=========================================="

# 1. 检查依赖
echo "[1/5] 检查依赖..."
command -v node >/dev/null 2>&1 || { echo "错误: 未安装 Node.js"; exit 1; }
command -v python3 >/dev/null 2>&1 || { echo "错误: 未安装 Python3"; exit 1; }
command -v pip3 >/dev/null 2>&1 || { echo "错误: 未安装 pip3"; exit 1; }

echo "  Node.js: $(node --version)"
echo "  Python: $(python3 --version)"

# 2. 安装 Python 依赖
echo "[2/5] 安装 Python 依赖..."
cd python-backend
pip3 install -r requirements.txt pyinstaller==6.14.0 --quiet
cd ..

# 3. 构建 Python 后端
echo "[3/5] 构建 Python 后端 (PyInstaller)..."
cd python-backend
pyinstaller build.spec --distpath ../dist-backend --workpath ../build-backend --clean
cd ..

# 4. 安装 Node 依赖
echo "[4/5] 安装 Node 依赖..."
npm ci

# 5. 构建 Electron 应用
echo "[5/5] 构建 Electron 应用..."
if [ -n "$PLATFORM" ]; then
    npm run build
    npx electron-builder --$PLATFORM
else
    npm run build
    npx electron-builder
fi

echo "=========================================="
echo "构建完成!"
echo "输出目录: dist/"
echo "=========================================="
ls -la dist/ 2>/dev/null || echo "无输出文件"
