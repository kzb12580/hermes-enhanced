"""
网络代理管理 — 统一代理检测/配置，贯穿安装、模型下载、API调用
支持: 系统代理 / Clash / V2Ray / 手动配置 / 环境变量
"""
import os
import re
import json
import socket
import logging
import platform
from typing import Optional
from pathlib import Path

_log = logging.getLogger(__name__)

# ── 代理检测 ──────────────────────────────────────────────────────────────

def _try_connect(host: str, port: int, timeout: float = 1.0) -> bool:
    """测试端口是否可达"""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (OSError, socket.timeout):
        return False


def detect_clash() -> Optional[str]:
    """检测 Clash/V2Ray/Mihomo 常见端口"""
    common_ports = [
        ("127.0.0.1", 7890),   # Clash 默认
        ("127.0.0.1", 7891),   # Clash 备用
        ("127.0.0.1", 7897),   # Clash Verge
        ("127.0.0.1", 10808),  # V2RayN HTTP
        ("127.0.0.1", 10809),  # V2RayN SOCKS
        ("127.0.0.1", 1080),   # SOCKS5 通用
        ("127.0.0.1", 8080),   # HTTP 通用
        ("127.0.0.1", 1087),   # macOS ClashX
        ("127.0.0.1", 9090),   # Clash API
    ]
    for host, port in common_ports:
        if _try_connect(host, port):
            proto = "http" if port in (7890, 7891, 7897, 10808, 8080, 1087) else "socks5"
            proxy_url = f"{proto}://{host}:{port}"
            _log.info(f"检测到代理: {proxy_url}")
            return proxy_url
    return None


def detect_system_proxy() -> Optional[str]:
    """检测系统代理设置"""
    system = platform.system()

    if system == "Windows":
        try:
            import winreg
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
            )
            enabled, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if enabled:
                server, _ = winreg.QueryValueEx(key, "ProxyServer")
                if server:
                    proxy = server if "://" in server else f"http://{server}"
                    _log.info(f"Windows 系统代理: {proxy}")
                    return proxy
        except Exception:
            pass

    elif system == "Darwin":
        try:
            import subprocess
            result = subprocess.run(
                ["networksetup", "-getwebproxy", "Wi-Fi"],
                capture_output=True, text=True, timeout=5
            )
            for line in result.stdout.split("\n"):
                if "Enabled: Yes" in line:
                    # 获取代理服务器
                    result2 = subprocess.run(
                        ["networksetup", "-getwebproxy", "Wi-Fi"],
                        capture_output=True, text=True, timeout=5
                    )
                    for line2 in result2.stdout.split("\n"):
                        if "Server:" in line2:
                            server = line2.split("Server:")[1].strip()
                            if server:
                                proxy = f"http://{server}:80"
                                _log.info(f"macOS 系统代理: {proxy}")
                                return proxy
        except Exception:
            pass

    elif system == "Linux":
        # 检查环境变量
        for var in ["http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY"]:
            val = os.environ.get(var)
            if val:
                _log.info(f"Linux 环境变量代理: {val}")
                return val

    return None


def detect_env_proxy() -> Optional[str]:
    """从环境变量读取代理"""
    for var in ["http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                "all_proxy", "ALL_PROXY"]:
        val = os.environ.get(var)
        if val:
            return val
    return None


def get_proxy(preferred: Optional[str] = None) -> Optional[str]:
    """
    获取代理 URL，优先级：
    1. 用户手动指定
    2. 保存的配置文件
    3. 环境变量
    4. 自动检测 Clash/V2Ray
    5. 系统代理
    """
    if preferred:
        return preferred

    # 读取配置文件
    config = load_network_config()
    if config.get("proxy"):
        return config["proxy"]
    if config.get("proxy_mode") == "disabled":
        return None

    # 环境变量
    env_proxy = detect_env_proxy()
    if env_proxy:
        return env_proxy

    # 自动检测
    if config.get("proxy_mode", "auto") == "auto":
        clash = detect_clash()
        if clash:
            return clash
        sys_proxy = detect_system_proxy()
        if sys_proxy:
            return sys_proxy

    return None


# ── 配置持久化 ────────────────────────────────────────────────────────────

_CONFIG_DIR = Path.home() / ".hermes" / "desktop"
_CONFIG_FILE = _CONFIG_DIR / "network.json"

# HuggingFace 镜像源
HF_MIRRORS = {
    "official": "https://huggingface.co",
    "hf-mirror": "https://hf-mirror.com",
    "modelscope": "https://modelscope.cn",  # 不同协议，仅作参考
}

# PyPI 镜像源
PYPI_MIRRORS = {
    "official": "https://pypi.org/simple",
    "aliyun": "https://mirrors.aliyun.com/pypi/simple",
    "tuna": "https://pypi.tuna.tsinghua.edu.cn/simple",
    "ustc": "https://pypi.mirrors.ustc.edu.cn/simple",
    "douban": "https://pypi.douban.com/simple",
}


def load_network_config() -> dict:
    """加载网络配置"""
    if _CONFIG_FILE.exists():
        try:
            return json.loads(_CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_network_config(config: dict):
    """保存网络配置"""
    _CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    existing = load_network_config()
    existing.update(config)
    _CONFIG_FILE.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")
    _log.info(f"网络配置已保存: {_CONFIG_FILE}")


def get_hf_mirror() -> str:
    """获取 HuggingFace 镜像地址"""
    config = load_network_config()
    mirror_key = config.get("hf_mirror", "official")
    if mirror_key in HF_MIRRORS:
        return HF_MIRRORS[mirror_key]
    # 自定义 URL
    if mirror_key.startswith("http"):
        return mirror_key
    return HF_MIRRORS["official"]


def get_pypi_mirror() -> str:
    """获取 PyPI 镜像地址"""
    config = load_network_config()
    mirror_key = config.get("pypi_mirror", "official")
    if mirror_key in PYPI_MIRRORS:
        return PYPI_MIRRORS[mirror_key]
    if mirror_key.startswith("http"):
        return mirror_key
    return PYPI_MIRRORS["official"]


def apply_proxy_to_env(proxy: Optional[str] = None):
    """将代理设置应用到当前进程环境变量"""
    proxy = proxy or get_proxy()
    if proxy:
        os.environ["http_proxy"] = proxy
        os.environ["HTTP_PROXY"] = proxy
        os.environ["https_proxy"] = proxy
        os.environ["HTTPS_PROXY"] = proxy
        os.environ["all_proxy"] = proxy
        os.environ["ALL_PROXY"] = proxy
        _log.info(f"已设置代理: {proxy}")
    else:
        for var in ["http_proxy", "HTTP_PROXY", "https_proxy", "HTTPS_PROXY",
                    "all_proxy", "ALL_PROXY"]:
            os.environ.pop(var, None)


def apply_hf_mirror_to_env():
    """设置 HuggingFace 镜像环境变量"""
    mirror = get_hf_mirror()
    if mirror != HF_MIRRORS["official"]:
        os.environ["HF_ENDPOINT"] = mirror
        _log.info(f"HuggingFace 镜像: {mirror}")


def apply_pypi_mirror_to_args(args: list[str]) -> list[str]:
    """给 pip install 命令注入镜像源参数"""
    mirror = get_pypi_mirror()
    if mirror != PYPI_MIRRORS["official"]:
        args = args + ["-i", mirror, "--trusted-host", mirror.split("//")[1].split("/")[0]]
    return args


# ── 网络诊断 ──────────────────────────────────────────────────────────────

def diagnose() -> dict:
    """网络诊断 — 检测所有关键网络连接"""
    results = {
        "proxy": None,
        "hf_mirror": get_hf_mirror(),
        "pypi_mirror": get_pypi_mirror(),
        "tests": [],
    }

    proxy = get_proxy()
    results["proxy"] = proxy

    # 测试 HuggingFace
    import urllib.request
    tests = [
        ("HuggingFace", get_hf_mirror()),
        ("PyPI", get_pypi_mirror()),
        ("OpenAI API", "https://api.openai.com/v1"),
    ]

    for name, url in tests:
        try:
            handler = urllib.request.ProxyHandler({"https": proxy} if proxy else {})
            opener = urllib.request.build_opener(handler)
            req = urllib.request.Request(url, method="HEAD")
            resp = opener.open(req, timeout=10)
            results["tests"].append({
                "name": name,
                "url": url,
                "ok": True,
                "status": resp.status,
            })
        except Exception as e:
            results["tests"].append({
                "name": name,
                "url": url,
                "ok": False,
                "error": str(e)[:100],
            })

    return results
