import unittest
from pathlib import Path

from niri_live_wallpaper.media import VideoInfo, is_image, parse_rate
from niri_live_wallpaper.variants import ScreenJob, Variant, plan, scaled_size

from .helpers import planned

UHD_60 = VideoInfo(width=3840, height=2160, fps=59.94, duration=60, has_audio=True)
HD_30 = VideoInfo(width=1280, height=720, fps=30, duration=3, has_audio=False)


def job(width, height, fps=None, scale=100):
    return ScreenJob("OUT", width, height, fps, scale)


class PlanTest(unittest.TestCase):
    def test_small_video_without_fps_cap_plays_original(self):
        self.assertIsNone(plan(HD_30, job(1920, 1200)))

    def test_unreadable_video_plays_original(self):
        self.assertIsNone(plan(None, job(1920, 1200)))

    def test_bigger_video_is_scaled_to_cover_and_cropped(self):
        self.assertEqual(
            plan(UHD_60, job(3440, 1440)),
            Variant(
                "3440x1440@src.mp4",
                "scale=3440:1440:force_original_aspect_ratio=increase,crop=3440:1440",
            ),
        )

    def test_fps_cap_and_downscale(self):
        variant = planned(UHD_60, job(1920, 1200, fps=30))
        self.assertEqual(variant.filename, "1920x1200@30.mp4")
        self.assertTrue(variant.video_filter.startswith("fps=30,scale=1920:1200"))

    def test_fps_cap_only_keeps_resolution(self):
        self.assertEqual(
            plan(HD_30, job(1920, 1200, fps=24)), Variant("1280x720@24.mp4", "fps=24")
        )

    def test_fps_cap_not_below_source_does_nothing(self):
        self.assertIsNone(plan(HD_30, job(1920, 1200, fps=30)))

    def test_odd_source_size_is_cropped_to_even(self):
        odd = VideoInfo(width=1281, height=721, fps=60, duration=1, has_audio=False)
        self.assertEqual(
            plan(odd, job(1920, 1200, fps=30)),
            Variant("1280x720@30.mp4", "fps=30,crop=trunc(iw/2)*2:trunc(ih/2)*2"),
        )

    def test_resolution_percentage(self):
        self.assertEqual(
            planned(UHD_60, job(1920, 1200, scale=50)).filename, "960x600@src.mp4"
        )

    def test_scaled_size_is_even(self):
        self.assertEqual(scaled_size(3440, 1440, 75), (2580, 1080))
        self.assertEqual(scaled_size(1920, 1200, 33), (634, 396))


class ImageTest(unittest.TestCase):
    def test_images_are_never_re_encoded(self):
        photo = VideoInfo(
            width=7680, height=4320, fps=0, duration=0, has_audio=False, is_image=True
        )
        self.assertIsNone(plan(photo, job(1920, 1200, fps=24)))

    def test_is_image_by_extension(self):
        self.assertTrue(is_image(Path("a/Sunset.PNG")))
        self.assertTrue(is_image(Path("b.webp")))
        self.assertFalse(is_image(Path("loop.gif")))  # animated: plays as a video
        self.assertFalse(is_image(Path("clip.mp4")))


class ParseRateTest(unittest.TestCase):
    def test_rates(self):
        self.assertAlmostEqual(parse_rate("30000/1001"), 29.97, places=2)
        self.assertEqual(parse_rate("25"), 25)
        self.assertEqual(parse_rate("0/0"), 0.0)
        self.assertEqual(parse_rate(""), 0.0)


if __name__ == "__main__":
    unittest.main()
