"""Main window: Plex-style top bar and foldable sidebar over a gradient background, page navigation,
the in-window player and the mini player that keeps playing while you browse."""
from PySide6.QtCore import (QEasingCurve, QParallelAnimationGroup, QPoint, QPropertyAnimation, QRectF,
                            QSize, Qt, QTimer)
from PySide6.QtGui import QColor, QKeySequence, QLinearGradient, QPainter, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from . import branding, icons, theme
from .chrome import DragBar, WindowButtons, make_frameless
from .api import QUALITIES
from .cards import label
from .config import APP_NAME
from .details import DetailsPage
from .login import LoginPage
from .pages import DownloadsPage, HomePage, LibraryPage, MessagePage, SearchPage
from .player import PlayerView, osd_button, skip_icon
from .workers import run_async

SIDEBAR_WIDE, SIDEBAR_NARROW = 248, 72


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Settings")
        self.setMinimumWidth(560)
        form = QFormLayout()
        form.setSpacing(14)
        self.quality = QComboBox()
        for qid, text, _, _ in QUALITIES:
            self.quality.addItem(text, qid)
        self.quality.setCurrentIndex(max(0, self.quality.findData(cfg.get("quality", "original"))))
        form.addRow("Default playback quality", self.quality)

        self.folder = QLineEdit(cfg.get("download_dir", ""))
        browse = QPushButton("Browse…", objectName="Secondary")
        browse.clicked.connect(self._browse)
        row = QHBoxLayout()
        row.addWidget(self.folder, 1)
        row.addWidget(browse)
        form.addRow("Download folder", row)

        self.font_file = QLineEdit(cfg.get("font_file", ""))
        self.font_file.setPlaceholderText("Default (DM Sans)")
        pick = QPushButton("Choose…", objectName="Secondary")
        pick.clicked.connect(self._pick_font)
        reset = QPushButton("Default", objectName="Secondary")
        reset.clicked.connect(self.font_file.clear)
        row = QHBoxLayout()
        row.addWidget(self.font_file, 1)
        row.addWidget(pick)
        row.addWidget(reset)
        form.addRow("Interface font", row)

        hint = label("A font file (.ttf or .otf) on this computer can replace the interface font; it "
                     "takes effect the next time Ember starts. Advanced: an mpv.conf in the 'mpv' "
                     "folder of the settings directory customises playback.", "Faint", wrap=True)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box = QVBoxLayout(self)
        box.setContentsMargins(24, 24, 24, 20)
        box.addLayout(form)
        box.addWidget(hint)
        box.addWidget(buttons)

    def _browse(self):
        path = QFileDialog.getExistingDirectory(self, "Download folder", self.folder.text())
        if path:
            self.folder.setText(path)

    def _pick_font(self):
        path, _ = QFileDialog.getOpenFileName(self, "Interface font", "", "Fonts (*.ttf *.otf)")
        if path:
            self.font_file.setText(path)

    def accept(self):
        self.cfg["quality"] = self.quality.currentData()
        self.cfg["download_dir"] = self.folder.text().strip() or self.cfg["download_dir"]
        changed_font = self.font_file.text().strip() != self.cfg.get("font_file", "")
        self.cfg["font_file"] = self.font_file.text().strip()
        self.cfg.save()
        if changed_font:
            QMessageBox.information(self, "Interface font", "The new font will be used after you restart Ember.")
        super().accept()


class Background(QWidget):
    """Window background: warm dark glows, or an item's artwork across the whole window.
    Rendered once per size/artwork, so scrolling never repaints gradients."""

    def __init__(self):
        super().__init__(objectName="Root")
        self.cache = None
        self.art = None

    def set_art(self, pixmap):
        if pixmap is not self.art:
            self.art = pixmap
            self.cache = None
            self.update()

    def resizeEvent(self, event):
        self.cache = None

    def paintEvent(self, event):
        if self.cache is None or self.cache.size() != self.size():
            self.cache = self._render()
        QPainter(self).drawPixmap(0, 0, self.cache)

    def _render(self):
        w, h = self.width(), self.height()
        pm = theme.render_background(w, h)
        if self.art is None:
            return pm
        p = QPainter(pm)
        scaled = self.art.scaled(w, h, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                 Qt.TransformationMode.SmoothTransformation)
        p.setOpacity(0.62)
        p.drawPixmap((w - scaled.width()) // 2, 0, scaled)
        p.setOpacity(1)
        # Darken towards the left (text side) and the bottom so everything stays readable.
        left = QLinearGradient(0, 0, w, 0)
        left.setColorAt(0.0, QColor(10, 9, 8, 235))
        left.setColorAt(0.45, QColor(10, 9, 8, 150))
        left.setColorAt(1.0, QColor(10, 9, 8, 40))
        p.fillRect(0, 0, w, h, left)
        down = QLinearGradient(0, 0, 0, h)
        down.setColorAt(0.0, QColor(10, 9, 8, 30))
        down.setColorAt(0.6, QColor(10, 9, 8, 120))
        down.setColorAt(1.0, QColor(10, 9, 8, 235))
        p.fillRect(0, 0, w, h, down)
        p.end()
        return pm


class MiniPlayer(QWidget):
    """Bottom bar shown while a video keeps playing behind the library (like Plex's mini player)."""

    def __init__(self, window):
        super().__init__()
        self.window_ = window
        self.view = None
        self.position = self.duration = 0.0
        self.setFixedHeight(80)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.setStyleSheet("MiniPlayer { background: rgba(14,15,18,0.94); border-top: 1px solid rgba(255,255,255,0.07); }")
        self.thumb = QLabel()
        self.thumb.setFixedSize(40, 60)
        self.title = QLabel(objectName="OsdTitle")
        self.title.setStyleSheet("font-size: 15px;")
        self.sub = QLabel(objectName="OsdSub")
        info = QVBoxLayout()
        info.setSpacing(1)
        info.addStretch()
        info.addWidget(self.title)
        info.addWidget(self.sub)
        info.addStretch()
        left = QWidget()
        left.setCursor(Qt.CursorShape.PointingHandCursor)
        left.mouseReleaseEvent = lambda e: self.window_.restore_player()
        lrow = QHBoxLayout(left)
        lrow.setContentsMargins(0, 0, 0, 0)
        lrow.setSpacing(12)
        lrow.addWidget(self.thumb)
        lrow.addLayout(info, 1)
        self.play_btn = osd_button("pause", "Play/pause", 34, lambda: self.view and self.view.toggle_pause())
        center = QHBoxLayout()
        center.setSpacing(14)
        center.addWidget(osd_button(skip_icon(10, False, 34), "Back 10 seconds", 30,
                                    lambda: self.view and self.view.seek_by(-10000)))
        center.addWidget(self.play_btn)
        center.addWidget(osd_button(skip_icon(30, True, 34), "Forward 30 seconds", 30,
                                    lambda: self.view and self.view.seek_by(30000)))
        right = QHBoxLayout()
        right.addStretch()
        right.addWidget(osd_button("fullscreen", "Back to the player", 24, self.window_.restore_player))
        right.addWidget(osd_button("close", "Stop", 24, lambda: self.view and self.view.stop()))
        row = QHBoxLayout(self)
        row.setContentsMargins(20, 8, 18, 6)
        row.addWidget(left, 1)
        row.addLayout(center)
        row.addLayout(right, 1)

    def attach(self, view):
        self.view = view
        self.title.setText(view.title.text())
        self.sub.setText(view.subtitle.text())
        pm = view.thumb.pixmap()
        self.thumb.setPixmap(pm.scaled(80, 120, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                       Qt.TransformationMode.SmoothTransformation) if pm and not pm.isNull() else pm)
        if self.thumb.pixmap() and not self.thumb.pixmap().isNull():
            self.thumb.pixmap().setDevicePixelRatio(2)
        self.show()

    def update_state(self, position, duration, paused):
        self.position, self.duration = position, duration
        self.play_btn.setIcon(icons.icon("play" if paused else "pause", "#ffffff"))
        if self.view is not None:
            self.title.setText(self.view.title.text())
            self.sub.setText(self.view.subtitle.text())
        self.update()

    def paintEvent(self, event):
        super().paintEvent(event)
        if self.duration:
            p = QPainter(self)
            p.fillRect(QRectF(0, 0, self.width(), 3), QColor(255, 255, 255, 40))
            p.fillRect(QRectF(0, 0, self.width() * min(1.0, self.position / self.duration), 3),
                       theme.color("accent"))


class MainWindow(QMainWindow):
    def __init__(self, client, downloads):
        super().__init__()
        self.client, self.downloads = client, downloads
        self.player = None
        self.history = []
        self.offline = False
        self.setWindowTitle(APP_NAME)
        make_frameless(self)  # Windows: our own title bar, same colour as the app
        self.resize(1440, 900)
        self.setMinimumSize(960, 600)
        self.downloads.message.connect(self.toast)
        self._toast = QLabel(self, objectName="Toast")
        self._toast.hide()
        self._toast_timer = QTimer(self, singleShot=True, interval=3200, timeout=self._toast.hide)
        if client.cfg.signed_in and client.cfg.has_server:
            self._build_main()
        else:
            self._show_login(choose_server_only=client.cfg.signed_in)

    # --- shell ----------------------------------------------------------------------

    def _show_login(self, choose_server_only=False):
        if self.player is not None:
            self.player.stop()
        login = LoginPage(self.client, choose_server_only)
        login.done.connect(self._build_main)
        self.setCentralWidget(login)

    def _build_main(self):
        root = self.root_bg = Background()
        self.sidebar = QWidget(objectName="Sidebar")
        self.sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.side_box = QVBoxLayout(self.sidebar)
        self.side_box.setContentsMargins(0, 10, 0, 12)
        self.side_box.setSpacing(0)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)
        self.nav_texts = {}
        collapsed = bool(self.client.cfg.get("sidebar_collapsed"))
        self.sidebar.setFixedWidth(SIDEBAR_NARROW if collapsed else SIDEBAR_WIDE)
        self.sidebar.setProperty("collapsed", collapsed)

        self.stack = QStackedWidget()
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self.sidebar)
        body.addWidget(self.stack, 1)
        self.mini = MiniPlayer(self)
        self.mini.hide()
        layout = QVBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._top_bar())
        layout.addLayout(body, 1)
        layout.addWidget(self.mini)
        # The shell swaps between the library UI and the full-size player, inside this same window.
        self.shell = QStackedWidget()
        self.shell.addWidget(root)
        self.setCentralWidget(self.shell)
        QShortcut(QKeySequence("Ctrl+F"), self, lambda: self.search.setFocus())
        QShortcut(QKeySequence(Qt.Key.Key_Backspace), self, self._backspace)
        QShortcut(QKeySequence("Alt+Left"), self, self.back)
        self._fill_sidebar([])
        self.navigate(MessagePage("Connecting…"), root=True)
        run_async(self.client.reconnect, self._connected, lambda e: self._connected(False))

    def _connected(self, ok):
        self.offline = not ok
        self.offline_badge.setVisible(self.offline)
        if not ok:
            self._fill_sidebar([])
            self.toast("Can't reach your server — showing your downloads")
            self.show_downloads()
            return
        self.server_label.setText(self.client.cfg.get("server_name", ""))
        run_async(self.client.sections, self._fill_sidebar, lambda e: self.toast(f"Couldn't load libraries: {e}"))
        self.show_home()
        self.downloads._start_next()

    # --- sidebar --------------------------------------------------------------------

    def _nav_button(self, text, icon_name, slot):
        b = QPushButton()
        b.setIcon(icons.icon(icon_name, "#c6c9cd", active_color="#ffffff"))
        b.setIconSize(QSize(22, 22))
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setToolTip(text)
        b.clicked.connect(slot)
        self.nav.addButton(b)
        self.nav_texts[b] = text
        b.setText("" if self.sidebar.property("collapsed") else "   " + text)
        return b

    def _fill_sidebar(self, sections):
        while self.side_box.count():
            w = self.side_box.takeAt(0).widget()
            if w:
                if isinstance(w, QPushButton):
                    self.nav.removeButton(w)
                    self.nav_texts.pop(w, None)
                w.deleteLater()
        self.home_btn = self._nav_button("Home", "home", self.show_home)
        self.home_btn.setEnabled(not self.offline)
        self.side_box.addWidget(self.home_btn)
        self.section_buttons = {}
        self.heading = label("LIBRARIES", "SidebarHeading")
        if sections:
            self.side_box.addWidget(self.heading)
            for s in sections:
                b = self._nav_button(s["title"], icons.section_icon(s.get("type")),
                                     lambda _=False, s=s: self.show_section(s))
                self.section_buttons[s["key"]] = b
                self.side_box.addWidget(b)
        self.heading.setVisible(bool(sections) and not self.sidebar.property("collapsed"))
        self.side_box.addStretch()
        self.dl_btn = self._nav_button("Downloads", "download", self.show_downloads)
        self.side_box.addWidget(self.dl_btn)
        self._sync_sidebar()

    def toggle_sidebar(self):
        collapsed = not self.sidebar.property("collapsed")
        self.client.cfg["sidebar_collapsed"] = collapsed
        self.client.cfg.save()
        start, end = self.sidebar.width(), SIDEBAR_NARROW if collapsed else SIDEBAR_WIDE
        self.sidebar.setMinimumWidth(0)
        self.sidebar.setMaximumWidth(16777215)
        group = QParallelAnimationGroup(self)
        for prop in (b"minimumWidth", b"maximumWidth"):
            anim = QPropertyAnimation(self.sidebar, prop)
            anim.setDuration(220)
            anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            anim.setStartValue(start)
            anim.setEndValue(end)
            group.addAnimation(anim)
        if collapsed:  # hide labels first so they don't squash while shrinking
            self._apply_collapsed(True)
        else:
            group.finished.connect(lambda: self._apply_collapsed(False))
        group.start(QParallelAnimationGroup.DeletionPolicy.DeleteWhenStopped)

    def _apply_collapsed(self, collapsed):
        self.sidebar.setProperty("collapsed", collapsed)
        for b, text in self.nav_texts.items():
            b.setText("" if collapsed else "   " + text)
        self.heading.setVisible(bool(self.section_buttons) and not collapsed)
        self.sidebar.style().unpolish(self.sidebar)
        self.sidebar.style().polish(self.sidebar)
        for b in self.nav_texts:
            b.style().unpolish(b)
            b.style().polish(b)

    def _sync_sidebar(self):
        """Highlight the sidebar entry for the root page currently shown."""
        root = self.history[0] if getattr(self, "history", None) else None
        if isinstance(root, HomePage):
            self.home_btn.setChecked(True)
        elif isinstance(root, DownloadsPage):
            self.dl_btn.setChecked(True)
        elif isinstance(root, LibraryPage) and root.section["key"] in self.section_buttons:
            self.section_buttons[root.section["key"]].setChecked(True)

    # --- top bar --------------------------------------------------------------------

    def _icon_button(self, name, tip, slot, size=22):
        b = QPushButton(objectName="IconButton")
        b.setIcon(icons.icon(name, "#d0d3d6", active_color="#ffffff"))
        b.setIconSize(QSize(size, size))
        b.setToolTip(tip)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        return b

    def _top_bar(self):
        bar = DragBar(objectName="TopBar")  # doubles as the window's title bar
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        bar.setFixedHeight(64)
        row = QHBoxLayout(bar)
        row.setContentsMargins(14, 0, 0, 0)
        row.setSpacing(10)
        row.addWidget(self._icon_button("menu", "Show or hide the sidebar", self.toggle_sidebar, 24))
        logo = QLabel()
        logo.setPixmap(branding.wordmark_pixmap(28, theme.FONT if theme.FONT else "DM Sans"))
        logo.setCursor(Qt.CursorShape.PointingHandCursor)
        logo.mouseReleaseEvent = lambda e: (not self.offline) and self.show_home()
        row.addWidget(logo)
        row.addSpacing(28)
        self.back_btn = self._icon_button("back", "Back (Alt+←)", self.back)
        row.addWidget(self.back_btn)
        self.search = QLineEdit(objectName="Search")
        self.search.setPlaceholderText("Search")
        self.search.setFixedWidth(420)
        self.search.addAction(icons.icon("search", "#a6a6a6"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self._search)
        row.addWidget(self.search)
        row.addStretch()
        self.offline_badge = QLabel("OFFLINE — DOWNLOADS ONLY", objectName="OfflineBadge")
        self.offline_badge.hide()
        row.addWidget(self.offline_badge)
        self.server_label = label("", "Muted")
        row.addWidget(self.server_label)
        account = self._icon_button("person", "Account and settings", lambda: self._account_menu(account), 26)
        row.addWidget(account)
        row.addSpacing(10)
        buttons = WindowButtons(self)
        row.addWidget(buttons, 0, Qt.AlignmentFlag.AlignTop)
        if not buttons.isVisible():
            row.addSpacing(10)
        return bar

    def _account_menu(self, button):
        menu = QMenu(self)
        menu.addSection(self.client.cfg.get("server_name", "Not connected").upper())
        menu.addAction("Settings…", lambda: SettingsDialog(self.client.cfg, self).exec())
        menu.addAction("Switch server…", lambda: self._show_login(choose_server_only=True))
        menu.addAction("Reconnect", self._build_main)
        menu.addSeparator()
        menu.addAction("Sign out", self._sign_out)
        menu.exec(button.mapToGlobal(QPoint(button.width() - menu.sizeHint().width(), button.height() + 4)))

    def _sign_out(self):
        if QMessageBox.question(self, "Sign out", "Sign out of your Plex account? "
                                "Downloads stay on this computer.") == QMessageBox.StandardButton.Yes:
            self.client.cfg.sign_out()
            self._show_login()

    # --- navigation ---------------------------------------------------------------

    def navigate(self, page, root=False):
        if root:
            self.search.clear()
            while self.history:
                old = self.history.pop()
                self.stack.removeWidget(old)
                old.deleteLater()
        self.history.append(page)
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)
        self.back_btn.setEnabled(len(self.history) > 1)
        self.update_backdrop()
        if self.player is not None and self.shell.currentWidget() is self.player:
            self.minimize_player()  # opening something from the player keeps it playing

    def back(self):
        if len(self.history) <= 1:
            return
        old = self.history.pop()
        self.stack.removeWidget(old)
        old.deleteLater()
        self.stack.setCurrentWidget(self.history[-1])
        self.back_btn.setEnabled(len(self.history) > 1)
        self.update_backdrop()
        current = self.history[-1]
        if isinstance(current, DetailsPage):
            current.refresh()  # pick up watched/progress changes (no rebuild if unchanged)

    def update_backdrop(self):
        """Show the current page's artwork behind the whole window (details pages), else the glows."""
        page = self.history[-1] if self.history else None
        self.root_bg.set_art(getattr(page, "backdrop_pixmap", None))

    def _backspace(self):
        if not self.search.hasFocus():
            self.back()

    def show_home(self):
        self.home_btn.setChecked(True)
        self.navigate(HomePage(self), root=True)

    def show_section(self, section):
        btn = self.section_buttons.get(section["key"])
        if btn:
            btn.setChecked(True)
        self.navigate(LibraryPage(self, section), root=True)

    def show_downloads(self):
        self.dl_btn.setChecked(True)
        self.navigate(DownloadsPage(self), root=True)

    def _search(self):
        q = self.search.text().strip()
        if q and not self.offline:
            checked = self.nav.checkedButton()
            if checked:
                self.nav.setExclusive(False)
                checked.setChecked(False)
                self.nav.setExclusive(True)
            self.navigate(SearchPage(self, q))

    def open_item(self, meta):
        if self.offline:
            return
        if meta.get("type") == "track":
            self.play(meta)
        elif meta.get("type") == "photo":
            self.toast("Photos aren't supported yet")
        else:
            self.open_key(meta.get("ratingKey"), meta.get("title", ""))

    def open_key(self, rating_key, title=""):
        if rating_key:
            self.navigate(DetailsPage(self, rating_key, title))

    # --- playback -----------------------------------------------------------------

    def play(self, meta, from_start=False, media_index=0, local_only=False):
        local = self.downloads.local_file(meta.get("ratingKey"))
        if local_only and not local:
            self.toast("That download isn't available")
            return
        start = 0 if from_start else int(meta.get("viewOffset") or 0)

        def launch(full):
            if self.player is not None:
                self.player.stop()
            self.was_maximized = self.isMaximized()
            self.player = PlayerView(self, full, media_index, start, local)
            self.player.closed.connect(self._player_closed)
            self.player.minimize_requested.connect(self.minimize_player)
            self.player.progress.connect(self.mini.update_state)
            self.mini.hide()
            self.shell.addWidget(self.player)
            self.shell.setCurrentWidget(self.player)
            self.player.setFocus()
            QTimer.singleShot(0, self.player.start)

        has_parts = bool((meta.get("Media") or [{}])[0].get("Part", [{}])[0].get("Stream"))
        if local or has_parts or self.offline:
            launch(meta)
        else:  # list views omit stream details; fetch them for track selection
            run_async(lambda: self.client.metadata(meta["ratingKey"]), launch,
                      lambda e: self.toast(f"Couldn't start playback: {e}"))

    def minimize_player(self):
        """Keep the video playing and show the library with a mini player at the bottom."""
        if self.player is None:
            return
        self.set_fullscreen(False)
        self.shell.setCurrentIndex(0)
        self.mini.attach(self.player)

    def restore_player(self):
        if self.player is not None:
            self.mini.hide()
            self.shell.setCurrentWidget(self.player)
            self.player.setFocus()
            self.player.show_controls()

    def set_fullscreen(self, on):
        if on and not self.isFullScreen():
            self.showFullScreen()
        elif not on and self.isFullScreen():
            self.showMaximized() if getattr(self, "was_maximized", False) else self.showNormal()

    def _player_closed(self, rating_key, position):
        view, self.player = self.player, None
        self.mini.hide()
        self.mini.view = None
        self.set_fullscreen(False)
        self.shell.setCurrentIndex(0)
        if view is not None:
            self.shell.removeWidget(view)
            view.deleteLater()
        current = self.history[-1] if self.history else None
        if current is not None and hasattr(current, "refresh"):
            QTimer.singleShot(600, lambda: self._safe_refresh(current))

    @staticmethod
    def _safe_refresh(page):
        try:
            page.refresh()
        except RuntimeError:
            pass

    # --- toasts -------------------------------------------------------------------

    def toast(self, text):
        self._toast.setText(text)
        self._toast.adjustSize()
        bottom = 30 + (self.mini.height() if getattr(self, "mini", None) and self.mini.isVisible() else 0)
        self._toast.move((self.width() - self._toast.width()) // 2, self.height() - self._toast.height() - bottom)
        self._toast.raise_()
        self._toast.show()
        self._toast_timer.start()

    def closeEvent(self, event):
        if self.player is not None:
            self.player.stop()
        self.downloads.shutdown()
        super().closeEvent(event)

