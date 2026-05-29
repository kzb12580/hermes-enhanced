"""
Hermes Desktop PC 自动化集成模块
将 GUI + Office 工具注册到 Hermes 工具系统
"""

from gui_tools import GUI_TOOLS
from office_tools import OFFICE_TOOLS

# 所有桌面自动化工具
ALL_DESKTOP_TOOLS = {}
ALL_DESKTOP_TOOLS.update(GUI_TOOLS)
ALL_DESKTOP_TOOLS.update(OFFICE_TOOLS)

# 工具总数
TOOL_COUNT = len(ALL_DESKTOP_TOOLS)

def register_to_hermes(agent):
    """将工具注册到 Hermes Agent"""
    for name, tool_def in ALL_DESKTOP_TOOLS.items():
        agent.register_tool(
            name=name,
            fn=tool_def["fn"],
            description=tool_def["description"],
            concurrency=tool_def["concurrency"],
        )
    return TOOL_COUNT


# 依赖检查
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
        "transformers": "pip install transformers torch",
    }
    installed = {}
    missing = {}
    for pkg, install_cmd in deps.items():
        try:
            __import__(pkg)
            installed[pkg] = True
        except ImportError:
            missing[pkg] = install_cmd

    return {
        "installed": list(installed.keys()),
        "missing": missing,
        "total": len(deps),
        "ok": len(installed),
        "need_install": len(missing),
    }


# 一键安装所有依赖
def install_all():
    """安装所有依赖"""
    import subprocess
    packages = [
        "pyautogui", "pygetwindow", "pyperclip",
        "Pillow", "python-docx", "python-pptx", "openpyxl",
        "pytesseract", "transformers", "torch", "torchvision",
        "opencv-python-headless", "peft",
    ]
    result = subprocess.run(
        ["pip", "install"] + packages,
        capture_output=True, text=True
    )
    return {"installed": packages, "returncode": result.returncode}
