using TUnit.Assertions.Attributes;

namespace TUnitContract;

// Upstream #5940: [CallerArgumentExpression] parameters are emitted before a params parameter in the generated
// extension (otherwise CS0231). Compile-time: the generated methods only compile with the fix. Runtime: the params
// array is passed by name, because the caller-expression parameters now sit in front of it.
internal sealed class Pr5940_ParamsCallerExpressionTests
{
    private static readonly int Five = 5;
    private static readonly string Text = "abc";

    [Test]
    public async Task Required_Parameter_Before_Params()
    {
        await Assert.That(Text).ContractContainsAny("a", candidates: ["x", "y"]);
    }

    [Test]
    public async Task Two_Required_Parameters_Before_Params()
    {
        await Assert.That(Five).ContractIsBetweenExcluding(1, 10, excluded: [3, 4]);
    }

    [Test]
    public async Task Optional_Parameter_Before_Params()
    {
        await Assert.That(Text).ContractMeetsLength(1, suffixes: ["x"]);
    }

    [Test]
    public async Task Generic_Parameter_Before_Generic_Params()
    {
        await Assert.That(Five).ContractIsOneOfWithDefault(1, alternatives: [2, 3]);
    }

    [Test]
    public async Task Params_Only()
    {
        await Assert.That(Text).ContractContainsExactly("a", "b");
    }
}

/// <summary>Source methods that end in a params array.</summary>
public static partial class Pr5940ParamsAssertions
{
    /// <summary>Required parameter then params.</summary>
    /// <param name="value">The value under test.</param>
    /// <param name="label">The label.</param>
    /// <param name="candidates">The candidates.</param>
    /// <returns>Whether the check passes.</returns>
    [GenerateAssertion]
    public static bool ContractContainsAny(this string value, string label, params string[] candidates)
        => candidates.Length > 0 && value.Length >= label.Length;

    /// <summary>Two required parameters then params.</summary>
    /// <param name="value">The value under test.</param>
    /// <param name="min">The lower bound.</param>
    /// <param name="max">The upper bound.</param>
    /// <param name="excluded">The excluded values.</param>
    /// <returns>Whether the check passes.</returns>
    [GenerateAssertion]
    public static bool ContractIsBetweenExcluding(this int value, int min, int max, params int[] excluded)
        => value >= min && value <= max && !excluded.Contains(value);

    /// <summary>Optional parameter then params.</summary>
    /// <param name="value">The value under test.</param>
    /// <param name="minLength">The minimum length.</param>
    /// <param name="suffixes">The suffixes.</param>
    /// <returns>Whether the check passes.</returns>
    [GenerateAssertion]
    public static bool ContractMeetsLength(this string value, int minLength = 1, params string[] suffixes)
        => value.Length >= minLength && suffixes.Length >= 0;

    /// <summary>Generic parameter then generic params.</summary>
    /// <typeparam name="T">The value type.</typeparam>
    /// <param name="value">The value under test.</param>
    /// <param name="fallback">The fallback.</param>
    /// <param name="alternatives">The alternatives.</param>
    /// <returns>Whether the check passes.</returns>
    [GenerateAssertion]
    public static bool ContractIsOneOfWithDefault<T>(this T value, T fallback, params T[] alternatives)
        => alternatives.Length >= 0 || EqualityComparer<T>.Default.Equals(fallback, value);

    /// <summary>Params only.</summary>
    /// <param name="value">The value under test.</param>
    /// <param name="required">The required values.</param>
    /// <returns>Whether the check passes.</returns>
    [GenerateAssertion]
    public static bool ContractContainsExactly(this string value, params string[] required)
        => required.Length >= 0 && value.Length >= 0;
}
