using TUnit.Assertions.Attributes;

namespace TUnitContract;

// Upstream #7687: the documentation of a public [GenerateAssertion] source method is inherited by the generated
// extension method, instead of the generator placeholder ("Generated assertion for ..."). Runtime: the XML
// documentation file next to the test assembly references the source method and keeps no placeholder.
internal sealed class Pr7687_GenerateAssertionXmlDocsTests
{
    private static readonly int Twelve = 12;

    [Test]
    public async Task Generated_Extension_Inherits_The_Documentation_Of_The_Source_Method()
    {
        var members = GeneratedXmlDocs.MembersOf("IsMultipleOfForContract");

        await Assert.That(members).IsNotEmpty();
        foreach (var member in members)
        {
            await Assert.That(GeneratedXmlDocs.InheritsFrom(member, "Pr7687DocumentedAssertions.IsMultipleOfForContract")).IsTrue();
            await Assert.That(member.Value).DoesNotContain("Generated assertion for");
        }
    }

    [Test]
    public async Task Documented_Source_Method_Compiles_Into_A_Usable_Assertion()
    {
        await Assert.That(Twelve).IsMultipleOfForContract(3);
    }
}

/// <summary>Documented source methods for the inherited-documentation contract.</summary>
public static partial class Pr7687DocumentedAssertions
{
    /// <summary>
    /// Checks that the value is a multiple of <paramref name="factor"/>.
    /// </summary>
    /// <param name="value">The value under test.</param>
    /// <param name="factor">The factor; must not be zero.</param>
    /// <returns><see langword="true"/> if the value is a multiple of <paramref name="factor"/>.</returns>
    [GenerateAssertion(ExpectationMessage = "to be a multiple of {factor}")]
    public static bool IsMultipleOfForContract(this int value, int factor) => value % factor == 0;
}
