"""Drive Marquee offscreen against the mock server and screenshot each screen."""
import json, os, sys, time
OUT = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from marquee import app as appmod  # noqa: F401  (ensures package imports)
from marquee import theme
from marquee.api import PlexClient
from marquee.config import Config
from marquee.downloads import DownloadManager
from marquee.images import ImageLoader
from marquee.window import MainWindow

qapp = QApplication(sys.argv)
theme.load_fonts()
qapp.setFont(theme.font(13))
qapp.setStyle("Fusion")
qapp.setStyleSheet(theme.STYLESHEET)
cfg = Config()
cfg.update(user_token="USR", server_url=f"http://127.0.0.1:{os.environ['PORT']}", server_token="SRVTOKEN",
           server_name="Living Room Server", server_id="mock", download_dir=os.path.join(OUT, "dl"))
cfg.save()
client = PlexClient(cfg)
ImageLoader(client)
downloads = DownloadManager(client)
win = MainWindow(client, downloads)
win.resize(1440, 900)
win.show()
results = {}


def shot(name, widget=None):
    w = widget or win
    pm = w.grab()
    if widget is not None and os.environ.get("QT_QPA_PLATFORM") != "offscreen":
        # Video is drawn by mpv into a native child window: grab it from the screen instead.
        pm = w.screen().grabWindow(int(w.winId()))
    pm.save(os.path.join(OUT, name + ".png"))
    print("shot", name, flush=True)


def page():
    return win.history[-1]


steps = []


def step(delay):
    def deco(fn):
        steps.append((delay, fn))
        return fn
    return deco


@step(3500)
def home():
    shot("1-home")


@step(200)
def go_library():
    win.show_section({"key": "1", "title": "Movies", "type": "movie"})


@step(3000)
def lib_recommended():
    shot("2-library-recommended")
    page().tabs.button(1).click()


@step(3000)
def lib_grid():
    shot("3-library-grid")
    win.open_key("100")


@step(3000)
def movie_details():
    shot("4-movie-details")
    win.open_key("200")


@step(3000)
def show_details():
    shot("5-show-details")
    win.open_key("210")


@step(3000)
def season_details():
    shot("6-season")
    win.search.setText("the")
    win._search()


@step(3000)
def search():
    shot("7-search")
    win.open_key("100")


@step(2500)
def start_play():
    downloads.download(client.metadata("101"))  # queue a download in the background
    win.play(page().meta)


@step(6000)
def playing():
    p = win.player
    results["play_mode"] = p.mode
    results["play_pos_ms"] = p.pos_ms
    results["mpv_path"] = p.player.path
    results["mpv_aid"] = p.player.aid
    results["mpv_tracks"] = [(t["type"], t.get("id"), t.get("ff-index"), t.get("external", False))
                             for t in p.player.track_list]
    results["mpv_sid"] = p.player.sid
    results["mpv_vo"] = p.player.current_vo
    results["mpv_hwdec"] = p.player.hwdec_current
    results["mpv_vo_configured"] = p.player.vo_configured
    shot("8-player", p)
    p._choose_audio(next(s for s in p.part["Stream"] if s["id"] == 10003))  # Français


@step(1500)
def audio_switched():
    results["aid_after_switch"] = win.player.player.aid
    win.player._choose_quality("4000")


@step(5000)
def transcoding():
    p = win.player
    results["transcode_mode"] = p.mode
    results["transcode_path"] = p.player.path
    results["transcode_pos"] = p.pos_ms
    results["transcode_loaded"] = p.loaded
    p.close()


@step(1500)
def downloads_page():
    win.show_downloads()


@step(3000)
def downloads_shot():
    shot("9-downloads")
    results["download_state"] = downloads.state("101")
    results["download_file"] = downloads.local_file("101")


@step(500)
def offline_play():
    m = next(x for x in downloads.items() if x["ratingKey"] == "101")
    win.play(m, local_only=True)


@step(3000)
def offline_check():
    p = win.player
    results["local_mode"] = p.mode
    results["local_path"] = p.player.path
    p.close()


@step(800)
def done():
    print("RESULTS " + json.dumps(results, default=str), flush=True)
    with open(os.path.join(OUT, "results.json"), "w") as f:
        json.dump(results, f, indent=2, default=str)
    win.close()
    qapp.quit()


def run(i=0):
    if i < len(steps):
        delay, fn = steps[i]

        def go():
            try:
                fn()
            except Exception as e:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                results[f"error_{fn.__name__}"] = repr(e)
            run(i + 1)
        QTimer.singleShot(delay, go)


run()
QTimer.singleShot(120000, qapp.quit)
sys.exit(qapp.exec())
