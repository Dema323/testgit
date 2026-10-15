"""Poster cards: list model, painted card delegate, grid and hub views, smooth scrolling, skeletons."""
from PySide6.QtCore import (QAbstractListModel, QEasingCurve, QEvent, QModelIndex, QObject, QPoint,
                            QPropertyAnimation, QRect, QRectF, QSize, Qt, Signal)
from PySide6.QtGui import QColor, QCursor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QListView, QPushButton, QSizePolicy, QStyle,
                               QStyledItemDelegate, QVBoxLayout, QWidget)

from . import icons, theme
from .api import card_image, card_subtitle, card_title
from .images import ImageLoader
from .workers import run_async

SHAPES = {  # card width, image height (logical px)
    "poster": (156, 234),
    "wide": (288, 162),
    "square": (168, 168),
}
TEXT_HEIGHT = 50
GAP = 20
RADIUS = 6
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


class SmoothScroll(QObject):
    """Animated mouse-wheel scrolling for a scroll area (touchpads keep native scrolling)."""

    def __init__(self, area, horizontal=False, step=150):
        super().__init__(area)
        self.bar = area.horizontalScrollBar() if horizontal else area.verticalScrollBar()
        self.horizontal, self.step = horizontal, step
        self.anim = QPropertyAnimation(self.bar, b"value", self)
        self.anim.setDuration(280)
        self.anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.target = None
        area.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() != QEvent.Type.Wheel or not event.pixelDelta().isNull():
            return False
        delta = event.angleDelta()
        d = delta.x() if self.horizontal else delta.y()
        if d == 0 or (not self.horizontal and abs(delta.x()) > abs(delta.y())):
            return False
        self.scroll_by(-d / 120 * self.step)
        return True

    def scroll_by(self, amount):
        running = self.anim.state() == QPropertyAnimation.State.Running
        start = self.target if running and self.target is not None else self.bar.value()
        self.target = int(max(self.bar.minimum(), min(self.bar.maximum(), start + amount)))
        self.anim.stop()
        self.anim.setStartValue(self.bar.value())
        self.anim.setEndValue(self.target)
        self.anim.start()


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
        self.title_font = theme.font(14, QFont.Weight.DemiBold)
        self.sub_font = theme.font(13, QFont.Weight.Medium)
        self.links = {}  # row -> [(QRect, target metadata)] for show / "S9" / "E9" text links

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

        pm = self._pixmap(m, w, h)
        if pm is not None and not pm.isNull():
            painter.setClipPath(clip)
            painter.drawPixmap(img, pm, QRectF(pm.rect()))
            painter.setClipping(False)
        else:
            painter.fillPath(clip, theme.color("card"))
            glyph = icons.pixmap(icons.section_icon({"episode": "show", "season": "show",
                                                     "track": "artist", "album": "artist"}
                                                    .get(m.get("type"), m.get("type"))),
                                 "#3d4147", 40)
            painter.drawPixmap(int(img.center().x() - 20), int(img.center().y() - 20), glyph)

        self._badges(painter, m, img)

        if hovered:
            painter.fillPath(clip, QColor(0, 0, 0, 70))
            painter.setPen(QPen(theme.color("accent"), 3))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(img.adjusted(1.5, 1.5, -1.5, -1.5), RADIUS, RADIUS)
            if m.get("type") in ("movie", "episode", "track", "clip") and not m.get("_download_state"):
                c = img.center()
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(theme.color("accent"))
                painter.drawEllipse(c, 27, 27)
                painter.drawPixmap(int(c.x() - 13), int(c.y() - 14), icons.pixmap("play", "#111111", 28))

        mouse = self.view.viewport().mapFromGlobal(QCursor.pos())
        links = []
        title = card_title(m, self.context)
        title_rect = QRect(int(x), int(y + h + 9), w, 20)
        painter.setFont(self.title_font)
        fm = painter.fontMetrics()
        title = fm.elidedText(title, Qt.TextElideMode.ElideRight, w)
        if m.get("type") == "episode" and self.context != "season" and m.get("grandparentRatingKey"):
            # Episode cards: show name -> show, "S9" -> season, "E9" -> episode (like Plex)
            r_show = QRect(title_rect.x(), title_rect.y(), fm.horizontalAdvance(title), 20)
            links.append((r_show, {"ratingKey": m["grandparentRatingKey"], "type": "show"}))
            self._link_text(painter, r_show, title, QColor(theme.TEXT), r_show.contains(mouse))
            painter.setFont(self.sub_font)
            fm = painter.fontMetrics()
            sx = int(x)
            season = f"S{int(m.get('parentIndex') or 0)}"
            r_s = QRect(sx, int(y + h + 29), fm.horizontalAdvance(season), 18)
            dot = " · "
            r_e = QRect(r_s.right() + 1 + fm.horizontalAdvance(dot), r_s.y(),
                        fm.horizontalAdvance(f"E{int(m.get('index') or 0)}"), 18)
            muted = QColor(255, 255, 255, 150)
            if m.get("parentRatingKey"):
                links.append((r_s, {"ratingKey": m["parentRatingKey"], "type": "season"}))
            links.append((r_e, {"ratingKey": m["ratingKey"], "type": "episode"}))
            self._link_text(painter, r_s, season, muted, r_s.contains(mouse))
            painter.setPen(muted)
            painter.drawText(QRect(r_s.right() + 1, r_s.y(), 40, 18), Qt.AlignmentFlag.AlignLeft, dot)
            self._link_text(painter, r_e, f"E{int(m.get('index') or 0)}", muted, r_e.contains(mouse))
        else:
            painter.setPen(QColor(theme.TEXT))
            painter.drawText(title_rect, Qt.AlignmentFlag.AlignLeft, title)
            painter.setPen(QColor(255, 255, 255, 150))
            painter.setFont(self.sub_font)
            fm = painter.fontMetrics()
            painter.drawText(QRect(int(x), int(y + h + 29), w, 18), Qt.AlignmentFlag.AlignLeft,
                             fm.elidedText(card_subtitle(m, self.context), Qt.TextElideMode.ElideRight, w))
        self.links[index.row()] = links
        painter.restore()

    @staticmethod
    def _link_text(painter, rect, text, color, hovered):
        painter.setPen(QColor(theme.ACCENT) if hovered else color)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft, text)
        if hovered:
            painter.drawLine(rect.left(), rect.bottom() - 1, rect.right(), rect.bottom() - 1)

    def link_at(self, row, pos):
        return next((target for rect, target in self.links.get(row, []) if rect.contains(pos)), None)

    def _badges(self, painter, m, img):
        accent = theme.color("accent")
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
                self._pill(painter, img, label, QColor(0, 0, 0, 210), QColor(theme.TEXT))
            return

        unwatched = None
        if m.get("type") in ("show", "season") and "leafCount" in m:
            unwatched = int(m.get("leafCount", 0)) - int(m.get("viewedLeafCount", 0))
        if unwatched:
            self._pill(painter, img, str(unwatched), accent, QColor("#111111"))
        elif m.get("type") in ("movie", "episode") and not m.get("viewCount") and not m.get("viewOffset"):
            tri = QPainterPath()  # unwatched corner marker
            tri.moveTo(img.right() - 22, img.top())
            tri.lineTo(img.right() - RADIUS, img.top())
            tri.quadTo(img.right(), img.top(), img.right(), img.top() + RADIUS)
            tri.lineTo(img.right(), img.top() + 22)
            tri.closeSubpath()
            painter.fillPath(tri, accent)

    def _pill(self, painter, img, text, bg, fg):
        painter.setFont(theme.font(12, QFont.Weight.Bold))
        fm = painter.fontMetrics()
        pw = max(24, fm.horizontalAdvance(text) + 14)
        r = QRectF(img.right() - pw - 7, img.top() + 7, pw, 22)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(bg)
        painter.drawRoundedRect(r, 11, 11)
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
        self.setFrameShape(QListView.Shape.NoFrame)
        self.clicked.connect(lambda idx: self.opened.emit(idx.data(ITEM)))
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._context)

    def mouseReleaseEvent(self, event):
        idx = self.indexAt(event.position().toPoint())
        if idx.isValid() and event.button() == Qt.MouseButton.LeftButton:
            target = self.card_delegate.link_at(idx.row(), event.position().toPoint())
            if target is not None:
                self.opened.emit(target)  # e.g. jump to the season from "S9"
                return
        super().mouseReleaseEvent(event)

    def mouseMoveEvent(self, event):
        super().mouseMoveEvent(event)
        self.viewport().update()  # link hover underline

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
        SmoothScroll(self)


class HubView(CardView):
    def wheelEvent(self, event):
        # Horizontal swipes scroll the row; plain wheel turns go to the page.
        if abs(event.angleDelta().x()) > abs(event.angleDelta().y()) or not event.pixelDelta().isNull() \
                and abs(event.pixelDelta().x()) > abs(event.pixelDelta().y()):
            super().wheelEvent(event)
        else:
            event.ignore()


class HubRow(QWidget):
    """Titled horizontal strip of cards with animated page arrows."""
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
        self.scroller = SmoothScroll(self.view, horizontal=True)
        self.scroller.anim.setDuration(420)
        bar = self.view.horizontalScrollBar()
        bar.rangeChanged.connect(lambda *_: self._update_arrows())
        bar.valueChanged.connect(lambda *_: self._update_arrows())

        header = QHBoxLayout()
        header.setContentsMargins(GAP // 2, 0, 0, 0)
        self.title = QLabel(title, objectName="HubTitle")
        header.addWidget(self.title)
        header.addStretch()
        self.prev = self._arrow("chevron_left", -1)
        self.next = self._arrow("chevron_right", 1)
        header.addWidget(self.prev)
        header.addWidget(self.next)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)
        layout.addLayout(header)
        layout.addWidget(self.view)

    def _arrow(self, name, direction):
        b = QPushButton(objectName="IconButton")
        b.setIcon(icons.icon(name, "#bbbbbb", active_color="#ffffff"))
        b.setIconSize(QSize(22, 22))
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(lambda: self.scroller.scroll_by(direction * int(self.view.viewport().width() * 0.85)))
        return b

    def _update_arrows(self):
        bar = self.view.horizontalScrollBar()
        self.prev.setEnabled(bar.value() > bar.minimum())
        self.next.setEnabled(bar.value() < bar.maximum())
        self.prev.setVisible(bar.maximum() > 0)
        self.next.setVisible(bar.maximum() > 0)


class SkeletonRow(QWidget):
    """Grey placeholder of a hub row, shown while a page loads."""

    def __init__(self, shape="poster", count=8, parent=None):
        super().__init__(parent)
        self.shape, self.count = shape, count
        self.setFixedHeight(SHAPES[shape][1] + TEXT_HEIGHT + 40)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 14))
        p.drawRoundedRect(QRectF(GAP // 2, 4, 200, 20), 4, 4)
        w, h = SHAPES[self.shape]
        for i in range(self.count):
            x = GAP // 2 + i * (w + GAP)
            if x > self.width():
                break
            p.setBrush(QColor(255, 255, 255, 12))
            p.drawRoundedRect(QRectF(x, 40, w, h), RADIUS, RADIUS)
            p.setBrush(QColor(255, 255, 255, 10))
            p.drawRoundedRect(QRectF(x, 40 + h + 12, w * 0.7, 12), 3, 3)


def episode_links_html(m, with_title=True, color="rgba(255,255,255,0.75)"):
    """'S9 · E9 — Title' where S9 links to the season and E9 to the episode."""
    style = f"color:{color}; text-decoration:none;"
    season = f"S{int(m.get('parentIndex') or 0)}"
    if m.get("parentRatingKey"):
        season = f'<a href="{m["parentRatingKey"]}" style="{style}">{season}</a>'
    episode = f'<a href="{m.get("ratingKey")}" style="{style}">E{int(m.get("index") or 0)}</a>'
    title = f" — {m.get('title', '')}" if with_title and m.get("title") else ""
    return f"{season} · {episode}{title.replace('<', '&lt;')}"


class LinkLabel(QLabel):
    """Rich-text label whose links are rating keys; on_open(rating_key) is called on click."""

    def __init__(self, html="", on_open=None, name="EpLinks"):
        super().__init__(html)
        self.setObjectName(name)
        self.setTextFormat(Qt.TextFormat.RichText)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.LinksAccessibleByMouse)
        self.setOpenExternalLinks(False)
        if on_open:
            self.linkActivated.connect(on_open)


def label(text, name=None, wrap=False):
    lab = QLabel(text)
    if name:
        lab.setObjectName(name)
    lab.setWordWrap(wrap)
    lab.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
    return lab
