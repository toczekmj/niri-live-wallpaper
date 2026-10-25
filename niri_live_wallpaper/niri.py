"""Talking to the niri compositor: which screens exist, what is drawn on the background layer,
and whether its config is set up for a stationary wallpaper."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import paths, proc

# A stationary wallpaper needs both lines (niri wiki, "Overview"): the layer-rule puts mpvpaper's
# surfaces in the backdrop, behind the workspaces, and the transparent workspace background lets
# the backdrop show through. niri's default background is opaque grey, so with only the layer-rule
# the video is hidden behind every workspace and visible only in the overview. DMS already sets
# the transparent background; other setups usually don't. Each kept on one line to be easy to copy.
LAYER_RULE = 'layer-rule { match namespace="^mpvpaper$"; place-within-backdrop true; }'
TRANSPARENT_BACKGROUND = 'layout { background-color "transparent"; }'
STATIONARY_SNIPPET = f"{LAYER_RULE}\n{TRANSPARENT_BACKGROUND}\n"

OUR_NAMESPACE = "mpvpaper"


@dataclass(frozen=True)
class Output:
    name: str     # connector name, e.g. "HDMI-A-1"; also the key for per-screen settings
    width: int    # physical pixels in the current mode, rotation applied
    height: int


# --------------------------------------------------------------------------- live state (niri msg)

def outputs() -> list[Output]:
    """Enabled outputs from `niri msg -j outputs`, or [] if niri can't be asked."""
    data = _msg("outputs")
    try:
        return parse_outputs(data) if isinstance(data, dict) else []
    except (KeyError, TypeError, IndexError):
        return []


def parse_outputs(data: dict[str, Any]) -> list[Output]:
    found = []
    for name, output in sorted(data.items()):
        if output.get("current_mode") is None:
            continue  # disabled output
        mode = output["modes"][output["current_mode"]]
        width, height = mode["width"], mode["height"]
        transform = (output.get("logical") or {}).get("transform", "")
        if "90" in transform or "270" in transform:
            width, height = height, width
        found.append(Output(name, width, height))
    return found


def other_background_surfaces() -> list[str] | None:
    """Namespaces of background-layer surfaces that aren't ours, e.g. another wallpaper program
    that may be drawn over the video. None if niri can't be asked."""
    data = _msg("layers")
    if not isinstance(data, list):
        return None
    return parse_other_background_surfaces(data)


def parse_other_background_surfaces(layers: list[dict[str, Any]]) -> list[str]:
    names = {layer.get("namespace", "?") for layer in layers
             if layer.get("layer") == "Background" and layer.get("namespace") != OUR_NAMESPACE}
    return sorted(names)


def _msg(request: str) -> Any:
    result = proc.run(["niri", "msg", "-j", request], timeout=5)
    if not proc.succeeded(result):
        return None
    try:
        return json.loads(result.stdout)
    except ValueError:
        return None


# --------------------------------------------------------------------------- config file

def config_file() -> Path:
    """The config niri loads, in niri's own lookup order (minus the `-c` flag, which we can't see):
    $NIRI_CONFIG, then ~/.config/niri/config.kdl, then /etc/niri/config.kdl."""
    if os.environ.get("NIRI_CONFIG"):
        return Path(os.environ["NIRI_CONFIG"]).expanduser()
    user = paths.NIRI_CONFIG_DIR / "config.kdl"
    system = Path("/etc/niri/config.kdl")
    return system if not user.exists() and system.exists() else user


def config_texts(start: Path | None = None) -> list[str]:
    """Text of the config file and every file it includes, with // comments removed.

    Only these files matter, because niri reads nothing else; a .kdl file that isn't included has
    no effect.
    """
    texts: list[str] = []
    todo, seen = [start or config_file()], set()
    while todo:
        file = todo.pop().resolve()
        if file in seen:
            continue  # include loops are possible
        seen.add(file)
        try:
            text = re.sub(r"//.*", "", file.read_text())
        except OSError:
            continue
        texts.append(text)
        todo += [file.parent / Path(inc).expanduser() for inc in re.findall(r'include\s+"([^"]+)"', text)]
    return texts


def layer_rule_present(start: Path | None = None) -> bool:
    """True if niri's config has a layer-rule putting mpvpaper in the backdrop."""
    return any(_has_backdrop_rule(text) for text in config_texts(start))


def background_transparent(start: Path | None = None) -> bool:
    """True if every workspace background-color in the config is (at least partly) transparent.

    Without any background-color, niri uses its opaque grey default. Per-output overrides count
    too: one opaque screen is enough to hide the video there, so it's reported as not transparent.
    """
    values = [v for text in config_texts(start)
              for v in re.findall(r'(?<![\w-])background-color\s+"([^"]+)"', text)]
    return bool(values) and all(is_see_through(v) for v in values)


def is_see_through(color: str) -> bool:
    """Whether a niri (CSS) colour has alpha below 1: "transparent", "#rrggbbaa", "#rgba", "rgba()"."""
    color = color.strip().lower()
    if color == "transparent":
        return True
    if re.fullmatch(r"#[0-9a-f]{8}", color):
        return int(color[7:9], 16) < 255
    if re.fullmatch(r"#[0-9a-f]{4}", color):
        return color[4] != "f"
    match = re.fullmatch(r"(?:rgba|hsla)\(([^)]*)\)", color)
    if match:
        parts = re.split(r"[\s,/]+", match.group(1).strip())
        if len(parts) == 4:
            alpha = parts[3]
            try:
                return (float(alpha[:-1]) / 100 if alpha.endswith("%") else float(alpha)) < 1
            except ValueError:
                return False
    return False


def _has_backdrop_rule(kdl_text: str) -> bool:
    for block in re.findall(r"layer-rule\s*\{[^}]*\}", kdl_text):
        if OUR_NAMESPACE in block and re.search(r"place-within-backdrop\s+true", block):
            return True
    return False
