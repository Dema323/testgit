"""Application entry point."""
import datetime
import locale
import os
import sys
import traceback

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import theme
from .api import PlexClient
from .config import APP_NAME, Config, data_dir
from .downloads import DownloadManager
from .images import ImageLoader
from .window import MainWindow


def _install_crash_log():
    """Write unexpected errors to <settings>/error.log; the packaged exe has no console."""
    log_path = os.path.join(data_dir(), "error.log")

    def hook(kind, value, tb):
        text = "".join(traceback.format_exception(kind, value, tb))
        try:
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n--- {datetime.datetime.now().isoformat(timespec='seconds')} ---\n{text}")
        except OSError:
            pass
        sys.__excepthook__(kind, value, tb)
        if QApplication.instance() and kind is not KeyboardInterrupt:
            QMessageBox.critical(None, APP_NAME, f"Something went wrong:\n\n{value}\n\n"
                                 f"Details were saved to:\n{log_path}")
    sys.excepthook = hook


def _close_splash():
    try:
        import pyi_splash  # noqa: PLC0415 - only exists inside the packaged exe
        pyi_splash.close()
    except ImportError:
        pass


def main():
    _install_crash_log()
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setStyle("Fusion")
    app.setWindowIcon(QIcon(os.path.join(os.path.dirname(__file__), "assets", "ember.png")))
    app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)
    # libmpv requires the C numeric locale; Qt may have changed it.
    locale.setlocale(locale.LC_NUMERIC, "C")
    cfg = Config()
    theme.load_fonts(cfg.get("font_file", ""))
    app.setFont(theme.font(14))
    app.setStyleSheet(theme.stylesheet())

    client = PlexClient(cfg)
    ImageLoader(client)
    downloads = DownloadManager(client)
    window = MainWindow(client, downloads)
    window.show()
    QTimer.singleShot(0, _close_splash)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
