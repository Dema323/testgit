"""Colors, fonts and the application stylesheet."""
import glob
import os

from PySide6.QtCore import QRectF
from PySide6.QtGui import QColor, QFont, QFontDatabase, QPainter, QPixmap, QRadialGradient

ACCENT = "#e5a00d"
ACCENT_HOVER = "#f3b125"
BG = "#141619"
BG_TOP = "#1d2024"
SURFACE = "#22252a"
SIDEBAR = "rgba(0,0,0,0.32)"
CARD = "#26292e"
CONTROL = "#34383e"
TEXT = "#ffffff"
TEXT_MUTED = "rgba(255,255,255,0.62)"
TEXT_FAINT = "rgba(255,255,255,0.38)"

FONT = "Figtree"
FONT_FAMILIES = [FONT, "Segoe UI", "Helvetica Neue", "Arial"]

# Page background: black with four soft corner glows (slate, grey-teal, steel), like Plex's.
GLOWS = [  # centre (x, y as fraction), radii (fraction of width, height), colour
    ((0.0, 1.0), (0.8401, 1.4915), QColor(63, 76, 97, 153)),
    ((0.9681, 1.0), (0.8006, 1.4328), QColor(91, 100, 106, 153)),
    ((1.0, 0.0), (0.8241, 1.5106), QColor(58, 70, 87, 153)),
    ((0.0, 0.0), (0.8606, 1.5874), QColor(84, 100, 115, 153)),
]


def color(name):
    return QColor({"accent": ACCENT, "bg": BG, "card": CARD, "control": CONTROL,
                   "text": TEXT, "surface": SURFACE}[name])


def load_fonts(custom_file=""):
    """Load the bundled fonts, plus an optional user-chosen font file that then becomes the UI font."""
    global FONT, FONT_FAMILIES
    for path in glob.glob(os.path.join(os.path.dirname(__file__), "fonts", "*.ttf")):
        QFontDatabase.addApplicationFont(path)
    if custom_file and os.path.exists(custom_file):
        fid = QFontDatabase.addApplicationFont(custom_file)
        families = QFontDatabase.applicationFontFamilies(fid) if fid >= 0 else []
        if families:
            FONT = families[0]
            FONT_FAMILIES = [FONT, "Figtree", "Segoe UI", "Arial"]
    return FONT


def render_background(width, height, dim=0.0):
    """The page background as a pixmap (render once per size; it is costly to paint every frame)."""
    pm = QPixmap(max(1, width), max(1, height))
    pm.fill(QColor(0, 0, 0))
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    w, h = pm.width(), pm.height()
    for (cx, cy), (rx, ry), col in GLOWS:
        p.save()
        p.translate(cx * w, cy * h)
        p.scale(rx * w, ry * h)
        g = QRadialGradient(0, 0, 1)
        g.setColorAt(0, col)
        g.setColorAt(1, QColor(col.red(), col.green(), col.blue(), 0))
        p.fillRect(QRectF(-cx / rx, -cy / ry, 1 / rx, 1 / ry), g)
        p.restore()
    if dim:
        p.fillRect(pm.rect(), QColor(0, 0, 0, int(255 * dim)))
    p.end()
    return pm


def font(size=14, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPixelSize(size)
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    f.setStyleStrategy(QFont.StyleStrategy.PreferAntialias)
    return f


def stylesheet():
    return _STYLESHEET.replace("__FONT__", FONT)


_STYLESHEET = f"""
* {{ font-family: "__FONT__", "Figtree", "Segoe UI", sans-serif; color: {TEXT}; }}
QMainWindow {{ background: #000; }}
QToolTip {{ background: {SURFACE}; color: {TEXT}; border: 1px solid {CONTROL}; padding: 5px 9px;
            border-radius: 4px; font-size: 13px; }}

#Sidebar {{ background: {SIDEBAR}; }}
#Sidebar QPushButton {{
    text-align: left; padding: 10px 14px; margin: 1px 10px; border: none; border-radius: 8px;
    font-size: 15px; font-weight: 600; color: rgba(255,255,255,0.72); background: transparent;
}}
#Sidebar QPushButton:hover {{ color: {TEXT}; background: rgba(255,255,255,0.08); }}
#Sidebar QPushButton:checked {{ color: {TEXT}; background: rgba(255,255,255,0.14); }}
#Sidebar[collapsed="true"] QPushButton {{ padding: 10px 0; margin: 1px 10px; text-align: center; }}
#SidebarHeading {{ color: {TEXT_FAINT}; font-size: 11px; font-weight: 700; letter-spacing: 1.4px;
                   padding: 20px 24px 8px 24px; }}
#Brand {{ font-size: 23px; font-weight: 800; color: {ACCENT}; padding: 20px 20px 16px 20px;
          letter-spacing: -0.3px; }}

#TopBar {{ background: rgba(0,0,0,0.32); }}
#Search {{
    background: rgba(255,255,255,0.1); border: 1px solid transparent; border-radius: 18px;
    padding: 0 14px 0 4px; font-size: 14px; font-weight: 500; min-height: 36px;
    selection-background-color: {ACCENT};
}}
#Search:focus {{ background: rgba(255,255,255,0.13); border: 1px solid rgba(255,255,255,0.22); }}
#OfflineBadge {{ color: {ACCENT}; font-size: 12px; font-weight: 700; letter-spacing: 0.6px; }}

QScrollArea, QScrollArea > QWidget > QWidget, #Page {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.14); border-radius: 4px; min-height: 48px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.28); }}
QScrollBar:horizontal {{ height: 0; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; height: 0; width: 0; }}
QListView {{ background: transparent; border: none; outline: none; }}

#HubTitle {{ font-size: 20px; font-weight: 700; letter-spacing: -0.2px; }}
#PageTitle {{ font-size: 30px; font-weight: 800; letter-spacing: -0.5px; }}
#Muted {{ color: {TEXT_MUTED}; font-size: 14px; font-weight: 500; }}
#Faint {{ color: {TEXT_FAINT}; font-size: 13px; font-weight: 500; }}
#DetailTitle {{ font-size: 42px; font-weight: 800; letter-spacing: -0.8px; }}
#DetailParent {{ font-size: 18px; font-weight: 700; color: {TEXT_MUTED}; }}
#DetailMeta {{ font-size: 16px; font-weight: 500; color: {TEXT_MUTED}; }}
#Tagline {{ font-size: 16px; font-style: italic; color: {TEXT_MUTED}; }}
#Summary {{ font-size: 16px; line-height: 150%; color: rgba(255,255,255,0.88); }}
#FactLabel {{ color: {TEXT_FAINT}; font-size: 12px; font-weight: 700; letter-spacing: 0.8px; }}
#FactValue {{ font-size: 14px; font-weight: 500; color: {TEXT_MUTED}; }}
#Badge {{ border: 1px solid rgba(255,255,255,0.4); border-radius: 3px; padding: 1px 6px;
          font-size: 11px; font-weight: 800; color: rgba(255,255,255,0.75); letter-spacing: 0.4px; }}

QPushButton {{ border: none; background: transparent; }}
#Primary {{
    background: {ACCENT}; color: #111; font-weight: 700; font-size: 15px;
    border-radius: 5px; padding: 10px 24px 10px 16px;
}}
#Primary:hover {{ background: {ACCENT_HOVER}; }}
#Primary:disabled {{ background: {CONTROL}; color: {TEXT_FAINT}; }}
#Secondary {{
    background: rgba(255,255,255,0.1); font-weight: 600; font-size: 15px;
    border-radius: 5px; padding: 10px 18px;
}}
#Secondary:hover {{ background: rgba(255,255,255,0.17); }}
#Round {{ background: rgba(255,255,255,0.1); border-radius: 21px; min-width: 42px; min-height: 42px; }}
#Round:hover {{ background: rgba(255,255,255,0.18); }}
#Round:checked {{ background: rgba(229,160,13,0.22); }}
#IconButton {{ border-radius: 18px; padding: 6px; }}
#IconButton:hover {{ background: rgba(255,255,255,0.1); }}
#Link {{ color: {TEXT_MUTED}; font-size: 15px; font-weight: 600; text-align: left; padding: 0; }}
#Link:hover {{ color: {ACCENT}; }}
#Tab {{ font-size: 15px; font-weight: 600; color: {TEXT_MUTED}; padding: 7px 2px; margin-right: 24px;
        border-bottom: 3px solid transparent; border-radius: 0; }}
#Tab:hover {{ color: {TEXT}; }}
#Tab:checked {{ color: {TEXT}; border-bottom: 3px solid {ACCENT}; }}

QComboBox {{
    background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.09); border-radius: 5px;
    padding: 7px 30px 7px 12px; font-size: 14px; font-weight: 500; min-height: 20px;
}}
QComboBox:hover {{ background: rgba(255,255,255,0.12); }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {CONTROL}; selection-background-color: {CONTROL};
    outline: none; padding: 4px;
}}
QMenu {{ background: {SURFACE}; border: 1px solid {CONTROL}; border-radius: 6px; padding: 6px 0; }}
QMenu::item {{ padding: 8px 30px 8px 22px; font-size: 14px; font-weight: 500; }}
QMenu::item:selected {{ background: {CONTROL}; }}
QMenu::item:checked {{ color: {ACCENT}; }}
QMenu::indicator {{ width: 0; }}
QMenu::separator {{ height: 1px; background: {CONTROL}; margin: 5px 0; }}
QMenu::section {{ color: {TEXT_FAINT}; font-size: 11px; font-weight: 700; padding: 6px 22px; }}

QLineEdit {{ background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.12);
             border-radius: 5px; padding: 8px 10px; font-size: 14px; }}
QDialog {{ background: {SURFACE}; }}
QProgressBar {{ background: rgba(255,255,255,0.12); border: none; border-radius: 2px; max-height: 4px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}
#Toast {{ background: rgba(28,30,34,0.96); border: 1px solid rgba(255,255,255,0.08); border-radius: 8px;
          padding: 11px 18px; font-size: 14px; font-weight: 500; }}

/* player overlay */
#OsdTitle {{ font-size: 18px; font-weight: 700; }}
#OsdSub {{ font-size: 14px; font-weight: 500; color: {TEXT_MUTED}; }}
#OsdClock {{ font-size: 13px; font-weight: 600; color: rgba(255,255,255,0.8); }}
#OsdStatus {{ font-size: 14px; font-weight: 600; color: {ACCENT}; }}
#OsdButton {{ border-radius: 22px; padding: 8px; }}
#OsdButton:hover {{ background: rgba(255,255,255,0.14); }}
#OsdButton:checked {{ background: rgba(255,255,255,0.18); }}
#Panel {{ background: rgba(18,19,22,0.78); border-radius: 10px; }}
#PanelTitle {{ font-size: 13px; font-weight: 700; color: {TEXT_FAINT}; letter-spacing: 1px; }}
#PanelItem {{ text-align: left; padding: 9px 14px; border-radius: 6px; font-size: 15px; font-weight: 500;
              color: rgba(255,255,255,0.82); }}
#PanelItem:hover {{ background: rgba(255,255,255,0.08); color: white; }}
#PanelItem:checked {{ color: {ACCENT}; font-weight: 700; }}
#PanelTab {{ font-size: 14px; font-weight: 700; color: {TEXT_MUTED}; padding: 8px 4px; margin-right: 18px;
             border-bottom: 2px solid transparent; border-radius: 0; }}
#PanelTab:checked {{ color: white; border-bottom: 2px solid {ACCENT}; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.25); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: white; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: white; width: 12px; height: 12px; margin: -4px 0; border-radius: 6px; }}
"""
