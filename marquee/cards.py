"""Poster cards: a list model, a painted card delegate, grid and horizontal hub views."""
from PySide6.QtCore import (QAbstractListModel, QModelIndex, QPoint, QRect, QRectF, QSize, Qt,
                            Signal)
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListView, QPushButton, QStyle,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from . import icons, theme
from .api import card_image, card_subtitle, card_title
from .images import ImageLoader
from .workers import run_async

SHAPES = {  # card width, image height
    "poster": (152, 228),
    "wide": (284, 160),
    "square": (164, 164),
}
TEXT_HEIGHT = 46
GAP = 18
RADIUS = 5
ITEM = Qt.ItemDataRole.UserRole + 1


def shape_for(items, hint=None):
    if hint:
        return hint
    kinds = {m.get("type") for m in items}
    if kinds and kinds <= {"episode", "clip"}:
        return "wide"
    if kinds and kinds <= {"artist", "album", "track", "photo", "playlist"}:
        return "square"
    return "poster"


class MediaModel(QAbstractListModel):
    """Items for a card view. Optionally pages more in from `pager(start, size) -> (items, total)`."""

    def __init__(self, items=None, pager=None, page_size=120, parent=None):
        super().__init__(parent)
        self.items = list(items or [])
        self.pager = pager
        self.page_size = page_size
        self.total = None if pager else len(self.items)
        self.loading = False

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.items)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        m = self.items[index.row()]
        if role == ITEM:
            return m
        if role == Qt.ItemDataRole.DisplayRole:
            return card_title(m)
        if role == Qt.ItemDataRole.ToolTipRole:
            return m.get("title")
        return None

    def set_items(self, items):
        self.beginResetModel()
        self.items = list(items)
        self.total = len(self.items) if not self.pager else self.total
        self.endResetModel()

    def update_item(self, rating_key, changes):
        for row, m in enumerate(self.items):
            if m.get("ratingKey") == rating_key:
                m.update(changes)
                self.dataChanged.emit(self.index(row), self.index(row))

    def canFetchMore(self, parent=QModelIndex()):
        return bool(self.pager) and not self.loading and (self.total is None or len(self.items) < self.total)

    def fetchMore(self, parent=QModelIndex()):
        if not self.canFetchMore():
            return
        self.loading = True
        start = len(self.items)
        run_async(lambda: self.pager(start, self.page_size), self._page_loaded, self._page_failed)

    def _page_loaded(self, result):
        items, total = result
        self.loading = False
        self.total = total
        if items:
            self.beginInsertRows(QModelIndex(), len(self.items), len(self.items) + len(items) - 1)
            self.items.extend(items)
            self.endInsertRows()
        else:
            self.total = len(self.items)

    def _page_failed(self, _err):
        self.loading = False
        self.total = len(self.items)


class CardDelegate(QStyledItemDelegate):
    def __init__(self, view, shape="poster", context="hub"):
        super().__init__(view)
        self.view, self.shape, self.context = view, shape, context
        self.title_font = theme.font(13, QFont.Weight.DemiBold)
        self.sub_font = theme.font(12)

    def sizeHint(self, option, index):
        w, h = SHAPES[self.shape]
        return QSize(w + GAP, h + TEXT_HEIGHT)

    def paint(self, painter, option, index):
        m = index.data(ITEM)
        w, h = SHAPES[self.shape]
        x, y = option.rect.x() + GAP // 2, option.rect.y()
        img = QRectF(x, y, w, h)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)

        painter.save()
        painter.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)
        clip = QPainterPath()
        clip.addRoundedRect(img, RADIUS, RADIUS)

        # artwork (or a placeholder while it loads)
        painter.fillPath(clip, theme.color("card"))
        pm = self._pixmap(m, w, h)
        if pm is not None and not pm.isNull():
            painter.setClipPath(clip)
            scaled = pm.scaled(int(w * pm.devicePixelRatio()), int(h * pm.devicePixelRatio()),
                               Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                               Qt.TransformationMode.SmoothTransformation)
            sx = (scaled.width() - w * pm.devicePixelRatio()) / 2
            sy = (scaled.height() - h * pm.devicePixelRatio()) / 2
            painter.drawPixmap(img, scaled, QRectF(sx, sy, w * pm.devicePixelRatio(), h * pm.devicePixelRatio()))
            painter.setClipping(False)
        else:
            glyph = icons.pixmap(icons.section_icon({"episode": "show", "season": "show",
                                                     "track": "artist", "album": "artist"}
                                                    .get(m.get("type"), m.get("type"))),
                                 "#4a4e54", 40)
            painter.drawPixmap(int(img.center().x() - 20), int(img.center().y() - 20), glyph)

        self._badges(painter, m, img)

        if hovered:
            painter.fillPath(clip, QColor(0, 0, 0, 90))
            painter.setPen(QPen(theme.color("accent"), 3))
            painter.drawRoundedRect(img.adjusted(1.5, 1.5, -1.5, -1.5), RADIUS, RADIUS)
            if m.get("type") in ("movie", "episode", "track", "clip") and not m.get("_download_state"):
                c = img.center()
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(theme.color("accent"))
                painter.drawEllipse(c, 26, 26)
                painter.drawPixmap(int(c.x() - 14), int(c.y() - 14), icons.pixmap("play", "#000000", 28))

        # title + subtitle
        painter.setPen(QColor(theme.TEXT))
        painter.setFont(self.title_font)
        fm = painter.fontMetrics()
        text_rect = QRect(int(x), int(y + h + 7), w, 18)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft,
                         fm.elidedText(card_title(m, self.context), Qt.TextElideMode.ElideRight, w))
        painter.setPen(QColor(255, 255, 255, 140))
        painter.setFont(self.sub_font)
        fm = painter.fontMetrics()
        painter.drawText(QRect(int(x), int(y + h + 25), w, 18), Qt.AlignmentFlag.AlignLeft,
                         fm.elidedText(card_subtitle(m, self.context), Qt.TextElideMode.ElideRight, w))
        painter.restore()

    def _badges(self, painter, m, img):
        accent = theme.color("accent")
        # progress
        progress = None
        if m.get("_download_state") in ("queued", "downloading"):
            total = m.get("_download_total") or 0
            progress = (m.get("_download_bytes", 0) / total) if total else 0.0
        elif m.get("viewOffset") and m.get("duration"):
            progress = min(1.0, m["viewOffset"] / m["duration"])
        if progress is not None:
            bar = QRectF(img.left(), img.bottom() - 5, img.width(), 5)
            painter.fillRect(bar, QColor(0, 0, 0, 170))
            painter.fillRect(QRectF(bar.left(), bar.top(), bar.width() * progress, 5), accent)

        if m.get("_download_state"):
            label = {"queued": "Queued", "downloading": f"{int((progress or 0) * 100)}%",
                     "failed": "Failed", "done": ""}.get(m["_download_state"], "")
            if label:
                self._pill(painter, img, label, QColor(0, 0, 0, 200), QColor(theme.TEXT))
            return

        unwatched = None
        if m.get("type") in ("show", "season") and "leafCount" in m:
            unwatched = int(m.get("leafCount", 0)) - int(m.get("viewedLeafCount", 0))
        if unwatched:
            self._pill(painter, img, str(unwatched), accent, QColor("#000000"))
        elif m.get("type") in ("movie", "episode") and not m.get("viewCount") and not m.get("viewOffset"):
            tri = QPainterPath()  # small unwatched corner marker
            tri.moveTo(img.right() - 22, img.top())
            tri.lineTo(img.right() - RADIUS, img.top())
            tri.quadTo(img.right(), img.top(), img.right(), img.top() + RADIUS)
            tri.lineTo(img.right(), img.top() + 22)
            tri.closeSubpath()
            painter.fillPath(tri, accent)

    def _pill(self, painter, img, text, bg, fg):
        painter.setFont(theme.font(11, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        pw = max(22, fm.horizontalAdvance(text) + 12)
        r = QRectF(img.right() - pw - 6, img.top() + 6, pw, 20)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(r, 10, 10)
        painter.setPen(fg)
        painter.drawText(r, Qt.AlignmentFlag.AlignCenter, text)

    def _pixmap(self, m, w, h):
        loader = ImageLoader.instance()
        path = card_image(m, self.shape)
        if not loader or not path:
            return None
        dpr = self.view.devicePixelRatioF()
        pw, ph = int(w * dpr), int(h * dpr)
        pm = loader.cached(path, pw, ph)
        if pm is None:
            viewport = self.view.viewport()
            loader.load(path, pw, ph, lambda _pm: viewport.update())
        return pm


class CardView(QListView):
    """Base for grids and hub rows: emits the clicked item's metadata."""
    opened = Signal(dict)
    context_requested = Signal(dict, QPoint)

    def __init__(self, model, shape="poster", context="hub", parent=None):
        super().__init__(parent)
        self.setModel(model)
        self.card_delegate = CardDelegate(self, shape, context)
        self.setItemDelegate(self.card_delegate)
        self.setMouseTracking(True)
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SelectionMode.NoSelection)
        self.setEditTriggers(QListView.EditTrigger.NoEditTriggers)
        self.setVerticalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setHorizontalScrollMode(QListView.ScrollMode.ScrollPerPixel)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.clicked.connect(lambda idx: self.opened.emit(idx.data(ITEM)))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context)

    def _context(self, pos):
        idx = self.indexAt(pos)
        if idx.isValid():
            self.context_requested.emit(idx.data(ITEM), self.viewport().mapToGlobal(pos))


class GridView(CardView):
    def __init__(self, model, shape="poster", context="grid", parent=None):
        super().__init__(model, shape, context, parent)
        self.setViewMode(QListView.ViewMode.IconMode)
        self.setFlow(QListView.Flow.LeftToRight)
        self.setWrapping(True)
        self.setResizeMode(QListView.ResizeMode.Adjust)
        self.setMovement(QListView.Movement.Static)
        self.setSpacing(0)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.verticalScrollBar().setSingleStep(40)


class HubView(CardView):
    def wheelEvent(self, event):
        # Horizontal swipes scroll the row; plain wheel turns go to the page.
        if abs(event.angleDelta().x()) > abs(event.angleDelta().y()):
            super().wheelEvent(event)
        else:
            event.ignore()


class HubRow(QWidget):
    """Titled horizontal strip of cards with page arrows, like a home-screen hub."""
    opened = Signal(dict)
    title_clicked = Signal()

    def __init__(self, title, items, shape=None, context="hub", parent=None):
        super().__init__(parent)
        shape = shape_for(items, shape)
        self.model = MediaModel(items, parent=self)
        self.view = HubView(self.model, shape, context, self)
        self.view.setFlow(QListView.Flow.LeftToRight)
        self.view.setWrapping(False)
        self.view.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.view.setFixedHeight(SHAPES[shape][1] + TEXT_HEIGHT + 4)
        self.view.opened.connect(self.opened)
        self.view.horizontalScrollBar().rangeChanged.connect(lambda *_: self._update_arrows())
        self.view.horizontalScrollBar().valueChanged.connect(lambda *_: self._update_arrows())

        header = QHBoxLayout()
        header.setContentsMargins(GAP // 2, 0, 0, 0)
        self.title = QPushButton(title)
        self.title.setObjectName("Link")
        self.title.setStyleSheet("font-size: 19px; font-weight: 600; color: white;")
        self.title.setCursor(Qt.CursorShape.PointingHandCursor)
        self.title.clicked.connect(self.title_clicked)
        header.addWidget(self.title)
        header.addStretch()
        self.prev = self._arrow("chevron_left", -1)
        self.next = self._arrow("chevron_right", 1)
        header.addWidget(self.prev)
        header.addWidget(self.next)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(header)
        layout.addWidget(self.view)

    def _arrow(self, name, direction):
        b = QPushButton()
        b.setObjectName("IconButton")
        b.setIcon(icons.icon(name, "#bbbbbb", active_color="#ffffff"))
        b.setIconSize(QSize(22, 22))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self._page(direction))
        return b

    def _page(self, direction):
        bar = self.view.horizontalScrollBar()
        bar.setValue(bar.value() + direction * int(self.view.viewport().width() * 0.85))

    def _update_arrows(self):
        bar = self.view.horizontalScrollBar()
        self.prev.setEnabled(bar.value() > bar.minimum())
        self.next.setEnabled(bar.value() < bar.maximum())
        self.prev.setVisible(bar.maximum() > 0)
        self.next.setVisible(bar.maximum() > 0)


def label(text, name=None, wrap=False):
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return lab
