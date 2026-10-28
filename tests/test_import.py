import unittest
from pathlib import Path

from niri_live_wallpaper.desktop import parse_menu_output, parse_selection
from niri_live_wallpaper.tui.formatting import import_summary


class ParseSelectionTest(unittest.TestCase):
    def test_one_path_per_line(self):
        self.assertEqual(parse_selection("/a/x.mp4\n/b/y z.webm\n\n"),
                         [Path("/a/x.mp4"), Path("/b/y z.webm")])

    def test_nothing_selected(self):
        self.assertEqual(parse_selection(""), [])


class MenuOutputTest(unittest.TestCase):
    def test_enter_with_expect_has_an_empty_first_line(self):
        self.assertEqual(parse_menu_output("\nChill\t●  Chill   · 2 files\n", True), ("", ["Chill"]))

    def test_an_expected_key_comes_first(self):
        self.assertEqual(parse_menu_output("ctrl-r\nChill\t●  Chill\n", True), ("ctrl-r", ["Chill"]))

    def test_without_expect_every_line_is_a_pick(self):
        self.assertEqual(parse_menu_output("a.png\ta.png\nb.mp4\tb.mp4\n", False), ("", ["a.png", "b.mp4"]))

    def test_names_with_spaces_and_accents_survive(self):
        self.assertEqual(parse_menu_output("\nMój zestaw 2\t●  Mój zestaw 2\n", True), ("", ["Mój zestaw 2"]))

    def test_nothing_picked(self):
        self.assertEqual(parse_menu_output("", True), ("", []))


class ImportSummaryTest(unittest.TestCase):
    def test_single_import_keeps_the_original_message(self):
        self.assertEqual(import_summary(["a.mp4"], [], []),
                         "Imported a.mp4. Press space to set it as your wallpaper")

    def test_several(self):
        self.assertEqual(import_summary(["a", "b", "c"], ["d"], ["e (Permission denied)"]),
                         "Imported 3 wallpapers. Press space to set one as your wallpaper "
                         "(1 already imported; failed: e (Permission denied))")

    def test_already_imported(self):
        self.assertEqual(import_summary([], ["a.mp4"], []), "a.mp4 is already imported")
        self.assertEqual(import_summary([], ["a", "b"], []), "All 2 wallpapers are already imported")

    def test_only_failures(self):
        self.assertEqual(import_summary([], [], ["a (No space left on device)"]),
                         "Nothing imported (failed: a (No space left on device))")


if __name__ == "__main__":
    unittest.main()
