"""Unit tests for nuget_validation_report.py. Run with: python -m unittest discover -s scripts -v"""

import contextlib
import io
import json
import os
import runpy
import sys
import tempfile
import unittest
from unittest import mock

import nuget_validation_report as nv

VALID = {"IsValid": True, "Packages": {"/a/artifacts/A.1.0.0.nupkg": {"Errors": [], "IsValid": True}}}


def _error(code, message, file_name=None, help_text=None):
    return {"ErrorCode": code, "Message": message, "HelpText": help_text, "FileName": file_name}


class ReportTests(unittest.TestCase):
    def test_valid_packages(self):
        self.assertEqual(nv.report(VALID), (["OK    A.1.0.0.nupkg"], True))

    def test_errors_grouped_by_rule_with_examples(self):
        errors = [_error(112, f"path {i}", "lib/net10.0/A.dll") for i in range(5)] + [_error(32, "no icon")]
        result = {"IsValid": False, "Packages": {"C:\\out\\A.1.0.0.nupkg": {"Errors": errors, "IsValid": False}}}
        lines, valid = nv.report(result)
        self.assertFalse(valid)
        self.assertEqual(lines[0], "FAIL  A.1.0.0.nupkg (6 error(s))")
        self.assertEqual(lines[1], "::error::A.1.0.0.nupkg: rule 112, 5x: path 0 [lib/net10.0/A.dll]; "
                                   "path 1 [lib/net10.0/A.dll]; path 2 [lib/net10.0/A.dll] (and 2 more)")
        self.assertEqual(lines[2], "::error::A.1.0.0.nupkg: rule 32, 1x: no icon")

    def test_help_text_shown(self):
        result = {"IsValid": False, "Packages": {"A.nupkg": {"Errors": [_error(7, "bad", help_text="see docs")]}}}
        self.assertIn("rule 7, 1x: bad (see docs)", nv.report(result)[0][1])

    def test_invalid_flag_without_errors_is_invalid(self):
        result = {"IsValid": False, "Packages": {"A.nupkg": {"Errors": [], "IsValid": True}}}
        self.assertFalse(nv.report(result)[1])


class MainTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.addCleanup(self._td.cleanup)

    def run_main(self, text):
        path = os.path.join(self._td.name, "validation.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = nv.main(["nuget_validation_report.py", path])
        return code, out.getvalue()

    def test_valid_output_with_a_byte_order_mark(self):
        self.assertEqual(self.run_main("\ufeff" + json.dumps(VALID)), (0, "OK    A.1.0.0.nupkg\n"))

    def test_invalid_output_exits_one(self):
        result = {"IsValid": False, "Packages": {"A.nupkg": {"Errors": [_error(32, "no icon")]}}}
        self.assertEqual(self.run_main(json.dumps(result))[0], 1)

    def test_text_that_is_not_json_exits_one(self):
        code, out = self.run_main("Unhandled exception")
        self.assertEqual(code, 1)
        self.assertIn("did not write JSON", out)
        self.assertIn("Unhandled exception", out)

    def test_no_package_exits_one(self):
        code, out = self.run_main(json.dumps({"IsValid": True, "Packages": {}}))
        self.assertEqual(code, 1)
        self.assertIn("reported no package", out)

    def test_wrong_arguments_print_usage(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(nv.main(["nuget_validation_report.py"]), 2)

    def test_runs_as_a_program(self):
        path = os.path.join(self._td.name, "validation.json")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(VALID))
        with mock.patch.object(sys, "argv", ["nuget_validation_report.py", path]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            runpy.run_path(nv.__file__, run_name="__main__")
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
