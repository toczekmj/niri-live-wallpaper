"""Small helpers shared by the tests."""

from __future__ import annotations

from niri_live_wallpaper.media import VideoInfo
from niri_live_wallpaper.variants import ScreenJob, Variant, plan


def planned(info: VideoInfo | None, job: ScreenJob) -> Variant:
    """plan(), for tests that expect a copy to be needed (and then look at it)."""
    variant = plan(info, job)
    assert variant is not None, "expected a copy to be planned, got None"
    return variant
