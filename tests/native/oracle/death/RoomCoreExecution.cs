using System;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Xml;
using Celeste;
using Microsoft.Xna.Framework;
using Monocle;

namespace DeathOracle;

static class RoomCoreExecution
{
    static readonly PropertyInfo DeltaTime = typeof(Engine).GetProperty("DeltaTime", BindingFlags.Public | BindingFlags.Static);
    static readonly PropertyInfo RawDeltaTime = typeof(Engine).GetProperty("RawDeltaTime", BindingFlags.Public | BindingFlags.Static);
    static readonly PropertyInfo FrameCounter = typeof(Engine).GetProperty("FrameCounter", BindingFlags.Public | BindingFlags.Static);

    sealed class Probe : IDisposable
    {
        public readonly StreamWriter Trace;
        public readonly string Content;
        public string Member = "native-guard-preconditions";
        public Level Level;

        public Probe(string[] args)
        {
            if (args.Length != 2) throw new ArgumentException("Expected a private trace path");
            string path = Path.GetFullPath(args[1]);
            string root = Path.GetFullPath(".audit/native-player-death-respawn") + Path.DirectorySeparatorChar;
            if (!path.StartsWith(root, StringComparison.Ordinal)) throw new ArgumentException("Execution trace must remain private");
            Content = Path.GetDirectoryName(path);
            GFX.Game = new Atlas();
            using (var atlas = JsonDocument.Parse(File.ReadAllText(Path.Combine(Content, "atlas.json"))))
            {
                foreach (var entry in atlas.RootElement.EnumerateObject())
                {
                    var values = entry.Value.EnumerateArray().ToArray();
                    GFX.Game.AddMetadata(entry.Name, values[0].GetString(), values.Skip(1).Select(value => value.GetInt32()).ToArray());
                }
            }
            var xml = new XmlDocument();
            xml.Load(Path.Combine(Content, "Sprites.xml"));
            GFX.SpriteBank = new SpriteBank(GFX.Game, xml);
            PlayerSprite.CreateFramesMetadata("player");
            Trace = new StreamWriter(new FileStream(path, FileMode.CreateNew, FileAccess.Write, FileShare.Read)) { AutoFlush = true };
        }

        public void Dispose() => Trace.Dispose();

        public void Write(object row) => Trace.WriteLine(JsonSerializer.Serialize(row));

        public void Invoke(string name, Action action)
        {
            Member = name;
            Write(new { @event = "enter", member = Member });
            action();
            Write(new { @event = "return", member = Member });
        }

        public void Bootstrap()
        {
            if (!NativeImportGuard.Installed || NativeImportGuard.Attempts.Length != 0)
                throw new InvalidOperationException("Execution requires a fresh assembly-local native guard");
            var mappingsBefore = NativeImportGuardProbe.NativeMappings();
            Write(new { @event = "caller-preconditions", nativeMappingsBefore = mappingsBefore });
            if (mappingsBefore.Length != 0) throw new InvalidOperationException("Preloaded native mappings invalidate this source execution probe");
            PlatformIdentityFixture.Configure("pc-linux");
            Invoke("Celeste.Tags.Initialize", Tags.Initialize);
            Invoke("Monocle.Tracker.Initialize", Tracker.Initialize);
            Invoke("Celeste.Level.constructor", () => Level = new Level());
            Write(new { @event = "caller-level-created", Level.Zoom, helperEntity = Level.HelperEntity.GetType().FullName,
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
                input = RoomCoreCaller.PrepareHeader(Level, Content) }));
        }
    }

    static void SetEngineTick(float deltaTime)
    {
        DeltaTime.SetValue(null, deltaTime);
        RawDeltaTime.SetValue(null, deltaTime);
        FrameCounter.SetValue(null, (ulong)FrameCounter.GetValue(null) + 1);
    }

    static string Identity(object value) => value == null ? null : value.GetType().Name + "#" + RuntimeHelpers.GetHashCode(value);

    static string[] EntityTypes(Level level) => level.Entities.Select(entity => entity.GetType().Name).OrderBy(name => name).ToArray();

    static object WipeState(Level level) => level.Wipe == null ? null : new {
        type = Identity(level.Wipe), wipeIn = level.Wipe.WipeIn, level.Wipe.Percent, level.Wipe.Completed,
        onCompleteTarget = level.Wipe.OnComplete?.Target == level ? "level" : null,
        onCompleteMethod = level.Wipe.OnComplete?.Method.Name };

    public static void Run(string[] args)
    {
        using var probe = new Probe(args);
        try
        {
            probe.Bootstrap();
            probe.Invoke("Celeste.Level.LoadLevel(Respawn)", () => probe.Level.LoadLevel(Player.IntroTypes.Respawn));
            var player = probe.Level.Tracker.GetEntity<Player>();
            if (player == null) throw new InvalidOperationException("LoadLevel did not create the tracked Player");
            probe.Write(new { @event = "caller-load-level-return", state = player.StateMachine.State,
                wipe = WipeState(probe.Level), position = new[] { player.Position.X, player.Position.Y },
                entities = probe.Level.Entities.Count, solidTiles = probe.Level.SolidTiles != null, camera = probe.Level.Camera != null });
            if (player.StateMachine.State != 14) throw new InvalidOperationException("Respawn did not enter state14");
            int normalTick = -1;
            int liveTick = -1;
            for (int tick = 0; tick < 360; tick++)
            {
                SetEngineTick(1f / 60f);
                probe.Level.BeforeUpdate();
                probe.Level.Update();
                probe.Level.AfterUpdate();
                if (normalTick < 0 && player.StateMachine.State == 0)
                {
                    normalTick = tick;
                    probe.Write(new { @event = "caller-normal0", tick, state = player.StateMachine.State,
                        position = new[] { player.Position.X, player.Position.Y },
                        scale = new[] { player.Sprite.Scale.X, player.Sprite.Scale.Y },
                        wipe = WipeState(probe.Level), timeActive = probe.Level.TimeActive, rawTimeActive = probe.Level.RawTimeActive });
                    continue;
                }
                if (normalTick >= 0 && tick > normalTick)
                {
                    liveTick = tick;
                    probe.Write(new { @event = "caller-live-tick", tick, state = player.StateMachine.State,
                        position = new[] { player.Position.X, player.Position.Y }, dead = player.Dead,
                        speed = new[] { player.Speed.X, player.Speed.Y }, timeActive = probe.Level.TimeActive,
                        rawTimeActive = probe.Level.RawTimeActive, wipe = WipeState(probe.Level) });
                    break;
                }
            }
            if (normalTick < 0) throw new InvalidOperationException("Respawn state14 did not transition to Normal0");
            if (liveTick < 0) throw new InvalidOperationException("Normal0 live tick was not executed");
            if (player.StateMachine.State != 0 || player.Dead) throw new InvalidOperationException("Live tick left Normal0");
            probe.Write(new { @event = "completed", status = "respawn14-normal0-one-live-tick", normalTick, liveTick,
                state = player.StateMachine.State, position = new[] { player.Position.X, player.Position.Y },
                nativeAttempts = NativeImportGuard.Attempts.Length, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAfter = NativeImportGuardProbe.NativeMappings() });
            return;
        }
        catch (Exception error)
        {
            probe.Write(new { @event = "boundary", member = probe.Member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAtBoundary = NativeImportGuardProbe.NativeMappings(),
                loadLevelEntered = probe.Level != null && probe.Level.LastIntroType == Player.IntroTypes.Respawn,
                lastIntroType = probe.Level?.LastIntroType.ToString(),
                completedLifecycleFamilies = 0, status = "blocked-execution-prefix-not-lifecycle-coverage" });
            throw;
        }
    }

    static void PrepareEngineDriver(Level level)
    {
        var instance = RuntimeHelpers.GetUninitializedObject(typeof(Engine));
        typeof(Engine).GetProperty("Instance", BindingFlags.Public | BindingFlags.Static).GetSetMethod(true).Invoke(null, new object[] { instance });
        typeof(Engine).GetField("scene", BindingFlags.NonPublic | BindingFlags.Instance).SetValue(instance, level);
    }

    static void PrepareLevelLoaderFields(Level level)
    {
        level.Particles = new ParticleSystem(-8000, 400);
        level.Particles.Tag = Tags.Global;
        level.Add(level.Particles);
        level.ParticlesBG = new ParticleSystem(8000, 400);
        level.ParticlesBG.Tag = Tags.Global;
        level.Add(level.ParticlesBG);
        level.ParticlesFG = new ParticleSystem(-50000, 800);
        level.ParticlesFG.Tag = Tags.Global;
        level.ParticlesFG.Add(new MirrorReflection());
        level.Add(level.ParticlesFG);
        level.strawberriesDisplay = new TotalStrawberriesDisplay();
        level.Add(level.strawberriesDisplay);
    }

    static void LoadGuiAtlas(string content)
    {
        GFX.Gui = new Atlas();
        using var atlas = JsonDocument.Parse(File.ReadAllText(Path.Combine(content, "gui-atlas.json")));
        foreach (var entry in atlas.RootElement.EnumerateObject())
        {
            var values = entry.Value.EnumerateArray().ToArray();
            GFX.Gui.AddMetadata(entry.Name, values[0].GetString(), values.Skip(1).Select(value => value.GetInt32()).ToArray());
        }
    }

    public static void RunDeathRespawn(string[] args)
    {
        using var probe = new Probe(args);
        try
        {
            probe.Bootstrap();
            probe.Invoke("caller-engine-pooler", () => {
                var property = typeof(Engine).GetProperty("Pooler", BindingFlags.Public | BindingFlags.Static);
                property.GetSetMethod(true).Invoke(null, new object[] { new Pooler() });
                probe.Write(new { @event = "caller-pooler", initialized = Engine.Pooler != null,
                    claim = "Original Pooler constructor and Engine.Pooler setter; no Engine game loop" });
            });
            probe.Invoke("caller-engine-driver-scene", () => {
                PrepareEngineDriver(probe.Level);
                probe.Write(new { @event = "caller-engine-scene", scene = Identity(Engine.Scene),
                    sameLevel = Engine.Scene == probe.Level,
                    claim = "Declared driver environment for original Engine.Scene reads; caller never swaps Scene after death" });
            });
            probe.Invoke("caller-rumble-profile", () => {
                Settings.Instance.Rumble = RumbleAmount.Off;
                probe.Write(new { @event = "caller-rumble", profile = "declared-no-rumble-device", rumble = Settings.Instance.Rumble.ToString(),
                    claim = "Mechanically inert input feedback; original Input.Rumble body still executes its Off branch" });
            });
            LoadGuiAtlas(probe.Content);
            probe.Invoke("caller-level-loader-fields", () => PrepareLevelLoaderFields(probe.Level));
            probe.Invoke("Celeste.Level.LoadLevel(Respawn)", () => probe.Level.LoadLevel(Player.IntroTypes.Respawn));
            var firstPlayer = probe.Level.Tracker.GetEntity<Player>();
            if (firstPlayer == null || firstPlayer.StateMachine.State != 14)
                throw new InvalidOperationException("First Respawn did not create the tracked state14 Player");
            probe.Write(new { @event = "caller-first-load-level-return", player = Identity(firstPlayer), state = firstPlayer.StateMachine.State,
                position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y }, entities = probe.Level.Entities.Count,
                entityTypes = EntityTypes(probe.Level), wipe = WipeState(probe.Level), sessionDeaths = probe.Level.Session.Deaths });

            var driver = new FrameDriver { scene = probe.Level };
            int tick = 0;
            int firstNormalTick = -1;
            for (; tick < 360; tick++)
            {
                bool sceneRan = Tick(probe, driver, tick);
                if (firstPlayer.StateMachine.State == 0)
                {
                    firstNormalTick = tick;
                    probe.Write(new { @event = "caller-first-normal0", tick, sceneRan, state = firstPlayer.StateMachine.State,
                        player = Identity(firstPlayer), position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                        scale = new[] { firstPlayer.Sprite.Scale.X, firstPlayer.Sprite.Scale.Y }, wipe = WipeState(probe.Level),
                        timeActive = probe.Level.TimeActive, rawTimeActive = probe.Level.RawTimeActive });
                    break;
                }
            }
            if (firstNormalTick < 0) throw new InvalidOperationException("First Respawn14 did not reach Normal0");

            PlayerDeadBody corpse = null;
            probe.Invoke("caller-probe-player-die", () => corpse = firstPlayer.Die(new Vector2(0f, -1f)));
            if (corpse == null) throw new InvalidOperationException("Controlled probe Die returned no PlayerDeadBody");
            if (!firstPlayer.Dead || firstPlayer.Collidable || !firstPlayer.StateMachine.Locked)
                throw new InvalidOperationException("Original Die guards did not execute");
            probe.Write(new { @event = "caller-probe-die", player = Identity(firstPlayer), corpse = Identity(corpse),
                stimulus = "caller-invoked-original-Player.Die-direction-not-hazard-proof", direction = new[] { 0f, -1f },
                dead = firstPlayer.Dead, collidable = firstPlayer.Collidable, locked = firstPlayer.StateMachine.Locked,
                sessionDeaths = probe.Level.Session.Deaths, sessionDeathsInCurrentLevel = probe.Level.Session.DeathsInCurrentLevel,
                saveDeaths = SaveData.Instance.TotalDeaths, sceneEntities = probe.Level.Entities.Count,
                trackedPlayer = probe.Level.Tracker.GetEntity<Player>() == null ? null : Identity(probe.Level.Tracker.GetEntity<Player>()) });

            bool bounceObserved = false;
            bool deathEffectObserved = false;
            bool deathWipeObserved = false;
            bool reloadObserved = false;
            bool secondNormal = false;
            int deathWipeTick = -1;
            int reloadTick = -1;
            int secondNormalTick = -1;
            for (int deathTick = tick + 1; deathTick < tick + 900; deathTick++)
            {
                bool sceneRan = Tick(probe, driver, deathTick);
                var sprite = corpse.Get<PlayerSprite>();
                var tween = corpse.Get<Tween>();
                var effect = corpse.Get<DeathEffect>();
                if (!bounceObserved && tween != null)
                {
                    bounceObserved = true;
                    probe.Write(new { @event = "caller-corpse-bounce", tick = deathTick, sceneRan,
                        corpse = Identity(corpse), position = new[] { corpse.Position.X, corpse.Position.Y },
                        animation = sprite.CurrentAnimationID, frame = sprite.CurrentAnimationFrame,
                        rotation = sprite.Rotation, scale = new[] { sprite.Scale.X, sprite.Scale.Y },
                        tween = new { tween.Active, tween.Percent, tween.TimeLeft }, freezeAfter = Engine.FreezeTimer });
                }
                if (!deathEffectObserved && effect != null)
                {
                    deathEffectObserved = true;
                    probe.Write(new { @event = "caller-corpse-death-effect", tick = deathTick, sceneRan,
                        corpse = Identity(corpse), position = new[] { corpse.Position.X, corpse.Position.Y },
                        effect = new { effect.Percent, effect.Duration }, tween = tween == null ? null : new { tween.Active, tween.Percent } });
                }
                var wipe = probe.Level.Wipe;
                if (!deathWipeObserved && wipe != null && !wipe.WipeIn)
                {
                    deathWipeObserved = true;
                    deathWipeTick = deathTick;
                    probe.Write(new { @event = "caller-death-wipe", tick = deathTick, sceneRan, wipe = WipeState(probe.Level),
                        corpse = Identity(corpse), corpseInScene = corpse.Scene != null,
                        position = new[] { corpse.Position.X, corpse.Position.Y },
                        animation = sprite.CurrentAnimationID, effect = effect == null ? null : new { effect.Percent, effect.Duration },
                        sessionDeaths = probe.Level.Session.Deaths, entities = probe.Level.Entities.Count });
                }
                var current = probe.Level.Tracker.GetEntity<Player>();
                if (!reloadObserved && current != null && current != firstPlayer)
                {
                    reloadObserved = true;
                    reloadTick = deathTick;
                    probe.Write(new { @event = "caller-reload-second-load", tick = deathTick, sceneRan,
                        previousPlayer = Identity(firstPlayer), player = Identity(current), state = current.StateMachine.State,
                        lastIntroType = probe.Level.LastIntroType.ToString(), position = new[] { current.Position.X, current.Position.Y },
                        corpse = Identity(corpse), corpseInScene = corpse.Scene != null,
                        corpseRemoved = corpse.Scene == null && !probe.Level.Entities.Contains(corpse),
                        sessionDeaths = probe.Level.Session.Deaths, sessionDeathsInCurrentLevel = probe.Level.Session.DeathsInCurrentLevel,
                        sessionTime = probe.Level.Session.Time, sessionDashes = probe.Level.Session.Dashes,
                        respawnPoint = probe.Level.Session.RespawnPoint == null ? null : new[] { probe.Level.Session.RespawnPoint.Value.X, probe.Level.Session.RespawnPoint.Value.Y },
                        wipe = WipeState(probe.Level), entities = probe.Level.Entities.Count,
                        entityTypes = EntityTypes(probe.Level) });
                    if (current.StateMachine.State != 14) throw new InvalidOperationException("Second LoadLevel did not return state14");
                }
                if (reloadObserved && current != null && current != firstPlayer && current.StateMachine.State == 0)
                {
                    secondNormal = true;
                    secondNormalTick = deathTick;
                    probe.Write(new { @event = "caller-second-normal0", tick = deathTick, sceneRan, player = Identity(current),
                        state = current.StateMachine.State, position = new[] { current.Position.X, current.Position.Y },
                        speed = new[] { current.Speed.X, current.Speed.Y },
                        scale = new[] { current.Sprite.Scale.X, current.Sprite.Scale.Y }, wipe = WipeState(probe.Level),
                        timeActive = probe.Level.TimeActive, rawTimeActive = probe.Level.RawTimeActive, sessionDeaths = probe.Level.Session.Deaths });
                    break;
                }
            }
            if (!deathWipeObserved) throw new InvalidOperationException("Original PlayerDeadBody End never created the death wipe");
            if (!reloadObserved) throw new InvalidOperationException("Death wipe completion never reloaded into a second Player");
            if (!secondNormal) throw new InvalidOperationException("Second Respawn14 did not reach Normal0");

            var resumedPlayer = probe.Level.Tracker.GetEntity<Player>();
            int resumedTick = secondNormalTick + 1;
            bool resumedSceneRan = Tick(probe, driver, resumedTick);
            probe.Write(new { @event = "caller-resumed-live-tick", tick = resumedTick, sceneRan = resumedSceneRan,
                player = Identity(resumedPlayer), state = resumedPlayer.StateMachine.State, dead = resumedPlayer.Dead,
                position = new[] { resumedPlayer.Position.X, resumedPlayer.Position.Y },
                speed = new[] { resumedPlayer.Speed.X, resumedPlayer.Speed.Y },
                timeActive = probe.Level.TimeActive, rawTimeActive = probe.Level.RawTimeActive, wipe = WipeState(probe.Level),
                sessionDeaths = probe.Level.Session.Deaths, inputSampled = false });
            if (resumedPlayer.StateMachine.State != 0 || resumedPlayer.Dead)
                throw new InvalidOperationException("Resumed tick left Normal0");
            probe.Write(new { @event = "completed", status = "original-die-corpse-wipe-reload-second-respawn14-normal0-one-resumed-tick",
                firstNormalTick, deathWipeTick, reloadTick, secondNormalTick, resumedTick,
                firstPlayer = Identity(firstPlayer), secondPlayer = Identity(resumedPlayer), corpse = Identity(corpse),
                corpseRemoved = corpse.Scene == null && !probe.Level.Entities.Contains(corpse),
                corpseCreated = 1, deathWipes = 1, reloads = 1, sourceLoadLevelCalls = 2, resumedNormalUpdates = 1,
                deathWipeOnComplete = "Level.Reload", engineScene = Identity(Engine.Scene), sameLevelAfterResume = Engine.Scene == probe.Level,
                firstLoadState = 14, secondLoadState = 14, resumedState = resumedPlayer.StateMachine.State,
                sessionDeaths = probe.Level.Session.Deaths, saveDeaths = SaveData.Instance.TotalDeaths,
                nativeAttempts = NativeImportGuard.Attempts.Length, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, hazardOrderingDirectionalCollisionDeathParity = false,
                claim = "Caller-invoked original Player.Die stimulus only; not a hazard, directional, or eight-family closure" });
            return;
        }
        catch (Exception error)
        {
            probe.Write(new { @event = "boundary", member = probe.Member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAtBoundary = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, status = "blocked-death-respawn-prefix-not-lifecycle-coverage" });
            throw;
        }
    }

    static bool Tick(Probe probe, FrameDriver driver, int tick)
    {
        probe.Member = "driver-tick";
        SetEngineTick(1f / 60f);
        bool freezeBefore = Engine.FreezeTimer > 0f;
        driver.scene = probe.Level;
        driver.Tick();
        bool sceneRan = !freezeBefore && !driver.DashAssistFreeze;
        probe.Write(new { @event = "driver-tick", tick, sceneRan, inputSampled = false,
            freezeBefore, freezeAfter = Engine.FreezeTimer, timeActive = probe.Level.TimeActive,
            rawTimeActive = probe.Level.RawTimeActive, player = Identity(probe.Level.Tracker.GetEntity<Player>()),
            state = probe.Level.Tracker.GetEntity<Player>()?.StateMachine.State, entities = probe.Level.Entities.Count,
            corpse = Identity(probe.Level.Entities.FirstOrDefault(entity => entity is PlayerDeadBody)),
            wipe = WipeState(probe.Level), sessionDeaths = probe.Level.Session.Deaths });
        return sceneRan;
    }
}
