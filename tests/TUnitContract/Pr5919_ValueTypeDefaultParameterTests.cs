using TUnit.Assertions.Attributes;
using TUnit.Assertions.Core;

namespace TUnitContract;

// Upstream #5919: a non-nullable value-type parameter declared "= default" (here CancellationToken) is emitted as the
// "default" literal by both assertion generators, not "= null" (CS1750). Compile-time, plus a runtime call that omits
// the argument.
internal sealed class Pr5919_ValueTypeDefaultParameterTests
{
    private static readonly int Five = 5;

    [Test]
    public async Task GenerateAssertion_Method_With_Default_Value_Type_Parameter()
    {
        await Assert.That(Five).RespectsTokenViaMethod();
    }

    [Test]
    public async Task AssertionExtension_Class_With_Default_Value_Type_Parameter()
    {
        await Assert.That("text").RespectsTokenViaClass();
    }
}

/// <summary>Source method with a defaulted value-type parameter.</summary>
public static partial class Pr5919MethodAssertions
{
    /// <summary>Checks that the token is not canceled and the value is positive.</summary>
    /// <param name="value">The value under test.</param>
    /// <param name="token">The token to observe.</param>
    /// <returns><see langword="true"/> when the check passes.</returns>
    [GenerateAssertion]
    public static bool RespectsTokenViaMethod(this int value, CancellationToken token = default)
    {
        return !token.IsCancellationRequested && value > 0;
    }
}

/// <summary>Assertion class with a defaulted value-type constructor parameter.</summary>
[AssertionExtension("RespectsTokenViaClass")]
public sealed class Pr5919TokenAssertion : Assertion<string>
{
    private readonly CancellationToken _token;

    /// <summary>Creates the assertion.</summary>
    /// <param name="context">The assertion context.</param>
    /// <param name="token">The token to observe.</param>
    public Pr5919TokenAssertion(AssertionContext<string> context, CancellationToken token = default)
        : base(context)
    {
        _token = token;
    }

    /// <inheritdoc />
    protected override Task<AssertionResult> CheckAsync(EvaluationMetadata<string> metadata)
    {
        return _token.IsCancellationRequested
            ? Task.FromResult(AssertionResult.Failed("token was canceled"))
            : Task.FromResult(AssertionResult.Passed);
    }

    /// <inheritdoc />
    protected override string GetExpectation() => "to respect the supplied token";
}
