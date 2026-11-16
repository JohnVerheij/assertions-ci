using System.Globalization;
using TUnit.Assertions.Attributes;
using TUnit.Assertions.Core;

namespace TUnitContract;

// Upstream #5935: a [GenerateAssertion] method with its own type parameters on a concrete non-sealed receiver gets an
// extension with exactly those type parameters, so a call with explicit type arguments binds (C# has no partial
// type-argument lists). Compile-time: the explicit calls below only compile with the fix.
internal sealed class Pr5935_CovariantGenericMethodTests
{
    [Test]
    public async Task Explicit_Type_Argument_On_Non_Sealed_Receiver()
    {
        await Assert.That(new ContractContainer()).ContractHasItem<int>(42);
    }

    [Test]
    public async Task Full_Inference_On_Non_Sealed_Receiver()
    {
        await Assert.That(new ContractContainer()).ContractHasItem(42);
    }

    [Test]
    public async Task Two_Explicit_Type_Arguments()
    {
        await Assert.That(new ContractContainer()).ContractHasPair<int, string>(42, "x");
    }

    [Test]
    public async Task Explicit_Type_Argument_On_Interface_Receiver()
    {
        IContractContainer container = new ContractContainer();
        await Assert.That(container).ContractHasInterfaceItem<int>(42);
    }

    [Test]
    public async Task Explicit_Type_Argument_With_Constraint()
    {
        await Assert.That(new ContractContainer()).ContractHasParsable<int>("42");
    }

    [Test]
    public async Task Explicit_Type_Argument_With_Async_Result()
    {
        await Assert.That(new ContractContainer()).ContractHasItemAsync<int>(42);
    }
}

/// <summary>Non-sealed receiver.</summary>
public class ContractContainer : IContractContainer
{
}

/// <summary>Interface receiver.</summary>
public interface IContractContainer
{
}

/// <summary>Generic source methods on non-sealed receivers.</summary>
public static partial class Pr5935ContainerAssertions
{
    /// <summary>Passes for non-null arguments.</summary>
    /// <typeparam name="T">The item type.</typeparam>
    /// <param name="container">The container.</param>
    /// <param name="item">The item.</param>
    /// <returns>Whether the check passes.</returns>
    [GenerateAssertion]
    public static bool ContractHasItem<T>(this ContractContainer container, T item) => container is not null && item is not null;

    /// <summary>Passes for non-null arguments.</summary>
    /// <typeparam name="TFirst">The first type.</typeparam>
    /// <typeparam name="TSecond">The second type.</typeparam>
    /// <param name="container">The container.</param>
    /// <param name="first">The first item.</param>
    /// <param name="second">The second item.</param>
    /// <returns>Whether the check passes.</returns>
    [GenerateAssertion]
    public static bool ContractHasPair<TFirst, TSecond>(this ContractContainer container, TFirst first, TSecond second)
        => container is not null && first is not null && second is not null;

    /// <summary>Passes for non-null arguments.</summary>
    /// <typeparam name="T">The item type.</typeparam>
    /// <param name="container">The container.</param>
    /// <param name="item">The item.</param>
    /// <returns>Whether the check passes.</returns>
    [GenerateAssertion]
    public static bool ContractHasInterfaceItem<T>(this IContractContainer container, T item) => container is not null && item is not null;

    /// <summary>Passes when the text parses as the type.</summary>
    /// <typeparam name="T">The parsed type.</typeparam>
    /// <param name="container">The container.</param>
    /// <param name="text">The text to parse.</param>
    /// <returns><see langword="true"/> when the text parses.</returns>
    [GenerateAssertion]
    public static bool ContractHasParsable<T>(this ContractContainer container, string text)
        where T : IParsable<T>
        => container is not null && T.TryParse(text, CultureInfo.InvariantCulture, out _);

    /// <summary>Passes for non-null arguments.</summary>
    /// <typeparam name="T">The item type.</typeparam>
    /// <param name="container">The container.</param>
    /// <param name="item">The item.</param>
    /// <returns>A passed or failed result.</returns>
    [GenerateAssertion]
    public static Task<AssertionResult> ContractHasItemAsync<T>(this ContractContainer container, T item)
        => Task.FromResult(container is not null && item is not null ? AssertionResult.Passed : AssertionResult.Failed("null"));
}
