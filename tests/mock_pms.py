"""Mock Plex Media Server for UI testing: fictional library, generated artwork, real video."""
import hashlib, json, os, re, sys, threading, urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter

PORT, LOG, SAMPLE, HLS = int(sys.argv[1]), sys.argv[2], sys.argv[3], sys.argv[4]
TOKEN = "SRVTOKEN"
qapp = QGuiApplication([])
img_lock = threading.Lock()

MOVIES = ["Northern Lights", "The Quiet Harbor", "Glass Orchard", "Midnight Cartographer", "Paper Moons",
          "Iron Valley", "Last Train to Avalon", "Salt & Ember", "The Long Field", "Copper Sky",
          "Wolves of Ardent", "Velvet Static", "Hollow Pines", "A Map of Rain"]
GENRES = ["Drama", "Thriller", "Science Fiction", "Adventure", "Comedy", "Mystery"]
items = {}


def stream_set(part_id, hdr=False):
    return [
        {"id": part_id * 10 + 1, "streamType": 1, "index": 0, "codec": "hevc" if hdr else "h264",
         "displayTitle": "4K (HEVC Main 10 HDR10)" if hdr else "1080p (H.264)",
         **({"colorTrc": "smpte2084"} if hdr else {})},
        {"id": part_id * 10 + 2, "streamType": 2, "index": 1, "selected": True, "displayTitle": "English (AAC Stereo)",
         "extendedDisplayTitle": "English (AAC Stereo)", "languageCode": "eng"},
        {"id": part_id * 10 + 3, "streamType": 2, "index": 2, "displayTitle": "Français (AAC Stereo)",
         "extendedDisplayTitle": "Français (AAC Stereo)", "languageCode": "fra"},
        {"id": part_id * 10 + 4, "streamType": 3, "key": f"/library/streams/{part_id * 10 + 4}",
         "displayTitle": "English (SRT External)", "extendedDisplayTitle": "English (SRT External)"},
    ]


def media(part_id, hdr=False, duration=20000):
    return [{"id": part_id, "videoResolution": "4k" if hdr else "1080", "videoCodec": "hevc" if hdr else "h264",
             "audioCodec": "aac", "container": "mkv", "duration": duration,
             "Part": [{"id": part_id, "key": f"/library/parts/{part_id}/1/file.mkv", "container": "mkv",
                       "file": f"/media/{part_id}.mkv", "size": os.path.getsize(SAMPLE), "duration": duration,
                       "Stream": stream_set(part_id, hdr)}]}]


def add(m):
    items[m["ratingKey"]] = m
    return m


for i, title in enumerate(MOVIES):
    rk = str(100 + i)
    add({"ratingKey": rk, "key": f"/library/metadata/{rk}", "type": "movie", "title": title,
         "year": 2008 + i, "duration": 12000 if i == 0 else 5400000 + i * 600000, "librarySectionID": 1,
         "summary": f"{title} is a fictional film used to test this player. A sweeping story about people, "
                    "places and the long road between them, told across three acts.",
         "tagline": "Every journey has a last stop." if i == 0 else "",
         "contentRating": "PG-13", "audienceRating": 7.1 + (i % 3) / 2, "studio": "Test Pictures",
         "thumb": f"/library/metadata/{rk}/thumb/1", "art": f"/library/metadata/{rk}/art/1",
         "viewOffset": 3000 if i == 0 else (2400000 if i == 3 else None), "viewCount": 1 if i in (5, 8) else None,
         "addedAt": 1700000000 + i,
         "Genre": [{"tag": GENRES[i % 6]}, {"tag": GENRES[(i + 2) % 6]}],
         "Director": [{"tag": "Ada Lindqvist"}], "Writer": [{"tag": "Tomas Reyes"}, {"tag": "June Park"}],
         "Role": [{"tag": n, "role": r, "thumb": f"/people/{n.replace(' ', '')}"} for n, r in
                  [("Maya Okafor", "Captain Reed"), ("Leo Brandt", "Sam"), ("Ines Duarte", "Dr. Vale"),
                   ("Omar Haddad", "The Pilot"), ("Kira Sato", "Mira"), ("Ben Ashworth", "Holt")]],
         "Media": media(1000 + i, hdr=i in (0, 2))})
    items[rk] = {k: v for k, v in items[rk].items() if v is not None}

SHOWS = [("Signal Fire", 2, 6), ("The Orchard House", 1, 8)]
for s, (title, n_seasons, n_eps) in enumerate(SHOWS):
    show_rk = str(200 + s * 100)
    eps_total = n_seasons * n_eps
    add({"ratingKey": show_rk, "key": f"/library/metadata/{show_rk}/children", "type": "show", "title": title,
         "year": 2019 + s, "childCount": n_seasons, "leafCount": eps_total, "viewedLeafCount": 3 if s == 0 else 0,
         "summary": f"{title} is a fictional series used for testing.", "contentRating": "TV-14",
         "thumb": f"/library/metadata/{show_rk}/thumb/1", "art": f"/library/metadata/{show_rk}/art/1",
         "librarySectionID": 2, "Genre": [{"tag": "Drama"}],
         "Role": [{"tag": "Nadia Flores", "role": "Eve"}, {"tag": "Arjun Mehta", "role": "Theo"}]})
    for sn in range(1, n_seasons + 1):
        season_rk = str(int(show_rk) + sn * 10)
        add({"ratingKey": season_rk, "key": f"/library/metadata/{season_rk}/children", "type": "season",
             "title": f"Season {sn}", "index": sn, "parentTitle": title, "parentRatingKey": show_rk,
             "leafCount": n_eps, "viewedLeafCount": 3 if (s == 0 and sn == 1) else 0,
             "thumb": f"/library/metadata/{season_rk}/thumb/1", "art": f"/library/metadata/{show_rk}/art/1",
             "parentThumb": f"/library/metadata/{show_rk}/thumb/1"})
        for e in range(1, n_eps + 1):
            ep_rk = str(int(season_rk) + e)
            add({"ratingKey": ep_rk, "key": f"/library/metadata/{ep_rk}", "type": "episode",
                 "title": ["Ignition", "Smoke", "Embers", "Backdraft", "The Watch", "Ash"][(e - 1) % 6] + (f" {e}" if e > 6 else ""),
                 "index": e, "parentIndex": sn, "parentRatingKey": season_rk, "grandparentRatingKey": show_rk,
                 "grandparentTitle": title, "parentTitle": f"Season {sn}", "duration": 20000,
                 "summary": "A fictional episode. Things escalate quickly when an unexpected visitor arrives.",
                 "originallyAvailableAt": f"2020-0{sn}-{e:02}", "contentRating": "TV-14",
                 "thumb": f"/library/metadata/{ep_rk}/thumb/1", "art": f"/library/metadata/{show_rk}/art/1",
                 "grandparentThumb": f"/library/metadata/{show_rk}/thumb/1",
                 "grandparentArt": f"/library/metadata/{show_rk}/art/1",
                 **({"viewCount": 1} if (s == 0 and sn == 1 and e <= 3) else {}),
                 **({"viewOffset": 7000} if (s == 0 and sn == 1 and e == 4) else {}),
                 "Media": media(int(ep_rk))})

children = {}
for m in items.values():
    parent = m.get("parentRatingKey")
    if parent:
        children.setdefault(parent, []).append(m)
movies = [items[str(100 + i)] for i in range(len(MOVIES))]
shows = [items["200"], items["300"]]
continue_watching = [items["214"], items["100"], items["103"]]


def lite(m):  # list views omit Stream details, like the real server
    out = {k: v for k, v in m.items() if k not in ("Role", "Writer", "Director")}
    if "Media" in out:
        out["Media"] = [{k: v for k, v in md.items() if k != "Part"} | {"Part": [
            {k: v for k, v in p.items() if k != "Stream"} for p in md["Part"]]} for md in out["Media"]]
    return out


def full(m):
    out = dict(m)
    if m["type"] == "show":
        out["OnDeck"] = {"Metadata": [lite(items["214"])]}
    return out


def mc(**kw):
    return {"MediaContainer": kw}


def image(path, w, h):
    with img_lock:
        seed = int(hashlib.md5(path.split("/thumb")[0].split("/art")[0].encode()).hexdigest()[:6], 16)
        hue = seed % 360
        img = QImage(w, h, QImage.Format.Format_RGB32)
        p = QPainter(img)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        g = QLinearGradient(0, 0, w * 0.4, h)
        g.setColorAt(0, QColor.fromHsv(hue, 150, 200))
        g.setColorAt(1, QColor.fromHsv((hue + 40) % 360, 200, 60))
        p.fillRect(0, 0, w, h, g)
        p.setBrush(QColor(255, 255, 255, 30))
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(w * 0.45, h * 0.1, w * 0.8, w * 0.8))
        rk = re.search(r"/metadata/(\d+)", path)
        m = items.get(rk.group(1)) if rk else None
        text = (m.get("title") if m else path.rsplit("/", 1)[-1]) or ""
        if m and m["type"] == "season":
            text = m["parentTitle"] + "\n" + m["title"]
        if "/art/" in path:
            text = ""
        if path.startswith("/people/"):
            text = ""
            p.setBrush(QColor(255, 255, 255, 70))
            p.drawEllipse(QRectF(w * 0.3, h * 0.18, w * 0.4, w * 0.4))
            p.drawEllipse(QRectF(w * 0.15, h * 0.62, w * 0.7, h * 0.6))
        f = QFont("DejaVu Sans")
        f.setPixelSize(max(12, int(w / 9)))
        f.setBold(True)
        p.setFont(f)
        p.setPen(QColor(255, 255, 255, 235))
        p.drawText(QRectF(w * 0.08, h * 0.55, w * 0.84, h * 0.4), Qt.AlignmentFlag.AlignLeft | Qt.TextFlag.TextWordWrap, text.upper())
        p.end()
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QBuffer.OpenModeFlag.WriteOnly)
        img.save(buf, "JPG", 88)
        return bytes(ba)


class H(BaseHTTPRequestHandler):
    def log(self):
        u = urllib.parse.urlparse(self.path)
        with open(LOG, "a") as f:
            f.write(json.dumps({"m": self.command, "path": u.path, "q": dict(urllib.parse.parse_qsl(u.query)),
                                "token": self.headers.get("X-Plex-Token"),
                                "range": self.headers.get("Range")}) + "\n")
        return u.path, dict(urllib.parse.parse_qsl(u.query))

    def send_json(self, obj, code=200):
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, path, ctype):
        size = os.path.getsize(path)
        rng = self.headers.get("Range")
        start, end = 0, size - 1
        if rng and rng.startswith("bytes="):
            a, _, b = rng[6:].partition("-")
            start = int(a or 0)
            end = int(b) if b else size - 1
            self.send_response(206)
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        else:
            self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        self.end_headers()
        with open(path, "rb") as f:
            f.seek(start)
            remaining = end - start + 1
            try:
                while remaining > 0:
                    chunk = f.read(min(1 << 16, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass

    def do_PUT(self):
        self.log()
        self.send_json({})

    def do_GET(self):
        path, q = self.log()
        if path != "/identity" and self.headers.get("X-Plex-Token") != TOKEN:
            self.send_json({}, 401)
            return
        if path == "/identity":
            return self.send_json(mc(machineIdentifier="mock"))
        if path == "/library/sections":
            return self.send_json(mc(Directory=[{"key": "1", "title": "Movies", "type": "movie"},
                                                {"key": "2", "title": "TV Shows", "type": "show"}]))
        if path == "/hubs":
            return self.send_json(mc(Hub=[
                {"title": "Continue Watching", "hubIdentifier": "home.continue", "type": "mixed",
                 "Metadata": [lite(m) for m in continue_watching]},
                {"title": "Recently Added Movies", "hubIdentifier": "home.movies.recent", "type": "movie",
                 "Metadata": [lite(m) for m in movies[::-1]]},
                {"title": "Recently Added TV", "hubIdentifier": "home.television.recent", "type": "season",
                 "Metadata": [lite(items[k]) for k in ("220", "210", "310")]}]))
        m = re.fullmatch(r"/hubs/sections/(\d+)", path)
        if m:
            src = movies if m.group(1) == "1" else shows
            return self.send_json(mc(Hub=[
                {"title": "Continue Watching", "hubIdentifier": "movie.inprogress", "Metadata": [lite(x) for x in continue_watching if x["type"] == ("movie" if m.group(1) == "1" else "episode")]},
                {"title": "Recently Added", "hubIdentifier": "movie.recentlyadded", "Metadata": [lite(x) for x in src[::-1]]},
                {"title": "Top Rated", "hubIdentifier": "movie.toprated", "Metadata": [lite(x) for x in src[::2]]}]))
        m = re.fullmatch(r"/library/sections/(\d+)/all", path)
        if m:
            src = movies if m.group(1) == "1" else shows
            if q.get("unwatched"):
                src = [x for x in src if not x.get("viewCount")]
            start, size = int(q.get("X-Plex-Container-Start", 0)), int(q.get("X-Plex-Container-Size", 50))
            return self.send_json(mc(totalSize=len(src), Metadata=[lite(x) for x in src[start:start + size]]))
        m = re.fullmatch(r"/library/metadata/(\d+)(/children|/allLeaves)?", path)
        if m and m.group(1) in items:
            rk, sub = m.groups()
            if sub == "/children":
                return self.send_json(mc(Metadata=[lite(x) for x in children.get(rk, [])]))
            if sub == "/allLeaves":
                leaves = [e for s in children.get(rk, []) for e in children.get(s["ratingKey"], [])] or children.get(rk, [])
                return self.send_json(mc(Metadata=[lite(x) for x in leaves]))
            return self.send_json(mc(Metadata=[full(items[rk])]))
        if path == "/hubs/search":
            hits = [x for x in items.values() if q.get("query", "").lower() in x["title"].lower()
                    and x["type"] in ("movie", "show", "episode")]
            return self.send_json(mc(Hub=[{"Metadata": [lite(x) for x in hits]}]))
        if path == "/photo/:/transcode":
            body = image(q["url"], int(q["width"]), int(q["height"]))
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            return self.wfile.write(body)
        if re.fullmatch(r"/library/parts/\d+/1/file\.mkv", path):
            return self.send_file(SAMPLE, "video/x-matroska")
        if path.startswith("/library/streams/"):
            srt = b"1\n00:00:01,000 --> 00:00:06,000\nMock subtitle line\n"
            self.send_response(200)
            self.send_header("Content-Length", str(len(srt)))
            self.end_headers()
            return self.wfile.write(srt)
        if path in ("/:/timeline", "/:/scrobble", "/:/unscrobble", "/video/:/transcode/universal/stop"):
            return self.send_json({})
        if path == "/video/:/transcode/universal/decision":
            return self.send_json(mc(generalDecisionCode=1000, generalDecisionText="Direct play OK"))
        if path == "/video/:/transcode/universal/start.m3u8":
            return self.send_file(os.path.join(HLS, "index.m3u8"), "application/vnd.apple.mpegurl")
        m = re.fullmatch(r"/video/:/transcode/universal/(index\d+\.ts)", path)
        if m:
            return self.send_file(os.path.join(HLS, m.group(1)), "video/mp2t")
        self.send_json({}, 404)

    def log_message(self, *a):
        pass


ThreadingHTTPServer(("127.0.0.1", PORT), H).serve_forever()
