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
    env = dict(os.environ, PORT=port, MARQUEE_HOME=home)
    subprocess.run([sys.executable, os.path.join(HERE, "drive.py"), out], env=env, timeout=240)
finally:
    mock.kill()

with open(os.path.join(out, "results.json")) as f:
    r = json.load(f)
checks = {
    "no errors": not any(k.startswith("error_") for k in r),
    "direct play": r.get("play_mode") == "direct",
    "resumed near 0:09": 8000 <= (r.get("play_pos_ms") or 0) <= 20000,
    "video output opened": bool(r.get("mpv_vo_configured")),
    "audio track switched": r.get("mpv_aid") == 1 and r.get("aid_after_switch") == 2,
    "transcode stream loaded": r.get("transcode_mode") == "transcode" and r.get("transcode_loaded") is True,
    "download finished": r.get("download_state") == "done",
    "offline playback": r.get("local_mode") == "local",
}
for name, ok in checks.items():
    print(("PASS  " if ok else "FAIL  ") + name)
print(f"video output: {r.get('mpv_vo')}  hardware decoding: {r.get('mpv_hwdec')}")
sys.exit(0 if all(checks.values()) else 1)
