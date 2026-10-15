"""Asynchronous artwork loading.

Images are fetched with QNetworkAccessManager, then decoded and center-cropped to the exact
requested pixel size on a worker thread, so painting a card is a plain pixmap copy.
Results are cached in memory and the fetched bytes on disk.
"""
import hashlib
import os
from collections import OrderedDict

from PySide6.QtCore import QObject, Qt, QUrl
from PySide6.QtGui import QImage, QPixmap
from PySide6.QtNetwork import QNetworkAccessManager, QNetworkReply, QNetworkRequest

from .config import data_dir
from .workers import run_async

MEMORY_LIMIT = 900  # pixmaps


def _decode(data, width, height):
    img = QImage()
    if not img.loadFromData(data):
        return None
    if width and height:
        img = img.scaled(width, height, Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                         Qt.TransformationMode.SmoothTransformation)
        img = img.copy((img.width() - width) // 2, (img.height() - height) // 2, width, height)
    return img.convertToFormat(QImage.Format.Format_ARGB32_Premultiplied)


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

    @staticmethod
    def _key(path, width, height):
        return f"{path}@{width}x{height}"

    def cached(self, path, width, height):
        key = self._key(path, width, height)
        pm = self.memory.get(key)
        if pm is not None:
            self.memory.move_to_end(key)
        return pm

    def load(self, path, width, height, callback):
        """Call callback(QPixmap) with the image cropped to exactly width x height device pixels."""
        if not path:
            return
        key = self._key(path, width, height)
        pm = self.cached(path, width, height)
        if pm is not None:
            callback(pm)
            return
        if key in self.pending:
            self.pending[key].append(callback)
            return
        self.pending[key] = [callback]

        if os.path.isabs(path) and os.path.exists(path):  # downloaded artwork
            self._decode_file(key, path, width, height)
            return
        # The server transcodes to the requested size, so one disk entry per size is fine.
        disk = os.path.join(self.cache_dir, hashlib.sha1(
            f"{self.client.cfg.get('server_id')}{key}".encode()).hexdigest() + ".img")
        if os.path.exists(disk):
            self._decode_file(key, disk, width, height)
            return
        url = self.client.image_url(path, width, height)
        if not url:
            self.pending.pop(key, None)
            return
        req = QNetworkRequest(QUrl(url))
        req.setRawHeader(b"X-Plex-Token", self.client.token.encode())
        req.setRawHeader(b"X-Plex-Client-Identifier", self.client.cfg["client_id"].encode())
        reply = self.nam.get(req)
        reply.finished.connect(lambda: self._fetched(key, disk, width, height, reply))

    def _decode_file(self, key, path, width, height):
        def work():
            with open(path, "rb") as f:
                return _decode(f.read(), width, height)
        run_async(work, lambda img: self._done(key, img), lambda e: self._done(key, None))

    def _fetched(self, key, disk, width, height, reply):
        data = bytes(reply.readAll())
        ok = reply.error() == QNetworkReply.NetworkError.NoError and data
        reply.deleteLater()
        if not ok:
            self._done(key, None)
            return

        def work():
            img = _decode(data, width, height)
            if img is not None:
                try:
                    with open(disk, "wb") as f:
                        f.write(data)
                except OSError:
                    pass
            return img
        run_async(work, lambda img: self._done(key, img), lambda e: self._done(key, None))

    def _done(self, key, image):
        pm = QPixmap.fromImage(image) if image is not None else QPixmap()
        if not pm.isNull():
            self.memory[key] = pm
            while len(self.memory) > MEMORY_LIMIT:
                self.memory.popitem(last=False)
        for cb in self.pending.pop(key, []):
            try:
                cb(pm)
            except RuntimeError:  # receiver deleted
                pass
