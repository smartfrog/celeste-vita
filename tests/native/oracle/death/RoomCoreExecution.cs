using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Xml;
using Celeste;
using Monocle;

namespace DeathOracle;

static class RoomCoreExecution
{
    static readonly PropertyInfo DeltaTime = typeof(Engine).GetProperty("DeltaTime", BindingFlags.Public | BindingFlags.Static);
    static readonly PropertyInfo RawDeltaTime = typeof(Engine).GetProperty("RawDeltaTime", BindingFlags.Public | BindingFlags.Static);
    static readonly PropertyInfo FrameCounter = typeof(Engine).GetProperty("FrameCounter", BindingFlags.Public | BindingFlags.Static);

    static void SetEngineTick(float deltaTime)
    {
        DeltaTime.SetValue(null, deltaTime);
        RawDeltaTime.SetValue(null, deltaTime);
        FrameCounter.SetValue(null, (ulong)FrameCounter.GetValue(null) + 1);
    }

    public static void Run(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("Expected room-core-execute and a fresh private trace path");
        string path = Path.GetFullPath(args[1]);
        string root = Path.GetFullPath(".audit/native-player-death-respawn") + Path.DirectorySeparatorChar;
        if (!path.StartsWith(root, StringComparison.Ordinal)) throw new ArgumentException("Execution trace must remain private");
        string content = Path.GetDirectoryName(path);
        GFX.Game = new Atlas();
        using (var atlas = JsonDocument.Parse(File.ReadAllText(Path.Combine(content, "atlas.json"))))
        {
            foreach (var entry in atlas.RootElement.EnumerateObject())
            {
                var values = entry.Value.EnumerateArray().ToArray();
                GFX.Game.AddMetadata(entry.Name, values[0].GetString(), values.Skip(1).Select(value => value.GetInt32()).ToArray());
            }
        }
        var xml = new XmlDocument();
        xml.Load(Path.Combine(content, "Sprites.xml"));
        GFX.SpriteBank = new SpriteBank(GFX.Game, xml);
        PlayerSprite.CreateFramesMetadata("player");
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
            Invoke("caller-audio-inert-profile", () => {
                int events = 0;
                foreach (var field in typeof(SFX).GetFields(BindingFlags.Static | BindingFlags.Public))
                    if (field.FieldType == typeof(string) && field.GetValue(null) is string value && value.Length > 0)
                    {
                        Audio.cachedEventDescriptions[value] = null;
                        events++;
                    }
                Write(new { @event = "caller-audio", description = "declared-inert-event-description-cache", events });
            });
            Invoke("Monocle.MInput.Initialize", MInput.Initialize);
            Invoke("Celeste.Input.Initialize", Input.Initialize);
            Invoke("room-header-input", () => Write(new { @event = "caller-input",
                input = RoomCoreCaller.PrepareHeader(level, Path.GetDirectoryName(path)) }));
            Invoke("Celeste.Level.LoadLevel(Respawn)", () => level.LoadLevel(Player.IntroTypes.Respawn));
            var player = level.Tracker.GetEntity<Player>();
            if (player == null) throw new InvalidOperationException("LoadLevel did not create the tracked Player");
            Write(new { @event = "caller-load-level-return", state = player.StateMachine.State,
                wipe = level.Wipe == null ? null : new { level.Wipe.Percent, level.Wipe.Completed },
                position = new[] { player.Position.X, player.Position.Y }, entities = level.Entities.Count,
                solidTiles = level.SolidTiles != null, camera = level.Camera != null });
            if (player.StateMachine.State != 14) throw new InvalidOperationException("Respawn did not enter state14");
            int normalTick = -1;
            int liveTick = -1;
            for (int tick = 0; tick < 360; tick++)
            {
                SetEngineTick(1f / 60f);
                level.BeforeUpdate();
                level.Update();
                level.AfterUpdate();
                if (normalTick < 0 && player.StateMachine.State == 0)
                {
                    normalTick = tick;
                    Write(new { @event = "caller-normal0", tick, state = player.StateMachine.State,
                        position = new[] { player.Position.X, player.Position.Y },
                        scale = new[] { player.Sprite.Scale.X, player.Sprite.Scale.Y },
                        wipe = level.Wipe == null ? null : new { level.Wipe.Percent, level.Wipe.Completed },
                        timeActive = level.TimeActive, rawTimeActive = level.RawTimeActive });
                    continue;
                }
                if (normalTick >= 0 && tick > normalTick)
                {
                    liveTick = tick;
                    Write(new { @event = "caller-live-tick", tick, state = player.StateMachine.State,
                        position = new[] { player.Position.X, player.Position.Y }, dead = player.Dead,
                        speed = new[] { player.Speed.X, player.Speed.Y }, timeActive = level.TimeActive,
                        rawTimeActive = level.RawTimeActive, wipe = level.Wipe == null ? null : new { level.Wipe.Percent, level.Wipe.Completed } });
                    break;
                }
            }
            if (normalTick < 0) throw new InvalidOperationException("Respawn state14 did not transition to Normal0");
            if (liveTick < 0) throw new InvalidOperationException("Normal0 live tick was not executed");
            if (player.StateMachine.State != 0 || player.Dead) throw new InvalidOperationException("Live tick left Normal0");
            Write(new { @event = "completed", status = "respawn14-normal0-one-live-tick", normalTick, liveTick,
                state = player.StateMachine.State, position = new[] { player.Position.X, player.Position.Y },
                nativeAttempts = NativeImportGuard.Attempts.Length, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAfter = NativeImportGuardProbe.NativeMappings() });
            return;
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
