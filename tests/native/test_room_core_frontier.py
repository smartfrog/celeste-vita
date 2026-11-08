import hashlib
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
from room_core_frontier import ROOT, SDK, build_tool, emit, project, run
from check_native_oracle import oracle_environment
from read_frontier_declarations import declaration_candidates, missing_types

SOURCE = '''using System;
namespace Fixture;
[AttributeUsage(AttributeTargets.Class)] public class Tracked : Attribute { public bool Inherited; public Tracked(bool inherited) { Inherited = inherited; } }
[AttributeUsage(AttributeTargets.Class)] public class Pooled : Attribute { }
public abstract class Base { }
[Tracked(false), Pooled] public class Subject : Base
{
    public static readonly int Initial = Initialize();
    public readonly int Instance = 19;
    public const int Constant = 7;
    public Subject(int value = 1) { }
    public int Value => 99;
    public static void Callback() { }
    public static int Initialize() { return 42; }
}
public class ImplicitSubject { public readonly int Initial = 23; }
'''

DRIVER = '''using System;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
namespace DeathOracle { public class UnsupportedClosure : Exception { public UnsupportedClosure(string message) : base(message) {} } }
static class MainProgram
{
    static void MustThrow(Action action)
    {
        try { action(); } catch (DeathOracle.UnsupportedClosure) { Console.WriteLine("excluded-member-threw"); return; }
        throw new Exception("Excluded member returned");
    }
    static void Main(string[] args)
    {
        if (args[0] == "constructor") MustThrow(() => new Fixture.Subject());
        if (args[0] == "implicit-constructor") MustThrow(() => new Fixture.ImplicitSubject());
        if (args[0] == "accessor") MustThrow(() => _ = ((Fixture.Subject)RuntimeHelpers.GetUninitializedObject(typeof(Fixture.Subject))).Value);
        if (args[0] == "delegate") { Action callback = Fixture.Subject.Callback; Console.WriteLine("registered"); MustThrow(callback); }
        if (args[0] == "initializer") { if (Fixture.Subject.Initial != 42) throw new Exception("Initializer changed"); Console.WriteLine("original-initializer"); }
        if (args[0] == "metadata")
        {
            var type = typeof(Fixture.Subject);
            if (type.BaseType != typeof(Fixture.Base) || type.IsAbstract || type.IsSealed) throw new Exception("Type metadata changed");
            if (((Fixture.Tracked)type.GetCustomAttributes(typeof(Fixture.Tracked), false).Single()).Inherited) throw new Exception("Tracked metadata changed");
            if (type.GetCustomAttributes(typeof(Fixture.Pooled), false).Length != 1) throw new Exception("Pooled metadata changed");
            var parameter = type.GetConstructor(new[] { typeof(int) }).GetParameters().Single();
            if (parameter.Name != "value" || !parameter.IsOptional || (int)parameter.DefaultValue != 1) throw new Exception("Constructor signature changed");
            var fields = type.GetFields(BindingFlags.Public | BindingFlags.Instance | BindingFlags.Static | BindingFlags.DeclaredOnly).OrderBy(field => field.MetadataToken).Select(field => field.Name);
            if (!fields.SequenceEqual(new[] { "Initial", "Instance", "Constant" })) throw new Exception("Field order changed");
            Console.WriteLine("original-reflection-metadata");
        }
    }
}
'''


class DeclarationDiagnosticTests(unittest.TestCase):
    def test_attribute_suffix_diagnostic_resolves_the_original_attribute_type(self):
        self.assertEqual(declaration_candidates('CommandAttribute', {'Command': [('Celeste.exe', 'Monocle.Command')]}),
            [('Celeste.exe', 'Monocle.Command')])

    def test_exact_attribute_type_is_not_replaced_by_a_shorter_name(self):
        catalog = {'CommandAttribute': [('Celeste.exe', 'Monocle.CommandAttribute')], 'Command': [('Celeste.exe', 'Monocle.Command')]}
        self.assertEqual(declaration_candidates('CommandAttribute', catalog), [('Celeste.exe', 'Monocle.CommandAttribute')])

    def test_missing_declaration_names_are_deduplicated(self):
        diagnostic = "Source.cs(1,1): error CS0246: Le nom de type ou d'espace de noms 'MissingType' est introuvable"
        self.assertEqual(missing_types(diagnostic + '\n' + diagnostic), ['MissingType'])

    def test_english_missing_declaration_is_recognized(self):
        self.assertEqual(missing_types("Source.cs(1,1): error CS0246: The type or namespace name 'MissingType' could not be found"), ['MissingType'])

    def test_member_errors_do_not_request_new_types(self):
        self.assertEqual(missing_types("Source.cs(1,1): error CS1061: Missing member 'OtherType'"), [])

    def test_unknown_missing_type_diagnostic_fails_loudly(self):
        with self.assertRaisesRegex(ValueError, 'Unrecognized missing declaration'):
            missing_types('Source.cs(1,1): error CS0246: unrecognized diagnostic')


@unittest.skipUnless(SDK.is_file(), 'Pinned offline SDK unavailable')
class DeclarationFrontierTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        parent = ROOT / '.audit/native-player-death-respawn/frontier-tests'
        parent.mkdir(exist_ok=True)
        cls.output = Path(tempfile.mkdtemp(prefix='negative-', dir=parent))
        tool = build_tool(cls.output / 'tool')
        source = cls.output / 'Source.cs'
        source.write_text(SOURCE)
        line = next(index for index, text in enumerate(SOURCE.splitlines(), 1) if 'public static int Initialize()' in text)
        generated, cls.inventory = emit(tool, [{'Source': str(source), 'Sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'ExecutableRanges': [[3, 3], [line, line]], 'Aliases': [], 'ExecutableImplicitTypes': ['Pooled', 'Base']}], cls.output)
        (cls.output / 'Combined.cs').write_text(DRIVER + generated)
        (cls.output / 'Test.csproj').write_text(project(cls.output / 'Combined.cs'))
        (cls.output / 'NuGet.Config').write_text('<configuration><packageSources><clear/></packageSources></configuration>')
        run([SDK, 'restore', cls.output / 'Test.csproj', '--configfile', cls.output / 'NuGet.Config'], cls.output, 'test-restore.log')
        run([SDK, 'build', cls.output / 'Test.csproj', '--no-restore', '-c', 'Release', '-p:UseSharedCompilation=false', '--disable-build-servers'], cls.output, 'test-build.log')

    def execute_case(self, name):
        result = subprocess.run([str(SDK), str(self.output / 'bin/Release/net8.0/Test.dll'), name],
            cwd=ROOT, env=oracle_environment(SDK), text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout

    def test_excluded_constructor_throws(self):
        self.assertIn('excluded-member-threw', self.execute_case('constructor'))

    def test_native_extern_declaration_cannot_bypass_managed_invocation_guards(self):
        output = self.output / 'native-extern-rejection'
        output.mkdir()
        source = output / 'Native.cs'
        source.write_text('using System.Runtime.InteropServices;\nnamespace Fixture;\npublic static class Native { [DllImport("unavailable")] public static extern int Invoke(); }\n')
        selection = {'Source': str(source), 'Sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
            'ExecutableRanges': [], 'Aliases': []}
        tool = self.output / 'tool/bin/Release/net8.0/Frontier.dll'
        with self.assertRaisesRegex(RuntimeError, 'Pinned frontier command failed'):
            emit(tool, [selection], output)
        self.assertIn('Native extern requires an explicit boundary', (output / 'frontier.log').read_text())

    def test_approved_native_declaration_has_distinct_unchanged_provenance(self):
        output = self.output / 'native-abi-contract'
        output.mkdir()
        source = output / 'Native.cs'
        declaration = '[DllImport("unavailable")] public static extern int Invoke();'
        source.write_text('using System.Runtime.InteropServices;\nnamespace Fixture;\npublic static class Native { ' + declaration + ' }\n')
        generated, inventory = emit(self.output / 'tool/bin/Release/net8.0/Frontier.dll',
            [{'Source': str(source), 'Sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
              'ExecutableRanges': [], 'Aliases': [], 'AllowNativeAbiDeclarations': True}], output)
        self.assertIn(declaration, generated)
        self.assertEqual([entry['Name'] for entry in inventory['Declarations'] if entry['Kind'] == 'native-abi'], ['Invoke'])
        self.assertFalse(any(entry['Name'] == 'Invoke' for entry in inventory['Executable']))

    def test_approved_native_declaration_still_rejects_a_managed_body(self):
        output = self.output / 'native-abi-invalid-body'
        output.mkdir()
        source = output / 'Native.cs'
        source.write_text('using System.Runtime.InteropServices;\nnamespace Fixture;\npublic static class Native { [DllImport("unavailable")] public static extern int Invoke() { return 0; } }\n')
        with self.assertRaisesRegex(RuntimeError, 'Pinned frontier command failed'):
            emit(self.output / 'tool/bin/Release/net8.0/Frontier.dll',
                [{'Source': str(source), 'Sha256': hashlib.sha256(source.read_bytes()).hexdigest(),
                  'ExecutableRanges': [], 'Aliases': [], 'AllowNativeAbiDeclarations': True}], output)
        self.assertIn('Native ABI declaration cannot have a managed body', (output / 'frontier.log').read_text())

    def test_excluded_implicit_constructor_throws(self):
        self.assertIn('excluded-member-threw', self.execute_case('implicit-constructor'))

    def test_excluded_accessor_throws(self):
        self.assertIn('excluded-member-threw', self.execute_case('accessor'))

    def test_registered_delegate_throws_only_when_invoked(self):
        self.assertEqual(self.execute_case('delegate').splitlines(), ['registered', 'excluded-member-threw'])

    def test_original_initializer_executes_without_poisoning_type(self):
        self.assertIn('original-initializer', self.execute_case('initializer'))

    def test_tracker_pooler_reflection_metadata_is_preserved(self):
        self.assertIn('original-reflection-metadata', self.execute_case('metadata'))

    def test_declarations_have_separate_source_provenance(self):
        self.assertTrue(any(entry['Kind'] == 'constructor' for entry in self.inventory['Declarations']))
        self.assertTrue(any(entry['Kind'] == 'initializer' for entry in self.inventory['Executable']))
        self.assertFalse(any(entry['Kind'] == 'constructor' and entry['Name'] == 'Subject' for entry in self.inventory['Executable']))
