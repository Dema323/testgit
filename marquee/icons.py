"""Monochrome UI icons (Material Design paths, Apache-2.0), tinted at render time."""
from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS = {
    "home": "M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z",
    "movie": "M18 4l2 4h-3l-2-4h-2l2 4h-3l-2-4H8l2 4H7L5 4H4c-1.1 0-1.99.9-1.99 2L2 18c0 1.1.9 2 2 2h16"
             "c1.1 0 2-.9 2-2V4h-4z",
    "show": "M21 3H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h5v2h8v-2h5c1.1 0 1.99-.9 1.99-2L23 5c0-1.1-.9-2-2-2z"
            "m0 14H3V5h18v12z",
    "artist": "M12 3v10.55c-.59-.34-1.27-.55-2-.55-2.21 0-4 1.79-4 4s1.79 4 4 4 4-1.79 4-4V7h4V3h-6z",
    "photo": "M21 19V5c0-1.1-.9-2-2-2H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2zM8.5 13.5"
             "l2.5 3.01L14.5 12l4.5 6H5l3.5-4.5z",
    "download": "M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z",
    "search": "M15.5 14h-.79l-.28-.27C15.41 12.59 16 11.11 16 9.5 16 5.91 13.09 3 9.5 3S3 5.91 3 9.5 "
              "5.91 16 9.5 16c1.61 0 3.09-.59 4.23-1.57l.27.28v.79l5 4.99L20.49 19l-4.99-5zm-6 0C7.01 "
              "14 5 11.99 5 9.5S7.01 5 9.5 5 14 7.01 14 9.5 11.99 14 9.5 14z",
    "play": "M8 5v14l11-7z",
    "pause": "M6 19h4V5H6v14zm8-14v14h4V5h-4z",
    "check": "M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
    "more": "M12 8c1.1 0 2-.9 2-2s-.9-2-2-2-2 .9-2 2 .9 2 2 2zm0 2c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2"
            "-2-2zm0 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2z",
    "fullscreen": "M7 14H5v5h5v-2H7v-3zm-2-4h2V7h3V5H5v5zm12 7h-3v2h5v-5h-2v3zM14 5v2h3v3h2V5h-5z",
    "fullscreen_exit": "M5 16h3v3h2v-5H5v2zm3-8H5v2h5V5H8v3zm6 11h2v-3h3v-2h-5v5zm2-11V5h-2v5h5V8h-3z",
    "subtitles": "M20 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2zM4 12h4v2H4"
                 "v-2zm10 6H4v-2h10v2zm6 0h-4v-2h4v2zm0-4H10v-2h10v2z",
    "back": "M20 11H7.83l5.59-5.59L12 4l-8 8 8 8 1.41-1.41L7.83 13H20v-2z",
    "close": "M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 "
             "13.41 12z",
    "rewind": "M11 18V6l-8.5 6 8.5 6zm.5-6l8.5 6V6l-8.5 6z",
    "forward": "M4 18l8.5-6L4 6v12zm9-12v12l8.5-6L13 6z",
    "tune": "M3 17v2h6v-2H3zM3 5v2h10V5H3zm10 16v-2h8v-2h-8v-2h-2v6h2zM7 9v2H3v2h4v2h2V9H7zm14 4v-2H11v2h10z"
            "m-6-4h2V7h4V5h-4V3h-2v6z",
    "person": "M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2"
              "c0-2.66-5.33-4-8-4z",
    "trash": "M6 19c0 1.1.9 2 2 2h8c1.1 0 2-.9 2-2V7H6v12zM19 4h-3.5l-1-1h-5l-1 1H5v2h14V4z",
    "chevron_left": "M15.41 7.41L14 6l-6 6 6 6 1.41-1.41L10.83 12z",
    "chevron_right": "M10 6L8.59 7.41 13.17 12l-4.58 4.59L10 18l6-6z",
    "next": "M6 18l8.5-6L6 6v12zM16 6v12h2V6h-2z",
    "offline": "M19.35 10.04C18.67 6.59 15.64 4 12 4c-1.48 0-2.85.43-4.01 1.17l1.46 1.46C10.21 6.23 11.08 "
               "6 12 6c3.04 0 5.5 2.46 5.5 5.5v.5H19c1.66 0 3 1.34 3 3 0 1.13-.64 2.11-1.56 2.62l1.45 1.45"
               "C23.16 18.16 24 16.68 24 15c0-2.64-2.05-4.78-4.65-4.96zM3 5.27l2.75 2.74C2.56 8.15 0 10.77 "
               "0 14c0 3.31 2.69 6 6 6h11.73l2 2L21 20.73 4.27 4 3 5.27zM7.73 10l8 8H6c-2.21 0-4-1.79-4-4s"
               "1.79-4 4-4h1.73z",
}

_cache = {}


def pixmap(name, color="#ffffff", size=24, dpr=2.0):
    key = (name, color, size, dpr)
    if key not in _cache:
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
               f'<path fill="{color}" d="{PATHS[name]}"/></svg>')
        renderer = QSvgRenderer(QByteArray(svg.encode()))
        pm = QPixmap(int(size * dpr), int(size * dpr))
        pm.fill(Qt.GlobalColor.transparent)
        p = QPainter(pm)
        renderer.render(p, QRectF(0, 0, size * dpr, size * dpr))
        p.end()
        pm.setDevicePixelRatio(dpr)
        _cache[key] = pm
    return _cache[key]


def icon(name, color="#ffffff", size=24, active_color=None):
    ic = QIcon(pixmap(name, color, size))
    if active_color:
        ic.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Active)
        ic.addPixmap(pixmap(name, active_color, size), QIcon.Mode.Selected)
    return ic


def section_icon(section_type):
    return {"movie": "movie", "show": "show", "artist": "artist", "photo": "photo"}.get(section_type, "movie")
