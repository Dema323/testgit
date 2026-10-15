"""First-run sign-in (plex.tv PIN flow in the browser) and server selection."""
from PySide6.QtCore import QTimer, QUrl, Qt, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QPushButton, QVBoxLayout, QWidget

from .cards import label
from .config import APP_NAME
from .workers import run_async


class LoginPage(QWidget):
    done = Signal()

    def __init__(self, client, choose_server_only=False):
        super().__init__()
        self.client = client
        self.setObjectName("Root")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground)
        card = QWidget()
        card.setFixedWidth(440)
        self.box = QVBoxLayout(card)
        self.box.setSpacing(16)
        outer = QVBoxLayout(self)
        outer.addStretch()
        outer.addWidget(card, 0, Qt.AlignmentFlag.AlignHCenter)
        outer.addStretch(2)
        self.poll = QTimer(self, interval=2000, timeout=self._check)
        self.pin = None
        if choose_server_only:
            self._load_servers()
        else:
            self._welcome()

    def _reset(self):
        while self.box.count():
            w = self.box.takeAt(0).widget()
            if w:
                w.deleteLater()
        brand = label(APP_NAME, "Brand")
        brand.setStyleSheet("font-size: 40px; padding: 0;")
        brand.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.box.addWidget(brand)

    def _text(self, text, name="Muted"):
        lab = label(text, name, wrap=True)
        lab.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        self.box.addWidget(lab)
        return lab

    def _button(self, text, slot, primary=True):
        b = QPushButton(text, objectName="Primary" if primary else "Secondary")
        b.setCursor(Qt.CursorShape.PointingHandCursor)
        b.setMinimumHeight(42)
        b.clicked.connect(slot)
        self.box.addWidget(b)
        return b

    def _welcome(self):
        self._reset()
        self._text("Sign in with your Plex account to browse and play your libraries.")
        self.sign_in = self._button("Sign in with Plex", self._start)

    def _start(self):
        self.sign_in.setEnabled(False)
        self.sign_in.setText("Opening browser…")

        def started(pin):
            self.pin = pin
            self.url = self.client.auth_url(pin["code"])
            QDesktopServices.openUrl(QUrl(self.url))
            self._reset()
            self._text("Finish signing in in your browser.")
            self._text("This window continues automatically.", "Faint")
            self._button("Open the sign-in page again", lambda: QDesktopServices.openUrl(QUrl(self.url)), False)
            self._button("Cancel", self._cancel, False)
            self.poll.start()
        run_async(self.client.create_pin, started, self._error)

    def _cancel(self):
        self.poll.stop()
        self._welcome()

    def _check(self):
        pin = self.pin

        def checked(token):
            if token and self.poll.isActive():
                self.poll.stop()
                self.client.cfg["user_token"] = token
                self.client.cfg.save()
                self._load_servers()
        run_async(lambda: self.client.check_pin(pin["id"]), checked, lambda e: None)

    def _load_servers(self):
        self._reset()
        self._text("Finding your servers…")
        run_async(self.client.servers, self._servers, self._error)

    def _servers(self, servers):
        self._reset()
        if not servers:
            self._text("No Plex Media Servers were found on this account.")
            self._button("Try again", self._load_servers, False)
            return
        if len(servers) == 1:
            self._connect(servers[0])
            return
        self._text("Choose a server")
        for s in servers:
            self._button(s["name"] + ("" if s.get("owned") else "  (shared with you)"),
                         lambda _=False, s=s: self._connect(s), False)

    def _connect(self, server):
        self._reset()
        self._text(f"Connecting to {server['name']}…")

        def connected(ok):
            if ok:
                self.done.emit()
            else:
                self._reset()
                self._text(f"Couldn't reach {server['name']} on any of its addresses. "
                           "Is the server running and reachable from this computer?")
                self._button("Try again", lambda: self._connect(server), False)
                self._button("Pick another server", self._load_servers, False)
        run_async(lambda: self.client.connect(server), connected, self._error)

    def _error(self, e):
        self.poll.stop()
        self._reset()
        self._text(f"Something went wrong: {e}")
        self._button("Start over", self._welcome, False)
