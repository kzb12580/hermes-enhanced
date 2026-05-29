"""
Hermes Desktop PC 自动化集成模块 — 已修复导入崩溃问题
"""

# 安全导入，缺失依赖时不崩溃
GUI_TOOLS = {}
OFFICE_TOOLS = {}

try:
    from .gui_tools import GUI_TOOLS
except ImportError:
    try:
        from gui_tools import GUI_TOOLS
    except ImportError:
        pass

try:
    from .office_tools import OFFICE_TOOLS
except ImportError:
    try:
        from office_tools import OFFICE_TOOLS
    except ImportError:
        pass

ALL_DESKTOP_TOOLS = {}
ALL_DESKTOP_TOOLS.update(GUI_TOOLS)
ALL_DESKTOP_TOOLS.update(OFFICE_TOOLS)
TOOL_COUNT = len(ALL_DESKTOP_TOOLS)


def check_dependencies() -> dict:
    """检查所有依赖是否安装"""
    deps = {
        "pyautogui": "pip install pyautogui",
        "pygetwindow": "pip install pygetwindow",
        "pyperclip": "pip install pyperclip",
        "PIL": "pip install Pillow",
        "docx": "pip install python-docx",
        "pptx": "pip install python-pptx",
        "openpyxl": "pip install openpyxl",
        "pytesseract": "pip install pytesseract",
        "transformers": "pip install transformers",
        "torch": "pip install torch",
        "cv2": "pip install opencv-python-headless",
    }
    installed, missing = {}, {}
    for pkg, cmd in deps.items():
        try:
            __import__(pkg)
            installed[pkg] = True
        except ImportError:
            missing[pkg] = cmd
    return {
        "installed": list(installed.keys()),
        "missing": missing,
        "total": len(deps), "ok": len(installed), "need_install": len(missing),
    }


def install_all():
    """安装所有依赖"""
    import subprocess
    packages = [
        "pyautogui", "pygetwindow", "pyperclip", "Pillow",
        "python-docx", "python-pptx", "openpyxl", "pytesseract",
        "transformers", "torch", "torchvision", "opencv-python-headless", "peft",
    ]
    result = subprocess.run(["pip", "install"] + packages, capture_output=True, text=True)
    return {"installed": packages, "returncode": result.returncode, "stderr": result.stderr[-500:] if result.stderr else ""}
