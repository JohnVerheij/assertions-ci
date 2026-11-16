using TUnit.FsCheck;

namespace TUnitContract;

// Upstream #5758: FsCheck properties receive the TUnit test's CancellationToken (not one FsCheck generates by
// reflection), so a [Timeout] reaches the property. Runtime: the token is the test context token and not canceled.
internal sealed class Pr5758_FsCheckCancellationTokenTests
{
    [Test]
    [FsCheckProperty(MaxTest = 20)]
    public bool CancellationToken_Is_Not_Canceled(CancellationToken cancellationToken)
    {
        return !cancellationToken.IsCancellationRequested;
    }

    [Test]
    [FsCheckProperty(MaxTest = 1)]
    public bool CancellationToken_Is_The_Test_Context_Token(CancellationToken cancellationToken)
    {
        var expected = TestContext.Current?.Execution.CancellationToken ?? CancellationToken.None;
        return cancellationToken == expected;
    }
}
