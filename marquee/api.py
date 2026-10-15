"""Plex Media Server and plex.tv HTTP API client.

All methods are blocking; the UI calls them through workers.run_async.
"""
import json
import platform
import urllib.error
import urllib.parse
import urllib.request

PRODUCT = "Marquee"
VERSION = "0.1.0"
PLEX_TV = "https://plex.tv"
PLAYABLE = {"movie", "episode", "track", "clip"}

# (id, label, max bitrate kbps, resolution). "original" plays the file untouched.
QUALITIES = [
    ("original", "Original quality", None, None),
    ("20000", "1080p · 20 Mbps", 20000, "1920x1080"),
    ("12000", "1080p · 12 Mbps", 12000, "1920x1080"),
    ("8000", "1080p · 8 Mbps", 8000, "1920x1080"),
    ("4000", "720p · 4 Mbps", 4000, "1280x720"),
    ("3000", "720p · 3 Mbps", 3000, "1280x720"),
    ("2000", "720p · 2 Mbps", 2000, "1280x720"),
    ("1500", "480p · 1.5 Mbps", 1500, "720x480"),
    ("720", "324p · 720 kbps", 720, "576x324"),
]

# Tells the server what this client can decode when it has to transcode:
# HLS in MPEG-TS with H.264/HEVC video. mpv handles anything, so this is generous.
PROFILE_EXTRA = "+".join([
    "add-transcode-target(type=videoProfile&context=streaming&protocol=hls&container=mpegts"
    "&videoCodec=h264,hevc&audioCodec=aac,ac3,eac3,mp3&replace=true)",
    "add-transcode-target(type=musicProfile&context=streaming&protocol=hls&container=mpegts"
    "&audioCodec=aac,mp3&replace=true)",
])


class PlexError(Exception):
    def __init__(self, message, status=None):
        super().__init__(message)
        self.status = status


def container(data):
    return data.get("MediaContainer", {}) if isinstance(data, dict) else {}


class PlexClient:
    def __init__(self, config):
        self.cfg = config

    # --- plumbing -------------------------------------------------------------

    @property
    def server_url(self):
        return self.cfg.get("server_url", "")

    @property
    def token(self):
        return self.cfg.get("server_token", "")

    def headers(self, token=None):
        h = {
            "Accept": "application/json",
            "X-Plex-Product": PRODUCT,
            "X-Plex-Version": VERSION,
            "X-Plex-Client-Identifier": self.cfg["client_id"],
            "X-Plex-Platform": platform.system(),
            "X-Plex-Platform-Version": platform.release(),
            "X-Plex-Device": platform.system(),
            "X-Plex-Device-Name": platform.node() or PRODUCT,
            "X-Plex-Provides": "player",
        }
        if token:
            h["X-Plex-Token"] = token
        return h

    def request(self, url, method="GET", token=None, params=None, timeout=20):
        if params:
            clean = {k: v for k, v in params.items() if v is not None}
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(clean)
        data = b"" if method in ("POST", "PUT") else None
        req = urllib.request.Request(url, data=data, method=method, headers=self.headers(token))
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = resp.read()
        except urllib.error.HTTPError as e:
            raise PlexError(f"HTTP {e.code} from {url.split('?')[0]}", e.code) from e
        except (urllib.error.URLError, OSError) as e:
            raise PlexError(f"Could not reach {url.split('?')[0]}: {getattr(e, 'reason', e)}") from e
        try:
            return json.loads(body) if body.strip() else {}
        except ValueError:
            return {}

    # endpoint is positional-only: Plex query parameters include names like "path".
    def get(self, endpoint, /, timeout=20, **params):
        return container(self.request(self.server_url + endpoint, token=self.token,
                                      params=params or None, timeout=timeout))

    def put(self, endpoint, /, **params):
        return self.request(self.server_url + endpoint, method="PUT", token=self.token, params=params)

    # --- plex.tv sign-in and server discovery -----------------------------------

    def create_pin(self):
        return self.request(PLEX_TV + "/api/v2/pins", method="POST", params={"strong": "true"})

    def check_pin(self, pin_id):
        return self.request(f"{PLEX_TV}/api/v2/pins/{pin_id}").get("authToken")

    def auth_url(self, code):
        return "https://app.plex.tv/auth#?" + urllib.parse.urlencode({
            "clientID": self.cfg["client_id"],
            "code": code,
            "context[device][product]": PRODUCT,
        })

    def servers(self):
        resources = self.request(PLEX_TV + "/api/v2/resources", token=self.cfg["user_token"],
                                 params={"includeHttps": 1, "includeRelay": 1})
        return [r for r in resources if "server" in r.get("provides", "")]

    def connect(self, resource):
        """Try a server's addresses (LAN, then remote, then relay) and keep the first that answers."""
        conns = sorted(resource.get("connections", []),
                       key=lambda c: (c.get("relay", False), not c.get("local", False)))
        token = resource.get("accessToken") or self.cfg["user_token"]
        for conn in conns:
            try:
                self.request(conn["uri"] + "/identity", token=token, timeout=5)
            except PlexError:
                continue
            self.cfg.update(server_url=conn["uri"].rstrip("/"), server_token=token,
                            server_name=resource.get("name"),
                            server_id=resource.get("clientIdentifier"))
            self.cfg.save()
            return True
        return False

    def reconnect(self):
        """Re-resolve the saved server's address, e.g. after moving between networks."""
        try:
            self.get("/identity", timeout=5)
            return True
        except PlexError:
            pass
        if not self.cfg.get("user_token") or not self.cfg.get("server_id"):
            return False
        try:
            for res in self.servers():
                if res.get("clientIdentifier") == self.cfg["server_id"]:
                    return self.connect(res)
        except PlexError:
            pass
        return False

    # --- library ------------------------------------------------------------------

    def sections(self):
        return self.get("/library/sections").get("Directory", [])

    def home_hubs(self):
        return [h for h in self.get("/hubs", count=20).get("Hub", []) if h.get("Metadata")]

    def section_hubs(self, section_id):
        return [h for h in self.get(f"/hubs/sections/{section_id}", count=20).get("Hub", [])
                if h.get("Metadata")]

    def section_items(self, section_id, start, size, sort=None, unwatched=False):
        mc = self.get(f"/library/sections/{section_id}/all", sort=sort,
                      unwatched=1 if unwatched else None,
                      **{"X-Plex-Container-Start": start, "X-Plex-Container-Size": size})
        return mc.get("Metadata", []), int(mc.get("totalSize", mc.get("size", 0)))

    def metadata(self, rating_key):
        items = self.get(f"/library/metadata/{rating_key}", includeOnDeck=1).get("Metadata", [])
        if not items:
            raise PlexError("Item not found", 404)
        return items[0]

    def children(self, rating_key):
        return self.get(f"/library/metadata/{rating_key}/children").get("Metadata", [])

    def all_leaves(self, rating_key):
        return self.get(f"/library/metadata/{rating_key}/allLeaves").get("Metadata", [])

    def browse(self, path):
        return self.get(path).get("Metadata", [])

    def search(self, query):
        hubs = self.get("/hubs/search", query=query, limit=30).get("Hub", [])
        return [m for hub in hubs for m in hub.get("Metadata", [])]

    def set_watched(self, rating_key, watched):
        path = "/:/scrobble" if watched else "/:/unscrobble"
        self.get(path, key=rating_key, identifier="com.plexapp.plugins.library")

    def set_streams(self, part_id, audio_id=None, subtitle_id=None):
        """Persist the chosen audio/subtitle stream server-side (0 = subtitles off)."""
        self.put(f"/library/parts/{part_id}", audioStreamID=audio_id,
                 subtitleStreamID=subtitle_id, allParts=1)

    def timeline(self, meta, state, time_ms, duration_ms, session=None):
        self.get("/:/timeline", timeout=8, ratingKey=meta["ratingKey"], key=meta["key"],
                 state=state, time=int(time_ms), duration=int(duration_ms),
                 **({"X-Plex-Session-Identifier": session} if session else {}))

    # --- URLs handed to mpv / the image loader -----------------------------------

    def image_url(self, path, width, height):
        if not path:
            return ""
        return self.server_url + "/photo/:/transcode?" + urllib.parse.urlencode({
            "width": width, "height": height, "minSize": 1, "upscale": 1, "url": path})

    def part_url(self, part_key):
        return self.server_url + part_key

    def download_url(self, part_key):
        return self.server_url + part_key + ("&" if "?" in part_key else "?") + "download=1"

    def mpv_headers(self):
        return [f"X-Plex-Token: {self.token}",
                f"X-Plex-Client-Identifier: {self.cfg['client_id']}"]

    def _transcode_params(self, rating_key, media_index, quality, offset_s, session, burn_subs):
        _, _, bitrate, resolution = next(q for q in QUALITIES if q[0] == quality)
        return {
            "path": f"/library/metadata/{rating_key}",
            "mediaIndex": media_index, "partIndex": 0,
            "protocol": "hls", "fastSeek": 1, "copyts": 1,
            "directPlay": 0, "directStream": 1, "directStreamAudio": 1,
            "videoQuality": 100, "videoResolution": resolution, "maxVideoBitrate": bitrate,
            "subtitleSize": 100, "audioBoost": 100, "location": "lan",
            "subtitles": "burn" if burn_subs else "none",
            "offset": int(offset_s), "session": session,
            "X-Plex-Session-Identifier": session,
            "X-Plex-Client-Identifier": self.cfg["client_id"],
            "X-Plex-Product": PRODUCT,
            "X-Plex-Platform": platform.system(),
            "X-Plex-Client-Profile-Extra": PROFILE_EXTRA,
        }

    def transcode_decision(self, *args):
        """Ask the server to plan the transcode; returns (ok, message)."""
        mc = self.get("/video/:/transcode/universal/decision", **self._transcode_params(*args))
        code = int(mc.get("generalDecisionCode", 1000) or 1000)
        return code < 2000, mc.get("generalDecisionText", "")

    def transcode_url(self, *args):
        return (self.server_url + "/video/:/transcode/universal/start.m3u8?"
                + urllib.parse.urlencode(self._transcode_params(*args)))

    def stop_transcode(self, session):
        self.get("/video/:/transcode/universal/stop", timeout=5, session=session)


# --- presentation helpers shared by the views ---------------------------------------

def fmt_duration(ms):
    minutes = int(ms or 0) // 60000
    h, m = divmod(minutes, 60)
    return f"{h} hr {m} min" if h else f"{m} min"


def fmt_clock(ms):
    s = int(ms or 0) // 1000
    h, s = divmod(s, 3600)
    m, s = divmod(s, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def episode_code(m):
    return f"S{int(m.get('parentIndex') or 0)} · E{int(m.get('index') or 0)}"


def card_title(m, context="hub"):
    if m.get("type") == "episode" and context != "season":
        return m.get("grandparentTitle") or m.get("title", "")
    if m.get("type") == "season" and context == "hub":
        return m.get("parentTitle") or m.get("title", "")
    return m.get("title", "")


def card_subtitle(m, context="hub"):
    kind = m.get("type")
    if kind == "episode":
        return m.get("title", "") if context == "season" else episode_code(m)
    if kind == "season":
        n = m.get("leafCount")
        return (m.get("title", "") if context == "hub" else
                f"{n} episode{'s' if n != 1 else ''}" if n is not None else "")
    if kind == "show":
        n = m.get("childCount")
        return f"{n} season{'s' if n != 1 else ''}" if n else str(m.get("year", ""))
    if kind == "album":
        return m.get("parentTitle", "")
    if kind == "track":
        return m.get("grandparentTitle", "")
    return str(m.get("year", "") or "")


def card_image(m, shape):
    if m.get("_poster"):  # downloaded item: local file
        return m["_art"] if shape == "wide" and m.get("_art") else m["_poster"]
    kind = m.get("type")
    if shape == "wide":
        if kind == "episode":
            return m.get("thumb") or m.get("grandparentArt")
        return m.get("art") or m.get("thumb")
    if kind == "episode":
        return m.get("grandparentThumb") or m.get("thumb")
    return m.get("thumb") or m.get("parentThumb")


def video_badges(meta):
    """'4K', 'HDR10', 'Dolby Vision', ... from the first version's video stream."""
    badges = []
    media = (meta.get("Media") or [{}])[0]
    res = str(media.get("videoResolution", "")).lower()
    if res == "4k":
        badges.append("4K")
    elif res.isdigit():
        badges.append(f"{res}p")
    for part in media.get("Part", []):
        for s in part.get("Stream", []):
            if s.get("streamType") != 1:
                continue
            title = (s.get("displayTitle", "") + " " + s.get("extendedDisplayTitle", "")).upper()
            if s.get("DOVIPresent") or "DOVI" in title or "DOLBY VISION" in title:
                badges.append("Dolby Vision")
            if "HDR10+" in title:
                badges.append("HDR10+")
            elif "HDR" in title or s.get("colorTrc") == "smpte2084":
                badges.append("HDR10")
            elif s.get("colorTrc") == "arib-std-b67":
                badges.append("HLG")
            break
    return badges


def streams(part, stream_type):
    return [s for s in part.get("Stream", []) if s.get("streamType") == stream_type]
