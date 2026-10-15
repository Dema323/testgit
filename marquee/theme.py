"""Colors, fonts and the application stylesheet (dark media-center look)."""
import os

from PySide6.QtGui import QColor, QFont, QFontDatabase

ACCENT = "#e5a00d"
ACCENT_HOVER = "#f3b125"
BG = "#1f2326"
BG_DEEP = "#16181a"
SIDEBAR = "#121314"
CARD = "#282a2d"
CONTROL = "#3f4245"
GREY = "#868c96"
TEXT = "#ffffff"
TEXT_MUTED = "rgba(255,255,255,0.6)"
TEXT_FAINT = "rgba(255,255,255,0.35)"

FONT_FAMILIES = ["Open Sans", "Segoe UI", "Helvetica Neue", "Arial"]


def color(name):
    return QColor({"accent": ACCENT, "bg": BG, "card": CARD, "control": CONTROL,
                   "grey": GREY, "text": TEXT, "sidebar": SIDEBAR}[name])


def load_fonts():
    here = os.path.join(os.path.dirname(__file__), "fonts")
    for name in ("OpenSans-400.woff", "OpenSans-600.woff", "OpenSans-700.woff"):
        QFontDatabase.addApplicationFont(os.path.join(here, name))


def font(size=13, weight=QFont.Weight.Normal):
    f = QFont()
    f.setFamilies(FONT_FAMILIES)
    f.setPixelSize(size)
    f.setWeight(weight)
    f.setHintingPreference(QFont.HintingPreference.PreferNoHinting)
    return f


STYLESHEET = f"""
* {{ font-family: "Open Sans", "Segoe UI", sans-serif; color: {TEXT}; }}
QMainWindow, #Root {{ background: {BG}; }}
QToolTip {{ background: {CARD}; color: {TEXT}; border: 1px solid {CONTROL}; padding: 4px 8px; }}

#Sidebar {{ background: {SIDEBAR}; }}
#Sidebar QPushButton {{
    text-align: left; padding: 9px 18px; border: none; border-radius: 0;
    font-size: 14px; color: {TEXT_MUTED}; background: transparent;
}}
#Sidebar QPushButton:hover {{ color: {TEXT}; background: rgba(255,255,255,0.05); }}
#Sidebar QPushButton:checked {{
    color: {TEXT}; background: rgba(255,255,255,0.08); border-left: 3px solid {ACCENT}; padding-left: 15px;
}}
#SidebarHeading {{ color: {TEXT_FAINT}; font-size: 11px; font-weight: 700; letter-spacing: 1px;
                   padding: 18px 18px 6px 18px; }}
#Brand {{ font-size: 21px; font-weight: 700; color: {ACCENT}; padding: 18px 18px 14px 18px; }}

#TopBar {{ background: {BG_DEEP}; border-bottom: 1px solid rgba(255,255,255,0.06); }}
#Search {{
    background: rgba(255,255,255,0.1); border: 1px solid transparent; border-radius: 17px;
    padding: 0 14px 0 4px; font-size: 14px; min-height: 34px; selection-background-color: {ACCENT};
}}
#Search:focus {{ background: rgba(255,255,255,0.16); border: 1px solid rgba(255,255,255,0.25); }}
#OfflineBadge {{ color: {ACCENT}; font-size: 12px; font-weight: 600; }}

QScrollArea, QScrollArea > QWidget > QWidget, #Page {{ background: transparent; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.18); border-radius: 5px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.3); }}
QScrollBar:horizontal {{ height: 0; }}
QScrollBar::add-line, QScrollBar::sub-line, QScrollBar::add-page, QScrollBar::sub-page {{
    background: none; border: none; height: 0; width: 0; }}

QListView {{ background: transparent; border: none; outline: none; }}

#HubTitle {{ font-size: 19px; font-weight: 600; }}
#PageTitle {{ font-size: 26px; font-weight: 700; }}
#Muted {{ color: {TEXT_MUTED}; font-size: 13px; }}
#Faint {{ color: {TEXT_FAINT}; font-size: 13px; }}
#DetailTitle {{ font-size: 34px; font-weight: 700; }}
#DetailParent {{ font-size: 18px; font-weight: 600; color: {TEXT_MUTED}; }}
#DetailMeta {{ font-size: 15px; color: {TEXT_MUTED}; }}
#Tagline {{ font-size: 15px; font-style: italic; color: {TEXT_MUTED}; }}
#Summary {{ font-size: 15px; line-height: 150%; }}
#FactLabel {{ color: {TEXT_FAINT}; font-size: 13px; font-weight: 600; }}
#FactValue {{ font-size: 13px; color: {TEXT_MUTED}; }}
#Badge {{ border: 1px solid rgba(255,255,255,0.45); border-radius: 3px; padding: 0 5px;
          font-size: 11px; font-weight: 700; color: {TEXT_MUTED}; }}

QPushButton {{ border: none; background: transparent; }}
#Primary {{
    background: {ACCENT}; color: #000; font-weight: 700; font-size: 15px;
    border-radius: 4px; padding: 9px 22px 9px 16px;
}}
#Primary:hover {{ background: {ACCENT_HOVER}; }}
#Primary:disabled {{ background: {CONTROL}; color: {TEXT_FAINT}; }}
#Secondary {{
    background: rgba(255,255,255,0.1); font-weight: 600; font-size: 14px;
    border-radius: 4px; padding: 9px 16px;
}}
#Secondary:hover {{ background: rgba(255,255,255,0.18); }}
#Round {{ background: rgba(255,255,255,0.1); border-radius: 20px; min-width: 40px; min-height: 40px; }}
#Round:hover {{ background: rgba(255,255,255,0.2); }}
#Round:checked {{ background: rgba(229,160,13,0.25); }}
#IconButton {{ border-radius: 18px; padding: 6px; }}
#IconButton:hover {{ background: rgba(255,255,255,0.12); }}
#Link {{ color: {TEXT_MUTED}; font-size: 14px; text-align: left; padding: 0; }}
#Link:hover {{ color: {ACCENT}; }}
#Tab {{ font-size: 14px; font-weight: 600; color: {TEXT_MUTED}; padding: 6px 2px; margin-right: 22px;
        border-bottom: 3px solid transparent; border-radius: 0; }}
#Tab:hover {{ color: {TEXT}; }}
#Tab:checked {{ color: {TEXT}; border-bottom: 3px solid {ACCENT}; }}

QComboBox {{
    background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.1); border-radius: 4px;
    padding: 6px 30px 6px 10px; font-size: 13px; min-height: 20px;
}}
QComboBox:hover {{ background: rgba(255,255,255,0.14); }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox QAbstractItemView {{
    background: {CARD}; border: 1px solid {CONTROL}; selection-background-color: {CONTROL};
    outline: none; padding: 4px;
}}
QMenu {{ background: {CARD}; border: 1px solid {CONTROL}; padding: 6px 0; }}
QMenu::item {{ padding: 7px 28px 7px 22px; font-size: 13px; }}
QMenu::item:selected {{ background: {CONTROL}; }}
QMenu::item:checked {{ color: {ACCENT}; }}
QMenu::indicator {{ width: 0; }}
QMenu::separator {{ height: 1px; background: {CONTROL}; margin: 5px 0; }}
QMenu::section {{ color: {TEXT_FAINT}; font-size: 11px; font-weight: 700; padding: 6px 22px; }}

QLineEdit {{ background: rgba(255,255,255,0.08); border: 1px solid rgba(255,255,255,0.12);
             border-radius: 4px; padding: 7px 10px; font-size: 13px; }}
QDialog {{ background: {CARD}; }}
QProgressBar {{ background: rgba(255,255,255,0.12); border: none; border-radius: 2px; max-height: 4px; }}
QProgressBar::chunk {{ background: {ACCENT}; border-radius: 2px; }}

#PlayerBar {{ background: qlineargradient(x1:0, y1:0, x2:0, y2:1, stop:0 rgba(0,0,0,0.0),
                                          stop:0.35 rgba(0,0,0,0.75), stop:1 rgba(0,0,0,0.92)); }}
#PlayerTitle {{ font-size: 15px; font-weight: 700; }}
#PlayerSub {{ font-size: 13px; color: {TEXT_MUTED}; }}
#Clock {{ font-size: 12px; color: {TEXT_MUTED}; }}
QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.25); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT}; }}
#Toast {{ background: rgba(20,20,20,0.92); border-radius: 6px; padding: 10px 16px; font-size: 13px; }}
"""
