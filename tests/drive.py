"""Drive Ember offscreen against the mock server and screenshot each screen."""
import json, os, sys, time
OUT = sys.argv[1]
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ember import app as appmod  # noqa: F401  (ensures package imports)
from ember import theme
from ember.api import PlexClient
from ember.config import Config
from ember.downloads import DownloadManager
from ember.images import ImageLoader
from ember.window import MainWindow

qapp = QApplication(sys.argv)
theme.load_fonts()
qapp.setFont(theme.font(14))
qapp.setStyle("Fusion")
qapp.setStyleSheet(theme.stylesheet())
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


def player_shot(name, p):
    """Video (native window) plus the controls overlay, composited."""
    from PySide6.QtGui import QPainter
    p.show_controls(animate=False)
    qapp.processEvents()
    if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
        base = p.grab()
    else:
        base = p.screen().grabWindow(int(p.video.winId()))
    painter = QPainter(base)
    painter.drawPixmap(0, 0, p.overlay.grab())
    painter.end()
    base.save(os.path.join(OUT, name + ".png"))
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
    win.toggle_sidebar()


@step(800)
def sidebar_collapsed():
    results["sidebar_collapsed_width"] = win.sidebar.width()
    shot("1b-home-sidebar-folded")
    win.toggle_sidebar()


@step(800)
def sidebar_expanded():
    results["sidebar_expanded_width"] = win.sidebar.width()


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
    from ember.cards import HubRow
    results["show200_seasons_row"] = bool(page().findChildren(HubRow))
    win.open_key("300")


@step(3000)
def show_details_dict_ondeck():
    shot("5b-show-ondeck-object")
    from ember.cards import HubRow
    results["show300_seasons_row"] = bool(page().findChildren(HubRow))
    results["show300_play_button"] = [b.text() for b in page().findChildren(type(win.back_btn))
                                      if b.objectName() == "Primary"]
    win.open_key("210")


@step(3000)
def season_details():
    shot("6-season")
    win.open_key("214")


@step(3000)
def episode_details():
    shot("6b-episode")
    from ember.details import CastCard
    results["episode_cast_cards"] = len(page().findChildren(CastCard))
    links = [b for b in page().findChildren(type(win.back_btn)) if b.objectName() == "Link"]
    results["episode_links"] = [b.text() for b in links]
    next(b for b in links if b.text() == "Season 1").click()


@step(2500)
def season_via_link():
    results["season_link_opened"] = page().meta.get("ratingKey") if getattr(page(), "meta", None) else None
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
    results["player_in_main_window"] = p.window() is win
    results["controls_hidden_while_playing"] = not p.controls_visible
    p.player.pause = True
    p._tick()
    results["controls_shown_when_paused"] = p.controls_visible
    p.player.pause = False
    player_shot("8-player", p)
    p.toggle_panel()
    player_shot("8b-player-settings", p)
    p.toggle_panel()
    # Ask mpv for what it actually rendered (GPU readback), since screen capture of a
    # Direct3D child window can come back black even when video is showing.
    try:
        p.player.command("screenshot-to-file", os.path.join(OUT, "8-player-mpv-frame.png"), "window")
        results["mpv_frame_saved"] = True
    except SystemError:  # no renderer (e.g. vo=null in headless Linux runs)
        results["mpv_frame_saved"] = False
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
    results["pos_before_minimize"] = p.pos_ms
    p.minimize_requested.emit()  # Back/Esc: keep playing, browse with the mini player


@step(2500)
def minimized():
    p = win.player
    results["minimized_still_playing"] = p is not None and p.pos_ms > results["pos_before_minimize"] + 1000
    results["mini_player_visible"] = win.mini.isVisible()
    results["library_shown_while_playing"] = win.shell.currentIndex() == 0
    shot("8c-mini-player")
    win.restore_player()


@step(1000)
def restored():
    p = win.player
    results["restored_player"] = win.shell.currentWidget() is p
    p.stop()


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
    p.stop()


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
