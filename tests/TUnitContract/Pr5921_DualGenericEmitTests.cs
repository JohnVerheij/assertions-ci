using TUnit.Assertions.Attributes;
using TUnit.Assertions.Core;

namespace TUnitContract;

// Upstream #5921: an [AssertionExtension] class over a non-sealed receiver that declares its own type parameter is
// emitted with one merged generic parameter list, not two adjacent lists (invalid C#). Compile-time, plus a runtime call.
internal sealed class Pr5921_DualGenericEmitTests
{
    [Test]
    public async Task Extension_With_Own_Generic_Over_Non_Sealed_Receiver_Compiles_And_Runs()
    {
        Exception exception = new InvalidOperationException("boom");
        await Assert.That(exception).DualGenericMatches<int>(value => value > 0);
    }
}

/// <summary>Assertion over a non-sealed receiver that declares its own type parameter.</summary>
/// <typeparam name="T">The predicate argument type.</typeparam>
[AssertionExtension("DualGenericMatches")]
public sealed class Pr5921DualGenericAssertion<T> : Assertion<Exception>
{
    private readonly Func<T, bool> _predicate;

    /// <summary>Creates the assertion.</summary>
    /// <param name="context">The assertion context.</param>
    /// <param name="predicate">The predicate.</param>
    public Pr5921DualGenericAssertion(AssertionContext<Exception> context, Func<T, bool> predicate)
        : base(context)
    {
        _predicate = predicate;
    }

    /// <inheritdoc />
    protected override Task<AssertionResult> CheckAsync(EvaluationMetadata<Exception> metadata)
    {
        return Task.FromResult(_predicate is null ? AssertionResult.Failed("no predicate") : AssertionResult.Passed);
    }

    /// <inheritdoc />
    protected override string GetExpectation() => "to match the predicate";
}
