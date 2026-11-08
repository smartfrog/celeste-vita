using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using Celeste;
using Monocle;

namespace DeathOracle;

static class RoomCoreExecution
{
    static string[] NativeMappings() => File.ReadLines("/proc/self/maps").Where(line =>
        line.Contains("fmod", StringComparison.OrdinalIgnoreCase) || line.Contains("SDL2", StringComparison.OrdinalIgnoreCase)).ToArray();

    public static void Run(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("Expected room-core-execute and a fresh private trace path");
        string path = Path.GetFullPath(args[1]);
        string root = Path.GetFullPath(".audit/native-player-death-respawn") + Path.DirectorySeparatorChar;
        if (!path.StartsWith(root, StringComparison.Ordinal)) throw new ArgumentException("Execution trace must remain private");
        using var trace = new StreamWriter(new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read));
        trace.AutoFlush = true;
        string member = "native-guard-preconditions";
        void Write(object row) => trace.WriteLine(JsonSerializer.Serialize(row));
        void Invoke(string name, Action action)
        {
            member = name;
            Write(new { @event = "enter", member });
            action();
            Write(new { @event = "return", member });
        }
        try
        {
            if (!NativeImportGuard.Installed || NativeImportGuard.Attempts.Length != 0)
                throw new InvalidOperationException("Execution requires a fresh assembly-local native guard");
            var mappingsBefore = NativeMappings();
            Write(new { @event = "caller-preconditions", nativeMappingsBefore = mappingsBefore });
            if (mappingsBefore.Length != 0) throw new InvalidOperationException("Preloaded native mappings invalidate this source execution probe");
            Invoke("Celeste.Tags.Initialize", Tags.Initialize);
            Invoke("Monocle.Tracker.Initialize", Tracker.Initialize);
            Level level = null;
            Invoke("Celeste.Level.constructor", () => level = new Level());
            Write(new { @event = "caller-level-created", level.Zoom, helperEntity = level.HelperEntity.GetType().FullName,
                trackedEntityTypes = Tracker.TrackedEntityTypes.Count, trackedComponentTypes = Tracker.TrackedComponentTypes.Count });
            Invoke("Celeste.Settings.constructor", () => Settings.Instance = new Settings());
            Invoke("Monocle.MInput.Initialize", MInput.Initialize);
            member = "caller-fixture-handoff";
            throw new InvalidOperationException("Remaining RoomCore caller fixture is not assembled; LoadLevel has not been invoked");
        }
        catch (Exception error)
        {
            Write(new { @event = "boundary", member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, nativeMappingsAtBoundary = NativeMappings(), loadLevelEntered = false,
                completedLifecycleFamilies = 0, status = "blocked-before-load-level-not-lifecycle-coverage" });
            throw;
        }
    }
}
