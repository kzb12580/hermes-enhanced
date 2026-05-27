# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for Hermes Desktop Python backend.

Usage:
    pyinstaller build.spec

Produces a single-folder (or single-file with --onefile) distribution under
dist/hermes-backend/.
"""

from pathlib import Path

_spec_dir = Path(__file__).resolve().parent

a = Analysis(
    [str(_spec_dir / "main.py")],
    pathex=[str(_spec_dir)],
    binaries=[],
    datas=[],
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
        # sse-starlette
        "sse_starlette",
        "sse_starlette.sse",
        # starlette sub-modules needed at runtime
        "starlette.middleware.cors",
        "starlette.routing",
        "starlette.responses",
        "starlette.requests",
        "starlette.exceptions",
        # pydantic sub-modules needed at runtime
        "pydantic",
        "pydantic.deprecated",
        "pydantic.deprecated.decorator",
        "pydantic_core",
        "pydantic_core._pydantic_core",
        "pydantic.json_schema",
        # network libraries
        "h11",
        "httptools",
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
    upx=False,
    console=False,
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
