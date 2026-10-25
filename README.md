# Niri Live Wallpaper

A terminal app for using **videos as your desktop wallpaper** on the [niri](https://github.com/niri-wm/niri)
compositor, made to work alongside [DankMaterialShell (DMS)](https://github.com/AvengeMedia/DankMaterialShell).

Many video-wallpaper apps (e.g. Hidamari) open a normal fullscreen window. A tiling compositor like niri tiles
it like any other window, so it covers your apps. Here the video is drawn by
[mpvpaper](https://github.com/GhostNaN/mpvpaper) on a real Wayland **background layer surface**
(`wlr-layer-shell`), behind all windows, the same way swaybg or DMS's own wallpaper work.

```
 Niri Live Wallpaper
 ──────────────────────────────────────────────────────────────────────────
 Setup
 ✓ niri: layer-rule found in ~/.config/niri
layer-rule { match namespace="^mpvpaper$"; place-within-backdrop true; }
 ✓ DMS: built-in wallpaper disabled
 ──────────────────────────────────────────────────────────────────────────
 Videos  (~/.local/share/niri-live-wallpaper/videos)
  ● ocean.mp4      3840×2160 · 60 fps → 30 fps · per-screen
  ○ forest.webm    1920×1080 · 24 fps

 Actions
  › Import a video (fuzzy finder)
  › Open video folder in file manager
  › Stop live wallpaper
  › Cycle wallpapers: [every 1h 30m]
  › Start at login: [on]
  › Ask to lower frame rate on import (>30 fps): [on]
  › Ask for per-screen frame rate & resolution on import: [off]
  › Quit
 ──────────────────────────────────────────────────────────────────────────
 wallpaper: playing   autostart: on   cycle: every 1h 30m, next in 52m
```

## Features

- **Video library:** import videos with a fuzzy finder (`fzf`), one or many at once, or drop files into the app's folder. Pick one
  with `space` and it becomes your wallpaper.
- **Start at login:** asked the first time you pick a wallpaper, and toggleable any time.
- **Cycling:** switch to the next video every hour, day, week, or a custom `hh:mm` interval.
- **Per-screen performance tuning:** videos bigger than a screen get a downscaled copy made for that screen, so a
  4K video isn't decoded for a 1080p panel. Frame rate (60/30/24/12/custom/original) and resolution (100/75/50/33%/custom)
  can be set per video and per screen. Videos faster than 30 fps trigger a question on import.
- **Never plays sound**, even if the file has an audio track.
- **DMS theming stays in sync:** a still frame of the current video is handed to DMS, so its colour scheme
  (matugen) and lock screen match the wallpaper.
- **Setup checks:** the top of the screen shows whether niri's config, other wallpaper programs and the
  session are set up correctly, on any niri setup, with or without DMS.

## Will it work on my niri?

**Yes, on any niri setup that runs under systemd. DankMaterialShell is optional.** The table below covers the
details:

| Your setup | Works? | What to know |
|---|---|---|
| niri + DMS (what this was built on) | yes | Turn off DMS's built-in wallpaper (setup step 3). Colours and the lock screen follow the video. |
| niri + another shell or bar (Noctalia, waybar, ironbar, …) | yes | Stop its wallpaper program (swaybg, swww, the shell's own wallpaper). The app spots anything else drawing a background. No theme sync: that part is DMS only. |
| niri on its own, no wallpaper tool | yes | The stationary option needs **both** config lines (setup step 2). niri's default workspace background is opaque grey, so the layer-rule alone would hide the video. |
| niri started with `niri-session` or a display manager (GDM, SDDM, greetd + `niri-session`, uwsm) | yes | These start niri as a systemd session, which the background service needs. |
| niri started as plain `niri` (e.g. from a TTY) | no | No `graphical-session.target`, and `WAYLAND_DISPLAY` isn't passed to systemd, so the service can't start. The setup check says so. |
| Distros without systemd (Void, Artix, Alpine, Gentoo/OpenRC, …) | no, not yet | Playback is run and started at login by a systemd user service. Everything else would work. |
| niri older than 25.05 | partly | Playback works; the stationary option (`place-within-backdrop`, `layout { background-color }`) needs 25.05+. |
| Any GPU | yes | Intel and AMD use VA-API for decoding and encoding copies. On NVIDIA (or with no VA-API driver), copies are encoded on the CPU with libx264, which is slower but works. |
| Multiple monitors, any resolution, scaling or rotation | yes | One player per screen; screens come from `niri msg`. Plugging monitors in and out is handled. |
| Distros other than Arch | yes, if mpvpaper is available | mpvpaper is packaged by e.g. openSUSE Tumbleweed, NixOS, Void, Alpine, FreeBSD, Guix (Fedora: Terra repo; Gentoo: GURU). It isn't in Debian, Ubuntu or the Fedora repos: build it from [source](https://github.com/GhostNaN/mpvpaper). |

## Dependencies

Package names are for Arch Linux. Every Python module the app uses ships with Python (including `curses`).

| What | Package | Command(s) used | Needed for | Required? |
|---|---|---|---|---|
| Compositor | `niri` (25.05+ for the stationary option) | `niri msg` | running the wallpaper; detecting screens and other wallpapers | **yes** |
| Python ≥ 3.10 | `python` | `python3` | running the app (standard library only) | **yes** |
| Video player | `mpvpaper` (AUR) | `mpvpaper` | **displaying the video** on the wallpaper layer | **yes** |
| Video library | `mpv` | (libmpv) | used by mpvpaper to decode and render the video; installed automatically with mpvpaper | **yes** |
| Service manager | `systemd` user session, with niri started as a session | `systemctl --user` | starting/stopping the wallpaper, start at login | **yes** |
| FFmpeg | `ffmpeg` | `ffprobe`, `ffmpeg` | reading resolution/fps, making per-screen copies, extracting the frame for DMS theming | strongly recommended: without it originals are played as they are and there's no theme sync |
| Fuzzy finder | `fzf` 0.33+ | `fzf` | **Import videos** | for importing (you can still drop files into the folder) |
| File search | `fd` | `fd` or `fdfind` (Debian/Ubuntu name) | faster file listing for the import picker | no: falls back to `find` (`findutils`) |
| Clipboard | `wl-clipboard` | `wl-copy` | **`c`: copy the niri config lines to the clipboard** | no: you can select them with the mouse instead |
| D-Bus tool | `glib2` | `gdbus` | **Open video folder**: asks your file manager over D-Bus (`org.freedesktop.FileManager1`) | no: falls back to `xdg-open` |
| File manager | e.g. `thunar`, `nautilus`, `dolphin` | – | handles the D-Bus request above | for opening the folder |
| XDG utils | `xdg-utils` | `xdg-open` | fallback for opening the folder (uses your `inode/directory` default app) | no |
| Hardware video | VA-API driver: AMD → included in `mesa`; Intel → `intel-media-driver`; NVIDIA → `nvidia-vaapi-driver` | – | GPU video decoding during playback and GPU encoding of copies (`hevc_vaapi`) | no: without it the CPU decodes, and copies are encoded with `libx264` (slower, more CPU). NVIDIA's driver decodes only, so copies use `libx264` there |
| Shell | `dms-shell` | `dms ipc` | theme sync (passing the frame to DMS); the DMS setup check | no: only if you use DMS |
| Terminal | any, with UTF-8 | – | drawing `✓ ✗ ● ○ ›` | yes |

Install everything at once:

```sh
sudo pacman -S --needed python ffmpeg fzf fd wl-clipboard glib2 xdg-utils
yay -S mpvpaper            # pulls in mpv
```

## Setup before the first run

The top of the app shows three setup checks: ✓ means fine, ✗ needs fixing, – is an optional suggestion. They're
re-checked every few seconds while the app is open.

### 1. Start niri as a session

Log in through a display manager or with `niri-session`, not by running plain `niri`. That's how niri normally
starts, and it's what makes `graphical-session.target` active and passes `WAYLAND_DISPLAY` / `NIRI_SOCKET` to
systemd, which the background service needs. Check: **✓ session: systemd and niri session ready**.

### 2. niri: a wallpaper that stays still (optional, recommended)

Without any config, the video is drawn on each workspace and scrolls with it. For a stationary wallpaper (how
DMS and most setups behave), add **both** lines to your niri config (`~/.config/niri/config.kdl`, `$NIRI_CONFIG`,
or any file they `include`):

```kdl
layer-rule { match namespace="^mpvpaper$"; place-within-backdrop true; }
layout { background-color "transparent"; }
```

- The **layer-rule** moves mpvpaper's surfaces (namespace `mpvpaper`, see `niri msg layers`) into niri's
  **backdrop**, behind the workspaces. It also shows behind the zoomed-out workspaces in the overview.
- The **transparent background** lets the backdrop show through. niri's default workspace background is opaque
  grey, so with only the layer-rule **the video is hidden behind every workspace** and visible only in the
  overview. DMS already sets this line in its generated `dms/colors.kdl`; other setups usually don't.

Both lines are shown at the top of the app; press `c` to copy them or select them with the mouse. niri reloads its
config automatically when you save. The check reads niri's config the way niri does: `config.kdl` (or
`$NIRI_CONFIG`) and every file it `include`s, ignoring commented-out lines. A `background-color` that isn't
transparent anywhere, including a per-output one, counts as opaque.

### 3. Only one wallpaper program

Anything else drawing on niri's background layer (swaybg, swww, a shell's own wallpaper) can end up on top of the
video. The app asks niri what's drawn there and names it: **✗ something else draws a background … swaybg
(wallpaper)**. Stop that program and remove it from your autostart.

**With DMS:** in **DMS Settings → Wallpaper → External Wallpaper Management**, turn on **Disable Built-in
Wallpapers**. DMS sometimes re-creates its wallpaper surface (e.g. after monitor changes), which would put it back
on top. Turning it off doesn't affect theming: DMS takes its colours from the wallpaper image path, and this app
sets that path to a frame of the video. It also removes DMS's blurred overview wallpaper; with step 2 the video
shows there instead. The app reads `~/.config/DankMaterialShell/settings.json` for this
(`screenPreferences.wallpaper` is `[]` when the toggle is on).

### 4. Run it

```sh
./nlw.py                 # straight from the checkout, nothing to install
# optional, to run it as `nlw` from anywhere:
ln -s "$PWD/nlw.py" ~/.local/bin/nlw
# or install it as a package (creates the `nlw` command):
pipx install .           # or: pip install --user .
```

`nlw --version` prints the version, and `nlw --help` lists the commands.

Import a video (`i`), select it with `space`, and answer the "start at login?" question.

## Usage

| Key | Action |
|---|---|
| `↑↓` / `j k`, `g` / `G` | move, jump to top/bottom |
| `space` / `enter` | on a video: set it as the wallpaper; on an action: run it |
| `i` | import videos: fuzzy-find videos under your home folder and they're **copied** into the app's video folder. Mark several with `Tab` (`Ctrl-A` marks everything currently shown, e.g. after typing a folder name), or just press `Enter` for one. With several, the frame-rate questions come first, then all copies are encoded; Esc during encoding skips the rest |
| `o` | open the app's video folder in your file manager (files you drop there appear within a second) |
| `e` / `f` | edit the selected video's frame rate & resolution, for all screens or per screen |
| `d` / `Delete` | delete the selected video (asks first; stops the wallpaper if it's the current one) |
| `s` | stop the wallpaper (start at login stays as it is) |
| `a` | toggle start at login |
| `c` | copy the two niri config lines (setup step 2) to the clipboard |
| `q` / `Esc` | quit (the wallpaper keeps playing; it's a background service) |

Menu-only options:

- **Cycle wallpapers:** off / every hour / every day / every week / custom `hh:mm` (`1:30`, `0:45`, or `2` for
  2:00; from 1 minute to 720 hours). The next video in the list takes over once the interval since the last change
  has passed. "Every day" means 24 h after the last change, not at midnight. A change that came due while the
  laptop was off or asleep happens shortly after it wakes. Picking a video by hand restarts the countdown. Needs
  at least 2 videos.
- **Ask to lower frame rate on import (>30 fps):** on by default. Importing a video faster than 30 fps (or
  selecting a dropped-in one for the first time) asks whether to convert it to 60/30/24/12/custom fps or keep the
  original.
- **Ask for per-screen frame rate & resolution on import:** off by default. When on, the settings editor
  (below) opens on import instead of the frame-rate question.

### Per-video, per-screen settings (`e`)

```
Screen           Frame rate              Resolution
All screens      30 fps                  50%
HDMI-A-1         = 30 fps                native (3440×1440)
eDP-1            24 fps                  = 50% (960×600)
```

- **Frame rate:** 60 / 30 / 24 / 12 / custom / original. Only rates below the source's are offered.
- **Resolution:** a percentage of that screen's native size: native, 75%, 50%, 33%, or custom 10–100%. mpv
  scales it up to fill the screen. Lower values decode less and save power; 50% looks soft up close but fine
  behind windows.
- A value starting with `= ` is inherited from **All screens**. Choose "Same as all screens" to go back to that.
- Changes apply as you go. If the video is your current wallpaper, only the screens whose settings changed get
  a new player; the others keep playing.

## How it works

```
 nlw (TUI)                            systemd --user                         niri
 ───────────                          ──────────────                         ────
 saves choices to config.json ──►  niri-live-wallpaper.service
 restart / enable / disable ────►    └─ nlw run (service.py)
 SIGUSR1 "re-read config" ──────►        ├─ mpvpaper HDMI-A-1 <copy> ─────► background layer
                                         ├─ mpvpaper eDP-1    <copy> ─────► (backdrop via layer-rule)
                                         └─ dms ipc call wallpaper set <frame.jpg>  (DMS theme)
```

- **The TUI never plays video itself.** It saves your choices and controls a systemd user service. Selecting a
  video runs `systemctl --user restart`, and start at login is `systemctl --user enable/disable`. The unit is
  `WantedBy=graphical-session.target`, the same as `dms.service`.
- **`nlw run`** (the service, `niri_live_wallpaper/service.py`) runs one `mpvpaper` per screen:
  `mpvpaper -p -o "no-audio loop-file=inf hwdec=auto-safe panscan=1.0 quiet" <output> <file>`.
  - `no-audio`: sound is never decoded or played. `hwdec=auto-safe`: GPU decoding when available.
    `panscan=1.0`: fill the screen and crop the overflow. `-p`: pause when mpvpaper thinks the wallpaper is hidden.
  - Every 30 s, or exactly when a cycle is due, or straight away when the TUI sends `SIGUSR1`, it re-reads the
    config and the list of screens from `niri msg -j outputs`. When a screen's file changes, it starts that
    screen's new player before stopping the old one, so there's no black flash.
  - When the video changes, it extracts one frame with `ffmpeg` and calls `dms ipc call wallpaper set` (or
    `setFor` per screen in DMS's per-monitor mode) so DMS's colours and lock screen match.
  - If an mpvpaper process dies (e.g. a screen was unplugged), the service exits with an error and systemd
    restarts it with the current screens.
- **Per-screen copies.** For each screen, the target size is the screen's resolution × the chosen percentage. A
  copy is encoded only when the source is **bigger** than that target and/or **faster** than the chosen frame
  rate; otherwise the original file is played. Copies are scaled to cover the target and cropped (same framing as
  mpv's `panscan`), have no audio, and are encoded with VA-API HEVC (`hevc_vaapi`, QP 26), falling back to
  `libx264`. Each copy is made once (on import, first selection, or after `e`) with progress shown; Esc cancels,
  and the original plays until the copy exists. The file name records what was encoded, e.g.
  `3440x1440@30.mp4`, and two screens with the same target share one file.
- **Settings are stored as choices, not results.** Screen resolutions are never saved; they're read from niri
  each time, so changing a monitor's mode just produces a new target. Per-screen overrides are keyed by niri's
  connector name (`HDMI-A-1`, `eDP-1`). If you plug a monitor into a different port, it gets the "All screens"
  values.

## Where everything is stored

| What | Path |
|---|---|
| Your videos (imported copies and dropped-in files) | `~/.local/share/niri-live-wallpaper/videos/` |
| App settings | `~/.config/niri-live-wallpaper/config.json` (format below) |
| Per-screen optimized copies | `~/.cache/niri-live-wallpaper/optimized/<video name>/<width>x<height>@<fps or "src">.mp4` |
| Frames handed to DMS for theming | `~/.cache/niri-live-wallpaper/frames/<video name>.jpg` |
| systemd unit (written by the app) | `~/.config/systemd/user/niri-live-wallpaper.service` |
| Start-at-login link (created by `systemctl enable`) | `~/.config/systemd/user/graphical-session.target.wants/niri-live-wallpaper.service` |
| Service log | systemd journal: `journalctl --user -u niri-live-wallpaper` |
| TUI log (warnings and errors, rotated at 256 KB) | `~/.local/state/niri-live-wallpaper/tui.log` |
| Read only: niri config (setup check) | `~/.config/niri/config.kdl` and the files it includes |
| Read only: DMS settings (setup check) | `~/.config/DankMaterialShell/settings.json` |

`$XDG_DATA_HOME`, `$XDG_CONFIG_HOME`, `$XDG_CACHE_HOME` and `$XDG_STATE_HOME` are respected if set. Everything under `~/.cache/…`
can be deleted at any time and will be regenerated.

The unit file runs `python3 -m niri_live_wallpaper run` with `PYTHONPATH` set to the folder containing the
package (your checkout). It's rewritten whenever you select a wallpaper or toggle
start at login, so after moving the app, do one of those.

### `config.json` format

```jsonc
{
  "version": 2,                        // file format version; older files are upgraded on load
  "wallpaper": "ocean.mp4",            // current video (file name in the videos folder)
  "last_change": 1792958392.7,         // when the wallpaper last changed (Unix time), for cycling
  "cycle": { "mode": "custom",         // off | hourly | daily | weekly | custom
             "minutes": 90 },          // custom interval (kept when you switch to a preset)
  "autostart_prompted": true,          // the "start at login?" question was asked
  "ask_fps": true,                     // ask to lower frame rate on import
  "ask_screens": false,                // open the per-screen editor on import
  "videos": {                          // a video listed here won't be asked about again
    "ocean.mp4": {
      "fps": 30,                       // all screens: fps cap; null = original
      "scale": 50,                     // all screens: % of native resolution; missing = 100
      "screens": {                     // per-screen overrides; a missing key = same as all screens
        "HDMI-A-1": { "scale": 100 },
        "eDP-1": { "fps": 24 }
      }
    }
  }
}
```

## Troubleshooting

- **Logs:** `journalctl --user -u niri-live-wallpaper -f` for the service, and
  `~/.local/state/niri-live-wallpaper/tui.log` for the TUI.
- **Video not visible:** look at the setup checks first.
  - Run `niri msg layers`. There should be an `mpvpaper` surface on each screen's background layer.
  - If another background surface is listed there (`quickshell`, `wallpaper`, …), see setup step 3.
  - If the video only shows in the overview, the workspace background isn't transparent (setup step 2). If
    it moves with workspaces, the layer-rule is missing (also step 2).
- **High CPU use:**
  - Check that GPU decoding works (`mpv --hwdec=auto-safe -v <file>` should mention `vaapi`), and that a VA-API
    driver is installed.
  - Lower the frame rate or resolution with `e`.
- **"Open video folder" opens a terminal or the wrong app:** your file manager doesn't provide
  `org.freedesktop.FileManager1`, so the app fell back to `xdg-open`, which uses your `inode/directory` default.
  Fix that default with `xdg-mime default thunar.desktop inode/directory` (use your file manager's `.desktop`
  name).
- **Cycling does nothing:** it needs at least 2 videos.

## Development

The code is a small Python package with no dependencies outside the standard library.
[PRACTICES.md](PRACTICES.md) explains how it's organised and why. [CHANGELOG.md](CHANGELOG.md) lists changes per
version.

```
nlw.py                       launcher: run from the checkout without installing
pyproject.toml               metadata, Python version, the `nlw` entry point
niri_live_wallpaper/
  __main__.py                command line (`nlw`, `nlw run`) and logging setup
  paths.py                   every file and directory the app uses
  proc.py                    how external programs are run (timeouts, missing programs)
  config.py                  config.json: schema, defaults, migrations
  cycling.py                 cycle schedule maths (pure)
  library.py                 the video folder: list, import, delete
  media.py                   ffprobe / ffmpeg: video info, theme frame, encoding
  variants.py                per-screen copies: what to encode (pure), encoding, pruning
  niri.py                    screens, background surfaces, niri config checks
  dms.py                     DMS built-in wallpaper check, theme sync
  systemd.py                 the user service: unit file, start/stop/enable, reload signal
  desktop.py                 clipboard, file manager, fzf picker
  checks.py                  the setup checks' wording and decisions (pure)
  service.py                 the background service: players, cycling, reloads
  tui/
    app.py                   main screen and actions
    settings_editor.py       frame-rate question and per-screen editor
    dialogs.py               yes/no, choose, text input
    formatting.py, style.py  texts, colours, keys
tests/                       unit tests for config, cycling, variants, niri, checks, import
packaging/aur/               AUR recipe (PKGBUILD) and the release checklist
```

Run the tests (no install needed):

```sh
python3 -m unittest -v
```

When changing the `config.json` format, bump `CURRENT_VERSION` in `config.py`, add a migration step, and add a
test. When releasing, bump the version in `niri_live_wallpaper/__init__.py` and `pyproject.toml` and add a
`CHANGELOG.md` entry.

## Uninstall

```sh
systemctl --user disable --now niri-live-wallpaper.service
rm ~/.config/systemd/user/niri-live-wallpaper.service && systemctl --user daemon-reload
rm -r ~/.config/niri-live-wallpaper ~/.cache/niri-live-wallpaper ~/.local/state/niri-live-wallpaper
rm -r ~/.local/share/niri-live-wallpaper     # your imported videos!
```

Then remove the two lines from your niri config (keep `background-color "transparent"` if DMS put it there)
and turn your previous wallpaper back on.

## License

MIT, see [LICENSE](LICENSE).
