using TUnit.Assertions.Attributes;
using TUnit.Assertions.Exceptions;

namespace TUnitContract;

// Upstream #5920: a [GenerateAssertion] method returning Task<bool> is emitted without a duplicate closing
// parenthesis. Compile-time, plus runtime coverage of the passing and failing paths.
internal sealed class Pr5920_TaskBoolEmitTests
{
    private static readonly int Three = 3;

    [Test]
    public async Task Task_Bool_Assertion_Passes()
    {
        await Assert.That(Three).IsPositiveAsyncForContract();
    }

    [Test]
    public async Task Task_Bool_Assertion_Fails_With_The_Found_Value()
    {
        var act = async () => await Assert.That(-Three).IsPositiveAsyncForContract();

        await Assert.That(act).Throws<AssertionException>().WithMessageContaining("found -3");
    }
}

/// <summary>Source methods that return Task of bool.</summary>
public static partial class Pr5920AsyncBoolAssertions
{
    /// <summary>Checks that the value is positive.</summary>
    /// <param name="value">The value under test.</param>
    /// <returns>A task that completes with <see langword="true"/> when the value is positive.</returns>
    [GenerateAssertion]
    public static async Task<bool> IsPositiveAsyncForContract(this int value)
    {
        await Task.Yield();
        return value > 0;
    }
}
