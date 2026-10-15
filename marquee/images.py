"""Asynchronous poster/artwork loading with memory and disk caches."""
import hashlib
import os
from collections import OrderedDict

from PySide6.QtCore import QObject, QUrl
from PySide6.QtGui import QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .config import data_dir

MEMORY_LIMIT = 800  # pixmaps


class ImageLoader(QObject):
    _instance = None

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.nam = QNetworkAccessManager(self)
        self.cache_dir = os.path.join(data_dir(), "cache", "images")
        os.makedirs(self.cache_dir, exist_ok=True)
        self.memory = OrderedDict()
        self.pending = {}
        ImageLoader._instance = self

    @classmethod
    def instance(cls):
        return cls._instance

    def cached(self, path, width, height):
        key = f"{path}@{width}x{height}"
        pm = self.memory.get(key)
        if pm is not None:
            self.memory.move_to_end(key)
        return pm

    def load(self, path, width, height, callback):
        """Call callback(QPixmap) once the image is available (possibly immediately)."""
        if not path:
            return
        key = f"{path}@{width}x{height}"
        pm = self.cached(path, width, height)
        if pm is not None:
            callback(pm)
            return
        if os.path.isabs(path) and os.path.exists(path):  # downloaded artwork
            self._store(key, QPixmap(path), [callback])
            return
        disk = os.path.join(self.cache_dir, hashlib.sha1(
            f"{self.client.cfg.get('server_id')}{key}".encode()).hexdigest() + ".img")
        if os.path.exists(disk):
            self._store(key, QPixmap(disk), [callback])
            return
        if key in self.pending:
            self.pending[key].append(callback)
            return
        url = path if path.startswith("http") and "/photo/" in path else \
            self.client.image_url(path, width, height)
        if not url:
            return
        self.pending[key] = [callback]
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"X-Plex-Token", self.client.token.encode())
        req.setRawHeader(b"X-Plex-Client-Identifier", self.client.cfg["client_id"].encode())
        reply = self.nam.get(req)
        reply.finished.connect(lambda: self._finished(key, disk, reply))

    def _finished(self, key, disk, reply):
        data = bytes(reply.readAll())
        ok = reply.error() == QNetworkReply.NetworkError.NoError
        reply.deleteLater()
        pm = QPixmap()
        if ok and pm.loadFromData(data):
            try:
                with open(disk, "wb") as f:
                    f.write(data)
            except OSError:
                pass
        self._store(key, pm, self.pending.pop(key, []))

    def _store(self, key, pm, callbacks):
        if not pm.isNull():
            self.memory[key] = pm
            while len(self.memory) > MEMORY_LIMIT:
                self.memory.popitem(last=False)
        for cb in callbacks:
            try:
                cb(pm)
            except RuntimeError:  # receiver deleted
                pass
