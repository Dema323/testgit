# PyInstaller build: `pyinstaller marquee.spec --noconfirm`  ->  dist/Marquee/Marquee.exe
# On Windows, put libmpv-2.dll next to this file first (the GitHub workflow does this).
import os

binaries = [("libmpv-2.dll", ".")] if os.path.exists("libmpv-2.dll") else []

a = Analysis(
    ["run.py"],
    binaries=binaries,
    datas=[("marquee/fonts", "marquee/fonts")],
    hiddenimports=["mpv"],
    excludes=["tkinter", "numpy", "PIL", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.Qt3DCore",
              "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="Marquee",
    console=False,
    icon=None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="Marquee")
