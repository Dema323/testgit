"""In-window video player: libmpv renders into a native child window (keeps HDR passthrough),
and the controls live in a transparent overlay window kept exactly on top of it.

Modes:
  direct     original file streamed from the server (all codecs, 4K HDR handled by mpv)
  transcode  server converts to HLS at the chosen quality
  local      a downloaded file played from disk (works offline)
"""
import math
import os
import sys
import time
import uuid

from PySide6.QtCore import (QEasingCurve, QEvent, QPoint, QPointF, QPropertyAnimation, QRectF, QSize,
                            Qt, QTimer, Signal)
from PySide6.QtGui import (QColor, QCursor, QFont, QIcon, QKeySequence, QLinearGradient, QPainter,
                           QPainterPath, QPen, QPixmap, QShortcut)
from PySide6.QtWidgets import (QButtonGroup, QGraphicsOpacityEffect, QHBoxLayout, QLabel, QPushButton,
                               QScrollArea, QSlider, QVBoxLayout, QWidget)

from . import icons, theme
from .api import QUALITIES, fmt_clock, streams
from .config import data_dir
from .images import ImageLoader
from .workers import run_async

REPORT_INTERVAL = 10
WATCHED_FRACTION = 0.9
HIDE_AFTER = 2.5  # seconds without mouse movement before controls fade while playing


def load_mpv():
    """Import python-mpv, making a bundled libmpv-2.dll findable in the packaged exe."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        os.environ["PATH"] = base + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(base)
    import mpv  # noqa: PLC0415 - deferred so the library UI works without libmpv
    return mpv


# --- painted controls -------------------------------------------------------------------

def skip_icon(seconds, forward, size=40):
    """Circular arrow with the number of seconds inside (like Plex's skip buttons)."""
    dpr = 2
    pm = QPixmap(size * dpr, size * dpr)
    pm.fill(Qt.GlobalColor.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.scale(dpr, dpr)
    s = size
    pen = QPen(QColor("white"), s * 0.075, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    p.setPen(pen)
    rect = QRectF(s * 0.14, s * 0.14, s * 0.72, s * 0.72)
    start = 100 if forward else 80
    span = -290 if forward else 290
    p.drawArc(rect, start * 16, span * 16)
    # arrowhead at the arc's start (top)
    cx, cy, r = s / 2, s / 2, s * 0.36
    ang = math.radians(start)
    tip = QPointF(cx + r * math.cos(ang), cy - r * math.sin(ang))
    d = 1 if forward else -1
    head = QPainterPath()
    head.moveTo(tip + QPointF(d * s * 0.13, 0))
    head.lineTo(tip + QPointF(-d * s * 0.04, -s * 0.11))
    head.lineTo(tip + QPointF(-d * s * 0.04, s * 0.11))
    head.closeSubpath()
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor("white"))
    p.drawPath(head)
    f = theme.font(int(s * 0.3), QFont.Weight.Bold)
    p.setFont(f)
    p.setPen(QColor("white"))
    p.drawText(QRectF(0, s * 0.04, s, s), Qt.AlignmentFlag.AlignCenter, str(seconds))
    p.end()
    pm.setDevicePixelRatio(dpr)
    return QIcon(pm)


class SeekBar(QWidget):
    """Plex-style seek bar: thin track that thickens on hover, buffered range, hover time bubble."""
    seek_requested = Signal(float)  # milliseconds

    def __init__(self):
        super().__init__()
        self.setFixedHeight(44)
        self.setMouseTracking(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.duration = 0.0
        self.position = 0.0
        self.buffered = 0.0
        self.hover_x = None
        self.dragging = False

    def _track(self):
        return QRectF(8, self.height() - 14, self.width() - 16, 6)

    def _ms_at(self, x):
        t = self._track()
        return max(0.0, min(1.0, (x - t.left()) / t.width())) * self.duration

    def set_state(self, position, duration, buffered):
        if not self.dragging:
            self.position = position
        self.duration, self.buffered = duration, buffered
        self.update()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton and self.duration:
            self.dragging = True
            self.position = self._ms_at(e.position().x())
            self.update()

    def mouseMoveEvent(self, e):
        self.hover_x = e.position().x()
        if self.dragging:
            self.position = self._ms_at(self.hover_x)
        self.update()

    def mouseReleaseEvent(self, e):
        if self.dragging:
            self.dragging = False
            self.seek_requested.emit(self.position)

    def leaveEvent(self, e):
        self.hover_x = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        t = self._track()
        active = self.hover_x is not None or self.dragging
        h = 6 if active else 4
        track = QRectF(t.left(), t.center().y() - h / 2, t.width(), h)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(255, 255, 255, 60))
        p.drawRoundedRect(track, h / 2, h / 2)
        if self.duration:
            frac = lambda v: max(0.0, min(1.0, v / self.duration))  # noqa: E731
            p.setBrush(QColor(255, 255, 255, 90))
            p.drawRoundedRect(QRectF(track.left(), track.top(), track.width() * frac(self.buffered), h), h / 2, h / 2)
            p.setBrush(theme.color("accent"))
            done = track.width() * frac(self.position)
            p.drawRoundedRect(QRectF(track.left(), track.top(), done, h), h / 2, h / 2)
            if active:
                p.setBrush(QColor("white"))
                p.drawEllipse(QPointF(track.left() + done, track.center().y()), 7, 7)
            if self.hover_x is not None:
                text = fmt_clock(self._ms_at(self.hover_x))
                p.setFont(theme.font(13, QFont.Weight.Bold))
                w = p.fontMetrics().horizontalAdvance(text) + 18
                x = max(0, min(self.width() - w, self.hover_x - w / 2))
                bubble = QRectF(x, 0, w, 24)
                p.setBrush(QColor(0, 0, 0, 200))
                p.drawRoundedRect(bubble, 5, 5)
                p.setPen(QColor("white"))
                p.drawText(bubble, Qt.AlignmentFlag.AlignCenter, text)


def osd_button(icon, tip, size=26, slot=None, checkable=False):
    b = QPushButton(objectName="OsdButton")
    b.setIcon(icon if isinstance(icon, QIcon) else icons.icon(icon, "#ffffff"))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setCheckable(checkable)
    if slot:
        b.clicked.connect(slot)
    return b


class Controls(QWidget):
    """Everything visible on top of the video; fades as a unit."""

    def paintEvent(self, e):
        p = QPainter(self)
        h = self.height()
        top = QLinearGradient(0, 0, 0, 140)
        top.setColorAt(0, QColor(0, 0, 0, 110))
        top.setColorAt(1, QColor(0, 0, 0, 0))
        p.fillRect(0, 0, self.width(), 140, top)
        bottom = QLinearGradient(0, h - 230, 0, h)
        bottom.setColorAt(0, QColor(0, 0, 0, 0))
        bottom.setColorAt(0.55, QColor(0, 0, 0, 95))
        bottom.setColorAt(1, QColor(0, 0, 0, 150))
        p.fillRect(0, h - 230, self.width(), 230, bottom)


class Overlay(QWidget):
    """Transparent tool window owned by the main window, kept over the video area."""

    def __init__(self, view):
        super().__init__(view.window(), Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint
                         | Qt.WindowType.NoDropShadowWindowHint | Qt.WindowType.WindowDoesNotAcceptFocus)
        self.view = view
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setMouseTracking(True)
        self.click_timer = QTimer(self, singleShot=True, interval=230, timeout=view.toggle_pause)

    def paintEvent(self, e):
        # Nearly-transparent fill so the window still receives mouse events over the video.
        QPainter(self).fillRect(self.rect(), QColor(0, 0, 0, 1))

    def mouseMoveEvent(self, e):
        self.view.show_controls()

    def mousePressEvent(self, e):
        if e.button() == Qt.MouseButton.LeftButton:
            if self.view.panel.isVisible():
                self.view.panel.hide()
            else:
                self.click_timer.start()

    def mouseDoubleClickEvent(self, e):
        self.click_timer.stop()
        self.view.toggle_fullscreen()

    def wheelEvent(self, e):
        self.view.change_volume(5 if e.angleDelta().y() > 0 else -5)

    def leaveEvent(self, e):
        self.view.maybe_hide_controls()


class PlayerView(QWidget):
    closed = Signal(str, int)  # ratingKey, last position (ms)

    def __init__(self, app, meta, media_index=0, start_ms=0, local_file=None):
        super().__init__()
        self.app = app
        self.client, self.downloads = app.client, app.downloads
        self.setStyleSheet("PlayerView { background: black; }")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.player = None
        self.closing = False
        self.loaded = False
        self.mode = None
        self.pos_ms = start_ms

        self.video = QWidget(self)
        self.video.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.video.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.video.setStyleSheet("background: black;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.video)

        self.overlay = Overlay(self)
        self._build_controls()
        self._shortcuts()
        app.installEventFilter(self)

        self.timer = QTimer(self, interval=250, timeout=self._tick)
        self.last_cursor = QCursor.pos()
        self.last_move = time.monotonic()
        self.controls_visible = True
        self.pending = (meta, media_index, start_ms, local_file)

    # --- UI -----------------------------------------------------------------------------

    def _build_controls(self):
        c = self.controls = Controls(self.overlay)
        c.setMouseTracking(True)
        self.fade = QGraphicsOpacityEffect(c)
        self.fade.setOpacity(1.0)
        c.setGraphicsEffect(self.fade)
        self.fade_anim = QPropertyAnimation(self.fade, b"opacity", self)
        self.fade_anim.setDuration(220)
        self.fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.fade_anim.finished.connect(lambda: c.setVisible(self.fade.opacity() > 0.01))

        back = osd_button("back", "Back (Esc)", 28, self.stop)
        self.top_title = QLabel(objectName="OsdTitle")
        self.fs_top = osd_button("fullscreen", "Fullscreen (F)", 26, self.toggle_fullscreen)
        top = QHBoxLayout()
        top.setContentsMargins(20, 16, 20, 0)
        top.addWidget(back)
        top.addSpacing(8)
        top.addWidget(self.top_title)
        top.addStretch()
        top.addWidget(self.fs_top)

        self.status = QLabel(objectName="OsdStatus")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.seek = SeekBar()
        self.seek.seek_requested.connect(self.seek_to)
        self.elapsed = QLabel("0:00", objectName="OsdClock")
        self.remaining = QLabel("", objectName="OsdClock")
        seek_row = QHBoxLayout()
        seek_row.setSpacing(10)
        seek_row.addWidget(self.elapsed, 0, Qt.AlignmentFlag.AlignBottom)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.remaining, 0, Qt.AlignmentFlag.AlignBottom)

        self.thumb = QLabel()
        self.thumb.setFixedSize(52, 78)
        self.title = QLabel(objectName="OsdTitle")
        self.subtitle = QLabel(objectName="OsdSub")
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addStretch()
        info.addWidget(self.title)
        info.addWidget(self.subtitle)
        info.addStretch()
        left = QHBoxLayout()
        left.setSpacing(14)
        left.addWidget(self.thumb)
        left.addLayout(info, 1)

        self.play_btn = osd_button("pause", "Pause (Space)", 44, self.toggle_pause)
        self.next_btn = osd_button("next", "Next episode", 28, self.play_next)
        center = QHBoxLayout()
        center.setSpacing(22)
        center.addWidget(osd_button(skip_icon(10, False), "Back 10 seconds (←)", 38, lambda: self.seek_by(-10000)))
        center.addWidget(self.play_btn)
        center.addWidget(osd_button(skip_icon(30, True), "Forward 30 seconds (→)", 38, lambda: self.seek_by(30000)))
        center.addWidget(self.next_btn)

        self.mute_btn = osd_button("volume", "Mute (M)", 24, self.toggle_mute)
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 130)
        self.volume.setValue(100)
        self.volume.setFixedWidth(96)
        self.volume.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.volume.valueChanged.connect(self._set_volume)
        self.settings_btn = osd_button("settings", "Audio, subtitles & quality", 26, self.toggle_panel, True)
        self.fs_btn = osd_button("fullscreen", "Fullscreen (F)", 26, self.toggle_fullscreen)
        right = QHBoxLayout()
        right.setSpacing(6)
        right.addStretch()
        right.addWidget(self.mute_btn)
        right.addWidget(self.volume)
        right.addSpacing(8)
        right.addWidget(self.settings_btn)
        right.addWidget(self.fs_btn)

        row = QHBoxLayout()
        row.addLayout(left, 1)
        row.addLayout(center)
        row.addLayout(right, 1)

        layout = QVBoxLayout(c)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(top)
        layout.addStretch()
        layout.addWidget(self.status)
        layout.addStretch()
        bottom = QVBoxLayout()
        bottom.setContentsMargins(30, 0, 30, 24)
        bottom.setSpacing(8)
        bottom.addLayout(seek_row)
        bottom.addLayout(row)
        layout.addLayout(bottom)

        self.panel = SettingsPanel(self, self.overlay)
        self.panel.hide()

    def _shortcuts(self):
        for keys, slot in ((Qt.Key.Key_Space, self.toggle_pause), (Qt.Key.Key_K, self.toggle_pause),
                           (Qt.Key.Key_F, self.toggle_fullscreen), (Qt.Key.Key_F11, self.toggle_fullscreen),
                           (Qt.Key.Key_Escape, self._escape), (Qt.Key.Key_M, self.toggle_mute),
                           (Qt.Key.Key_Left, lambda: self.seek_by(-10000)),
                           (Qt.Key.Key_Right, lambda: self.seek_by(30000)),
                           (Qt.Key.Key_Up, lambda: self.change_volume(5)),
                           (Qt.Key.Key_Down, lambda: self.change_volume(-5))):
            QShortcut(QKeySequence(keys), self, slot)

    # --- overlay placement ----------------------------------------------------------------

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.Move, QEvent.Type.Resize, QEvent.Type.WindowStateChange,
                            QEvent.Type.Show):
            QTimer.singleShot(0, self._place_overlay)
        elif event.type() == QEvent.Type.Hide:
            self.overlay.hide()
        return False

    def resizeEvent(self, event):
        self._place_overlay()

    def showEvent(self, event):
        QTimer.singleShot(0, self._place_overlay)

    def hideEvent(self, event):
        self.overlay.hide()

    def _place_overlay(self):
        if self.closing or not self.isVisible() or self.window().isMinimized():
            self.overlay.hide()
            return
        self.overlay.setGeometry(QRectFromWidget(self))
        self.controls.setGeometry(self.overlay.rect())
        self.panel.place()
        if not self.overlay.isVisible():
            self.overlay.show()

    # --- lifecycle --------------------------------------------------------------------------

    def start(self):
        """Create mpv once the view is on screen, then start the first item."""
        try:
            self.player = self._create_mpv()
        except Exception as e:  # noqa: BLE001 - missing libmpv etc.
            self.status.setText(f"Video player unavailable: {e}")
            return
        self.load(*self.pending)
        self.timer.start()
        self.controls_visible = False
        self._fade_to(0.0, False)  # controls appear on hover or when paused

    def _create_mpv(self):
        mpv = load_mpv()
        conf_dir = os.path.join(data_dir(), "mpv")  # your own mpv.conf / scripts go here
        os.makedirs(conf_dir, exist_ok=True)
        base = dict(
            wid=str(int(self.video.winId())),
            # gpu-next first; the older gpu renderer is the fallback for old GPUs, VMs and RDP.
            vo=os.environ.get("MARQUEE_VO", "gpu-next,gpu,"),
            hwdec="auto-safe",
            keep_open="yes",
            osc=False, input_default_bindings=False, input_vo_keyboard=False, input_cursor=False,
            cursor_autohide="no", ytdl=False, sub_auto="no",
            config=True, config_dir=conf_dir,
            demuxer_max_bytes="400MiB", demuxer_max_back_bytes="150MiB",
            sub_font=theme.FONT, sub_font_size=44, sub_border_size=2.5,
        )
        # HDR10/Dolby Vision: with gpu-next on Direct3D 11, target-colorspace-hint switches an
        # HDR-enabled Windows display into HDR and passes the stream's metadata through.
        optional = dict(target_colorspace_hint=True)
        if os.name == "nt":
            optional["gpu_api"] = "d3d11"
        try:
            return mpv.MPV(**base, **optional)
        except Exception:  # noqa: BLE001 - older libmpv without these options
            return mpv.MPV(**base)

    def load(self, meta, media_index=0, start_ms=0, local_file=None):
        self.meta = meta
        self.media_index = media_index
        media = meta.get("Media") or [{}]
        self.part = (media[min(media_index, len(media) - 1)].get("Part") or [{}])[0]
        self.local_file = local_file
        self.duration_ms = meta.get("duration") or self.part.get("duration") or 0
        self.pos_ms = start_ms
        self.quality = "original" if local_file else self.client.cfg.get("quality", "original")
        selected = lambda t: next((s for s in streams(self.part, t) if s.get("selected")), None)  # noqa: E731
        audio, sub = selected(2), selected(3)
        self.audio_id = audio["id"] if audio else None
        self.sub_id = sub["id"] if sub else 0
        self.session = None
        self.reported_state, self.last_report = None, 0.0
        self.scrobbled = False

        kind = meta.get("type")
        if kind == "episode":
            self.title.setText(meta.get("grandparentTitle", ""))
            self.subtitle.setText(f"S{meta.get('parentIndex', '')} · E{meta.get('index', '')}  —  {meta.get('title', '')}")
        else:
            self.title.setText(meta.get("title", ""))
            self.subtitle.setText(str(meta.get("year", "")) if kind == "movie" else meta.get("grandparentTitle", ""))
        self.top_title.setText(self.title.text())
        self.next_btn.setVisible(kind == "episode" and not local_file)
        self.thumb.clear()
        thumb = meta.get("_poster") or (meta.get("grandparentThumb") if kind == "episode" else meta.get("thumb"))
        if ImageLoader.instance() and thumb:
            ImageLoader.instance().load(thumb, 104, 156, lambda pm: self.thumb.setPixmap(_rounded_thumb(pm)))
        self._start_stream(start_ms)

    def _start_stream(self, pos_ms):
        self._stop_transcode()
        self.loaded = False
        self.started_at = time.monotonic()
        self.offset_ms = 0
        self.relative = None
        self.status.setText("")
        self.player["http-header-fields"] = self.client.mpv_headers()
        if self.local_file:
            self.mode = "local"
            self._play(self.local_file, pos_ms)
        elif self.quality == "original":
            self.mode = "direct"
            self._play(self.client.part_url(self.part["key"]), pos_ms)
        else:
            self.mode = "transcode"
            self.session = str(uuid.uuid4())
            self.offset_ms = pos_ms
            args = (self.meta["ratingKey"], self.media_index, self.quality, pos_ms / 1000,
                    self.session, bool(self.sub_id))
            url = self.client.transcode_url(*args)

            def decided(result):
                ok, text = result
                if not ok:
                    self.status.setText(f"The server can't convert this: {text}")
                    return
                self._play(url, 0)
            run_async(lambda: self.client.transcode_decision(*args), decided, lambda e: self._play(url, 0))

    def _play(self, url, pos_ms):
        if self.closing or self.player is None:
            return
        self.player["start"] = f"{pos_ms / 1000:.3f}" if pos_ms else "none"
        self.player.play(url)
        self.player.pause = False

    def _apply_tracks(self):
        if self.mode == "transcode":
            return  # the server already picked audio and burned in subtitles
        tracks = self.player.track_list or []

        def mpv_id(plex_stream, kind):
            index = plex_stream.get("index")
            return next((t["id"] for t in tracks if t.get("type") == kind
                         and not t.get("external") and t.get("ff-index") == index), None)

        audio = next((s for s in streams(self.part, 2) if s["id"] == self.audio_id), None)
        if audio and mpv_id(audio, "audio") is not None:
            self.player.aid = mpv_id(audio, "audio")
        sub = next((s for s in streams(self.part, 3) if s["id"] == self.sub_id), None)
        if not sub:
            self.player.sid = "no"
        elif sub.get("key") and self.mode != "local":
            self.player.command("sub-add", self.client.part_url(sub["key"]), "select",
                                sub.get("displayTitle", "Subtitles"))
        elif mpv_id(sub, "sub") is not None:
            self.player.sid = mpv_id(sub, "sub")

    # --- polling loop ---------------------------------------------------------------------------

    def _tick(self):
        if self.closing or self.player is None:
            return
        try:
            tp = self.player.time_pos
            paused = bool(self.player.pause)
            eof = bool(self.player.eof_reached)
            idle = bool(self.player.idle_active)
            buffering = bool(self.player.paused_for_cache) or bool(self.player.seeking)
            cache = self.player.demuxer_cache_time
            if not self.loaded and self.player.track_list:
                self.loaded = True
                if not self.duration_ms and self.player.duration:
                    self.duration_ms = self.player.duration * 1000
                self._apply_tracks()
        except Exception:  # noqa: BLE001 - mpv shut down underneath us
            return
        base = 0
        if tp is not None:
            if self.mode == "transcode":
                if self.relative is None:  # does the HLS stream start at 0 or at the offset?
                    self.relative = not (self.offset_ms > 15000 and abs(tp * 1000 - self.offset_ms) < 15000)
                base = self.offset_ms if self.relative else 0
            self.pos_ms = base + tp * 1000
        elif idle and not self.loaded and time.monotonic() - self.started_at > 20 and not self.status.text():
            self.status.setText("Couldn't play this item. Try a lower quality, or check the server.")
        if self.loaded and not self.status.text().startswith(("Couldn", "The server", "Volume")):
            self.status.setText("Buffering…" if buffering and not paused else "")

        buffered = base + (cache or 0) * 1000
        self.seek.set_state(self.pos_ms, self.duration_ms, buffered)
        shown = self.seek.position if self.seek.dragging else self.pos_ms
        self.elapsed.setText(fmt_clock(shown))
        self.remaining.setText("-" + fmt_clock(max(0, self.duration_ms - shown)) if self.duration_ms else "")
        self.play_btn.setIcon(icons.icon("play" if paused else "pause", "#ffffff"))

        state = "paused" if paused else "playing"
        if self.loaded and (state != self.reported_state or time.monotonic() - self.last_report > REPORT_INTERVAL):
            self._report(state)
        if self.loaded and eof:
            self._finished()
            return
        self._autohide(paused)

    def _autohide(self, paused):
        """Controls show while paused or while the mouse moves over the video; otherwise they fade."""
        pos = QCursor.pos()
        hovering = self.overlay.isVisible() and self.overlay.geometry().contains(pos)
        if paused:
            if not self.controls_visible:
                self.show_controls()
            return
        if pos != self.last_cursor:
            self.last_cursor = pos
            if hovering:
                self.show_controls()
        idle = time.monotonic() - self.last_move
        # Off the video: keep a brief flash for keyboard actions (seek/volume), then fade.
        if self.controls_visible and not self.panel.isVisible() and (
                idle > HIDE_AFTER or (not hovering and idle > 1.5)):
            self.hide_controls()

    def maybe_hide_controls(self):
        if self.player is not None and not self.player.pause and not self.panel.isVisible():
            self.hide_controls()

    def show_controls(self, animate=True):
        self.last_move = time.monotonic()
        self.overlay.unsetCursor()
        if self.controls_visible and self.fade.opacity() > 0.99:
            return
        self.controls_visible = True
        self.controls.show()
        self._fade_to(1.0, animate)

    def hide_controls(self):
        self.controls_visible = False
        self.overlay.setCursor(Qt.CursorShape.BlankCursor)
        self._fade_to(0.0, True)

    def _fade_to(self, value, animate):
        self.fade_anim.stop()
        if not animate:
            self.fade.setOpacity(value)
            self.controls.setVisible(value > 0.01)
            return
        self.fade_anim.setStartValue(self.fade.opacity())
        self.fade_anim.setEndValue(value)
        self.fade_anim.start()

    def _report(self, state):
        self.reported_state, self.last_report = state, time.monotonic()
        meta, pos, dur, session = self.meta, self.pos_ms, self.duration_ms, self.session
        if self.mode == "local" and self.downloads:
            self.downloads.update_progress(meta["ratingKey"], pos)
        run_async(lambda: self.client.timeline(meta, state, pos, dur, session), None, lambda e: None)
        if not self.scrobbled and dur and pos >= WATCHED_FRACTION * dur:
            self.scrobbled = True
            run_async(lambda: self.client.set_watched(meta["ratingKey"], True), None, lambda e: None)

    def _finished(self):
        self._report("stopped")
        if self.meta.get("type") == "episode" and not self.local_file:
            self.play_next()
        else:
            self.stop()

    # --- controls ---------------------------------------------------------------------------

    def toggle_pause(self):
        if self.player:
            self.player.pause = not self.player.pause
            self.show_controls()

    def seek_by(self, delta_ms):
        self.seek_to(self.pos_ms + delta_ms)
        self.show_controls()

    def seek_to(self, ms):
        if not self.player:
            return
        ms = max(0, min(ms, (self.duration_ms or ms + 1) - 1000))
        self.pos_ms = ms
        if self.mode == "transcode":
            self._start_stream(ms)  # the server restarts conversion at the new position
        else:
            try:
                self.player.seek(ms / 1000, "absolute")
            except Exception:  # noqa: BLE001 - seeking before the file has opened
                self.player["start"] = f"{ms / 1000:.3f}"

    def change_volume(self, delta):
        self.volume.setValue(self.volume.value() + delta)
        self.show_controls()

    def _set_volume(self, value):
        if self.player:
            self.player.volume = value
            self.player.mute = False
        self.mute_btn.setIcon(icons.icon("volume_off" if value == 0 else "volume", "#ffffff"))

    def toggle_mute(self):
        if self.player:
            self.player.mute = not self.player.mute
            self.mute_btn.setIcon(icons.icon("volume_off" if self.player.mute else "volume", "#ffffff"))
            self.show_controls()

    def toggle_fullscreen(self):
        self.app.set_fullscreen(not self.window().isFullScreen())
        name = "fullscreen_exit" if self.window().isFullScreen() else "fullscreen"
        for b in (self.fs_btn, self.fs_top):
            b.setIcon(icons.icon(name, "#ffffff"))

    def toggle_panel(self):
        if self.panel.isVisible():
            self.panel.hide()
        else:
            self.panel.open()
        self.settings_btn.setChecked(self.panel.isVisible())
        self.show_controls()

    def _escape(self):
        if self.panel.isVisible():
            self.toggle_panel()
        elif self.window().isFullScreen():
            self.toggle_fullscreen()
        else:
            self.stop()

    def play_next(self):
        meta = self.meta
        if meta.get("type") != "episode" or not meta.get("parentRatingKey"):
            self.stop()
            return

        def find_next():
            episodes = self.client.children(meta["parentRatingKey"])
            later = [e for e in episodes if int(e.get("index") or 0) > int(meta.get("index") or 0)]
            if not later and meta.get("grandparentRatingKey"):
                seasons = self.client.children(meta["grandparentRatingKey"])
                after = [s for s in seasons if int(s.get("index") or 0) > int(meta.get("parentIndex") or 0)]
                if after:
                    later = self.client.children(after[0]["ratingKey"])
            return self.client.metadata(later[0]["ratingKey"]) if later else None

        def go(next_meta):
            if next_meta is None:
                self.stop()
            elif not self.closing:
                self.status.setText("")
                self.load(next_meta, 0, 0)
        self.status.setText("Up next…")
        run_async(find_next, go, lambda e: self.stop())

    # track/quality choices (used by the settings panel)

    def _persist_streams(self, then=None, **ids):
        part_id = self.part.get("id")
        if not part_id or self.mode == "local":
            if then:
                then()
            return
        run_async(lambda: self.client.set_streams(part_id, **ids),
                  (lambda _: then()) if then else None,
                  (lambda _: then()) if then else (lambda e: None))

    def _choose_audio(self, stream):
        self.audio_id = stream["id"]
        if self.mode == "transcode":
            self._persist_streams(lambda: self._start_stream(self.pos_ms), audio_id=stream["id"])
        else:
            self._persist_streams(audio_id=stream["id"])
            self._apply_tracks()

    def _choose_subtitle(self, stream):
        self.sub_id = stream["id"] if stream else 0
        if self.mode == "transcode":
            self._persist_streams(lambda: self._start_stream(self.pos_ms), subtitle_id=self.sub_id)
        else:
            self._persist_streams(subtitle_id=self.sub_id)
            self._apply_tracks()

    def _choose_quality(self, quality):
        if quality != self.quality and not self.local_file:
            self.quality = quality
            self._start_stream(self.pos_ms)

    # --- teardown ---------------------------------------------------------------------------------

    def _stop_transcode(self):
        if self.session:
            session, self.session = self.session, None
            run_async(lambda: self.client.stop_transcode(session), None, lambda e: None)

    def stop(self):
        if self.closing:
            return
        self.closing = True
        self.timer.stop()
        self.app.removeEventFilter(self)
        self.overlay.hide()
        if self.player is not None:
            if self.loaded:
                self._report("stopped")
            self._stop_transcode()
            try:
                self.player.terminate()
            except Exception:  # noqa: BLE001
                pass
            self.player = None
        self.overlay.deleteLater()
        meta = getattr(self, "meta", None) or self.pending[0]
        self.closed.emit(str(meta.get("ratingKey", "")), int(self.pos_ms))


def QRectFromWidget(widget):  # noqa: N802 - small helper mirroring Qt naming
    top_left = widget.mapToGlobal(QPoint(0, 0))
    return widget.rect().translated(top_left)


def _rounded_thumb(pm):
    if pm.isNull():
        return pm
    out = QPixmap(104, 156)
    out.fill(Qt.GlobalColor.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, 104, 156), 8, 8)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    out.setDevicePixelRatio(2)
    return out


class SettingsPanel(QWidget):
    """Right-hand panel with Audio / Subtitles / Quality tabs."""

    def __init__(self, view, parent):
        super().__init__(parent)
        self.view = view
        self.setObjectName("Panel")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setFixedWidth(380)
        self.desired_height = 220
        self.tabs = QButtonGroup(self)
        tab_row = QHBoxLayout()
        tab_row.setContentsMargins(18, 10, 18, 0)
        for i, name in enumerate(("Audio", "Subtitles", "Quality")):
            b = QPushButton(name, objectName="PanelTab", checkable=True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            self.tabs.addButton(b, i)
            tab_row.addWidget(b)
        tab_row.addStretch()
        self.tabs.idClicked.connect(self._fill)
        self.list_holder = QWidget(objectName="Page")
        self.list_box = QVBoxLayout(self.list_holder)
        self.list_box.setContentsMargins(10, 8, 10, 12)
        self.list_box.setSpacing(2)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(self.list_holder)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.addLayout(tab_row)
        layout.addWidget(scroll)

    def place(self):
        parent = self.parentWidget()
        # Sit above the seek bar and transport row, sized to the list (scrolls if long).
        h = max(160, min(self.desired_height, parent.height() - 340))
        self.setGeometry(parent.width() - self.width() - 30, parent.height() - h - 256, self.width(), h)

    def open(self):
        self.place()
        if self.tabs.checkedId() < 0:
            self.tabs.button(0).setChecked(True)
        self._fill(self.tabs.checkedId())
        self.show()
        self.raise_()

    def _fill(self, tab):
        while self.list_box.count():
            w = self.list_box.takeAt(0).widget()
            if w:
                w.deleteLater()
        v = self.view
        group = QButtonGroup(self.list_holder)
        options = []
        if tab == 0:
            options = [(s.get("extendedDisplayTitle") or s.get("displayTitle") or f"Track {s['id']}",
                        s["id"] == v.audio_id, lambda s=s: v._choose_audio(s)) for s in streams(v.part, 2)]
        elif tab == 1:
            options = [("None", not v.sub_id, lambda: v._choose_subtitle(None))]
            options += [(s.get("extendedDisplayTitle") or s.get("displayTitle") or f"Subtitle {s['id']}",
                         s["id"] == v.sub_id, lambda s=s: v._choose_subtitle(s))
                        for s in streams(v.part, 3) if not (v.mode == "local" and s.get("key"))]
        else:
            if v.local_file:
                self.list_box.addWidget(label_widget("Playing a downloaded file at original quality."))
            else:
                options = [(text, qid == v.quality, lambda q=qid: v._choose_quality(q))
                           for qid, text, _, _ in QUALITIES]
        for text, checked, action in options:
            b = QPushButton(("✓   " if checked else "     ") + text, objectName="PanelItem", checkable=True)
            b.setChecked(checked)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            b.clicked.connect(lambda _=False, a=action, t=tab: (a(), self._fill(t)))
            group.addButton(b)
            self.list_box.addWidget(b)
        if not options and tab != 2:
            self.list_box.addWidget(label_widget("Nothing to choose here."))
        self.list_box.addStretch()
        self.desired_height = 76 + 44 * max(1, len(options))
        self.place()


def label_widget(text):
    lab = QLabel(text, objectName="OsdSub")
    lab.setWordWrap(True)
    lab.setContentsMargins(14, 10, 14, 10)
    return lab
