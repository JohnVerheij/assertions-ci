using System.Diagnostics;
using TUnit.Assertions.Exceptions;

namespace TUnitContract;

// Upstream #5938: WaitsFor and Eventually take a CancellationToken. External cancellation interrupts the polling loop
// as OperationCanceledException before the internal timeout; the internal timeout still throws AssertionException.
// Compile-time (the cancellationToken argument) and runtime.
internal sealed class Pr5938_WaitsForCancellationTokenTests
{
    [Test]
    public async Task WaitsFor_Propagates_External_Cancellation_Before_The_Timeout()
    {
        using var cts = new CancellationTokenSource();
        cts.CancelAfter(TimeSpan.FromMilliseconds(100));
        var stopwatch = Stopwatch.StartNew();

        var act = async () => await Assert.That(() => false)
            .WaitsFor(assert => assert.IsTrue(), timeout: TimeSpan.FromSeconds(30), cancellationToken: cts.Token);

        await Assert.That(act).Throws<OperationCanceledException>();
        await Assert.That(stopwatch.Elapsed).IsLessThan(TimeSpan.FromSeconds(10));
    }

    [Test]
    public async Task WaitsFor_Throws_AssertionException_On_Timeout_When_The_Token_Is_Not_Canceled()
    {
        using var cts = new CancellationTokenSource();

        var act = async () => await Assert.That(() => false)
            .WaitsFor(assert => assert.IsTrue(), timeout: TimeSpan.FromMilliseconds(200), cancellationToken: cts.Token);

        await Assert.That(act).Throws<AssertionException>();
    }

    [Test]
    public async Task WaitsFor_Honors_A_Token_That_Is_Already_Canceled()
    {
        using var cts = new CancellationTokenSource();
        await cts.CancelAsync();

        var act = async () => await Assert.That(() => false)
            .WaitsFor(assert => assert.IsTrue(), timeout: TimeSpan.FromSeconds(30), cancellationToken: cts.Token);

        await Assert.That(act).Throws<OperationCanceledException>();
    }

    [Test]
    public async Task Eventually_Propagates_External_Cancellation_Before_The_Timeout()
    {
        using var cts = new CancellationTokenSource();
        cts.CancelAfter(TimeSpan.FromMilliseconds(100));
        var stopwatch = Stopwatch.StartNew();

        var act = async () => await Assert.That(() => false)
            .Eventually(assert => assert.IsTrue(), timeout: TimeSpan.FromSeconds(30), cancellationToken: cts.Token);

        await Assert.That(act).Throws<OperationCanceledException>();
        await Assert.That(stopwatch.Elapsed).IsLessThan(TimeSpan.FromSeconds(10));
    }
}
