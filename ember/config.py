"""Settings and per-user data locations."""
import json
import os
import shutil
import uuid

APP_NAME = "Ember"
OLD_NAME = "Marquee"  # the app's previous name; its settings are carried over


def data_dir():
    if os.environ.get("EMBER_HOME"):
        base = os.environ["EMBER_HOME"]
        old = None
    elif os.name == "nt":
        root = os.environ.get("APPDATA", os.path.expanduser("~"))
        base, old = os.path.join(root, APP_NAME), os.path.join(root, OLD_NAME)
    else:
        root = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        base, old = os.path.join(root, APP_NAME.lower()), os.path.join(root, OLD_NAME.lower())
    if old and not os.path.exists(base) and os.path.isdir(old):
        try:  # keep sign-in, settings and downloads from before the rename
            shutil.copytree(old, base, ignore=shutil.ignore_patterns("cache"))
        except OSError:
            pass
    os.makedirs(base, exist_ok=True)
    return base


def default_download_dir():
    return os.path.join(os.path.expanduser("~"), "Videos", APP_NAME)


class Config(dict):
    """JSON-backed settings. Holds the Plex token, so the file is private to the user."""

    def __init__(self):
        super().__init__()
        self.path = os.path.join(data_dir(), "config.json")
        try:
            with open(self.path, encoding="utf-8") as f:
                self.update(json.load(f))
        except (FileNotFoundError, ValueError):
            pass
        self.setdefault("client_id", str(uuid.uuid4()))
        self.setdefault("quality", "original")
        self.setdefault("download_dir", default_download_dir())
        self.setdefault("font_file", "")          # optional custom interface font (.ttf/.otf)
        self.setdefault("sidebar_collapsed", False)

    def save(self):
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self, f, indent=2)

    @property
    def signed_in(self):
        return bool(self.get("user_token"))

    @property
    def has_server(self):
        return bool(self.get("server_url") and self.get("server_token"))

    def sign_out(self):
        for key in ("user_token", "server_url", "server_token", "server_name", "server_id"):
            self.pop(key, None)
        self.save()


def log_error(context=""):
    """Append the current exception's traceback to error.log (the exe has no console)."""
    import datetime
    import traceback
    try:
        with open(os.path.join(data_dir(), "error.log"), "a", encoding="utf-8") as f:
            f.write(f"\n--- {datetime.datetime.now().isoformat(timespec='seconds')} {context} ---\n")
            f.write(traceback.format_exc())
    except OSError:
        pass
    traceback.print_exc()
