using System.Xml.Linq;

namespace TUnitContract;

/// <summary>Reads the XML documentation file the compiler wrote next to the test assembly.</summary>
internal static class GeneratedXmlDocs
{
    private static readonly Lazy<XDocument> Document = new(Load);

    /// <summary>Returns the documented generated extension methods with the given name.</summary>
    /// <param name="memberName">The name of the generated extension method.</param>
    /// <returns>The generated extension methods.</returns>
    public static IReadOnlyList<XElement> MembersOf(string memberName)
    {
        return Document.Value.Descendants("member")
            .Where(member => IsGeneratedExtension(member, memberName))
            .ToList();
    }

    /// <summary>Tells whether the member's documentation contains an inheritdoc that points at <paramref name="target"/>.</summary>
    /// <param name="member">The documented member.</param>
    /// <param name="target">A fragment of the cref the generator is expected to inherit from.</param>
    /// <returns><see langword="true"/> when such an inheritdoc exists.</returns>
    public static bool InheritsFrom(XElement member, string target)
    {
        return member.Descendants("inheritdoc")
            .Any(element => ((string?)element.Attribute("cref"))?.Contains(target, StringComparison.Ordinal) == true);
    }

    private static bool IsGeneratedExtension(XElement member, string memberName)
    {
        var name = (string?)member.Attribute("name") ?? string.Empty;
        return name.StartsWith("M:TUnit.Assertions.Extensions.", StringComparison.Ordinal)
            && name.Contains("." + memberName + "(", StringComparison.Ordinal);
    }

    private static XDocument Load()
    {
        var assemblyPath = typeof(GeneratedXmlDocs).Assembly.Location;
        var xmlPath = Path.ChangeExtension(assemblyPath, ".xml");
        return XDocument.Load(xmlPath);
    }
}
