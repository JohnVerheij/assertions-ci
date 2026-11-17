using TUnit.Assertions.Attributes;
using TUnit.Assertions.Core;

namespace TUnitContract;

// Upstream #7692: the documentation of an [AssertionExtension] class (summary, remarks, type parameters) and of its
// public constructor (parameters, exceptions) is inherited by the generated extension method. Runtime: the XML
// documentation file next to the test assembly references the class and the constructor and keeps no placeholder.
internal sealed class Pr7692_AssertionExtensionXmlDocsTests
{
    private static readonly int Five = 5;

    [Test]
    public async Task Generated_Extension_Inherits_The_Documentation_Of_The_Class_And_Constructor()
    {
        var members = GeneratedXmlDocs.MembersOf("IsInContractRange");

        await Assert.That(members).IsNotEmpty();
        foreach (var member in members)
        {
            await Assert.That(GeneratedXmlDocs.InheritsFrom(member, "T:TUnitContract.Pr7692RangeAssertion")).IsTrue();
            await Assert.That(GeneratedXmlDocs.InheritsFrom(member, "Pr7692RangeAssertion.#ctor")).IsTrue();
            await Assert.That(member.Value).DoesNotContain("Generated assertion for");
        }
    }

    [Test]
    public async Task Documented_Assertion_Class_Compiles_Into_A_Usable_Assertion()
    {
        await Assert.That(Five).IsInContractRange(1, 10);
    }
}

/// <summary>
/// Checks that the value lies in a range.
/// </summary>
/// <remarks>Both bounds are inclusive.</remarks>
[AssertionExtension("IsInContractRange")]
public sealed class Pr7692RangeAssertion : Assertion<int>
{
    private readonly int _minimum;
    private readonly int _maximum;

    /// <summary>
    /// Creates the assertion for a range.
    /// </summary>
    /// <param name="context">The assertion context.</param>
    /// <param name="minimum">The inclusive lower bound.</param>
    /// <param name="maximum">The inclusive upper bound.</param>
    /// <exception cref="ArgumentException">The minimum is greater than the maximum.</exception>
    public Pr7692RangeAssertion(AssertionContext<int> context, int minimum, int maximum)
        : base(context)
    {
        if (minimum > maximum)
        {
            throw new ArgumentException("The minimum is greater than the maximum.", nameof(minimum));
        }

        _minimum = minimum;
        _maximum = maximum;
    }

    /// <inheritdoc />
    protected override Task<AssertionResult> CheckAsync(EvaluationMetadata<int> metadata)
    {
        return Task.FromResult(
            metadata.Value >= _minimum && metadata.Value <= _maximum
                ? AssertionResult.Passed
                : AssertionResult.Failed($"found {metadata.Value}"));
    }

    /// <inheritdoc />
    protected override string GetExpectation() => $"to be between {_minimum} and {_maximum}";
}
