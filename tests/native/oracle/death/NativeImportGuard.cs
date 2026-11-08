using System;
using System.Collections.Generic;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Runtime.InteropServices;

namespace DeathOracle;

public sealed record NativeImportAttempt(string Library, string Assembly, Guid ModuleVersionId, DllImportSearchPath? SearchPath);

public static class NativeImportGuard
{
    static readonly List<NativeImportAttempt> attempts = new();

    public static bool Installed { get; private set; }

    public static NativeImportAttempt[] Attempts
    {
        get { lock (attempts) return attempts.ToArray(); }
    }

    [ModuleInitializer]
    public static void Install()
    {
        NativeLibrary.SetDllImportResolver(typeof(NativeImportGuard).Assembly, Reject);
        Installed = true;
    }

    static IntPtr Reject(string library, Assembly assembly, DllImportSearchPath? searchPath)
    {
        var attempt = new NativeImportAttempt(library, assembly.FullName, assembly.ManifestModule.ModuleVersionId, searchPath);
        lock (attempts) attempts.Add(attempt);
        throw new UnsupportedClosure("Excluded native ABI import: " + library + "; assembly=" + attempt.Assembly +
            "; module=" + attempt.ModuleVersionId);
    }
}
