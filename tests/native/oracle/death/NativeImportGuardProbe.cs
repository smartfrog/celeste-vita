using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Reflection.Metadata;
using System.Reflection.PortableExecutable;
using System.Runtime.InteropServices;
using System.Text.Json;

namespace DeathOracle;

static class NativeImportGuardProbe
{
    static object ImportMetadata(string path)
    {
        using var stream = File.OpenRead(path);
        using var image = new PEReader(stream);
        var metadata = image.GetMetadataReader();
        var type = metadata.TypeDefinitions.Select(metadata.GetTypeDefinition).Single(value =>
            metadata.GetString(value.Namespace) == "Celeste" && metadata.GetString(value.Name) == "Audio");
        var method = type.GetMethods().Select(metadata.GetMethodDefinition).Single(value =>
            metadata.GetString(value.Name) == "FMOD_SDL_Register");
        var import = method.GetImport();
        return new
        {
            Attributes = (int)method.Attributes,
            ImplementationFlags = (int)method.ImplAttributes,
            ImportFlags = (int)import.Attributes,
            Library = metadata.GetString(metadata.GetModuleReference(import.Module).Name),
            EntryPoint = metadata.GetString(import.Name),
            Signature = Convert.ToHexString(metadata.GetBlobBytes(method.Signature)),
            Parameters = method.GetParameters().Select(metadata.GetParameter).Select(parameter => new
            {
                parameter.SequenceNumber,
                Attributes = (int)parameter.Attributes,
                Name = metadata.GetString(parameter.Name),
                Marshalling = parameter.GetMarshallingDescriptor().IsNil ? "" :
                    Convert.ToHexString(metadata.GetBlobBytes(parameter.GetMarshallingDescriptor()))
            }).ToArray()
        };
    }

    static MethodInfo PinnedImport() => Assembly.GetExecutingAssembly().GetType("Celeste.Audio", true)
        .GetMethod("FMOD_SDL_Register", BindingFlags.NonPublic | BindingFlags.Static) ??
        throw new InvalidOperationException("Pinned native import missing");

    internal static string[] NativeMappings() => File.ReadLines("/proc/self/maps").Where(line =>
        line.Contains("fmod", StringComparison.OrdinalIgnoreCase) || line.Contains("SDL2", StringComparison.OrdinalIgnoreCase)).ToArray();

    internal static void ExpectGuardedNative(MethodInfo method, object[] arguments, string library)
    {
        if (method == null || (method.Attributes & MethodAttributes.PinvokeImpl) == 0 || method.GetMethodBody() != null)
            throw new InvalidOperationException("Expected an unchanged native ABI declaration");
        try
        {
            method.Invoke(null, arguments);
            throw new InvalidOperationException("Native import bypassed the resolver");
        }
        catch (TargetInvocationException error) when (error.InnerException is UnsupportedClosure)
        {
            var attempt = NativeImportGuard.Attempts.Single();
            if (attempt.Library != library || attempt.Assembly != Assembly.GetExecutingAssembly().FullName ||
                attempt.ModuleVersionId != Assembly.GetExecutingAssembly().ManifestModule.ModuleVersionId ||
                !error.InnerException.Message.Contains(attempt.Library) || !error.InnerException.Message.Contains(attempt.Assembly))
                throw new InvalidOperationException("Unexpected native boundary attempt", error);
        }
    }

    public static void Run(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("Expected native guard diagnostic and pinned original assembly path");
        if (!NativeImportGuard.Installed || NativeImportGuard.Attempts.Length != 0)
            throw new InvalidOperationException("Native resolver was not installed before the diagnostic");
        var mappingsBefore = NativeMappings();
        if (mappingsBefore.Length != 0) throw new InvalidOperationException("Preloaded native mappings invalidate the native diagnostic");
        string status;
        object identity = null;
        if (args[0] == "native-abi-identity")
        {
            identity = ImportMetadata(args[1]);
            if (JsonSerializer.Serialize(identity) != JsonSerializer.Serialize(ImportMetadata(Assembly.GetExecutingAssembly().Location)))
                throw new InvalidOperationException("Pinned import metadata differs from the original assembly");
            var method = PinnedImport();
            var import = method.GetCustomAttribute<DllImportAttribute>();
            if ((method.Attributes & MethodAttributes.PinvokeImpl) == 0 || method.GetMethodBody() != null ||
                (method.MethodImplementationFlags & MethodImplAttributes.PreserveSig) == 0 ||
                import == null || import.Value != "fmod_SDL" || import.EntryPoint != "FMOD_SDL_Register" ||
                import.CallingConvention != CallingConvention.Cdecl || import.CharSet != CharSet.None ||
                import.SetLastError || !import.PreserveSig ||
                method.ReturnParameter.GetCustomAttribute<MarshalAsAttribute>() != null ||
                method.GetParameters().Single().GetCustomAttribute<MarshalAsAttribute>() != null)
                throw new InvalidOperationException("Pinned import reflection identity changed");
            status = "pinned-native-abi-identity-preserved";
        }
        else if (args[0] == "native-abi-negative")
        {
            ExpectGuardedNative(PinnedImport(), new object[] { IntPtr.Zero }, "fmod_SDL");
            status = "expected-native-abi-guard-attempt-not-room-core-coverage";
        }
        else if (args[0] == "native-abi-duplicate")
        {
            bool rejected = false;
            try
            {
                NativeImportGuard.Install();
            }
            catch (InvalidOperationException)
            {
                rejected = true;
            }
            if (!rejected) throw new InvalidOperationException("Duplicate resolver registration succeeded");
            if (!NativeImportGuard.Installed || NativeImportGuard.Attempts.Length != 0)
                throw new InvalidOperationException("Duplicate registration altered native guard state");
            status = "duplicate-resolver-registration-rejected";
        }
        else throw new ArgumentException("Unknown native guard diagnostic: " + args[0]);
        var mappingsAfter = NativeMappings();
        if (mappingsAfter.Length != 0) throw new InvalidOperationException("Native diagnostic mapped an SDL/FMOD library");
        Console.WriteLine(JsonSerializer.Serialize(new { status, identity, assembly = Assembly.GetExecutingAssembly().FullName,
            moduleVersionId = Assembly.GetExecutingAssembly().ManifestModule.ModuleVersionId,
            processId = Environment.ProcessId, nativeGuardInstalled = NativeImportGuard.Installed,
            mappingsBefore, mappingsAfter, nativeAttempts = NativeImportGuard.Attempts }));
    }
}
