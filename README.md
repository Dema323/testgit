# Marquee

A desktop player for your Plex Media Server, with a dark, poster-driven interface.
It talks to your server through the standard Plex HTTP API and plays everything with
[mpv](https://mpv.io) (libmpv), embedded in the window.

Marquee is an independent project and is not affiliated with or endorsed by Plex, Inc.

## Features

- **Sign in with your Plex account.** It finds your servers and picks the fastest address
  (local network, then remote, then relay).
- **Home** shows your server's hubs: Continue Watching, Recently Added, and so on.
- **Libraries** have a *Recommended* tab and a *Library* poster grid. The grid can be sorted
  (title, date added, release date, rating, last watched) and filtered to unwatched items.
  It loads more items as you scroll.
- **Details pages** for movies, shows, seasons, episodes, artists and albums. Each shows the
  backdrop, tags such as 4K, HDR10, HDR10+ and Dolby Vision, cast, and facts. Buttons:
  Play / Resume / Play from start, mark watched or unwatched, and download.
- **Version, audio and subtitle pickers** on the details page and in the player. Your choice
  is saved to the server, so other Plex apps remember it too.
- **Playback**
  - *Original quality* streams the file untouched; mpv decodes it, including 4K HEVC.
  - Lower qualities (1080p 20/12/8 Mbps down to 720 kbps) ask the server to transcode.
    Switching quality mid-play keeps your position.
  - Resume points, watched status and "Now Playing" are reported back to the server.
  - Episodes go straight to the next one when they finish.
- **HDR10.** The player uses mpv's `gpu-next` renderer on Direct3D 11 with
  `target-colorspace-hint`, so an HDR-capable display switches into HDR and the HDR
  metadata is passed through. Turn on *Use HDR* in Windows display settings.
- **Offline downloads.** Download a movie, an episode, a whole season, all of a show, or an
  album. Downloads resume after interruptions and show progress on the Downloads page. If
  the server can't be reached, Marquee opens in offline mode and plays your downloads.
- **Keyboard**
  - Library: `Ctrl+F` search; `Alt+←` or `Backspace` to go back.
  - Player: `Space` play/pause; `←` / `→` jump back 10 s / forward 30 s; `↑` / `↓` volume;
    `F` fullscreen; `Esc` leave fullscreen or close.

## Build the Windows exe

Push this folder to a GitHub repository. The workflow in `.github/workflows/build-windows.yml`
runs on every push to `main`:

1. Installs the dependencies.
2. Downloads `libmpv-2.dll` from
   [shinchiro/mpv-winbuild-cmake](https://github.com/shinchiro/mpv-winbuild-cmake/releases).
3. Builds `Marquee.exe` with PyInstaller.
4. Uploads `Marquee-windows-x64.zip` as a build artifact.

Pushing a tag such as `v0.1.0` also attaches the zip to a GitHub release.

To build on a Windows machine yourself:

```powershell
pip install -r requirements.txt pyinstaller
# put libmpv-2.dll (from an mpv-dev-x86_64 build) in this folder, then:
pyinstaller marquee.spec --noconfirm
dist\Marquee\Marquee.exe
```

## Run from source

```
pip install -r requirements.txt
python run.py
```

This needs libmpv on the system: `libmpv-2.dll` on PATH on Windows, or the `libmpv2`
package on Linux.

## Settings and customisation

Settings and data live in `%APPDATA%\Marquee` on Windows or `~/.config/marquee` on Linux:

- `config.json`: your sign-in token and preferences. Keep it private.
- `downloads.json` and `downloads-art/`: the offline download index and artwork.
- `cache/images/`: cached posters.
- `mpv/mpv.conf`: optional extra mpv options, for example `scale=ewa_lanczossharp` or
  HDR tone-mapping settings. Lua scripts can go in `mpv/scripts/`.

Default quality and the download folder can be changed under *Settings* (the account menu,
top right).

## Limitations

- Photo libraries, playlists, Live TV/DVR and Plexamp-style music features are not implemented.
- Downloads save the original file; there is no download-at-lower-quality option.
- Separate subtitle files (for example `.srt` next to the video) aren't downloaded for offline use.
- Image-based subtitles (PGS/VobSub) work in original quality. When transcoding, the server
  burns the selected subtitle into the picture.

## Fonts

The bundled Open Sans is licensed under the SIL Open Font License (see `marquee/fonts/OFL.txt`).
If it can't be loaded, the interface falls back to Segoe UI.
