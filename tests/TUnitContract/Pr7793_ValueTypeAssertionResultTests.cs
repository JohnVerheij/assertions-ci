using System.Globalization;
using TUnit.Assertions.Attributes;
using TUnit.Assertions.Core;
using TUnit.Assertions.Exceptions;

namespace TUnitContract;

// Upstream #7793: a [GenerateAssertion] method that returns AssertionResult<T> of a value type compiles, and awaiting
// it gives T: an int for AssertionResult<int> (the generated file failed with CS0266) and an int? for
// AssertionResult<int?> (CS1519 on "int??"). Compile time (the typed locals), plus runtime.
internal sealed class Pr7793_ValueTypeAssertionResultTests
{
    [Test]
    public async Task Value_Type_Result_Is_Given_As_T()
    {
        int number = await Assert.That("42").ContractParsesAsInt();

        await Assert.That(number).IsEqualTo(42);
    }

    [Test]
    public async Task Value_Type_Result_Failure_Still_Fails()
    {
        await Assert.That(async () => await Assert.That("forty-two").ContractParsesAsInt())
            .Throws<AssertionException>();
    }

    [Test]
    public async Task Nullable_Value_Type_Result_Is_Given_As_Nullable_T()
    {
        int? none = await Assert.That(string.Empty).ContractLengthOrNull();
        int? three = await Assert.That("abc").ContractLengthOrNull();

        await Assert.That(none).IsNull();
        await Assert.That(three).IsEqualTo(3);
    }
}

/// <summary>Generated assertions that give a value type when awaited.</summary>
public static partial class Pr7793Assertions
{
    /// <summary>Checks that the value parses as an integer, and gives the integer.</summary>
    /// <param name="value">The value under test.</param>
    /// <returns>The parsed integer, or a failure when the value is not an integer.</returns>
    [GenerateAssertion(ExpectationMessage = "to parse as an integer")]
    public static AssertionResult<int> ContractParsesAsInt(this string value)
    {
        return int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out var number)
            ? AssertionResult<int>.Passed(number)
            : AssertionResult.Failed("it is not an integer");
    }

    /// <summary>Gives the length of the value, or <see langword="null"/> when it is empty.</summary>
    /// <param name="value">The value under test.</param>
    /// <returns>The length, or <see langword="null"/> for an empty value.</returns>
    [GenerateAssertion(ExpectationMessage = "to have a length")]
    public static AssertionResult<int?> ContractLengthOrNull(this string value)
    {
        return AssertionResult<int?>.Passed(value.Length == 0 ? null : value.Length);
    }
}
