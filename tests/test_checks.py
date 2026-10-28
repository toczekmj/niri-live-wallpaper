import unittest

from niri_live_wallpaper import checks
from niri_live_wallpaper.desktop import parse_version


class SetupChecksTest(unittest.TestCase):
    def test_niri(self):
        self.assertEqual(checks.niri_config(True, True).status, checks.OK)
        # The trap on a non-DMS setup: the rule alone hides the video behind opaque workspaces.
        self.assertEqual(checks.niri_config(True, False).status, checks.PROBLEM)
        # Without the rule the video works (it scrolls with workspaces), so it's only a suggestion.
        self.assertEqual(checks.niri_config(False, False).status, checks.INFO)
        self.assertEqual(checks.niri_config(False, True).status, checks.INFO)

    def test_other_wallpapers(self):
        self.assertIn("DMS", checks.other_wallpapers(True, []).text)
        self.assertEqual(checks.other_wallpapers(False, []).status, checks.OK)
        self.assertEqual(checks.other_wallpapers(None, []).status, checks.OK)  # no DMS installed
        swaybg = checks.other_wallpapers(None, ["wallpaper"])
        self.assertEqual(swaybg.status, checks.PROBLEM)
        self.assertIn("swaybg (wallpaper)", swaybg.text)
        self.assertIn("some-tool", checks.other_wallpapers(None, ["some-tool"]).text)
        self.assertEqual(checks.other_wallpapers(None, None).status, checks.INFO)

    def test_session(self):
        self.assertEqual(checks.session(None).status, checks.OK)
        self.assertEqual(checks.session("no systemd").status, checks.PROBLEM)


class VersionTest(unittest.TestCase):
    def test_parse(self):
        self.assertEqual(parse_version("0.74.5 (c0a193e0)"), (0, 74, 5))
        self.assertEqual(parse_version("0.29\n"), (0, 29))
        self.assertIsNone(parse_version("fzf dev"))
        version = parse_version("0.29.0")
        self.assertIsNotNone(version)
        self.assertLess(version or (), (0, 33))


if __name__ == "__main__":
    unittest.main()
