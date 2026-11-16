using TUnit.Assertions.Attributes;

namespace TUnitContract;

// Upstream #5796: generated assertion code starts with an auto-generated header and "#pragma warning disable", so
// CS1591 skips it. Compile-time: with GenerateDocumentationFile and warnings as
// errors this project only builds when the generated code carries the header (the generated types have no
// documentation of their own, so CS1591 would fail the build).
internal sealed class Pr5796_GeneratedHeaderTests
{
    private static readonly int Four = 4;

    [Test]
    public async Task Generated_Assertion_Is_Usable_In_A_Strict_Project()
    {
        await Assert.That(Four).IsEvenForHeaderContract();
    }
}

/// <summary>Source methods for the generated-header contract.</summary>
public static partial class Pr5796HeaderAssertions
{
    /// <summary>Checks that the value is even.</summary>
    /// <param name="value">The value under test.</param>
    /// <returns><see langword="true"/> when the value is even.</returns>
    [GenerateAssertion(ExpectationMessage = "to be even")]
    public static bool IsEvenForHeaderContract(this int value) => value % 2 == 0;
}
