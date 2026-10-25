# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/2.0.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

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

[Unreleased]: https://github.com/toczekmj/niri-live-wallpaper/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/toczekmj/niri-live-wallpaper/releases/tag/v0.1.0
