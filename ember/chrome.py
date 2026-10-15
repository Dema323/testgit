"""Custom window chrome: Ember draws its own title bar on Windows (no separate black system bar).

- DragBar: an area you can drag to move the window (native move, so Aero Snap works) and
  double-click to maximize.
- WindowButtons: minimize / maximize-restore / close.
- EdgeResizer: resize from the window edges (native resize).
"""
import ctypes
import os

from PySide6.QtCore import QEvent, QObject, QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QCursor
from PySide6.QtWidgets import QAbstractButton, QApplication, QHBoxLayout, QLineEdit, QPushButton, QWidget

from . import icons

FRAMELESS = os.name == "nt" or os.environ.get("EMBER_FRAMELESS") == "1"
EDGE = 6


def make_frameless(window):
    if not FRAMELESS:
        return
    window.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
    window.installEventFilter(_StateWatcher(window))
    QApplication.instance().installEventFilter(EdgeResizer(window))


def round_corners(window):
    """Windows 11: ask DWM for rounded corners on the frameless window (no effect elsewhere)."""
    if os.name != "nt":
        return
    try:
        pref = ctypes.c_int(2)  # DWMWCP_ROUND
        ctypes.windll.dwmapi.DwmSetWindowAttribute(int(window.winId()), 33, ctypes.byref(pref), 4)
    except (AttributeError, OSError):
        pass


def toggle_maximized(window):
    if window.isFullScreen():
        return
    window.showNormal() if window.isMaximized() else window.showMaximized()


def start_move(window):
    handle = window.windowHandle()
    if handle is not None and not window.isFullScreen():
        handle.startSystemMove()


class DragBar(QWidget):
    """Empty areas move the window; double-click maximizes. Buttons/inputs inside work as usual."""

    def mousePressEvent(self, event):
        if FRAMELESS and event.button() == Qt.MouseButton.LeftButton:
            start_move(self.window())
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if FRAMELESS and event.button() == Qt.MouseButton.LeftButton:
            toggle_maximized(self.window())


class WindowButtons(QWidget):
    def __init__(self, window, parent=None):
        super().__init__(parent)
        self.window_ = window
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(0)
        self.min_btn = self._button("win_min", "Minimize", window.showMinimized)
        self.max_btn = self._button("win_max", "Maximize", lambda: toggle_maximized(window))
        self.close_btn = self._button("close", "Close", window.close, close=True)
        for b in (self.min_btn, self.max_btn, self.close_btn):
            row.addWidget(b)
        self.setVisible(FRAMELESS)
        self.sync()

    def _button(self, name, tip, slot, close=False):
        b = QPushButton()
        b.setIcon(icons.icon(name, "#e6e6e6"))
        b.setIconSize(QSize(16, 16))
        b.setFixedSize(46, 34)
        b.setToolTip(tip)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        hover = "#c42b1c" if close else "rgba(255,255,255,0.12)"
        b.setStyleSheet(f"QPushButton {{ border: none; border-radius: 0; background: transparent; }}"
                        f"QPushButton:hover {{ background: {hover}; }}")
        b.clicked.connect(slot)
        return b

    def sync(self):
        maximized = self.window_.isMaximized()
        self.max_btn.setIcon(icons.icon("win_restore" if maximized else "win_max", "#e6e6e6"))
        self.max_btn.setToolTip("Restore" if maximized else "Maximize")


class _StateWatcher(QObject):
    def __init__(self, window):
        super().__init__(window)
        self.window_ = window

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.WindowStateChange:
            for b in self.window_.findChildren(WindowButtons):
                b.sync()
        elif event.type() == QEvent.Type.Show:
            round_corners(self.window_)
        return False


class EdgeResizer(QObject):
    """Resize a frameless window from its edges using the native resize loop."""

    def __init__(self, window):
        super().__init__(window)
        self.window_ = window
        self.cursor_set = False
        # Poll the cursor for the resize arrows (most widgets don't report plain mouse moves).
        self.timer = QTimer(self, interval=80, timeout=self._poll)
        self.timer.start()

    def _poll(self):
        if self.window_.isActiveWindow() or self.cursor_set:
            self._cursor(self._edges(QCursor.pos()))

    def _edges(self, global_pos):
        w = self.window_
        if w.isMaximized() or w.isFullScreen() or not w.isVisible():
            return Qt.Edge(0)
        local = w.mapFromGlobal(global_pos)
        x, y = local.x(), local.y()
        if not (-1 <= x <= w.width() and -1 <= y <= w.height()):
            return Qt.Edge(0)
        edges = Qt.Edge(0)
        if x < EDGE:
            edges |= Qt.Edge.LeftEdge
        elif x >= w.width() - EDGE:
            edges |= Qt.Edge.RightEdge
        if y < EDGE:
            edges |= Qt.Edge.TopEdge
        elif y >= w.height() - EDGE:
            edges |= Qt.Edge.BottomEdge
        return edges

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.MouseButtonPress or event.button() != Qt.MouseButton.LeftButton:
            return False
        if not isinstance(obj, QWidget) or obj.window() is not self.window_:
            return False
        edges = self._edges(QCursor.pos())
        if edges:
            self.window_.windowHandle().startSystemResize(edges)
            return True
        return False

    def _cursor(self, edges):
        shape = None
        horizontal = bool(edges & (Qt.Edge.LeftEdge | Qt.Edge.RightEdge))
        vertical = bool(edges & (Qt.Edge.TopEdge | Qt.Edge.BottomEdge))
        if horizontal and vertical:
            tl_br = edges in (Qt.Edge.LeftEdge | Qt.Edge.TopEdge, Qt.Edge.RightEdge | Qt.Edge.BottomEdge)
            shape = Qt.CursorShape.SizeFDiagCursor if tl_br else Qt.CursorShape.SizeBDiagCursor
        elif horizontal:
            shape = Qt.CursorShape.SizeHorCursor
        elif vertical:
            shape = Qt.CursorShape.SizeVerCursor
        if shape is not None:
            if self.cursor_set:
                QApplication.changeOverrideCursor(shape)
            else:
                QApplication.setOverrideCursor(shape)
                self.cursor_set = True
        elif self.cursor_set:
            QApplication.restoreOverrideCursor()
            self.cursor_set = False


def is_interactive(widget, stop):
    """True if widget (or an ancestor below `stop`) is a button or text field."""
    while widget is not None and widget is not stop:
        if isinstance(widget, (QAbstractButton, QLineEdit)):
            return True
        widget = widget.parentWidget()
    return False


__all__ = ["DragBar", "WindowButtons", "make_frameless", "start_move", "toggle_maximized", "FRAMELESS",
           "is_interactive", "QPoint"]
