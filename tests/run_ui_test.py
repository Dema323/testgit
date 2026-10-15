"""Run the real app against the mock Plex server and check playback end to end.

    python tests/run_ui_test.py OUTPUT_DIR
Writes screenshots and results.json to OUTPUT_DIR; exits non-zero if a check fails.
"""
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
out = os.path.abspath(sys.argv[1])
home = os.path.join(out, "home")
os.makedirs(os.path.join(home, "mpv"), exist_ok=True)
with open(os.path.join(home, "mpv", "mpv.conf"), "w") as f:
    f.write("ao=null\n")  # CI machines have no sound card

port = "38301"
fixtures = os.path.join(HERE, "fixtures")
mock = subprocess.Popen([sys.executable, os.path.join(HERE, "mock_pms.py"), port,
                         os.path.join(out, "requests.log"), os.path.join(fixtures, "sample.mkv"),
                         os.path.join(fixtures, "hls")],
                        env=dict(os.environ, QT_QPA_PLATFORM="offscreen"))
time.sleep(3)
try:
    env = dict(os.environ, PORT=port, EMBER_HOME=home)
    subprocess.run([sys.executable, os.path.join(HERE, "drive.py"), out], env=env, timeout=240)
finally:
    mock.kill()

with open(os.path.join(out, "results.json")) as f:
    r = json.load(f)
checks = {
    "no errors": not any(k.startswith("error_") for k in r),
    "direct play": r.get("play_mode") == "direct",
    # Resume point is 0:03; after ~5 s of playback the position should be well past it.
    "resumed from the saved position": 5000 <= (r.get("play_pos_ms") or 0) <= 20000,
    "video output opened": bool(r.get("mpv_vo_configured")),
    "audio track switched": r.get("mpv_aid") == 1 and r.get("aid_after_switch") == 2,
    "transcode stream loaded": r.get("transcode_mode") == "transcode" and r.get("transcode_loaded") is True,
    "download finished": r.get("download_state") == "done",
    "offline playback": r.get("local_mode") == "local",
    "show page lists seasons": r.get("show200_seasons_row") and r.get("show300_seasons_row"),
    "episode 'Season 1' link opens the season": r.get("season_link_opened") == "210",
    "player opens inside the main window": r.get("player_in_main_window") is True,
    "keeps playing while browsing (mini player)": r.get("minimized_still_playing") is True
        and r.get("mini_player_visible") is True and r.get("library_shown_while_playing") is True
        and r.get("restored_player") is True,
    "sidebar folds and unfolds": r.get("sidebar_collapsed_width") == 72 and r.get("sidebar_expanded_width") == 248,
    "episode page shows cast": (r.get("episode_cast_cards") or 0) > 0,
    "show artwork fills the window": r.get("show_art_fills_window") is True,
    "player controls take < 15% of the height": 0 < (r.get("controls_height_fraction") or 1) < 0.15,
    "own title bar on Windows": r.get("frameless") is True or sys.platform != "win32",
    "controls hidden while playing, shown when paused":
        r.get("controls_hidden_while_playing") is True and r.get("controls_shown_when_paused") is True,
}
for name, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)
print(f"video output: {r.get('mpv_vo')}  hardware decoding: {r.get('mpv_hwdec')}")
sys.exit(0 if all(checks.values()) else 1)
