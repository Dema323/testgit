# PyInstaller build: `pyinstaller marquee.spec --noconfirm`  ->  dist/Marquee.exe (single file)
# On Windows, put libmpv-2.dll next to this file first (the GitHub workflow does this).
import os

binaries = [("libmpv-2.dll", ".")] if os.path.exists("libmpv-2.dll") else []

a = Analysis(
    ["run.py"],
    binaries=binaries,
    datas=[("marquee/fonts", "marquee/fonts"), ("marquee/assets", "marquee/assets")],
    hiddenimports=["mpv"],
    excludes=["tkinter", "numpy", "PIL", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
              "PySide6.Qt3DCore", "PySide6.QtQuick", "PySide6.QtQml", "PySide6.QtPdf", "PySide6.QtMultimedia"],
)

# Drop Qt pieces this app never uses, so the single exe unpacks faster at launch.
UNUSED = ("opengl32sw.dll", "Qt6Pdf", "Qt6Quick", "Qt6Qml", "Qt6VirtualKeyboard", "Qt6OpenGL",
          "qtwebengine", "/translations/", "\\translations\\", "imageformats/qpdf", "imageformats\\qpdf")
a.binaries = [b for b in a.binaries if not any(u.lower() in b[0].lower() for u in UNUSED)]
a.datas = [d for d in a.datas if not any(u.lower() in d[0].lower() for u in UNUSED)]

pyz = PYZ(a.pure)
splash = Splash("marquee/assets/splash.png", binaries=a.binaries, datas=a.datas,
                text_pos=None, always_on_top=True)
exe = EXE(
    pyz, a.scripts, splash, splash.binaries, a.binaries, a.datas, [],
    name="Marquee",
    console=False,
    upx=False,
    icon="marquee/assets/marquee.ico",
    version="version_info.txt",
)
