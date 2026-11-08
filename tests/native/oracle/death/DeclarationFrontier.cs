using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.CSharp;
using Microsoft.CodeAnalysis.CSharp.Syntax;

record Selection(string Source, string Sha256, int[][] ExecutableRanges, string[] Aliases, string[] ExecutableImplicitTypes = null, bool AllowNativeAbiDeclarations = false);
record Request(Selection[] Selections, string Output, string Inventory);
record Evidence(string File, string SourceSha256, string Kind, string Name, int Start, int End, string Sha256);

sealed class Frontier : CSharpSyntaxRewriter
{
    readonly string source;
    readonly Selection selection;
    public readonly List<Evidence> Executable = new();
    public readonly List<Evidence> Declarations = new();

    public Frontier(Selection selection, string source)
    {
        this.selection = selection;
        this.source = source;
    }

    public static string Hash(string text) => Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(text))).ToLowerInvariant();

    bool Selected(SyntaxNode node)
    {
        var span = node.GetLocation().GetLineSpan();
        return selection.ExecutableRanges.Any(range => range[0] <= span.StartLinePosition.Line + 1 && range[1] >= span.EndLinePosition.Line + 1);
    }

    void Record(List<Evidence> inventory, SyntaxNode node, string kind, string name, int? end = null)
    {
        int stop = end ?? node.Span.End;
        inventory.Add(new(selection.Source, selection.Sha256, kind, name, node.SpanStart, stop,
            Hash(source.Substring(node.SpanStart, stop - node.SpanStart))));
    }

    BlockSyntax Guard(string name) => (BlockSyntax)SyntaxFactory.ParseStatement("{ throw new DeathOracle.UnsupportedClosure(" +
        JsonSerializer.Serialize("Excluded source member: " + selection.Source + ":" + name) + "); }");

    ExpressionSyntax GuardExpression(string name) => SyntaxFactory.ParseExpression("throw new DeathOracle.UnsupportedClosure(" +
        JsonSerializer.Serialize("Excluded source accessor: " + selection.Source + ":" + name) + ")");

    public override SyntaxNode VisitClassDeclaration(ClassDeclarationSyntax node)
    {
        Record(Declarations, node, "type", node.Identifier.Text, node.OpenBraceToken.Span.End);
        var rewritten = (ClassDeclarationSyntax)base.VisitClassDeclaration(node);
        if (node.Modifiers.Any(SyntaxKind.StaticKeyword) || node.Members.OfType<ConstructorDeclarationSyntax>().Any(value => !value.Modifiers.Any(SyntaxKind.StaticKeyword)))
            return rewritten;
        string name = string.Join(".", node.Ancestors().OfType<TypeDeclarationSyntax>().Reverse().Select(value => value.Identifier.Text).Append(node.Identifier.Text));
        bool active = selection.ExecutableImplicitTypes?.Contains(name) == true || Selected(node);
        Record(active ? Executable : Declarations, node, "implicit-constructor", name, node.OpenBraceToken.Span.End);
        string access = node.Modifiers.Any(SyntaxKind.AbstractKeyword) ? "protected" : "public";
        var constructor = (ConstructorDeclarationSyntax)SyntaxFactory.ParseMemberDeclaration(access + " " + node.Identifier.Text + "() {}\n");
        if (!active) constructor = constructor.WithBody(Guard(name + ".implicit-ctor"));
        return rewritten.AddMembers(constructor.WithAdditionalAnnotations(new SyntaxAnnotation("implicit-source-constructor")));
    }

    public override SyntaxNode VisitStructDeclaration(StructDeclarationSyntax node)
    {
        Record(Declarations, node, "type", node.Identifier.Text, node.OpenBraceToken.Span.End);
        return base.VisitStructDeclaration(node);
    }

    public override SyntaxNode VisitInterfaceDeclaration(InterfaceDeclarationSyntax node)
    {
        Record(Declarations, node, "interface", node.Identifier.Text, node.OpenBraceToken.Span.End);
        return base.VisitInterfaceDeclaration(node);
    }

    public override SyntaxNode VisitDelegateDeclaration(DelegateDeclarationSyntax node)
    {
        Record(Declarations, node, "delegate", node.Identifier.Text);
        return node;
    }

    public override SyntaxNode VisitEnumDeclaration(EnumDeclarationSyntax node)
    {
        Record(Declarations, node, "enum", node.Identifier.Text);
        return node;
    }

    public override SyntaxNode VisitFieldDeclaration(FieldDeclarationSyntax node)
    {
        Record(Declarations, node, "field", node.Declaration.Variables.ToString());
        foreach (var variable in node.Declaration.Variables.Where(variable => variable.Initializer != null))
            Record(Executable, variable.Initializer, "initializer", variable.Identifier.Text);
        return node;
    }

    public override SyntaxNode VisitMethodDeclaration(MethodDeclarationSyntax node)
    {
        if (node.Modifiers.Any(SyntaxKind.ExternKeyword))
        {
            if (!selection.AllowNativeAbiDeclarations)
                throw new InvalidDataException("Native extern requires an explicit boundary: " + selection.Source + ":" + node.Identifier.Text);
            if (node.Body != null || node.ExpressionBody != null)
                throw new InvalidDataException("Native ABI declaration cannot have a managed body: " + selection.Source + ":" + node.Identifier.Text);
            Record(Declarations, node, "native-abi", node.Identifier.Text);
            return node;
        }
        Record(Declarations, node, "method", node.Identifier.Text, node.Body?.SpanStart ?? node.ExpressionBody?.SpanStart ?? node.Span.End);
        if (Selected(node) || node.Body == null && node.ExpressionBody == null)
        {
            if (node.Body != null || node.ExpressionBody != null) Record(Executable, node, "method", node.Identifier.Text);
            return node;
        }
        return node.WithBody(Guard(node.Identifier.Text)).WithExpressionBody(null).WithSemicolonToken(default);
    }

    public override SyntaxNode VisitConstructorDeclaration(ConstructorDeclarationSyntax node)
    {
        Record(Declarations, node, "constructor", node.Identifier.Text, node.Body?.SpanStart ?? node.ExpressionBody?.SpanStart ?? node.Span.End);
        if (node.Initializer != null) Record(Executable, node.Initializer, "base-initializer", node.Identifier.Text);
        if (Selected(node) || node.Modifiers.Any(SyntaxKind.StaticKeyword))
        {
            Record(Executable, node, "constructor", node.Identifier.Text);
            return node;
        }
        return node.WithBody(Guard(node.Identifier.Text + ".ctor")).WithExpressionBody(null).WithSemicolonToken(default);
    }

    public override SyntaxNode VisitPropertyDeclaration(PropertyDeclarationSyntax node)
    {
        Record(Declarations, node, "property", node.Identifier.Text, node.AccessorList?.SpanStart ?? node.ExpressionBody?.SpanStart ?? node.Span.End);
        if (node.Initializer != null) Record(Executable, node.Initializer, "initializer", node.Identifier.Text);
        if (Selected(node))
        {
            Record(Executable, node, "property", node.Identifier.Text);
            return node;
        }
        if (node.ExpressionBody != null)
            return node.WithExpressionBody(node.ExpressionBody.WithExpression(GuardExpression(node.Identifier.Text)));
        if (node.AccessorList == null || node.Modifiers.Any(SyntaxKind.AbstractKeyword) || node.Parent is InterfaceDeclarationSyntax) return node;
        if (node.Initializer != null) throw new InvalidDataException("Initialized property accessors require explicit executable selection: " + node.Identifier.Text);
        return node.WithAccessorList(node.AccessorList.WithAccessors(SyntaxFactory.List(node.AccessorList.Accessors.Select(accessor =>
            accessor.WithBody(Guard(node.Identifier.Text + "." + accessor.Keyword.Text)).WithExpressionBody(null).WithSemicolonToken(default)))));
    }

    public override SyntaxNode VisitIndexerDeclaration(IndexerDeclarationSyntax node)
    {
        Record(Declarations, node, "indexer", "this", node.AccessorList?.SpanStart ?? node.ExpressionBody?.SpanStart ?? node.Span.End);
        if (Selected(node)) { Record(Executable, node, "indexer", "this"); return node; }
        if (node.ExpressionBody != null) return node.WithExpressionBody(node.ExpressionBody.WithExpression(GuardExpression("this")));
        if (node.AccessorList == null || node.Modifiers.Any(SyntaxKind.AbstractKeyword) || node.Parent is InterfaceDeclarationSyntax) return node;
        return node.WithAccessorList(node.AccessorList.WithAccessors(SyntaxFactory.List(node.AccessorList.Accessors.Select(accessor =>
            accessor.WithBody(Guard("this." + accessor.Keyword.Text)).WithExpressionBody(null).WithSemicolonToken(default)))));
    }

    public override SyntaxNode VisitOperatorDeclaration(OperatorDeclarationSyntax node)
    {
        Record(Declarations, node, "operator", node.OperatorToken.Text, node.Body?.SpanStart ?? node.ExpressionBody?.SpanStart ?? node.Span.End);
        if (Selected(node)) { Record(Executable, node, "operator", node.OperatorToken.Text); return node; }
        return node.WithBody(Guard("operator " + node.OperatorToken.Text)).WithExpressionBody(null).WithSemicolonToken(default);
    }

    public override SyntaxNode VisitConversionOperatorDeclaration(ConversionOperatorDeclarationSyntax node)
    {
        Record(Declarations, node, "conversion", node.Type.ToString(), node.Body?.SpanStart ?? node.ExpressionBody?.SpanStart ?? node.Span.End);
        if (Selected(node)) { Record(Executable, node, "conversion", node.Type.ToString()); return node; }
        return node.WithBody(Guard("conversion " + node.Type)).WithExpressionBody(null).WithSemicolonToken(default);
    }

    public override SyntaxNode VisitDestructorDeclaration(DestructorDeclarationSyntax node)
    {
        Record(Declarations, node, "destructor", node.Identifier.Text, node.Body?.SpanStart ?? node.ExpressionBody?.SpanStart ?? node.Span.End);
        if (Selected(node)) { Record(Executable, node, "destructor", node.Identifier.Text); return node; }
        return node.WithBody(Guard(node.Identifier.Text + ".finalizer")).WithExpressionBody(null).WithSemicolonToken(default);
    }

    public override SyntaxNode VisitEventDeclaration(EventDeclarationSyntax node)
    {
        Record(Declarations, node, "event", node.Identifier.Text, node.AccessorList?.SpanStart ?? node.Span.End);
        if (Selected(node)) { Record(Executable, node, "event", node.Identifier.Text); return node; }
        if (node.AccessorList == null || node.Modifiers.Any(SyntaxKind.AbstractKeyword) || node.Parent is InterfaceDeclarationSyntax) return node;
        return node.WithAccessorList(node.AccessorList.WithAccessors(SyntaxFactory.List(node.AccessorList.Accessors.Select(accessor =>
            accessor.WithBody(Guard(node.Identifier.Text + "." + accessor.Keyword.Text)).WithExpressionBody(null).WithSemicolonToken(default)))));
    }

    public override SyntaxNode VisitEventFieldDeclaration(EventFieldDeclarationSyntax node)
    {
        Record(Declarations, node, "event-field", node.Declaration.Variables.ToString());
        foreach (var variable in node.Declaration.Variables.Where(variable => variable.Initializer != null))
            Record(Executable, variable.Initializer, "initializer", variable.Identifier.Text);
        return node;
    }
}

static class Program
{
    static string[] Signatures(CompilationUnitSyntax root)
    {
        var result = new List<string>();
        foreach (var node in root.DescendantNodes())
        {
            if (node.HasAnnotations("implicit-source-constructor")) continue;
            int? end = node switch
            {
                EnumDeclarationSyntax value => value.Span.End,
                BaseTypeDeclarationSyntax value => value.OpenBraceToken.SpanStart,
                BaseMethodDeclarationSyntax value => value.Body?.SpanStart ?? value.ExpressionBody?.SpanStart ?? value.SemicolonToken.SpanStart,
                PropertyDeclarationSyntax value => value.AccessorList?.SpanStart ?? value.ExpressionBody?.SpanStart ?? value.Span.End,
                IndexerDeclarationSyntax value => value.AccessorList?.SpanStart ?? value.ExpressionBody?.SpanStart ?? value.Span.End,
                EventDeclarationSyntax value => value.AccessorList?.SpanStart ?? value.Span.End,
                AccessorDeclarationSyntax value => value.Body?.SpanStart ?? value.ExpressionBody?.SpanStart ?? value.SemicolonToken.SpanStart,
                FieldDeclarationSyntax value => value.Span.End,
                EventFieldDeclarationSyntax value => value.Span.End,
                DelegateDeclarationSyntax value => value.Span.End,
                _ => null
            };
            if (end != null)
                result.Add(Frontier.Hash(string.Join("\n", node.DescendantTokens().Where(token => token.SpanStart < end).Select(token => token.RawKind + ":" + token.Text))));
        }
        return result.ToArray();
    }

    static void Main(string[] args)
    {
        if (args.Length != 1) throw new ArgumentException("Expected a pinned frontier request");
        var request = JsonSerializer.Deserialize<Request>(File.ReadAllText(args[0]));
        var output = new StringBuilder();
        var executable = new List<Evidence>();
        var declarations = new List<Evidence>();
        foreach (var selection in request.Selections)
        {
            string source = File.ReadAllText(selection.Source);
            if (Frontier.Hash(source) != selection.Sha256) throw new InvalidDataException("Changed pinned source: " + selection.Source);
            var root = CSharpSyntaxTree.ParseText(source).GetCompilationUnitRoot();
            var errors = root.GetDiagnostics().Where(diagnostic => diagnostic.Severity == DiagnosticSeverity.Error).ToArray();
            if (errors.Length != 0) throw new InvalidDataException(string.Join("\n", errors.Select(error => error.ToString())));
            var externals = root.DescendantNodes().Where(node =>
                node is BaseMethodDeclarationSyntax method && method.Modifiers.Any(SyntaxKind.ExternKeyword) ||
                node is BasePropertyDeclarationSyntax property && property.Modifiers.Any(SyntaxKind.ExternKeyword));
            foreach (var external in externals)
                if (!selection.AllowNativeAbiDeclarations || external is not MethodDeclarationSyntax)
                    throw new InvalidDataException("Native extern requires an explicit boundary: " + selection.Source + ":" +
                        (external.GetLocation().GetLineSpan().StartLinePosition.Line + 1));
            var frontier = new Frontier(selection, source);
            var rewritten = (CompilationUnitSyntax)frontier.Visit(root);
            if (!Signatures(root).SequenceEqual(Signatures(rewritten)))
                throw new InvalidDataException("Declaration metadata or field order changed: " + selection.Source);
            foreach (var member in rewritten.Members)
            {
                if (member is not FileScopedNamespaceDeclarationSyntax space) throw new InvalidDataException("Expected one source file namespace");
                output.Append("namespace " + space.Name + " {\n");
                foreach (var use in rewritten.Usings)
                    output.Append(use.Alias == null && use.Name != null ? use.WithName(SyntaxFactory.ParseName("global::" + use.Name)).ToFullString() : use.ToFullString());
                foreach (string alias in selection.Aliases) output.Append("using " + alias + ";\n");
                foreach (var type in space.Members) output.Append(type.ToFullString());
                output.Append("\n}\n");
            }
            executable.AddRange(frontier.Executable);
            declarations.AddRange(frontier.Declarations);
        }
        File.WriteAllText(request.Output, output.ToString());
        File.WriteAllText(request.Inventory, JsonSerializer.Serialize(new { Executable = executable, Declarations = declarations,
            OutputSha256 = Frontier.Hash(output.ToString()) }, new JsonSerializerOptions { WriteIndented = true }) + "\n");
    }
}
