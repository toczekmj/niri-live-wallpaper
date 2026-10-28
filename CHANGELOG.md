# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/2.0.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [0.2.0] - 2026-10-28

### Added

- `install.sh`, a one-line installer: `bash -c "$(curl -fsSL …/install.sh)"`. On Arch-based distros it
  installs a pacman package (mpvpaper from the AUR); elsewhere it installs the app into its own Python
  environment and lists any missing programs. Supports `--dry-run`, `--yes` and `--uninstall`.
- Still images (png, jpg, webp, bmp, avif, jxl) can be imported and used as wallpapers next to videos. They
  are shown as they are, take part in cycling, and are handed to DMS directly for theming.
- Choose how a video or image fits a screen of a different shape: fill and crop, black bars, blurred bars,
  stretch or original size. When cropping, pick which edge to keep. The choice is made per screen in the settings
  editor (`e`), which gets a Fit column; importing an image that doesn't match a screen asks right away. Copies
  made for a screen follow the fit, and their file names record it.

- Playlists: named sets of wallpapers you create, rename, delete and fill (`p`, a fuzzy-finder popup; `+` adds the
  highlighted wallpaper). Pick one to show and play only its files; with none, everything plays as before. A file
  has its own settings (fit, frame rate, resolution, per-screen choices) in every playlist, copied from its
  settings when you add it. In a playlist, `d` removes a file from it, and importing adds to it. Every playlist
  has its own cycle time; "all wallpapers" keeps the existing one.

### Changed

- The settings editor and the "ask on import" option now cover fit as well as frame rate and resolution.
- The settings editor shows every change live on the wallpaper, and the fit menus preview each option as you
  move the highlight, including during an import (your current wallpaper comes back afterwards) and
  when you pick a wallpaper. Esc keeps the settings, `c` or `q` cancels and restores the previous ones. (Before,
  changes were only applied after closing it.)
- README: quick install at the top, a table of contents, and an up-to-date picture of the app.

## [0.1.0] - 2026-10-25

First public release.

### Added

- Terminal UI (`nlw`): a video library you fill by importing with a fuzzy finder (several files at once with
  Tab, Ctrl-A for all shown) or by dropping files into its folder. Select with space, delete, stop, and open
  the folder in your file manager.
- Background playback through a systemd user service that runs one `mpvpaper` per screen. Start at login is
  asked the first time and can be toggled any time. Sound is never played.
- Cycling through the library every hour, day, week, or a custom `hh:mm` interval.
- Per-screen optimized copies, so a 4K video isn't decoded for a smaller screen: downscaled and cropped to
  each screen (VA-API HEVC, libx264 fallback), with frame rate (60/30/24/12/custom) and resolution
  (100/75/50/33 %/custom) settable per video and per screen. Videos faster than 30 fps get a frame-rate
  question on import; an optional per-screen editor can open on import too.
- DankMaterialShell integration: a still frame of the video drives DMS's colour scheme and lock screen.
- Setup checks that work on any niri setup: the niri config for a stationary wallpaper (layer-rule plus
  transparent workspace background, following `include`s and `$NIRI_CONFIG`), other programs drawing a
  background (via `niri msg -j layers`, with a specific hint for DMS), and the systemd/niri session.
- `config.json` with a format version and automatic upgrades, logs in the journal (service) and in
  `~/.local/state/niri-live-wallpaper/tui.log` (TUI), unit tests (`python3 -m unittest`), an AUR recipe in
  `packaging/aur/`, and the MIT license.

[0.1.0]: https://github.com/toczekmj/niri-live-wallpaper/releases/tag/v0.1.0
