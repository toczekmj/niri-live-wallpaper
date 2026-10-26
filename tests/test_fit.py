import tempfile
import unittest
from pathlib import Path
from unittest import mock

from niri_live_wallpaper import config, fit, paths, variants
from niri_live_wallpaper.media import VideoInfo
from niri_live_wallpaper.service import MPV_OPTIONS, play_for
from niri_live_wallpaper.tui.formatting import describe_video
from niri_live_wallpaper.variants import ScreenJob, plan

ULTRAWIDE = VideoInfo(width=3440, height=1440, fps=0, duration=0, has_audio=False, is_image=True)
SQUARE_ISH = VideoInfo(width=1920, height=1200, fps=0, duration=0, has_audio=False, is_image=True)


def job(fit_mode="fill", align="center", width=1920, height=1200):
    return ScreenJob("OUT", width, height, None, 100, fit_mode, align)


class AspectTest(unittest.TestCase):
    def test_same_shape_is_not_different(self):
        self.assertFalse(fit.aspect_differs(3840, 2400, 1920, 1200))
        self.assertFalse(fit.aspect_differs(1921, 1200, 1920, 1200))  # within tolerance

    def test_widescreen_on_16_10_differs(self):
        self.assertTrue(fit.aspect_differs(3440, 1440, 1920, 1200))

    def test_unknown_size_is_not_different(self):
        self.assertFalse(fit.aspect_differs(0, 0, 1920, 1200))


class MpvOptionsTest(unittest.TestCase):
    def test_every_mode_has_options(self):
        for mode in fit.MODES:
            self.assertTrue(fit.mpv_options(mode.key))

    def test_fill_crop_focus(self):
        self.assertEqual(fit.mpv_options("fill", "left"), "panscan=1.0 video-align-x=-1 video-align-y=0")
        self.assertEqual(fit.mpv_options("fill", "bottom"), "panscan=1.0 video-align-x=0 video-align-y=1")

    def test_fit_stretch_center(self):
        self.assertEqual(fit.mpv_options("fit"), "panscan=0")
        self.assertEqual(fit.mpv_options("stretch"), "keepaspect=no")
        self.assertEqual(fit.mpv_options("center"), "video-unscaled=yes")


class BlurVariantTest(unittest.TestCase):
    def test_blur_makes_a_copy_per_screen_size(self):
        variant = plan(ULTRAWIDE, job("blur"))
        self.assertEqual(variant.filename, "1920x1200@src-blur.jpg")
        self.assertEqual(variant.video_filter, fit.blur_filter(1920, 1200))

    def test_no_copy_when_the_shapes_match(self):
        self.assertIsNone(plan(SQUARE_ISH, job("blur")))

    def test_other_fits_need_no_copy(self):
        for mode in ("fill", "fit", "stretch", "center"):
            self.assertIsNone(plan(ULTRAWIDE, job(mode)))


ULTRAWIDE_VIDEO = VideoInfo(width=3440, height=1440, fps=60, duration=10, has_audio=False)
VIDEO_16_9 = VideoInfo(width=3840, height=2160, fps=30, duration=10, has_audio=False)


class VideoFitPlanTest(unittest.TestCase):
    def test_fill_is_the_old_behaviour(self):
        variant = plan(VIDEO_16_9, job("fill"))
        self.assertEqual(variant.filename, "1920x1200@src.mp4")
        self.assertEqual(variant.video_filter,
                         "scale=1920:1200:force_original_aspect_ratio=increase,crop=1920:1200")

    def test_fill_crops_from_the_chosen_edge(self):
        variant = plan(VIDEO_16_9, job("fill", "left"))
        self.assertEqual(variant.filename, "1920x1200@src-left.mp4")
        self.assertTrue(variant.video_filter.endswith("crop=1920:1200:(iw-ow)*0:(ih-oh)*0.5"))
        self.assertTrue(plan(VIDEO_16_9, job("fill", "bottom")).video_filter.endswith("(iw-ow)*0.5:(ih-oh)*1"))

    def test_fit_shrinks_inside_the_screen(self):
        variant = plan(VIDEO_16_9, job("fit"))
        self.assertEqual((variant.filename, variant.video_filter), ("1920x1080@src-fit.mp4", "scale=1920:1080"))

    def test_fit_without_shrinking_needs_no_copy(self):
        self.assertIsNone(plan(VIDEO_16_9, job("fit", width=3840, height=2400)))

    def test_stretch_scales_to_the_screen_shape(self):
        variant = plan(VIDEO_16_9, job("stretch"))
        self.assertEqual((variant.filename, variant.video_filter), ("1920x1200@src-stretch.mp4", "scale=1920:1200"))

    def test_blur_is_always_a_copy_at_screen_size(self):
        variant = plan(VIDEO_16_9, job("blur", width=3840, height=2400))
        self.assertEqual(variant.filename, "3840x2400@src-blur.mp4")
        self.assertTrue(variant.graph)
        self.assertEqual(variant.video_filter, fit.blur_filter(3840, 2400))

    def test_blur_with_fps_cap_prefixes_the_graph(self):
        variant = plan(ULTRAWIDE_VIDEO, ScreenJob("OUT", 1920, 1200, 30, 50, "blur", "center"))
        self.assertEqual(variant.filename, "960x600@30-blur.mp4")
        self.assertTrue(variant.video_filter.startswith("fps=30,split["))

    def test_center_only_caps_the_frame_rate(self):
        self.assertIsNone(plan(VIDEO_16_9, job("center")))
        variant = plan(VIDEO_16_9, ScreenJob("OUT", 1920, 1200, 24, 50, "center", "center"))
        self.assertEqual((variant.filename, variant.video_filter), ("3840x2160@24.mp4", "fps=24"))

    def test_same_shape_makes_every_fit_the_plain_fill(self):
        for mode in ("fit", "blur", "stretch"):
            self.assertEqual(plan(VIDEO_16_9, job(mode, width=1920, height=1080)),
                             plan(VIDEO_16_9, job("fill", width=1920, height=1080)))

    def test_different_fits_never_share_a_file(self):
        names = {plan(VIDEO_16_9, job(m, a)).filename
                 for m, a in (("fill", "center"), ("fill", "left"), ("fit", "center"),
                              ("blur", "center"), ("stretch", "center"))}
        self.assertEqual(len(names), 5)


class FitSettingsTest(unittest.TestCase):
    CFG = {"videos": {
        "a.png": {"fit": "fill", "align": "right"},
        "b.png": {"fit": "blur", "screens": {"eDP-1": {"fit": "fill"}, "DP-1": {"fit": "fit"}}},
        "c.png": {"align": "left", "screens": {"eDP-1": {"fit": "fill"}}},
        "bad.png": {"fit": "zoom", "align": "up"},
    }}

    def test_defaults(self):
        self.assertEqual(config.screen_fit({}, "a.png", "eDP-1"), ("fill", "center"))

    def test_all_screens_values(self):
        self.assertEqual(config.screen_fit(self.CFG, "a.png", "eDP-1"), ("fill", "right"))
        self.assertEqual(config.screen_fit(self.CFG, "b.png", "HDMI-A-1"), ("blur", "center"))

    def test_per_screen_override(self):
        self.assertEqual(config.screen_fit(self.CFG, "b.png", "DP-1"), ("fit", "center"))

    def test_override_to_fill_undoes_the_all_screens_fit_and_its_crop_focus(self):
        self.assertEqual(config.screen_fit(self.CFG, "c.png", "eDP-1"), ("fill", "center"))
        self.assertEqual(config.screen_fit(self.CFG, "c.png", "other"), ("fill", "left"))

    def test_hand_edited_nonsense_falls_back(self):
        self.assertEqual(config.screen_fit(self.CFG, "bad.png", "eDP-1"), ("fill", "center"))


class SetFitTest(unittest.TestCase):
    def test_defaults_are_left_out(self):
        entry = {"fit": "blur", "align": "left", "fps": 30}
        config.set_fit(entry, "fill", "center")
        self.assertEqual(entry, {"fps": 30})

    def test_only_fill_keeps_a_crop_focus(self):
        entry = {}
        config.set_fit(entry, "fit", "left")
        self.assertEqual(entry, {"fit": "fit"})
        config.set_fit(entry, "fill", "left")
        self.assertEqual(entry, {"align": "left"})

    def test_override_always_names_its_fit(self):
        override = {}
        config.set_fit(override, "fill", "center", keep_default=True)
        self.assertEqual(override, {"fit": "fill"})


class PlayForTest(unittest.TestCase):
    def setUp(self):
        self._saved = paths.VIDEO_DIR
        paths.VIDEO_DIR = Path("/nonexistent/videos")  # nothing exists: originals are played

    def tearDown(self):
        paths.VIDEO_DIR = self._saved

    def test_video_gets_the_video_options_and_its_fit(self):
        self.assertEqual(play_for("clip.mp4", job()).options, MPV_OPTIONS + " panscan=1.0 video-align-x=0 video-align-y=0")
        self.assertEqual(play_for("clip.mp4", job("fit")).options, MPV_OPTIONS + " panscan=0")

    def test_image_options_follow_the_fit(self):
        self.assertIn("panscan=0", play_for("a.png", job("fit")).options)
        self.assertIn("video-align-x=1", play_for("a.png", job("fill", "right")).options)
        self.assertIn("image-display-duration=inf", play_for("a.png", job("fill")).options)

    def test_a_cropped_copy_is_shown_filling_the_screen_with_the_default_focus(self):
        with tempfile.TemporaryDirectory() as d:
            dummy = Path(d) / "x.png"
            with mock.patch.object(variants, "path_to_play", return_value=dummy):
                play = play_for("a.png", job("fill", "left"))
        self.assertIn("panscan=1.0 video-align-x=0", play.options)

    def test_blur_without_its_copy_falls_back_to_black_bars(self):
        self.assertIn("panscan=0", play_for("a.png", job("blur")).options)

    def test_changing_the_fit_changes_what_is_played(self):
        self.assertNotEqual(play_for("a.png", job("fill")), play_for("a.png", job("fit")))


class DescribeTest(unittest.TestCase):
    def test_default_fit_is_not_mentioned(self):
        self.assertEqual(describe_video(ULTRAWIDE, {}), "3440×1440 · image")

    def test_fit_and_crop_focus_are_shown(self):
        self.assertEqual(describe_video(ULTRAWIDE, {"fit": "blur"}), "3440×1440 · image · blurred bars")
        self.assertEqual(describe_video(ULTRAWIDE, {"align": "left"}), "3440×1440 · image · crop to left")


if __name__ == "__main__":
    unittest.main()
