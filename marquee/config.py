"""Settings and per-user data locations."""
import json
import os
import uuid

APP_NAME = "Marquee"


def data_dir():
    if os.environ.get("MARQUEE_HOME"):
        base = os.environ["MARQUEE_HOME"]
    elif os.name == "nt":
        base = os.path.join(os.environ.get("APPDATA", os.path.expanduser("~")), APP_NAME)
    else:
        base = os.path.join(os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config")),
                            APP_NAME.lower())
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
