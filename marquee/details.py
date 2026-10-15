"""Item details: backdrop, poster, actions, version/audio/subtitle pickers, seasons, episodes, cast."""
from PySide6.QtCore import QRectF, QSize, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPixmap
from PySide6.QtWidgets import (QComboBox, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
                               QVBoxLayout, QWidget)

from . import icons, theme
from .api import PLAYABLE, fmt_clock, fmt_duration, streams, video_badges
from .cards import HubRow, label
from .images import ImageLoader
from .workers import run_async


def rounded(pm, w, h, radius=6):
    """Center-crop a pixmap to w x h (logical px) with rounded corners."""
    dpr = pm.devicePixelRatio() or 1
    target = QPixmap(int(w * 2), int(h * 2))
    target.fill(Qt.GlobalColor.transparent)
    scaled = pm.scaled(target.size(), Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                       Qt.TransformationMode.SmoothTransformation)
    p = QPainter(target)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, target.width(), target.height()), radius * 2, radius * 2)
    p.setClipPath(path)
    p.drawPixmap(-(scaled.width() - target.width()) // 2, -(scaled.height() - target.height()) // 2, scaled)
    p.end()
    target.setDevicePixelRatio(2)
    del dpr
    return target


class ImageLabel(QLabel):
    def __init__(self, path, w, h, radius=6, placeholder="movie"):
        super().__init__()
        self.setFixedSize(w, h)
        self.setStyleSheet(f"background: {theme.CARD}; border-radius: {radius}px;")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setPixmap(icons.pixmap(placeholder, "#4a4e54", min(48, h // 3)))
        if path and ImageLoader.instance():
            ImageLoader.instance().load(path, w * 2, h * 2, lambda pm: (
                not pm.isNull() and (self.setPixmap(rounded(pm, w, h, radius)),
                                     self.setStyleSheet("background: transparent;"))))


def round_button(icon_name, tip, slot, checkable=False, checked=False):
    b = QPushButton(objectName="Round")
    b.setIcon(icons.icon(icon_name, "#ffffff"))
    b.setIconSize(QSize(20, 20))
    b.setToolTip(tip)
    b.setCheckable(checkable)
    b.setChecked(checked)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.clicked.connect(slot)
    return b


class EpisodeRow(QWidget):
    def __init__(self, app, m):
        super().__init__()
        self.app, self.m = app, m
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        thumb = ImageLabel(m.get("thumb"), 256, 144, 5, "show")
        if m.get("viewOffset") and m.get("duration"):
            bar = QWidget(thumb)
            bar.setGeometry(0, 139, int(256 * m["viewOffset"] / m["duration"]), 5)
            bar.setStyleSheet(f"background: {theme.ACCENT};")
        text = QVBoxLayout()
        text.setSpacing(4)
        top = QHBoxLayout()
        top.addWidget(label(f"{m.get('index', '')}. {m.get('title', '')}", "HubTitle"))
        if m.get("viewCount"):
            check = QLabel()
            check.setPixmap(icons.pixmap("check", theme.ACCENT, 18))
            top.addWidget(check)
        top.addStretch()
        text.addLayout(top)
        meta = [fmt_duration(m.get("duration"))]
        if m.get("originallyAvailableAt"):
            meta.append(m["originallyAvailableAt"])
        if m.get("viewOffset"):
            meta.append(f"{fmt_clock(m['duration'] - m['viewOffset'])} left")
        text.addWidget(label(" · ".join(x for x in meta if x), "Muted"))
        summary = label(m.get("summary", ""), "Muted", wrap=True)
        summary.setMaximumHeight(60)
        text.addWidget(summary)
        text.addStretch()
        play = round_button("play", "Play", lambda: app.play(m))
        row = QHBoxLayout(self)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(20)
        row.addWidget(thumb)
        row.addLayout(text, 1)
        row.addWidget(play, 0, Qt.AlignmentFlag.AlignVCenter)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.app.open_item(self.m)

    def paintEvent(self, event):
        if self.underMouse():
            p = QPainter(self)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            p.setBrush(QColor(255, 255, 255, 14))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRoundedRect(self.rect(), 6, 6)


class TrackRow(QPushButton):
    def __init__(self, app, m):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setStyleSheet("QPushButton { text-align: left; padding: 8px 10px; border-radius: 4px; }"
                           "QPushButton:hover { background: rgba(255,255,255,0.06); }")
        row = QHBoxLayout(self)
        row.setContentsMargins(10, 4, 10, 4)
        num = label(str(m.get("index", "")), "Faint")
        num.setFixedWidth(28)
        row.addWidget(num)
        row.addWidget(label(m.get("title", "")), 1)
        row.addWidget(label(fmt_clock(m.get("duration")), "Muted"))
        self.setMinimumHeight(40)
        self.clicked.connect(lambda: app.play(m))


class CastCard(QWidget):
    def __init__(self, role):
        super().__init__()
        self.setFixedWidth(124)
        box = QVBoxLayout(self)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(4)
        box.addWidget(ImageLabel(role.get("thumb"), 110, 110, 55, "person"), 0, Qt.AlignmentFlag.AlignHCenter)
        for text, name in ((role.get("tag", ""), None), (role.get("role", ""), "Faint")):
            lab = label(text, name)
            lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            lab.setStyleSheet("font-size: 13px;" + ("font-weight:600;" if not name else ""))
            lab.setFixedWidth(124)
            lab.setText(lab.fontMetrics().elidedText(text, Qt.TextElideMode.ElideRight, 120))
            box.addWidget(lab)


class DetailsPage(QWidget):
    """One page for movies, shows, seasons, episodes, artists, albums and collections."""

    def __init__(self, app, rating_key, title=""):
        super().__init__()
        self.app, self.rating_key, self.title = app, rating_key, title
        self.meta = None
        self.backdrop = None
        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.verticalScrollBar().setSingleStep(40)
        self.scroll.viewport().setAutoFillBackground(False)
        self.body = QWidget(objectName="Page")
        self.box = QVBoxLayout(self.body)
        self.box.setContentsMargins(40, 40, 40, 50)
        self.box.setSpacing(30)
        self.scroll.setWidget(self.body)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(self.scroll)
        self.box.addWidget(label("Loading…", "Muted"))
        self.app.downloads.changed.connect(self._update_download_button)
        self.refresh()

    # --- data ---------------------------------------------------------------------

    def refresh(self):
        def load():
            meta = self.app.client.metadata(self.rating_key)
            kids = []
            if meta.get("type") in ("show", "season", "artist", "album", "collection"):
                kids = self.app.client.children(self.rating_key)
            return meta, kids
        run_async(load, self._loaded, self._failed)

    def _failed(self, e):
        self._clear()
        self.box.addWidget(label(f"Couldn't load this item.\n{e}", "Muted", wrap=True))
        self.box.addStretch()

    def _loaded(self, result):
        self.meta, self.children = result
        self.title = self.meta.get("title", "")
        art = self.meta.get("art") or self.meta.get("grandparentArt") or self.meta.get("parentArt")
        if art and ImageLoader.instance():
            ImageLoader.instance().load(art, 1920, 1080, self._set_backdrop)
        self._build()

    def _set_backdrop(self, pm):
        self.backdrop = None if pm.isNull() else pm
        self.update()

    def paintEvent(self, event):
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(theme.BG))
        if self.backdrop is not None:
            w = self.width()
            h = int(w * 9 / 16)
            scaled = self.backdrop.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                          Qt.TransformationMode.SmoothTransformation)
            p.setOpacity(0.38)
            p.drawPixmap(0, 0, scaled)
            p.setOpacity(1)
            fade = QLinearGradient(0, 0, 0, h)
            fade.setColorAt(0.0, QColor(31, 35, 38, 40))
            fade.setColorAt(0.55, QColor(31, 35, 38, 170))
            fade.setColorAt(1.0, QColor(31, 35, 38, 255))
            p.fillRect(0, 0, w, h, fade)
            side = QLinearGradient(0, 0, w, 0)
            side.setColorAt(0.0, QColor(31, 35, 38, 200))
            side.setColorAt(0.6, QColor(31, 35, 38, 0))
            p.fillRect(0, 0, w, h, side)

    # --- layout -------------------------------------------------------------------

    def _clear(self):
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
            elif item.layout():
                QWidget().setLayout(item.layout())  # reparent so it gets deleted

    def _build(self):
        self._clear()
        m = self.meta
        kind = m.get("type")
        header = QHBoxLayout()
        header.setSpacing(40)
        wide = kind == "episode"
        poster_path = m.get("thumb") if kind != "episode" else m.get("thumb")
        shape = (360, 203) if wide else (220, 220) if kind in ("artist", "album") else (240, 360)
        header.addWidget(ImageLabel(poster_path, *shape, 6, "show" if kind in ("show", "season", "episode") else "movie"),
                         0, Qt.AlignmentFlag.AlignTop)
        header.addLayout(self._info(), 1)
        self.box.addLayout(header)

        if kind in PLAYABLE and kind != "track":
            pickers = self._stream_pickers()
            if pickers:
                self.box.addLayout(pickers)
        if kind == "show" and self.children:
            row = HubRow(f"Seasons ({len(self.children)})", self.children, "poster", context="show")
            row.opened.connect(self.app.open_item)
            self.box.addWidget(row)
        elif kind == "season":
            self.box.addWidget(label(f"{len(self.children)} Episodes", "HubTitle"))
            for ep in self.children:
                self.box.addWidget(EpisodeRow(self.app, ep))
        elif kind == "album":
            tracks = QVBoxLayout()
            tracks.setSpacing(0)
            for t in self.children:
                tracks.addWidget(TrackRow(self.app, t))
            self.box.addLayout(tracks)
        elif kind in ("artist", "collection") and self.children:
            row = HubRow("Albums" if kind == "artist" else "Items", self.children)
            row.opened.connect(self.app.open_item)
            self.box.addWidget(row)

        roles = m.get("Role") or []
        if roles:
            self.box.addWidget(label("Cast & Crew", "HubTitle"))
            cast = QScrollArea()
            cast.setWidgetResizable(True)
            cast.setFixedHeight(170)
            cast.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            holder = QWidget(objectName="Page")
            row = QHBoxLayout(holder)
            row.setContentsMargins(0, 0, 0, 0)
            row.setSpacing(14)
            for role in roles[:30]:
                row.addWidget(CastCard(role))
            row.addStretch()
            cast.setWidget(holder)
            self.box.addWidget(cast)
        self.box.addStretch()

    def _info(self):
        m = self.meta
        kind = m.get("type")
        col = QVBoxLayout()
        col.setSpacing(10)
        if kind == "episode":
            link = QPushButton(m.get("grandparentTitle", ""), objectName="Link")
            link.setStyleSheet("font-size: 18px; font-weight: 600;")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda: self.app.open_key(m.get("grandparentRatingKey"), m.get("grandparentTitle")))
            col.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)
        elif kind in ("season", "album"):
            link = QPushButton(m.get("parentTitle", ""), objectName="Link")
            link.setStyleSheet("font-size: 18px; font-weight: 600;")
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.clicked.connect(lambda: self.app.open_key(m.get("parentRatingKey"), m.get("parentTitle")))
            col.addWidget(link, 0, Qt.AlignmentFlag.AlignLeft)
        title = label(m.get("title", ""), "DetailTitle", wrap=True)
        col.addWidget(title)

        facts = []
        if kind == "episode":
            facts.append(f"Season {m.get('parentIndex', '')} · Episode {m.get('index', '')}")
        if m.get("year"):
            facts.append(str(m["year"]))
        if kind in ("movie", "episode") and m.get("duration"):
            facts.append(fmt_duration(m["duration"]))
        if kind == "show" and m.get("childCount"):
            facts.append(f"{m['childCount']} Seasons")
        if kind == "season" and m.get("leafCount"):
            facts.append(f"{m['leafCount']} Episodes")
        if m.get("contentRating"):
            facts.append(m["contentRating"])
        meta_row = QHBoxLayout()
        meta_row.setSpacing(10)
        meta_row.addWidget(label("   ·   ".join(facts), "DetailMeta"))
        for badge in video_badges(m):
            meta_row.addWidget(label(badge, "Badge"))
        rating = m.get("audienceRating") or m.get("rating")
        if rating:
            meta_row.addWidget(label(f"★ {float(rating):.1f}", "DetailMeta"))
        meta_row.addStretch()
        col.addLayout(meta_row)

        col.addSpacing(8)
        col.addLayout(self._actions())
        col.addSpacing(8)
        if m.get("tagline"):
            col.addWidget(label(m["tagline"], "Tagline", wrap=True))
        if m.get("summary"):
            summary = label(m["summary"], "Summary", wrap=True)
            summary.setMaximumWidth(860)
            col.addWidget(summary)

        grid = QGridLayout()
        grid.setHorizontalSpacing(24)
        grid.setVerticalSpacing(6)
        rows = [("Directed by", m.get("Director")), ("Written by", m.get("Writer")),
                ("Studio", [{"tag": m["studio"]}] if m.get("studio") else None), ("Genre", m.get("Genre"))]
        r = 0
        for name, tags in rows:
            if tags:
                grid.addWidget(label(name.upper(), "FactLabel"), r, 0)
                grid.addWidget(label(", ".join(t["tag"] for t in tags[:4]), "FactValue"), r, 1)
                r += 1
        grid.setColumnStretch(2, 1)
        col.addLayout(grid)
        col.addStretch()
        return col

    def _actions(self):
        m = self.meta
        kind = m.get("type")
        row = QHBoxLayout()
        row.setSpacing(12)
        play = QPushButton(objectName="Primary")
        play.setIcon(icons.icon("play", "#000000"))
        play.setIconSize(QSize(22, 22))
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        if kind in PLAYABLE:
            if m.get("viewOffset"):
                play.setText(f"Resume from {fmt_clock(m['viewOffset'])}")
                play.clicked.connect(lambda: self.app.play(m, media_index=self._version()))
                row.addWidget(play)
                again = QPushButton("Play from start", objectName="Secondary")
                again.setCursor(Qt.CursorShape.PointingHandCursor)
                again.clicked.connect(lambda: self.app.play(m, from_start=True, media_index=self._version()))
                row.addWidget(again)
            else:
                play.setText("Play")
                play.clicked.connect(lambda: self.app.play(m, media_index=self._version()))
                row.addWidget(play)
        elif kind in ("show", "season", "album", "artist"):
            target = self._up_next()
            if target is not None:
                play.setText("Play" if not target.get("viewOffset") else "Resume")
                if kind in ("show", "season") and target.get("type") == "episode":
                    play.setText(f"{play.text()} S{target.get('parentIndex')} · E{target.get('index')}")
                play.clicked.connect(lambda: self.app.play(target))
                row.addWidget(play)

        watched = bool(m.get("viewCount")) if kind in PLAYABLE else \
            m.get("leafCount") is not None and m.get("leafCount") == m.get("viewedLeafCount")
        if kind not in ("artist", "album", "collection"):
            self.watched_btn = round_button("check", "Mark as unwatched" if watched else "Mark as watched",
                                            self._toggle_watched, checkable=True, checked=watched)
            row.addWidget(self.watched_btn)
        if kind in PLAYABLE or kind in ("show", "season", "album"):
            self.download_btn = round_button("download", "", lambda: self.app.downloads.download(m))
            row.addWidget(self.download_btn)
            self._update_download_button()
        row.addStretch()
        return row

    def _up_next(self):
        m = self.meta
        if m.get("OnDeck", {}).get("Metadata"):
            return m["OnDeck"]["Metadata"][0]
        kids = [c for c in self.children if c.get("type") in PLAYABLE]
        if kids:
            return next((c for c in kids if not c.get("viewCount")), kids[0])
        return None

    def _stream_pickers(self):
        m = self.meta
        media = m.get("Media") or []
        if not media:
            return None
        row = QHBoxLayout()
        row.setSpacing(16)

        def picker(name, box):
            col = QVBoxLayout()
            col.setSpacing(4)
            col.addWidget(label(name.upper(), "FactLabel"))
            box.setMinimumWidth(260)
            box.setMaximumWidth(380)
            col.addWidget(box)
            row.addLayout(col)

        self.version_box = None
        if len(media) > 1:
            self.version_box = QComboBox()
            for v in media:
                bits = [str(v.get("videoResolution", "")).upper(), v.get("videoCodec", ""),
                        v.get("audioCodec", ""), v.get("container", "")]
                self.version_box.addItem(" · ".join(b for b in bits if b) or "Version")
            self.version_box.currentIndexChanged.connect(lambda _: self._fill_tracks())
            picker("Version", self.version_box)
        self.audio_box = QComboBox()
        self.sub_box = QComboBox()
        picker("Audio", self.audio_box)
        picker("Subtitles", self.sub_box)
        row.addStretch()
        self._fill_tracks()
        self.audio_box.activated.connect(lambda i: self._save_stream("audio", self.audio_box.itemData(i)))
        self.sub_box.activated.connect(lambda i: self._save_stream("subtitle", self.sub_box.itemData(i)))
        return row

    def _version(self):
        return self.version_box.currentIndex() if getattr(self, "version_box", None) else 0

    def _part(self):
        media = self.meta.get("Media") or [{}]
        return (media[self._version()].get("Part") or [{}])[0]

    def _fill_tracks(self):
        part = self._part()
        self.audio_box.clear()
        for s in streams(part, 2):
            self.audio_box.addItem(s.get("extendedDisplayTitle") or s.get("displayTitle", ""), s["id"])
            if s.get("selected"):
                self.audio_box.setCurrentIndex(self.audio_box.count() - 1)
        self.sub_box.clear()
        self.sub_box.addItem("None", 0)
        for s in streams(part, 3):
            self.sub_box.addItem(s.get("extendedDisplayTitle") or s.get("displayTitle", ""), s["id"])
            if s.get("selected"):
                self.sub_box.setCurrentIndex(self.sub_box.count() - 1)
        self.audio_box.setEnabled(self.audio_box.count() > 0)

    def _save_stream(self, kind, stream_id):
        part = self._part()
        for s in part.get("Stream", []):  # keep the local copy in sync for playback
            if s.get("streamType") == (2 if kind == "audio" else 3):
                s["selected"] = s["id"] == stream_id
        args = {"audio_id": stream_id} if kind == "audio" else {"subtitle_id": stream_id}
        run_async(lambda: self.app.client.set_streams(part["id"], **args), None,
                  lambda e: self.app.toast(f"Couldn't save track choice: {e}"))

    def _toggle_watched(self):
        watched = self.watched_btn.isChecked()
        run_async(lambda: self.app.client.set_watched(self.rating_key, watched),
                  lambda _: (self.app.toast("Marked as watched" if watched else "Marked as unwatched"),
                             self.refresh()),
                  lambda e: self.app.toast(f"Couldn't update: {e}"))

    def _update_download_button(self):
        btn = getattr(self, "download_btn", None)
        if btn is None or self.meta is None:
            return
        try:
            state = self.app.downloads.state(self.meta.get("ratingKey"))
            kind = self.meta.get("type")
            tip = {"done": "Downloaded", "downloading": "Downloading…", "queued": "Queued for download",
                   "failed": "Download failed — click to retry"}.get(
                state, "Download season" if kind == "season" else "Download all episodes" if kind == "show"
                else "Download album" if kind == "album" else "Download")
            btn.setToolTip(tip)
            btn.setIcon(icons.icon("check" if state == "done" else "download",
                                   theme.ACCENT if state in ("done", "downloading", "queued") else "#ffffff"))
        except RuntimeError:  # page already deleted
            pass
