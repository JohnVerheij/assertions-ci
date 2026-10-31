"""Unit tests for release_notes.py. Run with: python -m unittest discover -s scripts -v"""

from __future__ import annotations

import io
import os
import tempfile
import unittest
from contextlib import redirect_stdout

import release_notes as notes

CHANGELOG = """# Changelog

## [Unreleased]

## [0.13.0] - 2026-11-02: wait for log entries

### Added

- `WaitForLogAsync`.

## [0.12.0] - 2026-07-11: gate a run on its log output

### Added

- `WillLog()`.

[unreleased]: https://example.test/compare/v0.13.0...HEAD
[0.13.0]: https://example.test/releases/tag/v0.13.0
[0.12.0]: https://example.test/releases/tag/v0.12.0
"""


class ExtractTests(unittest.TestCase):
    def test_copies_the_section_up_to_the_next_header(self):
        self.assertEqual(
            notes.extract(CHANGELOG, "0.13.0"),
            "## [0.13.0] - 2026-11-02: wait for log entries\n\n### Added\n\n- `WaitForLogAsync`.\n",
        )

    def test_last_section_stops_at_the_link_definitions(self):
        self.assertEqual(
            notes.extract(CHANGELOG, "0.12.0"),
            "## [0.12.0] - 2026-07-11: gate a run on its log output\n\n### Added\n\n- `WillLog()`.\n",
        )

    def test_header_must_match_the_whole_version(self):
        changelog = "## [0.13.0-beta.1] - 2026-10-01\n\n- Beta.\n"
        with self.assertRaisesRegex(ValueError, "no section"):
            notes.extract(changelog, "0.13.0")

    def test_missing_section_fails(self):
        with self.assertRaisesRegex(ValueError, "no section for version 9.9.9"):
            notes.extract(CHANGELOG, "9.9.9")

    def test_section_with_only_its_header_fails(self):
        changelog = "## [0.14.0] - 2026-12-01\n\n\n## [0.13.0] - 2026-11-02\n\n- Something.\n"
        with self.assertRaisesRegex(ValueError, "empty"):
            notes.extract(changelog, "0.14.0")

    def test_windows_line_endings_are_handled(self):
        self.assertEqual(notes.extract("## [1.0.0] - x\r\n\r\n- One.\r\n", "1.0.0"), "## [1.0.0] - x\n\n- One.\n")


class MainTests(unittest.TestCase):
    def setUp(self):
        self._dir = tempfile.TemporaryDirectory()
        self.changelog = os.path.join(self._dir.name, "CHANGELOG.md")
        self.output = os.path.join(self._dir.name, "RELEASE_NOTES.md")
        with open(self.changelog, "w", encoding="utf-8") as handle:
            handle.write(CHANGELOG)

    def tearDown(self):
        self._dir.cleanup()

    def run_main(self, *args: str) -> tuple[int, str]:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            code = notes.main(["release_notes.py", *args])
        return code, stdout.getvalue()

    def test_writes_the_notes_file(self):
        code, _ = self.run_main("0.13.0", self.changelog, self.output)
        self.assertEqual(code, 0)
        with open(self.output, encoding="utf-8") as handle:
            self.assertTrue(handle.read().startswith("## [0.13.0]"))

    def test_missing_section_returns_1_and_writes_nothing(self):
        code, stdout = self.run_main("9.9.9", self.changelog, self.output)
        self.assertEqual(code, 1)
        self.assertTrue(stdout.startswith("::error::"))
        self.assertFalse(os.path.exists(self.output))

    def test_missing_changelog_returns_1(self):
        code, _ = self.run_main("0.13.0", os.path.join(self._dir.name, "absent.md"), self.output)
        self.assertEqual(code, 1)

    def test_wrong_argument_count_returns_1(self):
        code, stdout = self.run_main("0.13.0")
        self.assertEqual(code, 1)
        self.assertIn("usage", stdout)


if __name__ == "__main__":
    unittest.main()
