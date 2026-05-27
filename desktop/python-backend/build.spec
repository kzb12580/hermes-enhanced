# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Hermes Desktop Python backend.

Usage:
    pyinstaller build.spec

Produces a single-folder (or single-file with --onefile) distribution under
dist/hermes-backend/.
"""

from pathlib import Path

a = Analysis(
    [str(Path("main.py").resolve())],
    pathex=[str(Path(".").resolve())],
    binaries=[],
    datas=[],
    hiddenimports=[
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
        "sse_starlette",
        "sse_starlette.sse",
        "httpx",
        "httpx._client",
        "httpx._transports",
        "h11",
        "httptools",
        "httpcore",
        "httpcore._sync",
        "httpcore._async",
        "anyio._backends._asyncio",
        "sniffio",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter", "matplotlib", "numpy", "pandas"],
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
    upx=True,
    console=True,
    disable_windowed_traceback=False,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name="hermes-backend",
)
