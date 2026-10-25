import unittest
from pathlib import Path

from niri_live_wallpaper.desktop import parse_selection
from niri_live_wallpaper.tui.formatting import import_summary


class ParseSelectionTest(unittest.TestCase):
    def test_one_path_per_line(self):
        self.assertEqual(parse_selection("/a/x.mp4\n/b/y z.webm\n\n"),
                         [Path("/a/x.mp4"), Path("/b/y z.webm")])

    def test_nothing_selected(self):
        self.assertEqual(parse_selection(""), [])


class ImportSummaryTest(unittest.TestCase):
    def test_single_import_keeps_the_original_message(self):
        self.assertEqual(import_summary(["a.mp4"], [], []),
                         "Imported a.mp4. Press space to set it as your wallpaper")

    def test_several(self):
        self.assertEqual(import_summary(["a", "b", "c"], ["d"], ["e (Permission denied)"]),
                         "Imported 3 videos. Press space to set one as your wallpaper "
                         "(1 already imported; failed: e (Permission denied))")

    def test_already_imported(self):
        self.assertEqual(import_summary([], ["a.mp4"], []), "a.mp4 is already imported")
        self.assertEqual(import_summary([], ["a", "b"], []), "All 2 videos are already imported")

    def test_only_failures(self):
        self.assertEqual(import_summary([], [], ["a (No space left on device)"]),
                         "Nothing imported (failed: a (No space left on device))")


if __name__ == "__main__":
    unittest.main()
