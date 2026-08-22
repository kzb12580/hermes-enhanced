"""Hermes Desktop — 统一配置"""

import os

# ─── 网络配置 ────────────────────────────────────────────────────────────
BACKEND_HOST = os.environ.get("HERMES_HOST", "127.0.0.1")
BACKEND_PORT = int(os.environ.get("HERMES_PORT", "9876"))
BACKEND_URL = f"http://{BACKEND_HOST}:{BACKEND_PORT}"

# CORS 允许的来源
CORS_ORIGINS = [
    f"http://127.0.0.1:{BACKEND_PORT}",
    f"http://localhost:{BACKEND_PORT}",
    "http://127.0.0.1:5173",  # Vite dev server
    "http://localhost:5173",
    "http://localhost",
    "http://127.0.0.1",
    "app://.",
    "null",
    "*",  # 本地 127.0.0.1 服务允许 Electron file:// 协议渲染进程跨域
]

# ─── 性能限制 ────────────────────────────────────────────────────────────
MAX_CONTENT_LENGTH = 500_000
MAX_TOOL_RESULT_SIZE = 50_000  # 50KB per tool result
MAX_TOOL_CALLS_PER_TURN = 50
MAX_TOOL_ITERATIONS = 90

# ─── 文件限制 ────────────────────────────────────────────────────────────
MAX_FILE_SIZE = 10_000_000  # 10MB
MAX_EXCEL_ROWS = 500_000
