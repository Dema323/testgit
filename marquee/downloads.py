"""Offline downloads: queue original files from the server to disk, with artwork and metadata."""
import json
import os
import re
import threading
import urllib.request

from PySide6.QtCore import QObject, QThread, Signal

from .api import PLAYABLE, PlexError
from .config import data_dir
from .workers import run_async

CHUNK = 1 << 20


def _safe(name):
    return re.sub(r'[<>:"/\\|?*\x00-\x1f]', "", name).strip(" .") or "untitled"


def file_name(meta, part):
    ext = os.path.splitext(part.get("file", "") or part.get("key", ""))[1] or \
        "." + (part.get("container") or "mkv")
    if meta.get("type") == "episode":
        base = (f"{meta.get('grandparentTitle', '')} - S{int(meta.get('parentIndex') or 0):02}"
                f"E{int(meta.get('index') or 0):02} - {meta.get('title', '')}")
    elif meta.get("year"):
        base = f"{meta.get('title', '')} ({meta['year']})"
    else:
        base = meta.get("title", "")
    return _safe(base) + ext


class _Worker(QThread):
    progress = Signal(str, int, int)
    finished_item = Signal(str, bool, str)

    def __init__(self, client, entry):
        super().__init__()
        self.client, self.entry = client, entry
        self.cancelled = threading.Event()

    def run(self):
        e = self.entry
        rk = e["meta"]["ratingKey"]
        try:
            os.makedirs(os.path.dirname(e["file"]), exist_ok=True)
            for kind, path, w, h in (("_poster", e["meta"].get("grandparentThumb")
                                      if e["meta"].get("type") == "episode" else e["meta"].get("thumb"), 400, 600),
                                     ("_art", e["meta"].get("thumb") if e["meta"].get("type") == "episode"
                                      else e["meta"].get("art"), 960, 540)):
                if path and not os.path.exists(e[kind]):
                    self._fetch(self.client.image_url(path, w, h), e[kind])
            partial = e["file"] + ".part"
            have = os.path.getsize(partial) if os.path.exists(partial) else 0
            headers = self.client.headers(self.client.token)
            if have:
                headers["Range"] = f"bytes={have}-"
            req = urllib.request.Request(self.client.download_url(e["part_key"]), headers=headers)
            with urllib.request.urlopen(req, timeout=30) as resp:
                if have and resp.status != 206:
                    have = 0  # server ignored the range; start over
                total = have + int(resp.headers.get("Content-Length") or 0)
                with open(partial, "ab" if have else "wb") as out:
                    done = have
                    while not self.cancelled.is_set():
                        chunk = resp.read(CHUNK)
                        if not chunk:
                            break
                        out.write(chunk)
                        done += len(chunk)
                        self.progress.emit(rk, done, total)
            if self.cancelled.is_set():
                self.finished_item.emit(rk, False, "cancelled")
                return
            os.replace(partial, e["file"])
            self.finished_item.emit(rk, True, "")
        except Exception as ex:  # noqa: BLE001 - reported in the UI
            self.finished_item.emit(rk, False, str(ex))

    def _fetch(self, url, dest):
        req = urllib.request.Request(url, headers=self.client.headers(self.client.token))
        with urllib.request.urlopen(req, timeout=30) as resp, open(dest, "wb") as out:
            out.write(resp.read())


class DownloadManager(QObject):
    """Owns the download index (downloads.json) and runs one download at a time."""
    changed = Signal()
    progress = Signal(str, int, int)
    message = Signal(str)

    def __init__(self, client):
        super().__init__()
        self.client = client
        self.index_path = os.path.join(data_dir(), "downloads.json")
        self.art_dir = os.path.join(data_dir(), "downloads-art")
        os.makedirs(self.art_dir, exist_ok=True)
        try:
            with open(self.index_path, encoding="utf-8") as f:
                self.entries = json.load(f)
        except (FileNotFoundError, ValueError):
            self.entries = {}
        for e in self.entries.values():  # interrupted downloads resume on next start
            if e["status"] == "downloading":
                e["status"] = "queued"
        self.worker = None
        self._start_next()

    def _save(self):
        tmp = self.index_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(self.entries, f)
        os.replace(tmp, self.index_path)

    # --- queries ------------------------------------------------------------------

    def state(self, rating_key):
        e = self.entries.get(str(rating_key))
        return e["status"] if e else None

    def items(self):
        """Card-ready metadata for the downloads page, newest first."""
        out = []
        for e in reversed(list(self.entries.values())):
            m = dict(e["meta"])
            m.update(_poster=e["_poster"] if os.path.exists(e["_poster"]) else None,
                     _art=e["_art"] if os.path.exists(e["_art"]) else None,
                     _download_state=e["status"], _download_bytes=e.get("bytes", 0),
                     _download_total=e.get("total", 0), _file=e["file"])
            out.append(m)
        return out

    def local_file(self, rating_key):
        e = self.entries.get(str(rating_key))
        if e and e["status"] == "done" and os.path.exists(e["file"]):
            return e["file"]
        return None

    def update_progress(self, rating_key, view_offset):
        e = self.entries.get(str(rating_key))
        if e:
            e["meta"]["viewOffset"] = int(view_offset)
            self._save()

    # --- actions ------------------------------------------------------------------

    def download(self, meta):
        """Queue a movie/episode, or every episode of a show/season, or every track of an album."""
        def resolve():
            if meta.get("type") in PLAYABLE:
                return [self.client.metadata(meta["ratingKey"])]
            leaves = self.client.all_leaves(meta["ratingKey"])
            return [self.client.metadata(m["ratingKey"]) for m in leaves]
        run_async(resolve, self._enqueue, lambda e: self.message.emit(f"Download failed: {e}"))

    def _enqueue(self, metas):
        added = 0
        for meta in metas:
            rk = str(meta["ratingKey"])
            if rk in self.entries and self.entries[rk]["status"] != "failed":
                continue
            media = (meta.get("Media") or [None])[0]
            if not media or not media.get("Part"):
                continue
            part = media["Part"][0]
            folder = self.client.cfg["download_dir"]
            if meta.get("type") == "episode":
                folder = os.path.join(folder, _safe(meta.get("grandparentTitle", "")))
            self.entries[rk] = {
                "meta": meta, "part_key": part["key"], "status": "queued",
                "file": os.path.join(folder, file_name(meta, part)),
                "_poster": os.path.join(self.art_dir, f"{rk}-poster.jpg"),
                "_art": os.path.join(self.art_dir, f"{rk}-art.jpg"),
                "bytes": 0, "total": part.get("size", 0),
            }
            added += 1
        if added:
            self._save()
            self.message.emit(f"Added {added} item{'s' if added != 1 else ''} to downloads")
            self.changed.emit()
            self._start_next()
        elif metas:
            self.message.emit("Already downloaded")

    def remove(self, rating_key):
        rk = str(rating_key)
        if self.worker and self.worker.entry["meta"]["ratingKey"] == rk:
            self.worker.cancelled.set()
            self.worker.wait(5000)
        e = self.entries.pop(rk, None)
        if e:
            for path in (e["file"], e["file"] + ".part", e["_poster"], e["_art"]):
                try:
                    os.remove(path)
                except OSError:
                    pass
            self._save()
            self.changed.emit()
        self._start_next()

    def retry(self, rating_key):
        e = self.entries.get(str(rating_key))
        if e and e["status"] == "failed":
            e["status"] = "queued"
            self._save()
            self.changed.emit()
            self._start_next()

    def shutdown(self):
        if self.worker:
            self.worker.cancelled.set()
            self.worker.wait(5000)

    def _start_next(self):
        if self.worker is not None or not self.client.cfg.get("server_url"):
            return
        entry = next((e for e in self.entries.values() if e["status"] == "queued"), None)
        if entry is None:
            return
        entry["status"] = "downloading"
        self.worker = _Worker(self.client, entry)
        self.worker.progress.connect(self._on_progress)
        self.worker.finished_item.connect(self._on_finished)
        self.worker.start()
        self.changed.emit()

    def _on_progress(self, rk, done, total):
        e = self.entries.get(rk)
        if e:
            e["bytes"], e["total"] = done, total or e.get("total", 0)
        self.progress.emit(rk, done, total)

    def _on_finished(self, rk, ok, error):
        worker, self.worker = self.worker, None
        if worker:
            worker.wait()
            worker.deleteLater()
        e = self.entries.get(rk)
        if e and error != "cancelled":
            e["status"] = "done" if ok else "failed"
            e["error"] = error
            if not ok:
                self.message.emit(f"Download failed: {e['meta'].get('title', '')}: {error}")
        self._save()
        self.changed.emit()
        self._start_next()


def offline_error(e):
    return isinstance(e, PlexError) and e.status is None
