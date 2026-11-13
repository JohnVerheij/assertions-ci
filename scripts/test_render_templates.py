"""Unit tests for render_templates.py. Run with: python -m unittest discover -s scripts -v"""

import contextlib
import io
import os
import re
import runpy
import sys
import tempfile
import unittest
from unittest import mock

import family_sync
import render_templates as rt


class RenderTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.folder = self._td.name
        self.addCleanup(self._td.cleanup)

    def test_only_workflow_templates(self):
        templates = rt.workflow_templates()
        self.assertIn(".github/workflows/family-lint.yml", templates)
        self.assertTrue(all(rel.startswith(".github/workflows/") for rel in templates))
        self.assertNotIn(".github/renovate.json", templates)

    def test_every_workflow_rendered_without_placeholders(self):
        written = rt.render_workflows(self.folder)
        self.assertEqual(sorted(os.path.basename(path) for path in written),
                         sorted(rt.PREFIX + os.path.basename(rel) for rel in rt.workflow_templates()))
        for path in written:
            with open(path, encoding="utf-8") as handle:
                text = handle.read()
            self.assertIsNone(re.search(r"(?<!\$)\{\{", text), path)

    def test_callers_use_the_demo_pin_and_package(self):
        rt.render_workflows(self.folder)
        with open(os.path.join(self.folder, rt.PREFIX + "docs.yml"), encoding="utf-8") as handle:
            text = handle.read()
        self.assertIn("@" + rt.DEMO_PIN, text)
        self.assertIn(rt.DEMO_PACKAGE, text)

    def test_demo_pin_has_the_pin_form_family_sync_reads(self):
        ci = "uses: JohnVerheij/assertions-ci/.github/workflows/package-ci.yml@" + rt.DEMO_PIN
        self.assertEqual(family_sync.ACI_PIN_RE.search(ci).group(1), rt.DEMO_PIN)

    def test_main_prints_the_rendered_files(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(rt.main(["render_templates.py", self.folder]), 0)
        self.assertEqual(out.getvalue().count("rendered "), len(rt.workflow_templates()))

    def test_main_needs_an_existing_folder(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rt.main(["render_templates.py"]), 2)
            self.assertEqual(rt.main(["render_templates.py", os.path.join(self.folder, "missing")]), 2)

    def test_runs_as_a_program(self):
        with mock.patch.object(sys, "argv", ["render_templates.py", self.folder]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            runpy.run_path(rt.__file__, run_name="__main__")
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
