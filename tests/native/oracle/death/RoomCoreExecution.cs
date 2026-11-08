using System;
using System.IO;
using System.Text.Json;
using Celeste;
using Monocle;

namespace DeathOracle;

static class RoomCoreExecution
{
    public static void Run(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("Expected room-core-execute and a fresh private trace path");
        string path = Path.GetFullPath(args[1]);
        string root = Path.GetFullPath(".audit/native-player-death-respawn") + Path.DirectorySeparatorChar;
        if (!path.StartsWith(root, StringComparison.Ordinal)) throw new ArgumentException("Execution trace must remain private");
        using var trace = new StreamWriter(new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read));
        trace.AutoFlush = true;
        string member = "native-guard-preconditions";
        Level level = null;
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
            var mappingsBefore = NativeImportGuardProbe.NativeMappings();
            Write(new { @event = "caller-preconditions", nativeMappingsBefore = mappingsBefore });
            if (mappingsBefore.Length != 0) throw new InvalidOperationException("Preloaded native mappings invalidate this source execution probe");
            PlatformIdentityFixture.Configure("pc-linux");
            Invoke("Celeste.Tags.Initialize", Tags.Initialize);
            Invoke("Monocle.Tracker.Initialize", Tracker.Initialize);
            Invoke("Celeste.Level.constructor", () => level = new Level());
            Write(new { @event = "caller-level-created", level.Zoom, helperEntity = level.HelperEntity.GetType().FullName,
                trackedEntityTypes = Tracker.TrackedEntityTypes.Count, trackedComponentTypes = Tracker.TrackedComponentTypes.Count });
            Invoke("Celeste.Settings.constructor", () => Settings.Instance = new Settings());
            Invoke("Monocle.MInput.Initialize", MInput.Initialize);
            Invoke("room-header-input", () => Write(new { @event = "caller-input",
                input = RoomCoreCaller.PrepareHeader(level, Path.GetDirectoryName(path)) }));
            Invoke("Celeste.Level.LoadLevel(Respawn)", () => level.LoadLevel(Player.IntroTypes.Respawn));
            throw new InvalidOperationException("LoadLevel returned but remaining world caller and real tick driver are not yet assembled");
        }
        catch (Exception error)
        {
            Write(new { @event = "boundary", member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAtBoundary = NativeImportGuardProbe.NativeMappings(),
                loadLevelEntered = level != null && level.LastIntroType == Player.IntroTypes.Respawn,
                lastIntroType = level?.LastIntroType.ToString(),
                completedLifecycleFamilies = 0, status = "blocked-execution-prefix-not-lifecycle-coverage" });
            throw;
        }
    }
}
