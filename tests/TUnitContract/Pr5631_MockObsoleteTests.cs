using TUnit.Mocks;

namespace TUnitContract;

// Upstream #5631 (issue #5626): the mock source generator copies [Obsolete] onto the generated forwards and
// overrides, so mocking an interface or class with obsolete members does not leak CS0612/CS0618/CS0672 into a
// project that treats warnings as errors. Compile-time: this file only builds without warnings with the fix.
internal sealed class Pr5631_MockObsoleteTests
{
    [Test]
    public async Task Mock_Of_Type_With_Obsolete_Members_Compiles_Without_Warnings()
    {
        var dialog = Mock.Of<IObsoleteDialogService>();
        var partial = Mock.Of<ObsoleteBaseDialog>();

        await Assert.That(dialog).IsNotNull();
        await Assert.That(partial).IsNotNull();
    }
}

/// <summary>An interface whose members are obsolete in different ways.</summary>
public interface IObsoleteDialogService
{
    /// <summary>An obsolete method with a message.</summary>
    /// <param name="title">The title.</param>
    /// <param name="message">The message.</param>
    /// <returns>The result.</returns>
    [Obsolete("Use ShowAsync(options) instead")]
    string? Show(string? title, string? message);

    /// <summary>An obsolete generic method.</summary>
    /// <typeparam name="TData">The data type.</typeparam>
    /// <param name="data">The data.</param>
    /// <returns>The result.</returns>
    [Obsolete]
    Task<string?> ShowPanel<TData>(TData? data)
        where TData : class;

    /// <summary>An obsolete event.</summary>
    [Obsolete("Removed", true)]
    event EventHandler<string?>? Opened;

    /// <summary>A property with two obsolete accessors.</summary>
    string? Greeting { [Obsolete] get; [Obsolete] set; }

    /// <summary>A property with an obsolete getter only.</summary>
    string? Headline { [Obsolete] get; set; }

    /// <summary>A property with an obsolete setter only.</summary>
    string? Subtitle { get; [Obsolete] set; }

    /// <summary>A message with quotes and backslashes that must survive into the generated attribute.</summary>
    /// <returns>The result.</returns>
    [Obsolete("Use \"NewMethod\" in C:\\New\\Path")]
    string? WithTrickyChars();
}

/// <summary>A class with an obsolete virtual member.</summary>
public abstract class ObsoleteBaseDialog
{
    /// <summary>An obsolete virtual method.</summary>
    /// <param name="input">The input.</param>
    /// <returns>The input.</returns>
    [Obsolete]
    public virtual string? Compute(string? input) => input;
}
