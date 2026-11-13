"""Unit tests for coverage_table.py. Run with: python -m unittest discover -s scripts -v"""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from unittest import mock

import coverage_table as ct

REPORT = """<?xml version="1.0" encoding="utf-8"?>
<coverage line-rate="0.5" branch-rate="0.25">
  <packages>
    <package name="Demo" line-rate="0.5" branch-rate="0.25" />
    <package name="Demo.TUnit" line-rate="1" />
  </packages>
</coverage>
"""
EMPTY = '<?xml version="1.0"?><coverage line-rate="1" branch-rate="1"><packages /></coverage>'


class TableTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)

    def report(self, suite, framework, text):
        folder = os.path.join(self._td.name, "tests", suite, "bin", "Release", framework, "TestResults")
        os.makedirs(folder)
        path = os.path.join(folder, "coverage.cobertura.xml")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        return path

    def test_describe_a_ci_path(self):
        path = "tests/Demo.Tests/bin/Release/net11.0/TestResults/coverage.cobertura.xml"
        self.assertEqual(ct.describe(path), ("Demo.Tests", "net11.0"))

    def test_describe_an_unknown_layout(self):
        self.assertEqual(ct.describe("coverage.cobertura.xml"), ("?", "?"))
        self.assertEqual(ct.describe("tests/coverage.cobertura.xml"), ("?", "?"))
        self.assertEqual(ct.describe("out/bin/coverage.cobertura.xml"), ("?", "?"))

    def test_one_row_per_assembly(self):
        text = ct.table([self.report("Demo.Tests", "net10.0", REPORT)])
        self.assertIn("| Demo.Tests | net10.0 | Demo | 50.00% | 25.00% |", text)
        self.assertIn("| Demo.Tests | net10.0 | Demo.TUnit | 100.00% | n/a |", text)

    def test_report_without_measured_code(self):
        text = ct.table([self.report("Demo.Tests", "net11.0", EMPTY)])
        self.assertIn("| Demo.Tests | net11.0 | (no measured code) | n/a | n/a |", text)

    def test_main_appends_to_the_job_summary(self):
        path = self.report("Demo.Tests", "net10.0", REPORT)
        summary = os.path.join(self._td.name, "summary.md")
        out = io.StringIO()
        with mock.patch.dict(os.environ, {"GITHUB_STEP_SUMMARY": summary}), contextlib.redirect_stdout(out):
            self.assertEqual(ct.main(["coverage_table.py", path]), 0)
        with open(summary, encoding="utf-8") as handle:
            written = handle.read()
        self.assertTrue(written.startswith("### Coverage per test run\n\n| Suite |"))
        self.assertIn("| Demo.Tests | net10.0 | Demo |", out.getvalue())

    def test_main_without_a_job_summary_only_prints(self):
        path = self.report("Demo.Tests", "net10.0", REPORT)
        env = {key: value for key, value in os.environ.items() if key != "GITHUB_STEP_SUMMARY"}
        out = io.StringIO()
        with mock.patch.dict(os.environ, env, clear=True), contextlib.redirect_stdout(out):
            self.assertEqual(ct.main(["coverage_table.py", path]), 0)
        self.assertIn("| Suite |", out.getvalue())

    def test_main_without_reports_prints_usage(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ct.main(["coverage_table.py"]), 2)

    def test_runs_as_a_program(self):
        path = self.report("Demo.Tests", "net10.0", REPORT)
        env = {key: value for key, value in os.environ.items() if key != "GITHUB_STEP_SUMMARY"}
        with mock.patch.object(sys, "argv", ["coverage_table.py", path]), mock.patch.dict(os.environ, env, clear=True), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            runpy.run_path(ct.__file__, run_name="__main__")
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
