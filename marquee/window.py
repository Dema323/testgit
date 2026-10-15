"""Main window: sidebar, top bar with search, page navigation, playback and toasts."""
from PySide6.QtCore import QPoint, QSize, Qt, QTimer
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QDialog, QDialogButtonBox, QFileDialog,
                               QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMainWindow, QMenu,
                               QMessageBox, QPushButton, QStackedWidget, QVBoxLayout, QWidget)

from . import icons
from .api import QUALITIES
from .cards import label
from .config import APP_NAME
from .details import DetailsPage
from .login import LoginPage
from .pages import DownloadsPage, HomePage, LibraryPage, MessagePage, SearchPage
from .player import PlayerWindow
from .workers import run_async


class SettingsDialog(QDialog):
    def __init__(self, cfg, parent):
        super().__init__(parent)
        self.cfg = cfg
        self.setWindowTitle("Settings")
        self.setMinimumWidth(480)
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
        hint = label("Advanced: put an mpv.conf in the 'mpv' folder of the app's settings directory "
                     "to customise playback.", "Faint", wrap=True)
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

    def accept(self):
        self.cfg["quality"] = self.quality.currentData()
        self.cfg["download_dir"] = self.folder.text().strip() or self.cfg["download_dir"]
        self.cfg.save()
        super().accept()


class MainWindow(QMainWindow):
    def __init__(self, client, downloads):
        super().__init__()
        self.client, self.downloads = client, downloads
        self.player = None
        self.history = []
        self.offline = False
        self.setWindowTitle(APP_NAME)
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
        login = LoginPage(self.client, choose_server_only)
        login.done.connect(self._build_main)
        self.setCentralWidget(login)

    def _build_main(self):
        root = QWidget(objectName="Root")
        root.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.sidebar = QWidget(objectName="Sidebar")
        self.sidebar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        self.sidebar.setFixedWidth(232)
        self.side_box = QVBoxLayout(self.sidebar)
        self.side_box.setContentsMargins(0, 0, 0, 12)
        self.side_box.setSpacing(0)
        self.nav = QButtonGroup(self)
        self.nav.setExclusive(True)

        self.stack = QStackedWidget()
        content = QVBoxLayout()
        content.setContentsMargins(0, 0, 0, 0)
        content.setSpacing(0)
        content.addWidget(self._top_bar())
        content.addWidget(self.stack, 1)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self.sidebar)
        layout.addLayout(content, 1)
        self.setCentralWidget(root)
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

    def _nav_button(self, text, icon_name, slot):
        b = QPushButton("  " + text)
        b.setIcon(icons.icon(icon_name, "#a0a4a8", active_color="#ffffff"))
        b.setIconSize(QSize(20, 20))
        b.setCheckable(True)
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.clicked.connect(slot)
        self.nav.addButton(b)
        return b

    def _fill_sidebar(self, sections):
        while self.side_box.count():
            w = self.side_box.takeAt(0).widget()
            if w:
                if isinstance(w, QPushButton):
                    self.nav.removeButton(w)
                w.deleteLater()
        self.side_box.addWidget(label(APP_NAME, "Brand"))
        self.home_btn = self._nav_button("Home", "home", self.show_home)
        self.home_btn.setEnabled(not self.offline)
        self.side_box.addWidget(self.home_btn)
        self.section_buttons = {}
        if sections:
            self.side_box.addWidget(label("LIBRARIES", "SidebarHeading"))
            for s in sections:
                b = self._nav_button(s["title"], icons.section_icon(s.get("type")),
                                     lambda _=False, s=s: self.show_section(s))
                self.section_buttons[s["key"]] = b
                self.side_box.addWidget(b)
        self.side_box.addStretch()
        self.dl_btn = self._nav_button("Downloads", "download", self.show_downloads)
        self.side_box.addWidget(self.dl_btn)
        self._sync_sidebar()

    def _sync_sidebar(self):
        """Highlight the sidebar entry for the root page currently shown."""
        root = self.history[0] if getattr(self, "history", None) else None
        if isinstance(root, HomePage):
            self.home_btn.setChecked(True)
        elif isinstance(root, DownloadsPage):
            self.dl_btn.setChecked(True)
        elif isinstance(root, LibraryPage) and root.section["key"] in self.section_buttons:
            self.section_buttons[root.section["key"]].setChecked(True)

    def _top_bar(self):
        bar = QWidget(objectName="TopBar")
        bar.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        bar.setFixedHeight(60)
        row = QHBoxLayout(bar)
        row.setContentsMargins(16, 0, 20, 0)
        row.setSpacing(12)
        self.back_btn = QPushButton(objectName="IconButton")
        self.back_btn.setIcon(icons.icon("back", "#cccccc", active_color="#ffffff"))
        self.back_btn.setIconSize(QSize(22, 22))
        self.back_btn.setToolTip("Back (Alt+←)")
        self.back_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.back_btn.clicked.connect(self.back)
        row.addWidget(self.back_btn)
        self.search = QLineEdit(objectName="Search")
        self.search.setPlaceholderText("Search")
        self.search.setFixedWidth(380)
        self.search.addAction(icons.icon("search", "#9a9a9a"), QLineEdit.ActionPosition.LeadingPosition)
        self.search.setClearButtonEnabled(True)
        self.search.returnPressed.connect(self._search)
        row.addWidget(self.search)
        row.addStretch()
        self.offline_badge = QLabel("  OFFLINE — DOWNLOADS ONLY", objectName="OfflineBadge")
        self.offline_badge.hide()
        row.addWidget(self.offline_badge)
        self.server_label = label("", "Muted")
        row.addWidget(self.server_label)
        account = QPushButton(objectName="IconButton")
        account.setIcon(icons.icon("person", "#cccccc", active_color="#ffffff"))
        account.setIconSize(QSize(24, 24))
        account.setCursor(Qt.CursorShape.PointingHandCursor)
        account.clicked.connect(lambda: self._account_menu(account))
        row.addWidget(account)
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

    def back(self):
        if len(self.history) <= 1:
            return
        old = self.history.pop()
        self.stack.removeWidget(old)
        old.deleteLater()
        self.stack.setCurrentWidget(self.history[-1])
        self.back_btn.setEnabled(len(self.history) > 1)
        current = self.history[-1]
        if hasattr(current, "refresh") and isinstance(current, DetailsPage):
            current.refresh()  # pick up watched/progress changes

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
                self.player.close()
            self.player = PlayerWindow(self.client, self.downloads, full, media_index, start, local)
            self.player.closed.connect(self._player_closed)
            self.player.show()
            self.player.raise_()
            self.player.activateWindow()

        has_parts = bool((meta.get("Media") or [{}])[0].get("Part", [{}])[0].get("Stream"))
        if local or has_parts or self.offline:
            launch(meta)
        else:  # list views omit stream details; fetch them for track selection
            run_async(lambda: self.client.metadata(meta["ratingKey"]), launch,
                      lambda e: self.toast(f"Couldn't start playback: {e}"))

    def _player_closed(self, rating_key, position):
        self.player = None
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
        self._toast.move((self.width() - self._toast.width()) // 2, self.height() - self._toast.height() - 30)
        self._toast.raise_()
        self._toast.show()
        self._toast_timer.start()

    def closeEvent(self, event):
        if self.player is not None:
            self.player.close()
        self.downloads.shutdown()
        super().closeEvent(event)

