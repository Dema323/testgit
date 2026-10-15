"""Application entry point."""
import locale
import sys

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from . import theme
from .api import PlexClient
from .config import APP_NAME, Config
from .downloads import DownloadManager
from .images import ImageLoader
from .window import MainWindow


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    # libmpv requires the C numeric locale; Qt may have changed it.
    locale.setlocale(locale.LC_NUMERIC, "C")
    theme.load_fonts()
    app.setFont(theme.font(13))
    app.setStyleSheet(theme.STYLESHEET)

    cfg = Config()
    client = PlexClient(cfg)
    ImageLoader(client)
    downloads = DownloadManager(client)
    window = MainWindow(client, downloads)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
