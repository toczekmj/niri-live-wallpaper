"""The setup checks shown at the top of the TUI: is this niri session ready for a video wallpaper?

Pure functions: the TUI gathers the facts (niri config, niri's layer list, DMS settings, systemd)
and these decide what to tell the user. Written to make sense on any niri setup, with or without
DMS.
"""

from __future__ import annotations

from dataclasses import dataclass

OK, PROBLEM, INFO = "ok", "problem", "info"

# Background-layer namespaces we can name for the user (seen in practice or in niri's docs).
KNOWN_SURFACES = {
    "wallpaper": "swaybg",
    "quickshell": "a Quickshell shell's wallpaper (DMS, Noctalia, …)",
    "dms:blurwallpaper": "DMS's blurred overview wallpaper",
}


@dataclass(frozen=True)
class Check:
    status: str  # OK, PROBLEM or INFO
    text: str


def niri_config(layer_rule: bool, transparent_background: bool) -> Check:
    if layer_rule and transparent_background:
        return Check(OK, "niri: video stays still behind workspaces (layer-rule + transparent background)")
    if layer_rule:
        return Check(PROBLEM, "niri: workspace background is opaque, so the video only shows in the "
                              "overview → add the 2nd line (c copies both)")
    return Check(INFO, "niri (optional): for a video that stays still while workspaces scroll, add "
                       "these lines to your niri config (c to copy)")


def other_wallpapers(dms_builtin: bool | None, other_surfaces: list[str] | None) -> Check:
    if dms_builtin:
        return Check(PROBLEM, "DMS: built-in wallpaper is on → Settings → Wallpaper → "
                              "Disable Built-in Wallpapers")
    if other_surfaces is None:
        return Check(INFO, "can't ask niri what's drawn on the background layer")
    if other_surfaces:
        names = ", ".join(f"{KNOWN_SURFACES[n]} ({n})" if n in KNOWN_SURFACES else n
                          for n in other_surfaces)
        return Check(PROBLEM, f"something else draws a background and can cover the video: {names}. "
                              "Stop that wallpaper program")
    return Check(OK, "no other wallpaper program is drawing")


def session(problem: str | None) -> Check:
    if problem:
        return Check(PROBLEM, f"session: {problem}")
    return Check(OK, "session: systemd and niri session ready for the background service")
