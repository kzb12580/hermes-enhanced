"""Hermes Desktop — 全面日志系统

日志文件分流：
- desktop-backend.log  — 全量日志（INFO+，轮转 10MB×5）
- desktop-llm.log      — LLM 调用详情（请求/响应/token/耗时）
- desktop-tools.log    — 工具执行详情（入参/出参/耗时/成功失败）
- desktop-errors.log   — 错误日志（ERROR+，轮转 5MB×3）
- desktop-api.log      — HTTP 请求日志（中间件记录）

使用方式：
    from logger import get_logger
    logger = get_logger("chat")
    logger.info("xxx")
"""

import logging
import logging.handlers
import os
import sys
from pathlib import Path

# ── 日志目录 ────────────────────────────────────────────────────────────────

LOG_DIR = Path.home() / ".hermes" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ── 日志格式 ────────────────────────────────────────────────────────────────

# 详细格式：含行号和函数名
DETAILED_FMT = logging.Formatter(
    "%(asctime)s  %(levelname)-7s  [%(name)s]  %(funcName)s:%(lineno)d  %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

# 简洁格式：控制台用
CONSOLE_FMT = logging.Formatter(
    "%(asctime)s  %(levelname)-7s  [%(name)s]  %(message)s",
    datefmt="%H:%M:%S",
)

# ── Handler 工厂 ────────────────────────────────────────────────────────────

def _make_file_handler(
    filename: str,
    level: int = logging.DEBUG,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
    fmt: logging.Formatter = DETAILED_FMT,
) -> logging.handlers.RotatingFileHandler:
    """创建带轮转的文件 handler"""
    handler = logging.handlers.RotatingFileHandler(
        LOG_DIR / filename,
        maxBytes=max_bytes,
        backupCount=backup_count,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(fmt)
    return handler


def _make_console_handler(level: int = logging.INFO) -> logging.StreamHandler:
    """创建控制台 handler"""
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(level)
    handler.setFormatter(CONSOLE_FMT)
    return handler


# ── 专用 Logger ─────────────────────────────────────────────────────────────

def _setup_logger(
    name: str,
    handlers: list[logging.Handler],
    level: int = logging.DEBUG,
) -> logging.Logger:
    """配置并返回一个 logger"""
    logger = logging.getLogger(name)
    logger.setLevel(level)
    logger.propagate = False  # 不向上冒泡，避免重复输出
    for h in handlers:
        logger.addHandler(h)
    return logger


# 全量日志 — 记录一切
_all_handler = _make_file_handler("desktop-backend.log", level=logging.DEBUG)
_console_handler = _make_console_handler(level=logging.INFO)

# LLM 专用日志
_llm_handler = _make_file_handler(
    "desktop-llm.log", level=logging.DEBUG,
    max_bytes=20 * 1024 * 1024, backup_count=3,
)

# 工具专用日志
_tools_handler = _make_file_handler(
    "desktop-tools.log", level=logging.DEBUG,
    max_bytes=10 * 1024 * 1024, backup_count=3,
)

# 错误日志
_error_handler = _make_file_handler(
    "desktop-errors.log", level=logging.ERROR,
    max_bytes=5 * 1024 * 1024, backup_count=3,
)

# API 请求日志
_api_handler = _make_file_handler(
    "desktop-api.log", level=logging.DEBUG,
    max_bytes=10 * 1024 * 1024, backup_count=3,
)

# ── Root Logger 配置（兜底） ────────────────────────────────────────────────

_root = logging.getLogger()
_root.setLevel(logging.DEBUG)
# 清除可能存在的默认 handler
_root.handlers.clear()
_root.addHandler(_all_handler)
_root.addHandler(_console_handler)
_root.addHandler(_error_handler)

# ── 公共接口 ────────────────────────────────────────────────────────────────

def get_logger(name: str) -> logging.Logger:
    """获取一个命名 logger，自动挂载全量+控制台+错误 handler。
    
    特殊 name 会额外挂载专用 handler：
    - "llm" / "hermes-backend.llm"  → llm.log
    - "tools" / 包含 "tools"        → tools.log
    - "api" / 包含 "api"            → api.log
    """
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    # 避免重复添加
    if not logger.handlers:
        logger.addHandler(_all_handler)
        logger.addHandler(_console_handler)
        logger.addHandler(_error_handler)

        # 专用 handler
        name_lower = name.lower()
        if "llm" in name_lower:
            logger.addHandler(_llm_handler)
        if "tool" in name_lower:
            logger.addHandler(_tools_handler)
        if "api" in name_lower:
            logger.addHandler(_api_handler)

    return logger


def get_log_dir() -> Path:
    """返回日志目录路径"""
    return LOG_DIR


def get_log_files() -> dict[str, str]:
    """返回所有日志文件路径"""
    return {
        "all": str(LOG_DIR / "desktop-backend.log"),
        "llm": str(LOG_DIR / "desktop-llm.log"),
        "tools": str(LOG_DIR / "desktop-tools.log"),
        "errors": str(LOG_DIR / "desktop-errors.log"),
        "api": str(LOG_DIR / "desktop-api.log"),
    }


# ── 启动时记录日志配置 ──────────────────────────────────────────────────────

_boot_logger = get_logger("hermes-backend.init")
_boot_logger.info("日志系统初始化完成")
_boot_logger.info("日志目录: %s", LOG_DIR)
for name, path in get_log_files().items():
    _boot_logger.info("  %s → %s", name, path)


# ── 自动清理旧日志 ────────────────────────────────────────────────────────

def cleanup_old_logs(max_age_days: int = 30):
    """删除超过 max_age_days 天的 .log.1 .log.2 等轮转旧文件"""
    import glob
    import time as _time
    cutoff = _time.time() - max_age_days * 86400
    removed = 0
    for f in glob.glob(str(LOG_DIR / "*.log.*")):
        try:
            if os.path.getmtime(f) < cutoff:
                os.remove(f)
                removed += 1
        except OSError:
            pass
    if removed:
        _boot_logger.info("清理了 %d 个超过 %d 天的旧日志文件", removed, max_age_days)


cleanup_old_logs()
