"""Video player window: libmpv embedded in Qt with a media-center control bar.

Modes:
  direct     original file streamed from the server (all codecs, 4K HDR handled by mpv)
  transcode  server converts to HLS at the chosen quality
  local      a downloaded file played from disk (works offline)
"""
import os
import sys
import time
import uuid

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QActionGroup, QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (QHBoxLayout, QLabel, QMenu, QPushButton, QSlider, QStyle,
                               QVBoxLayout, QWidget)

from . import icons
from .api import QUALITIES, fmt_clock, streams
from .config import data_dir
from .images import ImageLoader
from .workers import run_async

REPORT_INTERVAL = 10
WATCHED_FRACTION = 0.9
HIDE_AFTER = 3.0


def load_mpv():
    """Import python-mpv, making a bundled libmpv-2.dll findable in the packaged exe."""
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
        os.environ["PATH"] = base + os.pathsep + os.environ.get("PATH", "")
        if hasattr(os, "add_dll_directory"):
            os.add_dll_directory(base)
    import mpv  # noqa: PLC0415 - deferred so the library UI works without libmpv
    return mpv


class ClickSlider(QSlider):
    """Seek bar that jumps to where you click and reports the final value on release."""
    seek_requested = Signal(int)

    def __init__(self):
        super().__init__(Qt.Orientation.Horizontal)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.dragging = False

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.dragging = True
            self.setValue(QStyle.sliderValueFromPosition(
                self.minimum(), self.maximum(), int(event.position().x()), self.width()))
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.dragging:
            self.dragging = False
            self.seek_requested.emit(self.value())


def _button(icon_name, tip, size=26, slot=None, checkable=False):
    b = QPushButton()
    b.setObjectName("IconButton")
    b.setIcon(icons.icon(icon_name, "#dddddd", active_color="#ffffff"))
    b.setIconSize(QSize(size, size))
    b.setToolTip(tip)
    b.setCursor(Qt.CursorShape.PointingHandCursor)
    b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    b.setCheckable(checkable)
    if slot:
        b.clicked.connect(slot)
    return b


class PlayerWindow(QWidget):
    closed = Signal(str, int)  # ratingKey, last position (ms)

    def __init__(self, client, downloads, meta, media_index=0, start_ms=0, local_file=None):
        super().__init__(None, Qt.WindowType.Window)
        self.client, self.downloads = client, downloads
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setStyleSheet("PlayerWindow { background: black; }")
        self.resize(1280, 760)
        self.player = None
        self.closing = False
        self._build_ui()
        self._shortcuts()

        self.timer = QTimer(self, interval=250, timeout=self._tick)
        self.last_cursor = QCursor.pos()
        self.last_move = time.monotonic()
        try:
            self.player = self._create_mpv()
        except Exception as e:  # noqa: BLE001 - missing libmpv etc.
            self.status.setText(f"Video player unavailable: {e}")
            return
        self.load(meta, media_index, start_ms, local_file)
        self.timer.start()

    # --- setup --------------------------------------------------------------------

    def _build_ui(self):
        self.video = QWidget(self)
        self.video.setAttribute(Qt.WidgetAttribute.WA_NativeWindow)
        self.video.setAttribute(Qt.WidgetAttribute.WA_DontCreateNativeAncestors)
        self.video.setStyleSheet("background: black;")
        self.video.setMouseTracking(True)
        self.video.mouseDoubleClickEvent = lambda e: self.toggle_fullscreen()
        self.video.mousePressEvent = lambda e: self.toggle_pause() \
            if e.button() == Qt.MouseButton.LeftButton else None

        self.bar = QWidget(self)
        self.bar.setObjectName("PlayerBar")
        self.bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)

        self.seek = ClickSlider()
        self.seek.seek_requested.connect(lambda s: self.seek_to(s * 1000))
        self.elapsed = QLabel("0:00", objectName="Clock")
        self.remaining = QLabel("", objectName="Clock")
        seek_row = QHBoxLayout()
        seek_row.addWidget(self.elapsed)
        seek_row.addWidget(self.seek, 1)
        seek_row.addWidget(self.remaining)

        self.thumb = QLabel()
        self.thumb.setFixedSize(40, 60)
        self.title = QLabel(objectName="PlayerTitle")
        self.subtitle = QLabel(objectName="PlayerSub")
        self.status = QLabel(objectName="PlayerSub")
        self.status.setStyleSheet("color: #e5a00d;")
        info = QVBoxLayout()
        info.setSpacing(2)
        info.addStretch()
        info.addWidget(self.title)
        info.addWidget(self.subtitle)
        info.addWidget(self.status)
        info.addStretch()
        left = QHBoxLayout()
        left.setSpacing(12)
        left.addWidget(self.thumb)
        left.addLayout(info, 1)

        self.play_btn = _button("pause", "Pause (Space)", 40, self.toggle_pause)
        self.next_btn = _button("next", "Next episode", 26, self.play_next)
        center = QHBoxLayout()
        center.setSpacing(18)
        center.addWidget(_button("rewind", "Back 10 seconds (←)", 28, lambda: self.seek_by(-10000)))
        center.addWidget(self.play_btn)
        center.addWidget(_button("forward", "Forward 30 seconds (→)", 28, lambda: self.seek_by(30000)))
        center.addWidget(self.next_btn)

        self.tracks_btn = _button("subtitles", "Audio & subtitles", 24, self._show_tracks_menu)
        self.quality_btn = _button("tune", "Playback quality", 24, self._show_quality_menu)
        self.fs_btn = _button("fullscreen", "Fullscreen (F)", 26, self.toggle_fullscreen)
        right = QHBoxLayout()
        right.setSpacing(6)
        right.addStretch()
        right.addWidget(self.tracks_btn)
        right.addWidget(self.quality_btn)
        right.addWidget(self.fs_btn)
        right.addWidget(_button("close", "Close (Esc)", 26, self.close))

        controls = QHBoxLayout()
        controls.addLayout(left, 1)
        controls.addLayout(center)
        controls.addLayout(right, 1)

        bar_layout = QVBoxLayout(self.bar)
        bar_layout.setContentsMargins(24, 10, 24, 14)
        bar_layout.setSpacing(6)
        bar_layout.addLayout(seek_row)
        bar_layout.addLayout(controls)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.video, 1)
        layout.addWidget(self.bar)

    def _shortcuts(self):
        for keys, slot in ((Qt.Key.Key_Space, self.toggle_pause), (Qt.Key.Key_K, self.toggle_pause),
                           (Qt.Key.Key_F, self.toggle_fullscreen), (Qt.Key.Key_F11, self.toggle_fullscreen),
                           (Qt.Key.Key_Escape, self._escape),
                           (Qt.Key.Key_Left, lambda: self.seek_by(-10000)),
                           (Qt.Key.Key_Right, lambda: self.seek_by(30000)),
                           (Qt.Key.Key_Up, lambda: self._volume(5)),
                           (Qt.Key.Key_Down, lambda: self._volume(-5))):
            QShortcut(QKeySequence(keys), self, slot)

    def _create_mpv(self):
        mpv = load_mpv()
        conf_dir = os.path.join(data_dir(), "mpv")  # put your own mpv.conf / scripts here
        os.makedirs(conf_dir, exist_ok=True)
        base = dict(
            wid=str(int(self.video.winId())),
            vo=os.environ.get("MARQUEE_VO", "gpu-next"),
            hwdec="auto-safe",
            keep_open="yes",
            osc=False, input_default_bindings=False, input_vo_keyboard=False, input_cursor=False,
            cursor_autohide="no", ytdl=False, sub_auto="no",
            config=True, config_dir=conf_dir,
            demuxer_max_bytes="400MiB", demuxer_max_back_bytes="150MiB",
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

    # --- loading ------------------------------------------------------------------

    def load(self, meta, media_index=0, start_ms=0, local_file=None):
        self.meta = meta
        self.media_index = media_index
        media = (meta.get("Media") or [{}])
        self.part = (media[min(media_index, len(media) - 1)].get("Part") or [{}])[0]
        self.local_file = local_file
        self.duration_ms = meta.get("duration") or self.part.get("duration") or 0
        self.pos_ms = start_ms
        self.quality = "original" if local_file else self.client.cfg.get("quality", "original")
        selected = lambda t: next((s for s in streams(self.part, t) if s.get("selected")), None)
        audio, sub = selected(2), selected(3)
        self.audio_id = audio["id"] if audio else None
        self.sub_id = sub["id"] if sub else 0
        self.session = None
        self.reported_state, self.last_report = None, 0.0
        self.scrobbled = False

        kind = meta.get("type")
        if kind == "episode":
            self.title.setText(meta.get("grandparentTitle", ""))
            self.subtitle.setText(f"S{meta.get('parentIndex', 0)} · E{meta.get('index', 0)} — {meta.get('title', '')}")
        else:
            self.title.setText(meta.get("title", ""))
            self.subtitle.setText(str(meta.get("year", "")) if kind == "movie" else meta.get("grandparentTitle", ""))
        self.setWindowTitle(self.title.text() + (f" — {meta.get('title')}" if kind == "episode" else ""))
        self.next_btn.setVisible(kind == "episode" and not local_file)
        self.quality_btn.setEnabled(not local_file)
        self.thumb.clear()
        thumb = meta.get("_poster") or (meta.get("grandparentThumb") if kind == "episode" else meta.get("thumb"))
        if ImageLoader.instance() and thumb:
            ImageLoader.instance().load(thumb, 80, 120, lambda pm: self.thumb.setPixmap(
                pm.scaled(40, 60, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                          Qt.TransformationMode.SmoothTransformation)))
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
                    self.status.setText(f"Server can't convert this: {text}")
                    return
                self._play(url, 0)
            # Ask the server to plan the conversion first; if that call isn't supported, just start.
            run_async(lambda: self.client.transcode_decision(*args), decided, lambda e: self._play(url, 0))

    def _play(self, url, pos_ms):
        if self.closing:
            return
        self.player["start"] = f"{pos_ms / 1000:.3f}" if pos_ms else "none"
        self.player.play(url)
        self.player.pause = False

    def _apply_tracks(self):
        """Select the remembered audio/subtitle tracks once mpv has opened the file."""
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

    # --- polling loop -------------------------------------------------------------

    def _tick(self):
        if self.closing or self.player is None:
            return
        try:
            tp = self.player.time_pos
            paused = bool(self.player.pause)
            eof = bool(self.player.eof_reached)
            idle = bool(self.player.idle_active)
            if not self.loaded and self.player.track_list:
                self.loaded = True
                if not self.duration_ms and self.player.duration:
                    self.duration_ms = self.player.duration * 1000
                self._apply_tracks()
        except Exception:  # noqa: BLE001 - mpv shut down underneath us
            return
        if tp is not None:
            if self.mode == "transcode":
                if self.relative is None:  # does the HLS stream start at 0 or at the offset?
                    self.relative = not (self.offset_ms > 15000 and abs(tp * 1000 - self.offset_ms) < 15000)
                self.pos_ms = self.offset_ms + tp * 1000 if self.relative else tp * 1000
            else:
                self.pos_ms = tp * 1000
        elif idle and not self.loaded and time.monotonic() - self.started_at > 20 and not self.status.text():
            self.status.setText("Couldn't play this item. Try a lower quality, or check the server.")

        if self.duration_ms:
            self.seek.setMaximum(int(self.duration_ms // 1000))
            if not self.seek.dragging:
                self.seek.setValue(int(self.pos_ms // 1000))
            self.remaining.setText("-" + fmt_clock(max(0, self.duration_ms - self.pos_ms)))
        self.elapsed.setText(fmt_clock(self.seek.value() * 1000 if self.seek.dragging else self.pos_ms))
        self.play_btn.setIcon(icons.icon("play" if paused else "pause", "#ffffff"))

        state = "paused" if paused else "playing"
        if self.loaded and (state != self.reported_state or time.monotonic() - self.last_report > REPORT_INTERVAL):
            self._report(state)
        if self.loaded and eof:
            self._finished()
            return
        self._autohide(paused)

    def _autohide(self, paused):
        pos = QCursor.pos()
        if pos != self.last_cursor:
            self.last_cursor, self.last_move = pos, time.monotonic()
            if not self.bar.isVisible():
                self.bar.show()
                self.video.unsetCursor()
        elif (self.isFullScreen() and not paused and self.bar.isVisible()
              and time.monotonic() - self.last_move > HIDE_AFTER):
            self.bar.hide()
            self.video.setCursor(Qt.CursorShape.BlankCursor)

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
            self.close()

    # --- controls -----------------------------------------------------------------

    def toggle_pause(self):
        if self.player:
            self.player.pause = not self.player.pause
            self.last_move = time.monotonic()

    def seek_by(self, delta_ms):
        self.seek_to(self.pos_ms + delta_ms)

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

    def _volume(self, delta):
        if self.player:
            self.player.volume = max(0, min(130, (self.player.volume or 100) + delta))
            self.status.setText(f"Volume {int(self.player.volume)}%")
            QTimer.singleShot(1500, lambda: self.status.text().startswith("Volume") and self.status.setText(""))

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
            self.bar.show()
            self.video.unsetCursor()
        else:
            self.showFullScreen()
        self.fs_btn.setIcon(icons.icon("fullscreen_exit" if self.isFullScreen() else "fullscreen", "#dddddd"))

    def _escape(self):
        if self.isFullScreen():
            self.toggle_fullscreen()
        else:
            self.close()

    def play_next(self):
        meta = self.meta
        if meta.get("type") != "episode" or not meta.get("parentRatingKey"):
            self.close()
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
                self.close()
            else:
                self.status.setText("")
                self.load(next_meta, 0, 0)
        self.status.setText("Loading next episode…")
        run_async(find_next, go, lambda e: self.close())

    # --- menus --------------------------------------------------------------------

    def _show_tracks_menu(self):
        menu = QMenu(self)
        menu.addSection("AUDIO")
        group = QActionGroup(menu)
        for s in streams(self.part, 2):
            a = QAction(s.get("extendedDisplayTitle") or s.get("displayTitle") or f"Track {s['id']}",
                        menu, checkable=True, checked=s["id"] == self.audio_id)
            a.triggered.connect(lambda _=False, s=s: self._choose_audio(s))
            group.addAction(a)
            menu.addAction(a)
        if not streams(self.part, 2):
            menu.addAction("(no audio tracks listed)").setEnabled(False)
        menu.addSection("SUBTITLES")
        group = QActionGroup(menu)
        off = QAction("None", menu, checkable=True, checked=not self.sub_id)
        off.triggered.connect(lambda: self._choose_subtitle(None))
        group.addAction(off)
        menu.addAction(off)
        for s in streams(self.part, 3):
            if self.mode == "local" and s.get("key"):
                continue  # sidecar subtitle files aren't downloaded
            a = QAction(s.get("extendedDisplayTitle") or s.get("displayTitle") or f"Subtitle {s['id']}",
                        menu, checkable=True, checked=s["id"] == self.sub_id)
            a.triggered.connect(lambda _=False, s=s: self._choose_subtitle(s))
            group.addAction(a)
            menu.addAction(a)
        menu.exec(self._menu_pos(menu, self.tracks_btn))

    def _show_quality_menu(self):
        menu = QMenu(self)
        menu.addSection("QUALITY")
        group = QActionGroup(menu)
        for qid, label, _, _ in QUALITIES:
            a = QAction(label, menu, checkable=True, checked=qid == self.quality)
            a.triggered.connect(lambda _=False, q=qid: self._choose_quality(q))
            group.addAction(a)
            menu.addAction(a)
        menu.exec(self._menu_pos(menu, self.quality_btn))

    @staticmethod
    def _menu_pos(menu, button):
        top_left = button.mapToGlobal(button.rect().topLeft())
        top_left.setY(top_left.y() - menu.sizeHint().height() - 6)
        top_left.setX(top_left.x() - menu.sizeHint().width() + button.width())
        return top_left

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
        if quality != self.quality:
            self.quality = quality
            self._start_stream(self.pos_ms)

    # --- teardown -----------------------------------------------------------------

    def _stop_transcode(self):
        if self.session:
            session, self.session = self.session, None
            run_async(lambda: self.client.stop_transcode(session), None, lambda e: None)

    def closeEvent(self, event):
        if not self.closing:
            self.closing = True
            self.timer.stop()
            if self.player is not None:
                if getattr(self, "loaded", False):
                    self._report("stopped")
                self._stop_transcode()
                try:
                    self.player.terminate()
                except Exception:  # noqa: BLE001
                    pass
                self.player = None
            self.closed.emit(str(getattr(self, "meta", {}).get("ratingKey", "")), int(getattr(self, "pos_ms", 0)))
        super().closeEvent(event)
