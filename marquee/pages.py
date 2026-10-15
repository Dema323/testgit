"""Browsing pages: home hubs, a library (recommended + grid), search results, downloads."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QButtonGroup, QComboBox, QHBoxLayout, QLabel, QMenu, QPushButton,
                               QScrollArea, QStackedWidget, QVBoxLayout, QWidget)

from .cards import GridView, HubRow, MediaModel, label, shape_for
from .workers import run_async

SORTS = [("Title", "titleSort"), ("Date added", "addedAt:desc"),
         ("Release date", "originallyAvailableAt:desc"), ("Rating", "rating:desc"),
         ("Last watched", "lastViewedAt:desc")]


class ScrollPage(QScrollArea):
    """Vertical page of stacked sections."""

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.setWidgetResizable(True)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.verticalScrollBar().setSingleStep(40)
        self.body = QWidget(objectName="Page")
        self.box = QVBoxLayout(self.body)
        self.box.setContentsMargins(30, 26, 30, 40)
        self.box.setSpacing(34)
        self.setWidget(self.body)

    def clear(self):
        while self.box.count():
            item = self.box.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

    def message(self, text):
        self.clear()
        lab = label(text, "Muted", wrap=True)
        lab.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.box.addStretch()
        self.box.addWidget(lab)
        self.box.addStretch()

    def add_hub(self, title, items, shape=None):
        row = HubRow(title, items, shape)
        row.opened.connect(self.app.open_item)
        self.box.addWidget(row)
        return row


def _hub_shape(hub):
    ident = hub.get("hubIdentifier", "")
    if "continue" in ident or "ondeck" in ident.lower() or hub.get("type") in ("episode", "clip"):
        return "wide"
    return None


class HomePage(ScrollPage):
    title = "Home"

    def __init__(self, app):
        super().__init__(app)
        self.refresh()

    def refresh(self):
        self.message("Loading…")
        run_async(self.app.client.home_hubs, self._loaded,
                  lambda e: self.message(f"Couldn't load your home screen.\n{e}"))

    def _loaded(self, hubs):
        self.clear()
        if not hubs:
            self.message("Nothing here yet. Add some media to your Plex libraries.")
            return
        for hub in hubs:
            self.add_hub(hub.get("title", ""), hub["Metadata"], _hub_shape(hub))
        self.box.addStretch()


class LibraryPage(QWidget):
    def __init__(self, app, section):
        super().__init__()
        self.app, self.section = app, section
        self.title = section.get("title", "")
        sid = section["key"]

        head = QHBoxLayout()
        head.setContentsMargins(30, 22, 30, 0)
        head.addWidget(label(self.title, "PageTitle"))
        head.addSpacing(30)
        self.tabs = QButtonGroup(self)
        for i, name in enumerate(("Recommended", "Library")):
            b = QPushButton(name, objectName="Tab", checkable=True)
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            self.tabs.addButton(b, i)
            head.addWidget(b, 0, Qt.AlignmentFlag.AlignBottom)
        head.addStretch()

        # Library tab: toolbar + paged grid
        self.count = label("", "Muted")
        self.sort = QComboBox()
        for name, _ in SORTS:
            self.sort.addItem(name)
        self.unwatched = QPushButton("Unwatched only", objectName="Secondary", checkable=True)
        self.unwatched.setStyleSheet("QPushButton:checked { background: rgba(229,160,13,0.25); }")
        tools = QHBoxLayout()
        tools.setContentsMargins(30, 6, 30, 6)
        tools.addWidget(self.count)
        tools.addStretch()
        tools.addWidget(self.unwatched)
        tools.addWidget(self.sort)
        self.grid_page = QWidget()
        grid_box = QVBoxLayout(self.grid_page)
        grid_box.setContentsMargins(0, 0, 0, 0)
        grid_box.addLayout(tools)
        self.grid = None
        self.grid_holder = QVBoxLayout()
        self.grid_holder.setContentsMargins(21, 0, 21, 0)
        grid_box.addLayout(self.grid_holder, 1)

        self.recommended = ScrollPage(app)
        self.recommended.box.setContentsMargins(30, 14, 30, 40)
        self.stack = QStackedWidget()
        self.stack.addWidget(self.recommended)
        self.stack.addWidget(self.grid_page)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        layout.addLayout(head)
        layout.addWidget(self.stack, 1)

        self.tabs.idClicked.connect(self._tab)
        self.sort.currentIndexChanged.connect(lambda _: self._load_grid())
        self.unwatched.toggled.connect(lambda _: self._load_grid())
        if section.get("type") == "photo":
            self.recommended.message("Photo libraries aren't supported yet.")
            self.tabs.button(0).setChecked(True)
            self.tabs.button(1).setEnabled(False)
            return
        self.tabs.button(0).setChecked(True)
        self._load_hubs(sid)

    def _tab(self, i):
        self.stack.setCurrentIndex(i)
        if i == 1 and self.grid is None:
            self._load_grid()

    def _load_hubs(self, sid):
        self.recommended.message("Loading…")

        def loaded(hubs):
            self.recommended.clear()
            if not hubs:  # no recommendations: go straight to the full library
                self.tabs.button(1).click()
                return
            for hub in hubs:
                self.recommended.add_hub(hub.get("title", ""), hub["Metadata"], _hub_shape(hub))
            self.recommended.box.addStretch()
        run_async(lambda: self.app.client.section_hubs(sid), loaded,
                  lambda e: self.recommended.message(f"Couldn't load this library.\n{e}"))

    def _load_grid(self):
        sid = self.section["key"]
        sort = SORTS[self.sort.currentIndex()][1]
        unwatched = self.unwatched.isChecked()
        client = self.app.client
        model = MediaModel(pager=lambda start, size: client.section_items(sid, start, size, sort, unwatched))
        model.rowsInserted.connect(lambda *_: self.count.setText(
            f"{model.total} item{'s' if model.total != 1 else ''}"))
        shape = "square" if self.section.get("type") == "artist" else "poster"
        if self.grid is not None:
            self.grid.deleteLater()
        self.grid = GridView(model, shape)
        self.grid.opened.connect(self.app.open_item)
        self.grid_holder.addWidget(self.grid)
        self.count.setText("Loading…")
        model.fetchMore()

    def refresh(self):
        if self.grid is not None and self.stack.currentIndex() == 1:
            self._load_grid()
        else:
            self._load_hubs(self.section["key"])


class SearchPage(ScrollPage):
    def __init__(self, app, query):
        super().__init__(app)
        self.query = query
        self.title = f"Search: {query}"
        self.refresh()

    def refresh(self):
        self.message("Searching…")
        run_async(lambda: self.app.client.search(self.query), self._loaded,
                  lambda e: self.message(f"Search failed.\n{e}"))

    def _loaded(self, results):
        self.clear()
        self.box.addWidget(label(f'Results for "{self.query}"', "PageTitle"))
        if not results:
            self.box.addWidget(label("No matches.", "Muted"))
            self.box.addStretch()
            return
        groups = {}
        for m in results:
            groups.setdefault(m.get("type"), []).append(m)
        names = {"movie": "Movies", "show": "TV Shows", "season": "Seasons", "episode": "Episodes",
                 "artist": "Artists", "album": "Albums", "track": "Tracks", "collection": "Collections"}
        for kind, items in groups.items():
            self.add_hub(names.get(kind, (kind or "Other").title()), items, shape_for(items))
        self.box.addStretch()


class DownloadsPage(QWidget):
    title = "Downloads"

    def __init__(self, app):
        super().__init__()
        self.app = app
        self.manager = app.downloads
        head = QHBoxLayout()
        head.setContentsMargins(30, 22, 30, 4)
        head.addWidget(label("Downloads", "PageTitle"))
        head.addStretch()
        self.info = label("", "Muted")
        head.addWidget(self.info)
        self.empty = label("Nothing downloaded yet. Use the download button on any movie, show or "
                           "episode to watch it offline.", "Muted", wrap=True)
        self.empty.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.model = MediaModel()
        self.grid = GridView(self.model, "poster")
        self.grid.opened.connect(self._open)
        self.grid.context_requested.connect(self._context)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(head)
        grid_box = QHBoxLayout()
        grid_box.setContentsMargins(21, 0, 21, 0)
        grid_box.addWidget(self.grid)
        layout.addLayout(grid_box, 1)
        layout.addWidget(self.empty, 1)

        self.manager.changed.connect(self.refresh)
        self.manager.progress.connect(self._progress)
        self.refresh()

    def refresh(self):
        items = self.manager.items()
        self.model.set_items(items)
        self.empty.setVisible(not items)
        self.grid.setVisible(bool(items))
        active = sum(1 for m in items if m["_download_state"] in ("queued", "downloading"))
        self.info.setText(f"{active} in progress" if active else
                          "Right-click an item to remove it" if items else "")

    def _progress(self, rk, done, total):
        self.model.update_item(rk, {"_download_bytes": done, "_download_total": total})

    def _open(self, m):
        state = m.get("_download_state")
        if state == "done":
            self.app.play(m, local_only=True)
        elif state == "failed":
            self.manager.retry(m["ratingKey"])
        else:
            self.app.toast("Still downloading — it'll be playable when finished.")

    def _context(self, m, pos):
        menu = QMenu(self)
        if m.get("_download_state") == "done":
            menu.addAction("Play", lambda: self.app.play(m, local_only=True))
            if m.get("viewOffset"):
                menu.addAction("Play from start", lambda: self.app.play(m, from_start=True, local_only=True))
        if m.get("_download_state") == "failed":
            menu.addAction("Retry download", lambda: self.manager.retry(m["ratingKey"]))
        menu.addAction("Remove download", lambda: self.manager.remove(m["ratingKey"]))
        menu.exec(pos)


class MessagePage(QLabel):
    def __init__(self, text, title=""):
        super().__init__(text)
        self.title = title
        self.setObjectName("Muted")
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
