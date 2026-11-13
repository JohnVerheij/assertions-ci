"""Unit tests for readme_samples.py. Run with: python -m unittest discover -s scripts -v"""

import contextlib
import io
import os
import runpy
import sys
import tempfile
import unittest
from unittest import mock

import readme_samples as rs

Q = '"' * 3  # the delimiter of a raw string literal


def _sample(*lines, first_line=10):
    return rs.Sample("README.md", first_line, list(lines))


def _kinds(*lines):
    usings, parts, file_scoped = rs.parts_of(_sample(*lines))
    return [text for _, text in usings], [(part.kind, part.start, part.lines) for part in parts], file_scoped


class SamplesOfTests(unittest.TestCase):
    def test_csharp_blocks_are_samples_and_others_are_not(self):
        text = "# T\n```csharp\nvar a = 1;\n```\n```cs\nvar b = 2;\n```\n```C#\nvar c = 3;\n```\n```json\n{}\n```\n"
        samples, skipped = rs.samples_of("README.md", text)
        self.assertEqual([sample.lines for sample in samples], [["var a = 1;"], ["var b = 2;"], ["var c = 3;"]])
        self.assertEqual([sample.first_line for sample in samples], [3, 6, 9])
        self.assertEqual(skipped, 0)

    def test_no_compile_blocks_are_counted_not_compiled(self):
        samples, skipped = rs.samples_of("README.md", "```csharp no-compile\nnot code\n```\n")
        self.assertEqual((samples, skipped), ([], 1))

    def test_tilde_and_indented_fences(self):
        text = "- item\n  ~~~csharp\n  var a = 1;\n  ~~~\n```\nplain\n```\n"
        samples, _ = rs.samples_of("README.md", text)
        self.assertEqual(samples[0].lines, ["  var a = 1;"])

    def test_byte_order_mark_does_not_hide_the_first_block(self):
        samples, _ = rs.samples_of("README.md", "\ufeff```csharp\nvar a = 1;\n```\n")
        self.assertEqual(samples[0].lines, ["var a = 1;"])

    def test_unterminated_fence_runs_to_the_end(self):
        samples, _ = rs.samples_of("README.md", "```csharp\nvar a = 1;\n")
        self.assertEqual(samples[0].lines, ["var a = 1;"])

    def test_source_names_the_line_directive_path(self):
        samples, _ = rs.samples_of("README.md", "```csharp\nvar a = 1;\n```\n", "/repo/README.md")
        self.assertEqual((samples[0].readme, samples[0].source), ("README.md", "/repo/README.md"))


class PartsTests(unittest.TestCase):
    def test_leading_usings_are_hoisted(self):
        usings, parts, _ = _kinds("// header", "using System.Numerics;", "global using static System.Math;",
                                  "using V = System.Numerics.Vector3;", "", "var v = new V();", "using var x = Make();")
        self.assertEqual(usings, ["using System.Numerics;", "global using static System.Math;",
                                  "using V = System.Numerics.Vector3;"])
        self.assertEqual(parts, [("statements", 5, ["var v = new V();", "using var x = Make();"])])

    def test_statements_with_continuations_and_blank_lines_stay_one_part(self):
        _, parts, _ = _kinds("await Assert.That(x)", "    .IsEqualTo(1);", "", "// next", "await Run();")
        self.assertEqual(len(parts), 1)
        self.assertEqual(parts[0][2][-1], "await Run();")

    def test_static_local_function_is_a_statement(self):
        _, parts, _ = _kinds("static int Twice(int x) => x * 2;", "await Assert.That(Twice(2)).IsEqualTo(4);")
        self.assertEqual([kind for kind, _, _ in parts], ["statements"])

    def test_member_with_attribute_and_body(self):
        _, parts, _ = _kinds("[Test]", "public async Task Works()", "{", "    await Task.Yield();", "}")
        self.assertEqual(parts, [("member", 0, ["[Test]", "public async Task Works()", "{", "    await Task.Yield();",
                                                "}"])])

    def test_attribute_before_a_type_makes_a_type(self):
        _, parts, _ = _kinds("[NotInParallel]", "public class MyTests", "{", "}")
        self.assertEqual(parts[0][0], "type")

    def test_static_readonly_field_then_statements(self):
        _, parts, _ = _kinds("static readonly Filter F = Filter.All(", "    A,", "    B);", "",
                             "await Assert.That(c).Has(F);")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("member", 0), ("statements", 4)])

    def test_expression_bodied_member_across_lines(self):
        _, parts, _ = _kinds("public static bool Near(this P p, P q)", "    => p.X == q.X;", "await Run();")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("member", 0), ("statements", 2)])

    def test_type_then_statements(self):
        _, parts, _ = _kinds("file static class Helpers", "{", "    public static int One() => 1;", "}",
                             "// Now in tests:", "await Assert.That(Helpers.One()).IsEqualTo(1);")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("type", 0), ("statements", 5)])

    def test_assembly_attribute(self):
        _, parts, _ = _kinds("[assembly: Some.Attribute]")
        self.assertEqual(parts[0][0], "assembly")

    def test_file_scoped_namespace(self):
        usings, parts, file_scoped = _kinds("using X;", "namespace My.Tests;", "public class A { }")
        self.assertEqual((usings, parts, file_scoped), (["using X;"], [], 1))

    def test_braces_in_strings_comments_and_characters_do_not_count(self):
        _, parts, _ = _kinds('var a = "{";', "var b = '{';", 'var c = @"x\\" + "}"; // {', "/* { */ var d = 1;",
                             'var e = $"{a}";', "var f = @\"\"\"{\"\"\";", "public int X => 1;")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 0), ("member", 6)])

    def test_escaped_quote_does_not_end_a_string(self):
        _, parts, _ = _kinds('var a = "say \\"{\\" twice";', "public int X => 1;")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 0), ("member", 1)])

    def test_open_block_comment_spans_lines(self):
        _, parts, _ = _kinds("/* one {", "two { */", "var a = 1;")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 2)])

    def test_unterminated_literal_ends_with_the_line_and_its_brace_does_not_count(self):
        _, parts, _ = _kinds("var c = '{", ";", "public int X => 1;")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 0), ("member", 2)])

    def test_multi_line_raw_string_keeps_its_lines(self):
        _, parts, _ = _kinds("var json = " + Q, "    [Information] hello", "    {", "    " + Q + ";",
                             "await Run(json);")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 0)])

    def test_single_line_raw_and_empty_strings(self):
        _, parts, _ = _kinds("var a = " + Q + "x { y" + Q + ";", 'var b = "";', "public int X => 1;")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 0), ("member", 2)])

    def test_multi_line_verbatim_string_keeps_its_lines(self):
        _, parts, _ = _kinds('var s = @"first ""quoted""', "[second] {", '";', "await Run(s);")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 0)])

    def test_collection_expression_and_arguments_across_lines(self):
        _, parts, _ = _kinds("int[] a =", "[", "    1, 2", "];", "list.AddRange(", "    [1, 2, 3]);")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 0)])

    def test_indexer_continues_a_call_chain(self):
        _, parts, _ = _kinds("await Assert.That(x).And", "    [0].IsNotNull();", "[Test]", "public void T() { }")
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 0), ("member", 2)])

    def test_alias_usings_and_leading_preprocessor_lines_are_hoisted(self):
        usings, parts, _ = _kinds("#nullable enable", "using Alias = global::System.String;",
                                  "using static global::System.Math;", "using Point = (int X, int Y);",
                                  "using Names = System.Collections.Generic.List<string>;", "Point p = (1, 2);")
        self.assertEqual(usings, ["#nullable enable", "using Alias = global::System.String;",
                                  "using static global::System.Math;", "using Point = (int X, int Y);",
                                  "using Names = System.Collections.Generic.List<string>;"])
        self.assertEqual([(kind, start) for kind, start, _ in parts], [("statements", 5)])

    def test_using_declaration_is_a_statement(self):
        usings, parts, _ = _kinds("using var stream = Open();", "using (var x = Make()) { }")
        self.assertEqual((usings, [kind for kind, _, _ in parts]), ([], ["statements"]))

    def test_later_preprocessor_line_stays_with_its_part(self):
        _, parts, _ = _kinds("public int A => 1;", "#endregion", "await Run();")
        self.assertEqual([(kind, start, lines) for kind, start, lines in parts],
                         [("member", 0, ["public int A => 1;", "#endregion"]), ("statements", 2, ["await Run();"])])

    def test_lambda_with_braces_keeps_its_lines(self):
        _, parts, _ = _kinds("Run(() =>", "{", "    public_value = 1;", "});")
        self.assertEqual(len(parts), 1)

    def test_comment_between_declarations_is_dropped(self):
        _, parts, _ = _kinds("public int A => 1;", "// between", "", "public int B => 2;")
        self.assertEqual([(kind, start, lines) for kind, start, lines in parts],
                         [("member", 0, ["public int A => 1;"]), ("member", 3, ["public int B => 2;"])])

    def test_leading_comments_and_blank_lines_are_skipped(self):
        _, parts, _ = _kinds("", "// intro", "var a = 1;")
        self.assertEqual(parts, [("statements", 2, ["var a = 1;"])])


class RenderTests(unittest.TestCase):
    def test_statements_compile_in_an_async_method(self):
        text = rs.render(_sample("using X;", "await Run();"), 3)
        self.assertEqual(text, "\n".join([
            "// <auto-generated/>", "// Sample 3 of README.md, written by readme_samples.py.",
            '#line 10 "README.md"', "using X;", "#line default",
            "namespace ReadmeSamples.Sample003", "{",
            "public partial class Sample : global::ReadmeSamples.Prelude", "{",
            "public async global::System.Threading.Tasks.Task RunAsync()", "{",
            '#line 11 "README.md"', "await Run();", "#line default", "}", "}", "}"]) + "\n")

    def test_members_compile_in_the_class_without_a_method(self):
        text = rs.render(_sample("public int X => 1;"), 1)
        self.assertIn("public partial class Sample", text)
        self.assertNotIn("RunAsync", text)

    def test_types_only_need_no_class(self):
        text = rs.render(_sample("[assembly: A]", "public class T { }"), 1)
        self.assertNotIn("class Sample", text)
        self.assertLess(text.index("[assembly: A]"), text.index("namespace ReadmeSamples.Sample001"))

    def test_file_scoped_namespace_is_a_file_of_its_own_with_a_prefix(self):
        text = rs.render(_sample("using X;", "namespace My; // tests", "public class T { }"), 1)
        self.assertIn('#line 11 "README.md"\nnamespace ReadmeSamples.Sample001.My; // tests\npublic class T { }\n'
                      '#line default', text)
        self.assertIn("namespace ReadmeSamples.Sample002.My;", rs.render(_sample("namespace My;", "class T { }"), 2))


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self._td = tempfile.TemporaryDirectory()
        self.root = self._td.name
        self.addCleanup(self._td.cleanup)

    def write(self, rel, text):
        path = os.path.join(self.root, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(text)

    def repository(self):
        self.write("README.md", "```csharp\nawait Run();\n```\n```csharp no-compile\nx\n```\n")
        self.write("src/Demo/README.md", "```csharp\npublic class T { }\n```\n")
        self.write("tests/Demo.TUnit.SmokeTest/Demo.TUnit.SmokeTest.csproj",
                   '<Project><ItemGroup><PackageReference Include="TUnit" Version="1.83.0" />'
                   '<PackageReference Include="Demo.TUnit" Version="$(SmokePackageVersion)" /></ItemGroup></Project>')
        self.write("tests/Demo.TUnit.SmokeTest/NuGet.config", "<configuration />")

    def test_package_references_take_the_packed_version(self):
        self.repository()
        csproj = os.path.join(self.root, "tests", "Demo.TUnit.SmokeTest", "Demo.TUnit.SmokeTest.csproj")
        self.assertEqual(rs.package_references(csproj, "Demo", "1.2.3"),
                         [(None, "TUnit", "1.83.0"), (None, "Demo.TUnit", "1.2.3")])

    def test_framework_conditions_kept_and_other_conditions_dropped(self):
        net10 = "'$(TargetFramework)' == 'net10.0'"
        net11 = "'$(TargetFramework)' == 'net11.0'"
        self.write("tests/Demo.TUnit.SmokeTest/Demo.TUnit.SmokeTest.csproj", f'''<Project>
  <ItemGroup><PackageReference Include="TUnit" Version="1.83.0" /></ItemGroup>
  <ItemGroup Condition="{net10}"><PackageReference Include="Lib" Version="10.0.1" /></ItemGroup>
  <ItemGroup Condition="{net11}"><PackageReference Include="Lib" Version="11.0.0" /></ItemGroup>
  <ItemGroup><PackageReference Include="Other" Version="2.0.0" Condition="{net11}" /></ItemGroup>
  <ItemGroup Condition="'$(ArtifactsLocalFeedExists)' == 'true'">
    <PackageReference Include="Demo.TUnit" Version="$(SmokePackageVersion)" />
  </ItemGroup>
</Project>''')
        csproj = os.path.join(self.root, "tests", "Demo.TUnit.SmokeTest", "Demo.TUnit.SmokeTest.csproj")
        references = rs.package_references(csproj, "Demo", "1.2.3")
        self.assertEqual(references, [(None, "TUnit", "1.83.0"), (net10, "Lib", "10.0.1"), (net11, "Lib", "11.0.0"),
                                      (net11, "Other", "2.0.0"), (None, "Demo.TUnit", "1.2.3")])
        text = rs.project("net10.0 net11.0", references)
        self.assertIn('  <ItemGroup>\n    <PackageReference Include="TUnit" Version="1.83.0" />\n'
                      '    <PackageReference Include="Demo.TUnit" Version="1.2.3" />\n  </ItemGroup>', text)
        self.assertIn(f'  <ItemGroup Condition="{net10}">\n    <PackageReference Include="Lib" Version="10.0.1" />\n'
                      '  </ItemGroup>', text)
        self.assertIn(f'  <ItemGroup Condition="{net11}">\n    <PackageReference Include="Lib" Version="11.0.0" />\n'
                      '    <PackageReference Include="Other" Version="2.0.0" />\n  </ItemGroup>', text)
        self.assertNotIn("ArtifactsLocalFeedExists", text)

    def test_project_lists_frameworks_references_and_the_prelude(self):
        text = rs.project("net10.0 net11.0", [(None, "TUnit", "1.83.0")])
        self.assertIn("<TargetFrameworks>net10.0;net11.0</TargetFrameworks>", text)
        self.assertIn('<PackageReference Include="TUnit" Version="1.83.0" />', text)
        self.assertIn('<Compile Include="../ReadmeSamples.Prelude.cs" Condition="Exists(\'../ReadmeSamples.Prelude.cs\')"',
                      text)

    def test_readmes_are_the_root_and_the_package_readmes(self):
        self.repository()
        self.assertEqual(rs.readmes(self.root), ["README.md", "src/Demo/README.md"])

    def test_no_readme(self):
        self.assertEqual(rs.readmes(self.root), [])

    def test_write_creates_the_project(self):
        self.repository()
        self.write("tests/.readme-samples/Stale.g.cs", "old")
        self.assertEqual(rs.write(self.root, "Demo", "1.2.3", "net10.0"), (2, 1))
        output = os.path.join(self.root, "tests", ".readme-samples")
        self.assertEqual(sorted(os.listdir(output)), ["NuGet.config", "Prelude.g.cs", "ReadmeSamples.csproj",
                                                      "Sample001.g.cs", "Sample002.g.cs"])
        with open(os.path.join(output, "Sample001.g.cs"), encoding="utf-8") as handle:
            source = os.path.abspath(os.path.join(self.root, "README.md")).replace(os.sep, "/")
            self.assertIn(f'#line 2 "{source}"', handle.read())

    def test_main_prints_the_counts(self):
        self.repository()
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(rs.main(["readme_samples.py", "Demo", "1.2.3", "net10.0", self.root]), 0)
        self.assertIn("2 README sample(s) written", out.getvalue())
        self.assertIn("1 block(s) marked no-compile", out.getvalue())

    def test_main_defaults_to_the_current_directory(self):
        self.repository()
        cwd = os.getcwd()
        os.chdir(self.root)
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(rs.main(["readme_samples.py", "Demo", "1.2.3", "net10.0"]), 0)
        finally:
            os.chdir(cwd)

    def test_main_with_wrong_arguments_prints_usage(self):
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(rs.main(["readme_samples.py", "Demo"]), 2)

    def test_runs_as_a_program(self):
        self.repository()
        with mock.patch.object(sys, "argv", ["readme_samples.py", "Demo", "1.2.3", "net10.0", self.root]), \
                contextlib.redirect_stdout(io.StringIO()), self.assertRaises(SystemExit) as raised:
            runpy.run_path(rs.__file__, run_name="__main__")
        self.assertEqual(raised.exception.code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
