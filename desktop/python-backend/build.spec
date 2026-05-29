# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Hermes Desktop Python backend.

All small dependencies are bundled. Only the 6GB LocateAnything-3B model
is left for user download.

Usage:
    pyinstaller build.spec

Produces a single-folder distribution under dist/hermes-backend/.
"""

from pathlib import Path

_spec_dir = Path(SPEC).resolve().parent if 'SPEC' in dir() else Path('.').resolve()

a = Analysis(
    [str(_spec_dir / "main.py")],
    pathex=[str(_spec_dir)],
    binaries=[],
    datas=[
        # Bundle tools/ directory (setup_deps, office_tools, etc.)
        (str(_spec_dir / "tools"), "tools"),
    ],
    hiddenimports=[
        # uvicorn
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "uvicorn.supervisors",
        # sse-starlette
        "sse_starlette",
        "sse_starlette.sse",
        # starlette
        "starlette.middleware.cors",
        "starlette.routing",
        "starlette.responses",
        "starlette.requests",
        "starlette.exceptions",
        # pydantic
        "pydantic",
        "pydantic.deprecated",
        "pydantic.deprecated.decorator",
        "pydantic_core",
        "pydantic_core._pydantic_core",
        "pydantic.json_schema",
        # network
        "h11",
        "httptools",
        "anyio._backends._asyncio",
        "sniffio",
        "multipart",
        "colorama",
        # GUI automation
        "pyautogui",
        "pygetwindow",
        "pyperclip",
        "PIL",
        "PIL.Image",
        "PIL.ImageGrab",
        "PIL.ImageTk",
        # Office
        "docx",
        "docx.shared",
        "docx.enum.text",
        "pptx",
        "pptx.util",
        "pptx.enum.text",
        "openpyxl",
        # ML
        "transformers",
        "accelerate",
        "sentencepiece",
        "google.protobuf",
        "huggingface_hub",
        # OCR
        "pytesseract",
        "cv2",
        # Email
        "imaplib",
        "smtplib",
        "email",
        # Skills
        "skills",
        "skills.loader",
        # Workflow
        "workflow_engine",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "numpy.random",
        "pandas",
        "scipy",
        "sklearn",
        "torch",       # 6GB+ — user downloads separately
        "torchaudio",
        "torchvision",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="hermes-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=False,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=False,
    upx_exclude=[],
    name="hermes-backend",
)
