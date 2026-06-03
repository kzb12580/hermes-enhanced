@echo off
REM Hermes Desktop - Windows 构建脚本
REM 用法: build.bat [platform]
REM platform: win, mac, linux (默认 win)

setlocal enabledelayedexpansion

set PLATFORM=%1
if "%PLATFORM%"=="" set PLATFORM=win

echo ==========================================
echo Hermes Desktop 构建脚本
echo ==========================================

REM 1. 检查依赖
echo [1/5] 检查依赖...
where node >nul 2>&1 || (echo 错误: 未安装 Node.js & exit /b 1)
where python >nul 2>&1 || (echo 错误: 未安装 Python & exit /b 1)
where pip >nul 2>&1 || (echo 错误: 未安装 pip & exit /b 1)

for /f "tokens=*" %%i in ('node --version') do set NODE_VER=%%i
for /f "tokens=*" %%i in ('python --version') do set PY_VER=%%i
echo   Node.js: %NODE_VER%
echo   Python: %PY_VER%

REM 2. 安装 Python 依赖
echo [2/5] 安装 Python 依赖...
cd python-backend
pip install -r requirements.txt pyinstaller==6.14.0 --quiet
cd ..

REM 3. 构建 Python 后端
echo [3/5] 构建 Python 后端 (PyInstaller)...
cd python-backend
pyinstaller build.spec --distpath ..\dist-backend --workpath ..\build-backend --clean
cd ..

REM 4. 安装 Node 依赖
echo [4/5] 安装 Node 依赖...
call npm ci

REM 5. 构建 Electron 应用
echo [5/5] 构建 Electron 应用...
call npm run build
call npx electron-builder --%PLATFORM%

echo ==========================================
echo 构建完成!
echo 输出目录: dist\
echo ==========================================
dir dist\ 2>nul || echo 无输出文件

endlocal
