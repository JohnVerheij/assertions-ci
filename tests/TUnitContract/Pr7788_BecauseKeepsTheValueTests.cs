using TUnit.Assertions.Attributes;
using TUnit.Assertions.Core;
using TUnit.Assertions.Exceptions;

namespace TUnitContract;

// Upstream #7788: Because(...) returns the assertion it is called on where awaiting gives a value, so awaiting the
// chain still gives that value: TUnit's HasSingleItem, Contains(predicate) and IsNotNull, and the classes the
// generator writes for [GenerateAssertion] methods that return AssertionResult<T>. Compile time (the typed locals),
// plus runtime.
internal sealed class Pr7788_BecauseKeepsTheValueTests
{
    private static readonly int[] Single = [7];
    private static readonly string? Present = "text";

    [Test]
    public async Task HasSingleItem_Because_Gives_The_Item()
    {
        int item = await Assert.That(Single).HasSingleItem().Because("one item is expected");

        await Assert.That(item).IsEqualTo(7);
    }

    [Test]
    public async Task Contains_Predicate_Because_Gives_The_Item()
    {
        int item = await Assert.That(Single).Contains(static x => x > 5).Because("an item above five is expected");

        await Assert.That(item).IsEqualTo(7);
    }

    [Test]
    public async Task IsNotNull_Because_Gives_The_Value()
    {
        string value = await Assert.That(Present).IsNotNull().Because("the value is set");

        await Assert.That(value).IsEqualTo("text");
    }

    [Test]
    public async Task Generated_AssertionResult_Because_Gives_The_Value()
    {
        string trimmed = await Assert.That(" padded ").ContractTrimsToContent().Because("the value has content");

        await Assert.That(trimmed).IsEqualTo("padded");
    }

    [Test]
    public async Task Generated_AssertionResult_Because_Failure_Carries_The_Reason()
    {
        var exception = await Assert.That(async () =>
                await Assert.That("   ").ContractTrimsToContent().Because("the value has content"))
            .Throws<AssertionException>();

        await Assert.That(exception!.Message).Contains("the value has content");
    }
}

/// <summary>A generated assertion that gives a value when awaited.</summary>
public static partial class Pr7788Assertions
{
    /// <summary>Checks that the value has content after trimming, and gives the trimmed value.</summary>
    /// <param name="value">The value under test.</param>
    /// <returns>The trimmed value, or a failure when only white space is left.</returns>
    [GenerateAssertion(ExpectationMessage = "to have content after trimming")]
    public static AssertionResult<string> ContractTrimsToContent(this string value)
    {
        var trimmed = value.Trim();
        return trimmed.Length > 0
            ? AssertionResult<string>.Passed(trimmed)
            : AssertionResult.Failed("it was only white space");
    }
}
