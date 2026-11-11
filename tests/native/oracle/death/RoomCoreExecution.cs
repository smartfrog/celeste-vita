using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text.Json;
using System.Xml;
using Celeste;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Content;
using Microsoft.Xna.Framework.Input;
using Monocle;

namespace DeathOracle;

static partial class RoomCoreExecution
{
    static readonly PropertyInfo DeltaTime = typeof(Engine).GetProperty("DeltaTime", BindingFlags.Public | BindingFlags.Static);
    static readonly PropertyInfo RawDeltaTime = typeof(Engine).GetProperty("RawDeltaTime", BindingFlags.Public | BindingFlags.Static);
    static readonly PropertyInfo FrameCounter = typeof(Engine).GetProperty("FrameCounter", BindingFlags.Public | BindingFlags.Static);
    static readonly FieldInfo HurtboxField = typeof(Player).GetField("hurtbox", BindingFlags.NonPublic | BindingFlags.Instance);
    static readonly FieldInfo OnGroundField = typeof(Player).GetField("onGround", BindingFlags.NonPublic | BindingFlags.Instance);
    static readonly FieldInfo SpikeSizeField = typeof(Spikes).GetField("size", BindingFlags.NonPublic | BindingFlags.Instance);

    sealed class Probe : IDisposable
    {
        public readonly StreamWriter Trace;
        public readonly string Content;
        public string Member = "native-guard-preconditions";
        public Level Level;

        public Probe(string[] args, int traceIndex = 1)
        {
            if (args.Length <= traceIndex) throw new ArgumentException("Expected a private trace path");
            string path = Path.GetFullPath(args[traceIndex]);
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

    static string[] KeyNames(Binding binding) => binding == null ? Array.Empty<string>()
        : binding.Keyboard.Select(key => key.ToString()).ToArray();

    static float[] Bounce(PlayerDeadBody corpse)
    {
        var field = typeof(PlayerDeadBody).GetField("bounce", BindingFlags.NonPublic | BindingFlags.Instance);
        if (field == null) throw new InvalidOperationException("PlayerDeadBody.bounce missing");
        var value = (Vector2)field.GetValue(corpse);
        return new[] { value.X, value.Y };
    }

    static List<Entity> PendingEntities(Level level)
    {
        var field = typeof(EntityList).GetField("toAdd", BindingFlags.NonPublic | BindingFlags.Instance);
        if (field == null || field.GetValue(level.Entities) is not List<Entity> pending)
            throw new InvalidOperationException("EntityList.toAdd missing");
        return pending;
    }

    static PlayerDeadBody PendingCorpse(Level level) => PendingEntities(level).OfType<PlayerDeadBody>().FirstOrDefault();

    static PlayerDeadBody[] PendingCorpses(Level level) => PendingEntities(level).OfType<PlayerDeadBody>().ToArray();

    static PlayerDeadBody[] CommittedCorpses(Level level) => level.Entities.OfType<PlayerDeadBody>().ToArray();

    static int RandomCalls()
    {
        if (Calc.Random is not PresentationOracle.TracedRandom random)
            throw new InvalidOperationException("Calc.Random is not the traced source RNG");
        return random.Calls;
    }

    static int SpikeSize(Spikes spike)
    {
        if (SpikeSizeField == null || SpikeSizeField.GetValue(spike) is not int size)
            throw new InvalidOperationException("Spikes.size missing");
        return size;
    }

    static float[] SpikeBounds(Spikes spike) => ColliderBounds(spike.Collider, spike);

    static bool IsGlobal(Entity entity) => (entity.Tag & (int)Tags.Global) != 0;

    static List<Spikes> RawSpikes(Level level, Spikes fixture) => level.Entities.OfType<Spikes>()
        .Where(spike => !ReferenceEquals(spike, fixture) && spike.Collider != null)
        .OrderBy(spike => spike.Collider.AbsoluteLeft).ThenBy(spike => spike.Collider.AbsoluteTop).ToList();

    static object[] RawHazardSnapshot(Level level, Spikes fixture) => RawSpikes(level, fixture)
        .Select((spike, index) => new {
            id = "raw-" + (index + 1), identity = Identity(spike), type = "Spikes",
            direction = spike.Direction.ToString(),
            position = new[] { spike.Position.X, spike.Position.Y },
            size = SpikeSize(spike), bounds = SpikeBounds(spike)
        }).ToArray();

    static string RawGeometryJson(Level level, Spikes fixture) => JsonSerializer.Serialize(
        RawSpikes(level, fixture).Select(spike => new { direction = spike.Direction.ToString(), bounds = SpikeBounds(spike) }).ToArray());

    static object[] GlobalEntitySnapshot(Level level) => level.Entities.Where(IsGlobal)
        .Select(entity => new { identity = Identity(entity), type = entity.GetType().Name })
        .OrderBy(entry => entry.type).ThenBy(entry => entry.identity).ToArray();

    static object FixtureView(Spikes fixture) => new {
        id = "explicit-fixture-1", type = "Spikes", direction = fixture.Direction.ToString(),
        position = new[] { fixture.Position.X, fixture.Position.Y }, size = SpikeSize(fixture),
        bounds = SpikeBounds(fixture),
        constructor = "Spikes(Vector2(64,155),16,Spikes.Directions.Left,\"default\")"
    };

    static string EntityId(Spikes spike, Spikes fixture, List<Spikes> raw)
    {
        if (ReferenceEquals(spike, fixture)) return "explicit-fixture-1";
        int index = raw.IndexOf(spike);
        return index >= 0 ? "raw-" + (index + 1) : Identity(spike);
    }

    static object[] PlayerColliderOrder(Level level, Spikes fixture)
    {
        var raw = RawSpikes(level, fixture);
        return level.Tracker.GetComponents<PlayerCollider>().Select((component, order) => {
            var spike = component.Entity as Spikes;
            return new {
                order, id = spike == null ? Identity(component.Entity) : EntityId(spike, fixture, raw),
                identity = Identity(component.Entity),
                entityType = component.Entity == null ? null : component.Entity.GetType().Name,
                direction = spike?.Direction.ToString(),
                position = spike == null ? null : new[] { spike.Position.X, spike.Position.Y },
                bounds = spike?.Collider == null ? null : SpikeBounds(spike)
            };
        }).ToArray();
    }

    static (int Order, string Id) FirstEligible(Level level, Spikes fixture, float[] hurtbox, float speedX, float speedY)
    {
        var raw = RawSpikes(level, fixture);
        var components = level.Tracker.GetComponents<PlayerCollider>();
        for (int order = 0; order < components.Count; order++)
        {
            if (components[order].Entity is not Spikes spike || spike.Collider == null) continue;
            var bounds = SpikeBounds(spike);
            bool eligible = spike.Direction switch {
                Spikes.Directions.Up => Overlaps(hurtbox, bounds) && speedY >= 0f && hurtbox[3] <= bounds[3],
                Spikes.Directions.Down => Overlaps(hurtbox, bounds) && speedY <= 0f,
                Spikes.Directions.Left => Overlaps(hurtbox, bounds) && speedX >= 0f,
                Spikes.Directions.Right => Overlaps(hurtbox, bounds) && speedX <= 0f,
                _ => false
            };
            if (eligible) return (order, EntityId(spike, fixture, raw));
        }
        return (-1, null);
    }

    static string[] EntityTypes(Level level) => level.Entities.Select(entity => entity.GetType().Name).OrderBy(name => name).ToArray();

    static Collider Hurtbox(Player player)
    {
        if (HurtboxField == null || HurtboxField.GetValue(player) is not Collider hurtbox)
            throw new InvalidOperationException("Player.hurtbox missing");
        return hurtbox;
    }

    static float[] ColliderBounds(Collider collider, Entity entity) => new[] {
        entity.Position.X + collider.Left, entity.Position.Y + collider.Top,
        entity.Position.X + collider.Right, entity.Position.Y + collider.Bottom };

    static bool Overlaps(float[] a, float[] b) =>
        a[0] < b[2] && a[2] > b[0] && a[1] < b[3] && a[3] > b[1];

    static bool CachedOnGround(Player player)
    {
        if (OnGroundField == null || OnGroundField.GetValue(player) is not bool onGround)
            throw new InvalidOperationException("Player.onGround missing");
        return onGround;
    }

    static T PrivateField<T>(Player player, string name)
    {
        var field = typeof(Player).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance);
        if (field == null || field.GetValue(player) is not T value)
            throw new InvalidOperationException("Player." + name + " missing");
        return value;
    }

    static object SpeedXInterveningState(Player player) => new {
        explodeLaunchBoostTimer = PrivateField<float>(player, "explodeLaunchBoostTimer"),
        wallBoostTimer = PrivateField<float>(player, "wallBoostTimer"),
        wallSpeedRetentionTimer = PrivateField<float>(player, "wallSpeedRetentionTimer"),
        hopWaitX = PrivateField<int>(player, "hopWaitX"),
        forceMoveXTimer = PrivateField<float>(player, "forceMoveXTimer"),
        forceMoveX = PrivateField<int>(player, "forceMoveX"),
        dashPressed = Input.Dash.Pressed,
        jumpCheck = Input.Jump.Check,
        grabCheck = Input.GrabCheck,
        ducking = player.Ducking,
        holding = player.Holding == null ? null : player.Holding.GetType().Name };

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

    public static void RunStaticSpike(string[] args)
    {
        if (args.Length != 3 || (args[1] != "lethal" && args[1] != "nonlethal"
            && args[1] != "geometry-nonlethal" && args[1] != "zero-lethal"
            && args[1] != "plane-equality-lethal" && args[1] != "left-lethal"
            && args[1] != "left-nonlethal" && args[1] != "left-zero-lethal"
            && args[1] != "simultaneous-fixture-lethal"))
            throw new ArgumentException("Expected room-core-up-spike lethal|nonlethal|geometry-nonlethal|zero-lethal|plane-equality-lethal|left-lethal|left-nonlethal|left-zero-lethal|simultaneous-fixture-lethal <private trace path>");
        string scenario = args[1];
        bool simultaneous = scenario == "simultaneous-fixture-lethal";
        bool left = scenario.StartsWith("left-", StringComparison.Ordinal);
        bool leftZero = scenario == "left-zero-lethal";
        bool lethal = left ? scenario == "left-lethal" || leftZero
            : scenario == "lethal" || scenario == "zero-lethal" || scenario == "plane-equality-lethal" || simultaneous;
        string stem = simultaneous ? "simultaneous-hazard" : left ? "left-spike" : "up-spike";
        using var probe = new Probe(args, 2);
        try
        {
            probe.Bootstrap();
            probe.Invoke("caller-engine-pooler", () => {
                var property = typeof(Engine).GetProperty("Pooler", BindingFlags.Public | BindingFlags.Static);
                property.GetSetMethod(true).Invoke(null, new object[] { new Pooler() });
                probe.Write(new { @event = "caller-pooler", initialized = Engine.Pooler != null });
            });
            probe.Invoke("caller-engine-driver-scene", () => {
                PrepareEngineDriver(probe.Level);
                probe.Write(new { @event = "caller-engine-scene", scene = Identity(Engine.Scene), sameLevel = Engine.Scene == probe.Level });
            });
            probe.Invoke("caller-rumble-profile", () => {
                Settings.Instance.Rumble = RumbleAmount.Off;
            });
            LoadGuiAtlas(probe.Content);
            probe.Invoke("caller-level-loader-fields", () => PrepareLevelLoaderFields(probe.Level));
            probe.Invoke("Celeste.Level.LoadLevel(Respawn)", () => probe.Level.LoadLevel(Player.IntroTypes.Respawn));
            var firstPlayer = probe.Level.Tracker.GetEntity<Player>();
            if (firstPlayer == null || firstPlayer.StateMachine.State != 14)
                throw new InvalidOperationException("Static-spike probe requires first Respawn14 Player");
            var driver = new FrameDriver { scene = probe.Level };
            int firstNormalTick = -1;
            for (int tick = 0; tick < 360; tick++)
            {
                Tick(probe, driver, tick);
                if (firstPlayer.StateMachine.State == 0) { firstNormalTick = tick; break; }
            }
            if (firstNormalTick < 0) throw new InvalidOperationException("First Respawn14 did not reach Normal0");
            var spike = probe.Level.Entities.OfType<Spikes>()
                .Where(s => s.Direction == (left ? Spikes.Directions.Left : Spikes.Directions.Up) && s.Collider != null)
                .OrderBy(s => s.Collider.AbsoluteLeft).ThenBy(s => s.Collider.AbsoluteTop).FirstOrDefault();
            if (spike == null) throw new InvalidOperationException("Room has no static " + (left ? "Left" : "Up") + " spike");
            int sessionDeathsBefore = probe.Level.Session.Deaths;
            int deathsInCurrentLevelBefore = probe.Level.Session.DeathsInCurrentLevel;
            int saveDeathsBefore = SaveData.Instance.TotalDeaths;
            float spikeBottom = spike.Collider.AbsoluteBottom;
            float spikeCenterX = spike.Collider.AbsoluteLeft + spike.Collider.Width / 2f;
            int collisionTick = firstNormalTick + 1;
            float zeroCalibratedCheckSpeedX = 0f;
            float zeroCalibratedCheckSpeedY = 0f;
            bool planeEquality = scenario == "plane-equality-lethal" || simultaneous;
            bool hazardProbe = scenario == "zero-lethal" || planeEquality;
            Spikes fixture = null;
            object[] rawHazardsBefore = null;
            string rawGeometryBefore = null;
            object[] globalEntitiesBefore = null;
            string globalGeometryBefore = null;
            string solidTilesIdentityBefore = null;
            int rngCallsBeforeFixture = 0;
            float hurtboxBottomOffset = 0f;
            float[] hazardHurtboxBounds = null;
            float[] hazardSpikeBounds = null;
            float[] leftSeedPosition = null;
            float[] leftSeedSpeed = null;
            float[] leftSeedHurtboxBounds = null;
            float[] leftSpikeBounds = null;
            Vector2 leftSeedRemainder = Vector2.Zero;
            Vector2 hazardRemainderBefore = Vector2.Zero;
            if (scenario == "geometry-nonlethal")
            {
                firstPlayer.Position = new Vector2(spikeCenterX, spikeBottom + 3f);
                firstPlayer.Speed = new Vector2(0f, -5f);
                probe.Write(new { @event = $"caller-{stem}-setup", scenario, inputSampled = false,
                    spikePosition = new[] { spike.Position.X, spike.Position.Y },
                    spikeBounds = ColliderBounds(spike.Collider, spike), spikeDirection = spike.Direction.ToString(),
                    playerPosition = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                    playerSpeed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                    state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead,
                    sessionDeaths = sessionDeathsBefore, saveDeaths = saveDeathsBefore,
                    poseBoundary = "caller-seeded in-air pose below the Up spike base; the 9px hurtbox reaches the 3px spike band while Bottom exceeds spike.Bottom; bounded predicate cell, not natural traversal" });
                int observedCells = 0;
                for (int geometryTick = firstNormalTick + 1; geometryTick <= firstNormalTick + 6; geometryTick++)
                {
                    Tick(probe, driver, geometryTick);
                    var hurtbox = Hurtbox(firstPlayer);
                    var hurtboxBounds = ColliderBounds(hurtbox, firstPlayer);
                    var spikeBounds = ColliderBounds(spike.Collider, spike);
                    bool overlap = Overlaps(hurtboxBounds, spikeBounds);
                    bool velocityTrue = firstPlayer.Speed.Y >= 0f;
                    bool geometryTrue = hurtboxBounds[3] <= spikeBounds[3];
                    bool cell = overlap && velocityTrue && !geometryTrue;
                    if (cell) observedCells++;
                    probe.Write(new { @event = "caller-up-spike-geometry-tick", scenario, tick = geometryTick,
                        speed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y }, speedY = firstPlayer.Speed.Y,
                        position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                        hurtboxBounds, spikeBounds,
                        overlap, velocityTrue, geometryTrue,
                        cell = cell ? "velocity-true-geometry-false" : "other",
                        onGroundField = CachedOnGround(firstPlayer), onGroundQuery = firstPlayer.OnGround(),
                        dead = firstPlayer.Dead, collidable = firstPlayer.Collidable,
                        locked = firstPlayer.StateMachine.Locked,
                        corpse = Identity(PendingCorpse(probe.Level) ?? probe.Level.Entities.OfType<PlayerDeadBody>().FirstOrDefault()),
                        wipe = WipeState(probe.Level), sessionDeaths = probe.Level.Session.Deaths,
                        saveDeaths = SaveData.Instance.TotalDeaths, inputSampled = false });
                }
                if (observedCells == 0) throw new InvalidOperationException("Geometry-false/velocity-true cell was not observed");
                if (firstPlayer.Dead) throw new InvalidOperationException("Geometry-false boundary unexpectedly killed the player");
                probe.Write(new { @event = "completed", status = "up-spike-geometry-nonlethal-source-collision-alive-no-lifecycle",
                    scenario, collisionTick, geometryTicks = 6, observedCells,
                    sessionDeaths = probe.Level.Session.Deaths, saveDeaths = SaveData.Instance.TotalDeaths,
                    corpseCreated = 0, deathWipes = 0, reloads = 0, inputSampled = false,
                    sourceProfile = "source-synced-6b-01; static Up spike; single-room-header; partial map; no full-family/traversal/input proof",
                    profileBoundary = "geometry-false uses a caller-seeded in-air pose below the Up spike base; the real PlayerCollider.Check/OnCollide predicate is exercised with actual overlap and Speed.Y>=0 but this is not a natural traversal path",
                    nativeAttempts = NativeImportGuard.Attempts.Length,
                    nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                    completedLifecycleFamilies = 0, hazardOrderingDirectionalCollisionDeathParity = false,
                    claim = "Existing static Up spike, real ticks with overlap and actual Speed.Y>=0 while player.Bottom>spike.Bottom; unchanged OnCollide geometry branch stays alive; not traversal/input/full-family proof" });
                return;
            }
            if (hazardProbe)
            {
                float zeroGravityStep = 0f;
                float safeX = spike.Collider.AbsoluteLeft - 10f;
                firstPlayer.Position = new Vector2(safeX, spikeBottom);
                firstPlayer.Speed = Vector2.Zero;
                if (simultaneous)
                {
                    rawHazardsBefore = RawHazardSnapshot(probe.Level, null);
                    rawGeometryBefore = RawGeometryJson(probe.Level, null);
                    globalEntitiesBefore = GlobalEntitySnapshot(probe.Level);
                    globalGeometryBefore = JsonSerializer.Serialize(globalEntitiesBefore);
                    solidTilesIdentityBefore = Identity(probe.Level.SolidTiles);
                    rngCallsBeforeFixture = RandomCalls();
                    fixture = new Spikes(new Vector2(64f, 155f), 16, Spikes.Directions.Left, "default");
                    probe.Level.Add(fixture);
                }
                probe.Write(new { @event = $"caller-{stem}-setup", scenario, inputSampled = false,
                    spikePosition = new[] { spike.Position.X, spike.Position.Y },
                    spikeBounds = ColliderBounds(spike.Collider, spike), spikeDirection = spike.Direction.ToString(),
                    playerPosition = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                    playerSpeed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                    state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead,
                    sessionDeaths = sessionDeathsBefore, saveDeaths = saveDeathsBefore,
                    poseBoundary = simultaneous
                        ? "caller-declared explicit fixture is constructed and Level.Add'ed before the safe tick at (30,168); the unchanged tick commits it through EntityList.UpdateLists/Added/Tracker without death, then measures the source gravity step"
                        : "caller uses a safe in-air pose away from the spike to measure one source gravity step; the collision seed is the observed negative of that step, never a zero seed" });
                if (simultaneous)
                {
                    var safeHurtbox = ColliderBounds(Hurtbox(firstPlayer), firstPlayer);
                    bool safeRawOverlap = Overlaps(safeHurtbox, ColliderBounds(spike.Collider, spike));
                    bool safeFixtureOverlap = Overlaps(safeHurtbox, SpikeBounds(fixture));
                    probe.Write(new { @event = "caller-simultaneous-fixture-add", scenario, tick = collisionTick,
                        rawHazardCount = ((object[])rawHazardsBefore).Length, rawHazards = rawHazardsBefore,
                        fixture = FixtureView(fixture),
                        fixtureInEntities = probe.Level.Entities.Contains(fixture),
                        fixtureScene = fixture.Scene != null,
                        fixturePendingCommit = PendingEntities(probe.Level).Contains(fixture),
                        fixtureTag = fixture.Tag, fixtureIsGlobal = IsGlobal(fixture),
                        rngCallsBeforeFixture, rngCallsAfterConstruct = RandomCalls(),
                        rngCallsAfterAdd = RandomCalls(),
                        rngCallsDeltaBeforeCommit = RandomCalls() - rngCallsBeforeFixture,
                        playerSafePosition = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                        playerSafeHurtboxBounds = safeHurtbox,
                        safeRawOverlap, safeFixtureOverlap, safeOverlap = safeRawOverlap || safeFixtureOverlap,
                        addedVia = "Level.Add(Entity) -> Scene.Add -> EntityList.Add; commit on the next BeforeUpdate via EntityList.UpdateLists -> Entity.Added -> Tracker.ComponentAdded",
                        claim = "Explicit caller-controlled fixture delta; five raw room hazards unchanged and not moved" });
                }
                int gravityStepTick = collisionTick;
                int rngCallsAfterBeforeUpdate = 0;
                if (simultaneous)
                    TickCommittingFixture(probe, driver, gravityStepTick, out rngCallsAfterBeforeUpdate);
                else
                    Tick(probe, driver, gravityStepTick);
                if (simultaneous)
                {
                    var rawHazardsAfter = RawHazardSnapshot(probe.Level, fixture);
                    int fixtureCount = probe.Level.Entities.OfType<Spikes>().Count(candidate => ReferenceEquals(candidate, fixture));
                    bool committed = fixture.Scene == probe.Level && probe.Level.Entities.Contains(fixture);
                    bool rawGeometryUnchanged = RawGeometryJson(probe.Level, fixture) == rawGeometryBefore;
                    int rngCallsAfterTick = RandomCalls();
                    if (!committed || fixtureCount != 1 || rawHazardsAfter.Length != 5 || !rawGeometryUnchanged)
                        throw new InvalidOperationException("Fixture did not commit through the original entity list while preserving the five raw hazards");
                    if (rngCallsAfterTick < rngCallsBeforeFixture)
                        throw new InvalidOperationException("Fixture commit rewound the source RNG");
                    probe.Write(new { @event = "caller-simultaneous-fixture-commit", scenario, tick = gravityStepTick,
                        committed, fixtureInEntities = probe.Level.Entities.Contains(fixture),
                        fixtureScene = fixture.Scene == probe.Level, fixtureTag = fixture.Tag,
                        fixtureIsGlobal = IsGlobal(fixture), fixture = FixtureView(fixture),
                        rawHazardCount = rawHazardsAfter.Length, fixtureCount, rawHazards = rawHazardsAfter,
                        rawGeometryUnchanged,
                        rngCallsBeforeFixture, rngCallsAfterAdded = rngCallsAfterBeforeUpdate,
                        rngCallsAdded = rngCallsAfterBeforeUpdate - rngCallsBeforeFixture,
                        rngCallsAfterTick, rngCallsTickOther = rngCallsAfterTick - rngCallsAfterBeforeUpdate,
                        rngCallsDelta = rngCallsAfterTick - rngCallsBeforeFixture, rngRewound = false,
                        rngIdentity = Identity(Calc.Random),
                        globalEntities = GlobalEntitySnapshot(probe.Level),
                        globalEntitiesRetained = JsonSerializer.Serialize(GlobalEntitySnapshot(probe.Level)) == globalGeometryBefore,
                        solidTilesIdentityBefore, solidTilesIdentityAfter = Identity(probe.Level.SolidTiles),
                        solidTilesAvailable = probe.Level.SolidTiles != null,
                        tileObservation = probe.Level.SolidTiles == null
                            ? "bounded partial-room profile has no SolidTiles object before or after fixture commit; fixture cannot rebake a tilemap object here"
                            : "SolidTiles identity is unchanged across fixture commit",
                        trackedPlayerColliderOrder = PlayerColliderOrder(probe.Level, fixture),
                        timeActive = probe.Level.TimeActive, rawTimeActive = probe.Level.RawTimeActive,
                        inputMoveX = Input.MoveX.Value, inputMoveY = Input.MoveY.Value, inputSampled = false,
                        rngObservation = "rngCallsAfterAdded is read after original Scene.BeforeUpdate/EntityList.UpdateLists and before Scene.Update on the same unchanged FrameDriver tick; no hook, callback or behavior change",
                        commitPath = "EntityList.UpdateLists -> Entity.Added -> Tracker.EntityAdded/ComponentAdded for the appended Spikes.PlayerCollider",
                        claim = "Fixture committed by one unchanged safe tick through the original entity/tracker path; raw hazard geometry unchanged; fixture Added consumption is isolated between the original scene phases" });
                }
                zeroGravityStep = firstPlayer.Speed.Y;
                probe.Write(new { @event = $"caller-{stem}-zero-gravity-step", scenario, tick = gravityStepTick,
                    speedBefore = new[] { 0f, 0f }, speedAfter = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                    gravityStep = zeroGravityStep, dead = firstPlayer.Dead,
                    sessionDeaths = probe.Level.Session.Deaths, saveDeaths = SaveData.Instance.TotalDeaths,
                    inputSampled = false,
                    sourceOrder = "Player.Update leaves onGround false; NormalUpdate applies 900*DeltaTime gravity to the zero seed before MoveV and PlayerCollider.Check" });
                if (firstPlayer.Dead || zeroGravityStep <= 0f)
                    throw new InvalidOperationException("Zero-speed gravity-step calibration did not produce positive gravity");

                collisionTick = gravityStepTick + 1;
                hurtboxBottomOffset = ColliderBounds(Hurtbox(firstPlayer), firstPlayer)[3] - firstPlayer.Position.Y;
                firstPlayer.Position = new Vector2(safeX, spikeBottom);
                firstPlayer.Speed = new Vector2(0f, -zeroGravityStep);
                var calibrationSpeedBefore = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y };
                var calibrationPositionBefore = new[] { firstPlayer.Position.X, firstPlayer.Position.Y };
                int calibrationTick = collisionTick;
                Tick(probe, driver, calibrationTick);
                zeroCalibratedCheckSpeedX = firstPlayer.Speed.X;
                zeroCalibratedCheckSpeedY = firstPlayer.Speed.Y;
                probe.Write(new { @event = $"caller-{stem}-zero-calibration", scenario, tick = calibrationTick,
                    speedBefore = calibrationSpeedBefore,
                    speedAfter = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                    positionBefore = calibrationPositionBefore,
                    positionAfter = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                    gravityStep = zeroGravityStep,
                    onGroundField = CachedOnGround(firstPlayer), onGroundQuery = firstPlayer.OnGround(),
                    overlap = Overlaps(ColliderBounds(Hurtbox(firstPlayer), firstPlayer), ColliderBounds(spike.Collider, spike)),
                    dead = firstPlayer.Dead, sessionDeaths = probe.Level.Session.Deaths,
                    saveDeaths = SaveData.Instance.TotalDeaths, inputSampled = false,
                    sourceOrder = "Player.Update leaves onGround false; NormalUpdate applies the same 900*DeltaTime gravity step to its exact negative, MoveV(0), then PlayerCollider.Check sees no spike overlap at the safe pose" });
                if (firstPlayer.Dead || zeroCalibratedCheckSpeedY != 0f)
                    throw new InvalidOperationException("Zero-speed calibration did not reach an unmodified Speed.Y==0");

                collisionTick = calibrationTick + 1;
                firstPlayer.Position = new Vector2(spikeCenterX, planeEquality ? spikeBottom - hurtboxBottomOffset : spikeBottom);
                firstPlayer.Speed = new Vector2(0f, -zeroGravityStep);
                var zeroHurtbox = Hurtbox(firstPlayer);
                var zeroHurtboxBounds = ColliderBounds(zeroHurtbox, firstPlayer);
                var zeroSpikeBounds = ColliderBounds(spike.Collider, spike);
                hazardHurtboxBounds = zeroHurtboxBounds;
                hazardSpikeBounds = zeroSpikeBounds;
                bool zeroOverlap = Overlaps(zeroHurtboxBounds, zeroSpikeBounds);
                bool zeroVelocity = zeroCalibratedCheckSpeedY >= 0f;
                bool zeroGeometry = zeroHurtboxBounds[3] <= zeroSpikeBounds[3];
                float planeBottomDelta = zeroHurtboxBounds[3] - zeroSpikeBounds[3];
                hazardRemainderBefore = firstPlayer.PositionRemainder;
                probe.Write(new { @event = $"caller-{stem}-zero-setup", scenario, tick = collisionTick,
                    preTickSpeed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y }, preTickSpeedY = firstPlayer.Speed.Y,
                    expectedPostGravitySpeedY = zeroCalibratedCheckSpeedY,
                    gravityStep = zeroGravityStep,
                    position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                    hurtboxBounds = zeroHurtboxBounds, spikeBounds = zeroSpikeBounds,
                    overlap = zeroOverlap, velocityTrue = zeroVelocity, geometryTrue = zeroGeometry,
                    onGroundField = CachedOnGround(firstPlayer), onGroundQuery = firstPlayer.OnGround(),
                    dead = firstPlayer.Dead, sessionDeaths = probe.Level.Session.Deaths,
                    saveDeaths = SaveData.Instance.TotalDeaths, inputSampled = false,
                    checkSpeedEvidence = "The same negative seed was observed reaching Speed.Y==0 under one unchanged real update at the safe pose; the collision tick repeats that seed, NormalUpdate cancels it to zero, MoveV(0), then PlayerCollider.Check sees zero" });
                if (!zeroOverlap || !zeroVelocity || !zeroGeometry)
                    throw new InvalidOperationException("Zero-speed collision setup did not satisfy overlap/velocity/geometry");
                if (planeEquality && planeBottomDelta != 0f)
                    throw new InvalidOperationException("Plane-equality collision setup did not place the hurtbox bottom exactly on the spike bottom");
                if (simultaneous)
                {
                    if (fixture == null || fixture.Scene != probe.Level)
                        throw new InvalidOperationException("Controlled fixture is missing before the simultaneous collision tick");
                    var rawSpikes = RawSpikes(probe.Level, fixture);
                    var rawU1 = rawSpikes.FirstOrDefault();
                    if (rawU1 == null || rawU1.Direction != Spikes.Directions.Up)
                        throw new InvalidOperationException("Raw Up hazard U1 is missing before the simultaneous collision tick");
                    var fixtureBounds = SpikeBounds(fixture);
                    var components = probe.Level.Tracker.GetComponents<PlayerCollider>();
                    int rawOrder = -1;
                    int fixtureOrder = -1;
                    for (int order = 0; order < components.Count; order++)
                    {
                        if (ReferenceEquals(components[order].Entity, rawU1)) rawOrder = order;
                        if (ReferenceEquals(components[order].Entity, fixture)) fixtureOrder = order;
                    }
                    bool overlapsRaw = Overlaps(zeroHurtboxBounds, zeroSpikeBounds);
                    bool overlapsFixture = Overlaps(zeroHurtboxBounds, fixtureBounds);
                    bool rawEligible = overlapsRaw && zeroCalibratedCheckSpeedY >= 0f && zeroHurtboxBounds[3] <= zeroSpikeBounds[3];
                    bool fixtureEligible = overlapsFixture && zeroCalibratedCheckSpeedX >= 0f;
                    var firstEligible = FirstEligible(probe.Level, fixture, zeroHurtboxBounds,
                        zeroCalibratedCheckSpeedX, zeroCalibratedCheckSpeedY);
                    if (!rawEligible || !fixtureEligible || firstEligible.Id != "raw-1" || firstEligible.Order != rawOrder)
                        throw new InvalidOperationException("The simultaneous collision seed does not select raw Up U1 first in original tracker order");
                    probe.Write(new { @event = "caller-simultaneous-fixture-seed", scenario, tick = collisionTick,
                        position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                        speed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                        hurtboxBounds = zeroHurtboxBounds,
                        rawU1 = new { id = "raw-1", identity = Identity(rawU1),
                            direction = rawU1.Direction.ToString(), bounds = zeroSpikeBounds },
                        fixture = FixtureView(fixture), fixtureBounds,
                        overlapsRaw, overlapsFixture,
                        expectedCheckSpeedX = zeroCalibratedCheckSpeedX,
                        expectedCheckSpeedY = zeroCalibratedCheckSpeedY,
                        rawEligible, fixtureEligible, rawOrder, fixtureOrder,
                        firstEligibleId = firstEligible.Id, firstEligibleOrder = firstEligible.Order,
                        trackedPlayerColliderOrder = PlayerColliderOrder(probe.Level, fixture),
                        sourcePredicates = "Up: Speed.Y>=0 && player.Bottom<=spike.Bottom; Left: Speed.X>=0",
                        loopMechanism = "Player.Update after each PlayerCollider.Check tests && Dead and executes { base.Collider = collider; return; }; first eligible raw Up death direction (0,-1) returns before the appended fixture component",
                        colliderCheckNote = "PlayerCollider.Check swaps base.Entity.Collider and calls player.CollideCheck(entity); it does not test player.Collidable",
                        callbackInstrumentation = false,
                        callbackCountClaim = "not instrumented and not claimed; single death is evidenced by the loop return source order, one pending/committed corpse and one counter increment",
                        claim = "Two original predicates are eligible from actual seed bounds and calibrated check speeds; raw Up U1 is first in unchanged tracker order and the appended Left fixture is last" });
                }
            }
            else if (leftZero)
            {
                float safeX = spike.Collider.AbsoluteLeft - 10f;
                float spikeBase = spike.Collider.AbsoluteBottom;
                firstPlayer.Position = new Vector2(safeX, spikeBase);
                firstPlayer.Speed = Vector2.Zero;
                var calibrationRemainderBefore = firstPlayer.PositionRemainder;
                int calibrationTick = collisionTick;
                Tick(probe, driver, calibrationTick);
                var calibrationRemainderAfter = firstPlayer.PositionRemainder;
                probe.Write(new { @event = "caller-left-spike-zero-calibration", scenario, tick = calibrationTick,
                    speedBefore = new[] { 0f, 0f }, speedAfter = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                    positionDelta = new[] { firstPlayer.Position.X - safeX, firstPlayer.Position.Y - spikeBase },
                    positionRemainderBefore = new[] { calibrationRemainderBefore.X, calibrationRemainderBefore.Y },
                    positionRemainderAfter = new[] { calibrationRemainderAfter.X, calibrationRemainderAfter.Y },
                    wind = new[] { probe.Level.Wind.X, probe.Level.Wind.Y },
                    liftSpeed = new[] { firstPlayer.LiftSpeed.X, firstPlayer.LiftSpeed.Y },
                    moveX = Input.MoveX.Value, moveY = Input.MoveY.Value,
                    onGroundField = CachedOnGround(firstPlayer), onGroundQuery = firstPlayer.OnGround(),
                    state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead, inputSampled = false,
                    sourceOrder = "NormalUpdate runs Calc.Approach(0, target 0, 1000*airMult*dt) which preserves 0; MoveH(0) adds 0 to the X subpixel counter so round(counter)==0 and no move; no Speed.X writer runs between base.Update and PlayerCollider.Check while the wall/boost/hop timers are inactive" });
                if (firstPlayer.Dead || firstPlayer.Speed.X != 0f || firstPlayer.Position.X != safeX || calibrationRemainderAfter.X != calibrationRemainderBefore.X)
                    throw new InvalidOperationException("Left zero-speed safe-pose calibration did not preserve exact Speed.X==0 and X subpixel state");
                collisionTick = calibrationTick + 1;
                firstPlayer.Position = new Vector2(spike.Collider.AbsoluteLeft - 1f, spikeBase);
                firstPlayer.Speed = Vector2.Zero;
            }
            else if (left)
            {
                float leftPlane = spike.Collider.AbsoluteLeft;
                float spikeBase = spike.Collider.AbsoluteBottom;
                firstPlayer.Position = new Vector2(leftPlane - (lethal ? 4.5f : 1f), spikeBase);
                firstPlayer.Speed = new Vector2(lethal ? 120f : -100f, 0f);
            }
            else if (lethal)
            {
                firstPlayer.Position = new Vector2(spikeCenterX, spikeBottom - 2.5f);
                firstPlayer.Speed = new Vector2(0f, 120f);
            }
            else
            {
                firstPlayer.Position = new Vector2(spikeCenterX, spikeBottom + 2f);
                firstPlayer.Speed = new Vector2(0f, -120f);
            }
            if (!hazardProbe)
                probe.Write(new { @event = $"caller-{stem}-setup", scenario, inputSampled = false,
                    spikePosition = new[] { spike.Position.X, spike.Position.Y },
                    spikeBounds = ColliderBounds(spike.Collider, spike), spikeDirection = spike.Direction.ToString(),
                    playerPosition = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                    playerSpeed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                    state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead,
                    sessionDeaths = sessionDeathsBefore, saveDeaths = saveDeathsBefore });
            if (left)
            {
                leftSpikeBounds = ColliderBounds(spike.Collider, spike);
                leftSeedPosition = new[] { firstPlayer.Position.X, firstPlayer.Position.Y };
                leftSeedSpeed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y };
                leftSeedHurtboxBounds = ColliderBounds(Hurtbox(firstPlayer), firstPlayer);
                leftSeedRemainder = firstPlayer.PositionRemainder;
                probe.Write(new { @event = "caller-left-spike-seed", scenario, tick = collisionTick,
                    spikeBounds = leftSpikeBounds, position = leftSeedPosition, speed = leftSeedSpeed,
                    hurtboxBounds = leftSeedHurtboxBounds,
                    overlap = Overlaps(leftSeedHurtboxBounds, leftSpikeBounds),
                    positionRemainder = new[] { leftSeedRemainder.X, leftSeedRemainder.Y },
                    state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead,
                    onGroundField = CachedOnGround(firstPlayer), onGroundQuery = firstPlayer.OnGround(),
                    sessionDeaths = sessionDeathsBefore, saveDeaths = saveDeathsBefore, inputSampled = false });
                if (leftZero)
                {
                    probe.Write(new { @event = "caller-left-spike-zero-setup", scenario, tick = collisionTick,
                        hazardCheckSpeedX = firstPlayer.Speed.X, speed = leftSeedSpeed, position = leftSeedPosition,
                        hurtboxBounds = leftSeedHurtboxBounds, spikeBounds = leftSpikeBounds,
                        overlap = Overlaps(leftSeedHurtboxBounds, leftSpikeBounds),
                        positionRemainder = new[] { leftSeedRemainder.X, leftSeedRemainder.Y },
                        wind = new[] { probe.Level.Wind.X, probe.Level.Wind.Y },
                        liftSpeed = new[] { firstPlayer.LiftSpeed.X, firstPlayer.LiftSpeed.Y },
                        moveX = Input.MoveX.Value, moveY = Input.MoveY.Value,
                        onGroundField = CachedOnGround(firstPlayer), onGroundQuery = firstPlayer.OnGround(),
                        state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead,
                        intervening = SpeedXInterveningState(firstPlayer), inputSampled = false,
                        proofLabel = "DERIVED exact Speed.X==0 at the original hazard check: seed 0 is preserved by Calc.Approach target 0 and MoveH(0) with a zero X subpixel counter, with no input, zero wind/lift, inactive wall/boost/hop branches and Normal0; post-Die Speed is not used" });
                    if (firstPlayer.Speed.X != 0f || !Overlaps(leftSeedHurtboxBounds, leftSpikeBounds))
                        throw new InvalidOperationException("Left zero-speed seed did not hold exact Speed.X==0 with actual hurtbox overlap");
                }
            }
            float preTickSpeedY = firstPlayer.Speed.Y;
            bool zeroCheckOverlap = hazardProbe && Overlaps(hazardHurtboxBounds, hazardSpikeBounds);
            bool zeroCheckGeometry = hazardProbe && hazardHurtboxBounds[3] <= hazardSpikeBounds[3];
            bool zeroCheckVelocity = hazardProbe && zeroCalibratedCheckSpeedY >= 0f;
            Tick(probe, driver, collisionTick);
            if (left)
            {
                float[] postPosition = new[] { firstPlayer.Position.X, firstPlayer.Position.Y };
                float[] postSpeed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y };
                float[] postHurtboxBounds = ColliderBounds(Hurtbox(firstPlayer), firstPlayer);
                var leftCorpse = lethal ? PendingCorpse(probe.Level) : null;
                probe.Write(new { @event = "caller-left-spike-check", scenario, tick = collisionTick,
                    spikeBounds = leftSpikeBounds, position = postPosition, speed = postSpeed,
                    hurtboxBounds = postHurtboxBounds,
                    overlap = Overlaps(postHurtboxBounds, leftSpikeBounds),
                    positionDelta = new[] { postPosition[0] - leftSeedPosition[0], postPosition[1] - leftSeedPosition[1] },
                    seedSpeed = leftSeedSpeed, seedPosition = leftSeedPosition,
                    seedHurtboxBounds = leftSeedHurtboxBounds, seedOverlap = Overlaps(leftSeedHurtboxBounds, leftSpikeBounds),
                    positionRemainderBefore = new[] { leftSeedRemainder.X, leftSeedRemainder.Y },
                    positionRemainderAfter = new[] { firstPlayer.PositionRemainder.X, firstPlayer.PositionRemainder.Y },
                    dead = firstPlayer.Dead, collidable = firstPlayer.Collidable, locked = firstPlayer.StateMachine.Locked,
                    corpse = Identity(leftCorpse), deathDirection = leftCorpse == null ? null : Bounce(leftCorpse),
                    state = firstPlayer.StateMachine.State, sessionDeaths = probe.Level.Session.Deaths,
                    saveDeaths = SaveData.Instance.TotalDeaths, wipe = WipeState(probe.Level), inputSampled = false });
                if (leftZero)
                {
                    probe.Write(new { @event = "caller-left-spike-zero-check", scenario, tick = collisionTick,
                        hazardCheckSpeedX = leftSeedSpeed[0],
                        overlapBefore = Overlaps(leftSeedHurtboxBounds, leftSpikeBounds),
                        overlapAfter = Overlaps(postHurtboxBounds, leftSpikeBounds),
                        positionDelta = new[] { postPosition[0] - leftSeedPosition[0], postPosition[1] - leftSeedPosition[1] },
                        positionRemainderBefore = new[] { leftSeedRemainder.X, leftSeedRemainder.Y },
                        positionRemainderAfter = new[] { firstPlayer.PositionRemainder.X, firstPlayer.PositionRemainder.Y },
                        dead = firstPlayer.Dead, collidable = firstPlayer.Collidable, locked = firstPlayer.StateMachine.Locked,
                        corpse = Identity(leftCorpse), deathDirection = leftCorpse == null ? null : Bounce(leftCorpse),
                        state = firstPlayer.StateMachine.State, sessionDeaths = probe.Level.Session.Deaths,
                        saveDeaths = SaveData.Instance.TotalDeaths, inputSampled = false,
                        proofLabel = "DERIVED exact Speed.X==0 at the original Left OnCollide check; the unchanged update preserved the zero seed and X subpixel counter, and the emitted [-1,0] death direction is the original Speed.X>=0 Left branch" });
                }
            }
            if (planeEquality)
            {
                float[] postTickHurtboxBounds = ColliderBounds(Hurtbox(firstPlayer), firstPlayer);
                if (postTickHurtboxBounds[3] != hazardSpikeBounds[3])
                    throw new InvalidOperationException("Plane-equality collision did not preserve the exact hurtbox bottom on the spike plane");
                if (firstPlayer.PositionRemainder != hazardRemainderBefore)
                    throw new InvalidOperationException("Plane-equality collision changed the subpixel position remainder");
                probe.Write(new { @event = $"caller-{stem}-plane-check", scenario, tick = collisionTick,
                    position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                    hurtboxBoundsBefore = hazardHurtboxBounds, hurtboxBoundsAfter = postTickHurtboxBounds,
                    spikeBounds = hazardSpikeBounds,
                    hurtboxBottomBefore = hazardHurtboxBounds[3], hurtboxBottomAfter = postTickHurtboxBounds[3],
                    spikeBottom = hazardSpikeBounds[3],
                    planeBottomDeltaBefore = hazardHurtboxBounds[3] - hazardSpikeBounds[3],
                    planeBottomDeltaAfter = postTickHurtboxBounds[3] - hazardSpikeBounds[3],
                    hurtboxBottomOffset,
                    positionRemainderBefore = new[] { hazardRemainderBefore.X, hazardRemainderBefore.Y },
                    positionRemainderAfter = new[] { firstPlayer.PositionRemainder.X, firstPlayer.PositionRemainder.Y },
                    preTickSpeedY, expectedPostGravitySpeedY = zeroCalibratedCheckSpeedY,
                    hazardCheckSpeedY = zeroCalibratedCheckSpeedY,
                    overlap = zeroCheckOverlap, velocityTrue = zeroCheckVelocity, geometryTrue = zeroCheckGeometry,
                    dead = firstPlayer.Dead,
                    proofLabel = "Actual hurtbox bottom equals the selected static Up spike bottom before the unchanged update; Speed.Y==0 is inferred from safe-pose calibration plus unchanged source order; MoveV(0) leaves the hurtbox bottom on the plane, then original PlayerCollider.Check/Spikes.OnCollide runs" });
            }
            PlayerDeadBody corpse = null;
            PlayerDeadBody pendingCorpse = lethal ? PendingCorpse(probe.Level) : null;
            var current = probe.Level.Tracker.GetEntity<Player>();
            probe.Write(new { @event = $"caller-{stem}-collision", scenario, tick = collisionTick,
                state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead,
                collidable = firstPlayer.Collidable, locked = firstPlayer.StateMachine.Locked,
                position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                speed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                corpse = Identity(pendingCorpse), deathDirection = pendingCorpse == null ? null : Bounce(pendingCorpse),
                sessionDeaths = probe.Level.Session.Deaths, saveDeaths = SaveData.Instance.TotalDeaths,
                trackedPlayer = current == null ? null : Identity(current),
                preTickSpeedY,
                hazardCheckSpeedY = hazardProbe ? zeroCalibratedCheckSpeedY : (float?)null,
                hazardCheckOverlap = hazardProbe ? zeroCheckOverlap : (bool?)null,
                hazardCheckGeometryTrue = hazardProbe ? zeroCheckGeometry : (bool?)null,
                hazardCheckVelocityTrue = hazardProbe ? zeroCheckVelocity : (bool?)null,
                checkSpeedEvidence = hazardProbe ? "The same negative seed was observed reaching zero in the prior unchanged update; the collision tick repeats it, NormalUpdate cancels it to zero, MoveV(0), then PlayerCollider.Check" : null,
                wipe = WipeState(probe.Level), inputSampled = false });
            if (simultaneous)
            {
                var pendingCorpses = PendingCorpses(probe.Level);
                var committedCorpses = CommittedCorpses(probe.Level);
                var rawHazardsAfterCollision = RawHazardSnapshot(probe.Level, fixture);
                bool rawGeometryUnchanged = RawGeometryJson(probe.Level, fixture) == rawGeometryBefore;
                bool fixturePresent = probe.Level.Entities.Contains(fixture);
                if (pendingCorpses.Length != 1 || committedCorpses.Length != 0 || rawHazardsAfterCollision.Length != 5
                    || !rawGeometryUnchanged || !fixturePresent)
                    throw new InvalidOperationException("Simultaneous collision did not leave exactly one pending corpse and the unchanged five raw hazards plus fixture");
                var deathBounce = Bounce(pendingCorpses[0]);
                if (deathBounce[0] != 0f || deathBounce[1] != -1f)
                    throw new InvalidOperationException("Simultaneous collision did not emit the first raw Up death direction");
                probe.Write(new { @event = "caller-simultaneous-fixture-collision", scenario, tick = collisionTick,
                    corpse = Identity(pendingCorpses[0]), deathDirection = deathBounce,
                    sessionDeaths = probe.Level.Session.Deaths,
                    deathsInCurrentLevel = probe.Level.Session.DeathsInCurrentLevel,
                    saveDeaths = SaveData.Instance.TotalDeaths,
                    deathsInCurrentLevelBefore, pendingCorpses = pendingCorpses.Length,
                    committedCorpses = committedCorpses.Length, rawHazardCount = rawHazardsAfterCollision.Length,
                    rawHazards = rawHazardsAfterCollision, rawGeometryUnchanged, fixturePresent,
                    fixture = FixtureView(fixture), fixtureBounds = SpikeBounds(fixture),
                    trackedPlayerColliderOrder = PlayerColliderOrder(probe.Level, fixture),
                    claim = "Exactly one pending PlayerDeadBody and one increment of each death counter after the first raw Up OnCollide; no second corpse is pending or committed" });
            }
            if (!lethal)
            {
                int followupTick = collisionTick + 1;
                Tick(probe, driver, followupTick);
                probe.Write(new { @event = $"caller-{stem}-followup", tick = followupTick,
                    state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead,
                    collidable = firstPlayer.Collidable, locked = firstPlayer.StateMachine.Locked,
                    position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                    corpse = Identity(probe.Level.Entities.OfType<PlayerDeadBody>().FirstOrDefault()),
                    sessionDeaths = probe.Level.Session.Deaths, saveDeaths = SaveData.Instance.TotalDeaths,
                    wipe = WipeState(probe.Level), inputSampled = false });
                if (left)
                    probe.Write(new { @event = "caller-left-spike-followup", scenario, tick = followupTick,
                        state = firstPlayer.StateMachine.State, dead = firstPlayer.Dead,
                        collidable = firstPlayer.Collidable, locked = firstPlayer.StateMachine.Locked,
                        position = new[] { firstPlayer.Position.X, firstPlayer.Position.Y },
                        speed = new[] { firstPlayer.Speed.X, firstPlayer.Speed.Y },
                        hurtboxBounds = ColliderBounds(Hurtbox(firstPlayer), firstPlayer),
                        spikeBounds = leftSpikeBounds,
                        overlap = Overlaps(ColliderBounds(Hurtbox(firstPlayer), firstPlayer), leftSpikeBounds),
                        corpse = Identity(probe.Level.Entities.OfType<PlayerDeadBody>().FirstOrDefault()),
                        sessionDeaths = probe.Level.Session.Deaths, saveDeaths = SaveData.Instance.TotalDeaths,
                        wipe = WipeState(probe.Level), inputSampled = false });
                probe.Write(new { @event = "completed", status = left
                        ? "left-spike-nonlethal-source-collision-alive-no-lifecycle"
                        : "up-spike-nonlethal-source-collision-alive-no-lifecycle",
                    scenario, collisionTick, sessionDeaths = probe.Level.Session.Deaths,
                    saveDeaths = SaveData.Instance.TotalDeaths, inputSampled = false,
                    sourceProfile = left
                        ? "source-synced-6b-01; static Left spike; single-room-header; partial map; no full-family/traversal/input proof"
                        : "source-synced-6b-01; static Up spike; single-room-header; partial map; no full-family/traversal/input proof",
                    nativeAttempts = NativeImportGuard.Attempts.Length,
                    nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                    completedLifecycleFamilies = 0, hazardOrderingDirectionalCollisionDeathParity = false,
                    claim = left
                        ? "Static Left spike collision through original PlayerCollider.Check and unchanged Spikes.OnCollide left nonlethal branch; no death/wipe/reload; not traversal/input/full-family proof"
                        : "Static Up spike collision through original PlayerCollider.Check and unchanged Spikes.OnCollide nonlethal branch; no death/wipe/reload; not traversal/input/full-family proof" });
                return;
            }
            if (!firstPlayer.Dead || firstPlayer.Collidable || !firstPlayer.StateMachine.Locked)
                throw new InvalidOperationException("Lethal static spike collision did not execute original Die guards");
            bool corpseObserved = false;
            bool bounceObserved = false;
            bool effectObserved = false;
            bool wipeObserved = false;
            bool reloadObserved = false;
            int wipeTick = -1;
            int reloadTick = -1;
            int secondNormalTick = -1;
            int maxCorpseCount = 0;
            for (int deathTick = collisionTick + 1; deathTick < collisionTick + 900; deathTick++)
            {
                bool sceneRan = Tick(probe, driver, deathTick);
                int pendingCorpseCount = 0;
                int committedCorpseCount = 0;
                if (simultaneous)
                {
                    pendingCorpseCount = PendingCorpses(probe.Level).Length;
                    committedCorpseCount = CommittedCorpses(probe.Level).Length;
                    maxCorpseCount = Math.Max(maxCorpseCount, pendingCorpseCount + committedCorpseCount);
                }
                if (!corpseObserved)
                {
                    corpse = probe.Level.Entities.OfType<PlayerDeadBody>().FirstOrDefault();
                    if (corpse != null)
                    {
                        corpseObserved = true;
                        probe.Write(new { @event = $"caller-{stem}-corpse", tick = deathTick, sceneRan,
                            corpse = Identity(corpse), deathDirection = Bounce(corpse), sessionDeaths = probe.Level.Session.Deaths });
                        if (simultaneous)
                            probe.Write(new { @event = "caller-simultaneous-corpse-state", tick = deathTick, sceneRan,
                                corpse = Identity(corpse), pendingCorpses = pendingCorpseCount,
                                committedCorpses = committedCorpseCount, maxCorpseCount,
                                sessionDeaths = probe.Level.Session.Deaths,
                                deathsInCurrentLevel = probe.Level.Session.DeathsInCurrentLevel,
                                saveDeaths = SaveData.Instance.TotalDeaths,
                                claim = "Exactly one committed PlayerDeadBody after the single source death; no second corpse through the first updates" });
                    }
                }
                if (!corpseObserved) continue;
                var sprite = corpse.Get<PlayerSprite>();
                var tween = corpse.Get<Tween>();
                var effect = corpse.Get<DeathEffect>();
                if (!bounceObserved && tween != null)
                {
                    bounceObserved = true;
                    probe.Write(new { @event = "caller-corpse-bounce", tick = deathTick, sceneRan,
                        corpse = Identity(corpse), animation = sprite.CurrentAnimationID,
                        tween = new { tween.Active, tween.Percent, tween.TimeLeft }, freezeAfter = Engine.FreezeTimer });
                }
                if (!effectObserved && effect != null)
                {
                    effectObserved = true;
                    probe.Write(new { @event = "caller-corpse-death-effect", tick = deathTick, sceneRan,
                        corpse = Identity(corpse), effect = new { effect.Percent, effect.Duration } });
                }
                var wipe = probe.Level.Wipe;
                if (!wipeObserved && wipe != null && !wipe.WipeIn)
                {
                    wipeObserved = true; wipeTick = deathTick;
                    probe.Write(new { @event = "caller-death-wipe", tick = deathTick, sceneRan,
                        wipe = WipeState(probe.Level), corpse = Identity(corpse),
                        corpseInScene = corpse.Scene != null, sessionDeaths = probe.Level.Session.Deaths });
                }
                var currentPlayer = probe.Level.Tracker.GetEntity<Player>();
                if (!reloadObserved && currentPlayer != null && currentPlayer != firstPlayer)
                {
                    reloadObserved = true; reloadTick = deathTick;
                    probe.Write(new { @event = "caller-reload-second-load", tick = deathTick, sceneRan,
                        previousPlayer = Identity(firstPlayer), player = Identity(currentPlayer),
                        state = currentPlayer.StateMachine.State, lastIntroType = probe.Level.LastIntroType.ToString(),
                        corpseRemoved = corpse.Scene == null && !probe.Level.Entities.Contains(corpse),
                        wipe = WipeState(probe.Level), sessionDeaths = probe.Level.Session.Deaths });
                    if (currentPlayer.StateMachine.State != 14)
                        throw new InvalidOperationException("Second LoadLevel did not return state14");
                    if (simultaneous)
                    {
                        var rawHazardsAfterReload = RawHazardSnapshot(probe.Level, fixture);
                        bool rawGeometryUnchanged = RawGeometryJson(probe.Level, fixture) == rawGeometryBefore;
                        bool fixturePresent = probe.Level.Entities.Contains(fixture) || fixture.Scene != null;
                        if (rawHazardsAfterReload.Length != 5 || !rawGeometryUnchanged || fixturePresent)
                            throw new InvalidOperationException("Controlled fixture did not unload as non-Global or raw hazard geometry changed after reload");
                        probe.Write(new { @event = "caller-simultaneous-reload-state", tick = deathTick,
                            rawHazardCount = rawHazardsAfterReload.Length, rawHazards = rawHazardsAfterReload,
                            rawGeometryUnchanged, fixturePresent,
                            fixtureScene = fixture.Scene == null ? null : Identity(fixture.Scene),
                            fixtureTag = fixture.Tag, fixtureWasGlobal = IsGlobal(fixture),
                            fixture = FixtureView(fixture), rngIdentity = Identity(Calc.Random),
                            rngCalls = RandomCalls(), timeActive = probe.Level.TimeActive,
                            rawTimeActive = probe.Level.RawTimeActive,
                            inputMoveX = Input.MoveX.Value, inputMoveY = Input.MoveY.Value, inputSampled = false,
                            globalEntities = GlobalEntitySnapshot(probe.Level),
                            globalEntitiesRetained = JsonSerializer.Serialize(GlobalEntitySnapshot(probe.Level)) == globalGeometryBefore,
                            solidTilesIdentity = Identity(probe.Level.SolidTiles),
                            claim = "Non-Global explicit fixture unloaded with the level; five raw hazards reload with unchanged geometry; global entities, persistent RNG object and clocks advance or persist, not rewound" });
                    }
                }
                if (reloadObserved && currentPlayer != null && currentPlayer != firstPlayer && currentPlayer.StateMachine.State == 0)
                {
                    secondNormalTick = deathTick;
                    probe.Write(new { @event = "caller-second-normal0", tick = deathTick, sceneRan,
                        player = Identity(currentPlayer), state = currentPlayer.StateMachine.State,
                        position = new[] { currentPlayer.Position.X, currentPlayer.Position.Y },
                        scale = new[] { currentPlayer.Sprite.Scale.X, currentPlayer.Sprite.Scale.Y },
                        wipe = WipeState(probe.Level), sessionDeaths = probe.Level.Session.Deaths });
                    break;
                }
            }
            if (!corpseObserved) throw new InvalidOperationException("Original " + (left ? "Left" : "Up") + " spike collision did not create PlayerDeadBody");
            if (!wipeObserved) throw new InvalidOperationException("Original corpse End did not create death wipe");
            if (!reloadObserved) throw new InvalidOperationException("Death wipe did not reload second Player");
            if (secondNormalTick < 0) throw new InvalidOperationException("Second Respawn14 did not reach Normal0");
            var resumedPlayer = probe.Level.Tracker.GetEntity<Player>();
            int resumedTick = secondNormalTick + 1;
            Tick(probe, driver, resumedTick);
            probe.Write(new { @event = "caller-resumed-live-tick", tick = resumedTick,
                player = Identity(resumedPlayer), state = resumedPlayer.StateMachine.State,
                dead = resumedPlayer.Dead, position = new[] { resumedPlayer.Position.X, resumedPlayer.Position.Y },
                speed = new[] { resumedPlayer.Speed.X, resumedPlayer.Speed.Y },
                sessionDeaths = probe.Level.Session.Deaths, inputSampled = false });
            if (resumedPlayer.StateMachine.State != 0 || resumedPlayer.Dead)
                throw new InvalidOperationException("Resumed tick left Normal0");
            if (simultaneous)
            {
                var rawHazardsFinal = RawHazardSnapshot(probe.Level, fixture);
                int rngCallsFinal = RandomCalls();
                if (maxCorpseCount != 1 || rawHazardsFinal.Length != 5 || fixture.Scene != null
                    || probe.Level.Entities.Contains(fixture))
                    throw new InvalidOperationException("Simultaneous fixture lifecycle did not preserve one corpse and five raw hazards after unload");
                probe.Write(new { @event = "completed",
                    status = "simultaneous-fixture-lethal-source-collision-death-respawn14-normal0-one-live-tick",
                    scenario, firstNormalTick, collisionTick, wipeTick, reloadTick, secondNormalTick, resumedTick,
                    corpse = Identity(corpse), corpseRemoved = corpse.Scene == null && !probe.Level.Entities.Contains(corpse),
                    deathDirection = Bounce(corpse), sessionDeaths = probe.Level.Session.Deaths,
                    saveDeaths = SaveData.Instance.TotalDeaths, sourceLoadLevelCalls = 2,
                    corpseCreated = 1, deathWipes = 1, reloads = 1,
                    resumedNormalUpdates = 1, inputSampled = false, preTickSpeedY,
                    hazardCheckSpeedY = zeroCalibratedCheckSpeedY,
                    hazardCheckOverlap = zeroCheckOverlap,
                    hazardCheckGeometryTrue = zeroCheckGeometry,
                    hazardCheckVelocityTrue = zeroCheckVelocity,
                    explicitFixtureCount = 1, rawHazardCount = rawHazardsFinal.Length,
                    rawHazards = rawHazardsFinal, rawGeometryUnchanged = RawGeometryJson(probe.Level, fixture) == rawGeometryBefore,
                    fixtureUnloaded = fixture.Scene == null && !probe.Level.Entities.Contains(fixture),
                    fixtureWasGlobal = IsGlobal(fixture), fixtureTag = fixture.Tag,
                    rngIdentity = Identity(Calc.Random), rngCalls = rngCallsFinal,
                    rngCallsBeforeFixture, rngCallsDelta = rngCallsFinal - rngCallsBeforeFixture,
                    maxCorpseCount, pendingCorpses = PendingCorpses(probe.Level).Length,
                    committedCorpses = CommittedCorpses(probe.Level).Length,
                    deathsInCurrentLevelBefore, deathsInCurrentLevel = probe.Level.Session.DeathsInCurrentLevel,
                    sourceProfile = "source-synced-6b-01; five raw room hazards plus one explicit caller fixture; single-room-header; partial map; no full-family/traversal/input proof",
                    nativeAttempts = NativeImportGuard.Attempts.Length,
                    nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                    completedLifecycleFamilies = 0, hazardOrderingDirectionalCollisionDeathParity = false,
                    claim = "Explicit controlled fixture at (64,155) size16 Left added at Normal0 through original Spikes constructor/Level.Add/Tracker; raw Up U1 and fixture Left are both eligible in one tick, first raw Up death direction (0,-1) returns from the Player.Update PlayerCollider loop, original Die/lifecycle; this is not natural room/full-family/traversal/input/hardware proof" });
                return;
            }
            probe.Write(new { @event = "completed",
                status = leftZero
                    ? "left-spike-zero-x-lethal-source-collision-death-respawn14-normal0-one-live-tick"
                    : left
                    ? "left-spike-lethal-source-collision-death-respawn14-normal0-one-live-tick"
                    : scenario == "plane-equality-lethal"
                    ? "up-spike-plane-equality-lethal-source-collision-death-respawn14-normal0-one-live-tick"
                    : scenario == "zero-lethal"
                    ? "up-spike-zero-lethal-source-collision-death-respawn14-normal0-one-live-tick"
                    : "up-spike-lethal-source-collision-death-respawn14-normal0-one-live-tick",
                scenario, firstNormalTick, collisionTick, wipeTick, reloadTick, secondNormalTick, resumedTick,
                corpse = Identity(corpse), corpseRemoved = corpse.Scene == null && !probe.Level.Entities.Contains(corpse),
                deathDirection = Bounce(corpse), sessionDeaths = probe.Level.Session.Deaths,
                saveDeaths = SaveData.Instance.TotalDeaths, sourceLoadLevelCalls = 2,
                resumedNormalUpdates = 1, inputSampled = false,
                preTickSpeedY,
                hazardCheckSpeedY = hazardProbe ? zeroCalibratedCheckSpeedY : (float?)null,
                hazardCheckOverlap = hazardProbe ? zeroCheckOverlap : (bool?)null,
                hazardCheckGeometryTrue = hazardProbe ? zeroCheckGeometry : (bool?)null,
                hazardCheckVelocityTrue = hazardProbe ? zeroCheckVelocity : (bool?)null,
                sourceProfile = left
                    ? "source-synced-6b-01; static Left spike; single-room-header; partial map; no full-family/traversal/input proof"
                    : "source-synced-6b-01; static Up spike; single-room-header; partial map; no full-family/traversal/input proof",
                nativeAttempts = NativeImportGuard.Attempts.Length,
                nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, hazardOrderingDirectionalCollisionDeathParity = false,
                claim = leftZero
                    ? "Existing static Left spike, caller-seeded (268,96) with Speed.X exactly 0 preserved by the unchanged update (Calc.Approach target 0, MoveH(0) with zero X subpixel counter), actual hurtbox overlap at the original hazard check, original Die(direction -1,0)/lifecycle; not traversal/input/full-family proof"
                    : left
                    ? "Existing static Left spike, caller-seeded pose/speed entering the left plane, actual hurtbox overlap observed after the unchanged update, original Die(direction -1,0)/lifecycle; not traversal/input/full-family proof"
                    : scenario == "plane-equality-lethal"
                    ? "Existing static Up spike, actual hurtbox bottom==spike bottom before and after the unchanged update (MoveV(0)); Speed.Y==0 inferred from safe-pose calibration plus unchanged source order; original Die/lifecycle; not traversal/input/full-family proof"
                    : scenario == "zero-lethal"
                    ? "Existing static Up spike, Speed.Y==0 inferred from safe-pose calibration plus unchanged source order, original Die/lifecycle; not traversal/input/full-family proof"
                    : "Existing static Up spike, caller-seeded pose/speed, one real Level tick through original PlayerCollider.Check and unchanged Spikes.OnCollide; not traversal/input/full-family proof" });
        }
        catch (Exception error)
        {
            probe.Write(new { @event = "boundary", member = probe.Member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAtBoundary = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, status = $"blocked-{stem}-prefix-not-lifecycle-coverage" });
            throw;
        }
    }

    public static void RunInputRight(string[] args)
    {
        using var probe = new Probe(args);
        try
        {
            probe.Bootstrap();
            probe.Invoke("caller-engine-pooler", () => {
                var property = typeof(Engine).GetProperty("Pooler", BindingFlags.Public | BindingFlags.Static);
                property.GetSetMethod(true).Invoke(null, new object[] { new Pooler() });
                probe.Write(new { @event = "caller-pooler", initialized = Engine.Pooler != null });
            });
            probe.Invoke("caller-engine-driver-scene", () => {
                PrepareEngineDriver(probe.Level);
                probe.Write(new { @event = "caller-engine-scene", scene = Identity(Engine.Scene), sameLevel = Engine.Scene == probe.Level });
            });
            probe.Invoke("caller-rumble-profile", () => { Settings.Instance.Rumble = RumbleAmount.Off; });
            LoadGuiAtlas(probe.Content);
            probe.Invoke("caller-level-loader-fields", () => PrepareLevelLoaderFields(probe.Level));

            string[] leftBefore = KeyNames(Settings.Instance.Left);
            string[] rightBefore = KeyNames(Settings.Instance.Right);
            string[] jumpBefore = KeyNames(Settings.Instance.Jump);
            probe.Invoke("caller-input-right-controls", () => {
                bool added = Settings.Instance.Right.Add(Keys.Right);
                Input.Initialize();
                probe.Write(new { @event = "caller-input-right-controls", profile = "source-axis-only",
                    added, key = "Right", rightKeyboardBefore = rightBefore,
                    rightKeyboardAfter = KeyNames(Settings.Instance.Right),
                    leftKeyboardBefore = leftBefore, leftKeyboardAfter = KeyNames(Settings.Instance.Left),
                    jumpKeyboardBefore = jumpBefore, jumpKeyboardAfter = KeyNames(Settings.Instance.Jump),
                    moveXPositiveKeyboard = KeyNames(Input.MoveX.Positive),
                    moveXNegativeKeyboard = KeyNames(Input.MoveX.Negative),
                    moveXPositiveAltKeyboard = KeyNames(Input.MoveX.PositiveAlt),
                    moveXNegativeAltKeyboard = KeyNames(Input.MoveX.NegativeAlt),
                    moveXGamepadIndex = Input.MoveX.GamepadIndex, moveXThreshold = Input.MoveX.Threshold,
                    moveXInverted = Input.MoveX.Inverted, inputReinitialized = true, inputSampled = false,
                    claim = "Declared Right key plus original Input.Initialize rebuild; no player Position/Speed/counter write and no full MInput sampling" });
            });
            if (rightBefore.Length != 0 || !KeyNames(Settings.Instance.Right).SequenceEqual(new[] { "Right" })
                || !KeyNames(Settings.Instance.Left).SequenceEqual(leftBefore)
                || !KeyNames(Settings.Instance.Jump).SequenceEqual(jumpBefore)
                || !KeyNames(Input.MoveX.Positive).SequenceEqual(new[] { "Right" })
                || KeyNames(Input.MoveX.Negative).Length != 0
                || KeyNames(Input.MoveX.PositiveAlt).Length != 0
                || KeyNames(Input.MoveX.NegativeAlt).Length != 0)
                throw new InvalidOperationException("Declared Right control fixture did not rebuild the source MoveX bindings as expected");

            probe.Invoke("Celeste.Level.LoadLevel(Respawn)", () => probe.Level.LoadLevel(Player.IntroTypes.Respawn));
            var player = probe.Level.Tracker.GetEntity<Player>();
            if (player == null || player.StateMachine.State != 14)
                throw new InvalidOperationException("Input-right probe requires the source-created Respawn14 Player");
            var naturalPosition = new[] { player.Position.X, player.Position.Y };
            var naturalSpeed = new[] { player.Speed.X, player.Speed.Y };
            probe.Write(new { @event = "caller-input-right-load", state = player.StateMachine.State,
                position = naturalPosition, speed = naturalSpeed, entities = probe.Level.Entities.Count,
                wipe = WipeState(probe.Level), inputSampled = false,
                claim = "Original LoadLevel(Respawn) created the Player; caller records the natural spawn without writing pose or speed" });

            var driver = new FrameDriver { scene = probe.Level };
            int normalTick = -1;
            for (int tick = 0; tick < 360; tick++)
            {
                Tick(probe, driver, tick);
                if (player.StateMachine.State == 0) { normalTick = tick; break; }
            }
            if (normalTick < 0) throw new InvalidOperationException("Respawn14 did not reach Normal0");
            var normalPosition = new[] { player.Position.X, player.Position.Y };
            var normalSpeed = new[] { player.Speed.X, player.Speed.Y };
            probe.Write(new { @event = "caller-input-right-normal0", tick = normalTick, state = player.StateMachine.State,
                position = normalPosition, speed = normalSpeed, dead = player.Dead, scale = new[] { player.Sprite.Scale.X, player.Sprite.Scale.Y },
                wipe = WipeState(probe.Level), inputSampled = false,
                claim = "Source Respawn14 transition reached Normal0 at the natural spawn; no axis update or caller motion write happened yet" });
            if (normalPosition[0] != naturalPosition[0] || normalPosition[1] != naturalPosition[1])
                throw new InvalidOperationException("Natural Respawn position changed before any axis update");

            MInput.Keyboard.PreviousState = default(KeyboardState);
            MInput.Keyboard.CurrentState = default(KeyboardState);
            Input.MoveX.Update();
            probe.Write(new { @event = "caller-input-right-neutral-axis", tick = normalTick,
                value = Input.MoveX.Value, previousValue = Input.MoveX.PreviousValue,
                keyboardRightDown = MInput.Keyboard.CurrentState.IsKeyDown(Keys.Right),
                keyboardPreviousRightDown = MInput.Keyboard.PreviousState.IsKeyDown(Keys.Right),
                positiveKeyboard = KeyNames(Input.MoveX.Positive), negativeKeyboard = KeyNames(Input.MoveX.Negative),
                inputSampled = true, inputSamplingProfile = "source-axis-only",
                rawFixtureBoundary = "default KeyboardState before any held fixture; Microsoft.Xna.Framework.Input.Keyboard.GetState not invoked",
                fullMInputUpdateExecuted = false, gamepadSampled = false, buttonsSampled = false,
                prePosition = new[] { player.Position.X, player.Position.Y },
                preSpeed = new[] { player.Speed.X, player.Speed.Y },
                claim = "Neutral axis baseline through the original VirtualIntegerAxis.Update; key is up and Value remains 0" });
            if (Input.MoveX.Value != 0)
                throw new InvalidOperationException("Neutral source axis did not record Value==0");

            int spawnIntegerX = (int)normalPosition[0];
            int heldTicks = 0;
            int movementTick = -1;
            int integerAfter = spawnIntegerX;
            float firstHeldSpeedX = 0f;
            float firstHeldRemainderBefore = 0f;
            float firstHeldRemainderAfter = 0f;
            for (int heldIndex = 0; heldIndex < 4; heldIndex++)
            {
                int tick = normalTick + 1 + heldIndex;
                MInput.Keyboard.PreviousState = default(KeyboardState);
                MInput.Keyboard.CurrentState = new KeyboardState(Keys.Right);
                bool previousRight = MInput.Keyboard.PreviousState.IsKeyDown(Keys.Right);
                Input.MoveX.Update();
                bool rightDown = MInput.Keyboard.CurrentState.IsKeyDown(Keys.Right);
                var prePosition = new[] { player.Position.X, player.Position.Y };
                var preSpeed = new[] { player.Speed.X, player.Speed.Y };
                var preRemainder = new[] { player.PositionRemainder.X, player.PositionRemainder.Y };
                int preState = player.StateMachine.State;
                probe.Write(new { @event = "caller-input-right-axis", tick, heldIndex,
                    value = Input.MoveX.Value, previousValue = Input.MoveX.PreviousValue,
                    keyboardRightDown = rightDown, keyboardPreviousRightDown = previousRight,
                    positiveKeyboard = KeyNames(Input.MoveX.Positive), negativeKeyboard = KeyNames(Input.MoveX.Negative),
                    positiveAltKeyboard = KeyNames(Input.MoveX.PositiveAlt), negativeAltKeyboard = KeyNames(Input.MoveX.NegativeAlt),
                    moveXInverted = Input.MoveX.Inverted, prePosition, preSpeed, preRemainder, preState,
                    inputSampled = true, inputSamplingProfile = "source-axis-only",
                    rawFixtureBoundary = "KeyboardState(Keys.Right) supplied by caller; Microsoft.Xna.Framework.Input.Keyboard.GetState not invoked",
                    fullMInputUpdateExecuted = false, gamepadSampled = false, buttonsSampled = false,
                    sourceOrder = "caller fixture -> original VirtualIntegerAxis.Update -> Binding.Axis -> MInput.Keyboard.Check -> KeyboardState.IsKeyDown, then the real Player.Update/NormalUpdate" });
                if (Input.MoveX.Value != 1)
                    throw new InvalidOperationException("Held source axis did not establish Value==1");
                heldTicks++;
                bool sceneRan = Tick(probe, driver, tick, "source-axis-only");
                var postPosition = new[] { player.Position.X, player.Position.Y };
                var postSpeed = new[] { player.Speed.X, player.Speed.Y };
                var postRemainder = new[] { player.PositionRemainder.X, player.PositionRemainder.Y };
                int postState = player.StateMachine.State;
                int beforeInt = (int)prePosition[0];
                int afterInt = (int)postPosition[0];
                if (heldIndex == 0)
                {
                    firstHeldSpeedX = postSpeed[0];
                    firstHeldRemainderBefore = preRemainder[0];
                    firstHeldRemainderAfter = postRemainder[0];
                    if (postSpeed[0] <= 0f)
                        throw new InvalidOperationException("First held Normal tick did not produce positive horizontal velocity");
                    if (afterInt == beforeInt && postRemainder[0] == preRemainder[0])
                        throw new InvalidOperationException("First held Normal tick advanced neither integer X nor the X subpixel counter");
                }
                probe.Write(new { @event = "caller-input-right-held-tick", tick, heldIndex, sceneRan,
                    axisValueBeforeTick = 1, prePosition, preSpeed, preRemainder, preState,
                    postPosition, postSpeed, postRemainder, postState, state = postState, dead = player.Dead,
                    onGroundField = CachedOnGround(player), onGroundQuery = player.OnGround(), facing = player.Facing.ToString(),
                    horizontalDelta = postPosition[0] - prePosition[0], speedXPositive = postSpeed[0] > 0f,
                    subpixelAdvanced = postRemainder[0] != preRemainder[0],
                    integerXBefore = beforeInt, integerXAfter = afterInt, integerXIncreased = afterInt > beforeInt,
                    movedFromSpawn = afterInt > spawnIntegerX,
                    inputSampled = true, inputSamplingProfile = "source-axis-only",
                    fullMInputUpdateExecuted = false, gamepadSampled = false, buttonsSampled = false });
                if (player.Dead || postState != 0)
                    throw new InvalidOperationException("Held Normal tick left Normal0 alive state");
                integerAfter = afterInt;
                if (afterInt > spawnIntegerX) { movementTick = tick; break; }
            }
            if (movementTick < 0)
                throw new InvalidOperationException("Source +X axis did not establish an integer X increase within four held ticks");

            MInput.Keyboard.PreviousState = new KeyboardState(Keys.Right);
            MInput.Keyboard.CurrentState = default(KeyboardState);
            Input.MoveX.Update();
            probe.Write(new { @event = "caller-input-right-release-axis", value = Input.MoveX.Value,
                previousValue = Input.MoveX.PreviousValue,
                keyboardRightDown = MInput.Keyboard.CurrentState.IsKeyDown(Keys.Right),
                keyboardPreviousRightDown = MInput.Keyboard.PreviousState.IsKeyDown(Keys.Right),
                inputSampled = true, inputSamplingProfile = "source-axis-only",
                fullMInputUpdateExecuted = false, gamepadSampled = false, buttonsSampled = false,
                claim = "Axis-only release update; no real tick follows and no claim is made that velocity stops immediately" });
            if (Input.MoveX.Value != 0)
                throw new InvalidOperationException("Released source axis did not return Value==0");

            probe.Write(new { @event = "completed", status = "input-right-source-axis-only-natural-respawn-integer-move",
                scenario = "input-right",
                naturalSpawn = new { state = 14, position = naturalPosition, speed = naturalSpeed },
                normal0 = new { tick = normalTick, state = 0, position = normalPosition, speed = normalSpeed, dead = false },
                neutralAxisValue = 0, heldTicks, movementTick, axisValueAtMovement = 1,
                firstHeldSpeedX, firstHeldRemainderBefore, firstHeldRemainderAfter,
                integerXBefore = spawnIntegerX, integerXAfter = integerAfter,
                displacementX = integerAfter - spawnIntegerX,
                stateAfter = player.StateMachine.State, alive = !player.Dead,
                postPosition = new[] { player.Position.X, player.Position.Y },
                postSpeed = new[] { player.Speed.X, player.Speed.Y },
                postRemainder = new[] { player.PositionRemainder.X, player.PositionRemainder.Y },
                controls = new { rightKeyboard = KeyNames(Settings.Instance.Right),
                    leftKeyboard = KeyNames(Settings.Instance.Left), jumpKeyboard = KeyNames(Settings.Instance.Jump),
                    moveXPositiveKeyboard = KeyNames(Input.MoveX.Positive),
                    moveXNegativeKeyboard = KeyNames(Input.MoveX.Negative) },
                inputSampled = true, inputSamplingProfile = "source-axis-only",
                rawFixtureBoundary = "Microsoft.Xna.Framework.Input.KeyboardState(Keys.Right) with PreviousState=default; Keyboard.GetState not invoked and no hardware/platform read",
                fullMInputUpdateExecuted = false, gamepadSampled = false, buttonsSampled = false,
                keyboardSampling = "only KeyboardState.IsKeyDown through original MInput.Keyboard.Check inside original VirtualIntegerAxis.Update; KeyboardData.Update/MInput.Update/UpdateVirtualInputs are not enabled",
                callerPositionSpeedWrites = 0,
                callerWriteGuard = "test_input_right_caller_declares_only_right_key_and_never_seeds_motion scans RunInputRight for Position/Speed/PositionRemainder/death-counter assignments",
                sourceProfile = "source-synced-6b-01; actual LoadLevel(Respawn) natural spawn; single-room-header; partial map; no full input/gamepad/keyboard-hardware/full-family proof",
                nativeAttempts = NativeImportGuard.Attempts.Length,
                nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, hazardOrderingDirectionalCollisionDeathParity = false,
                claim = "Actual source LoadLevel Respawn14->Normal0 natural spawn; one declared KeyboardState raw fixture feeds original VirtualIntegerAxis.Update/Binding.Axis/MInput.Keyboard.Check/IsKeyDown before real Player.Update; +X Value==1 and the first held Normal tick yields positive Speed.X, with integer X increase within four ticks and no caller Position/Speed/counter writes; not full MInput sampling or physical keyboard, no gamepad/button/hardware/native/family closure" });
        }
        catch (Exception error)
        {
            probe.Write(new { @event = "boundary", member = probe.Member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAtBoundary = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, status = "blocked-input-right-prefix-not-source-axis-motion" });
            throw;
        }
    }

    sealed class JumpInputSample
    {
        public int Tick;
        public int SampleIndex;
        public bool PreviousCDown;
        public bool CurrentCDown;
        public float FreezeBefore;
        public float FreezeAfter;
        public bool SceneRan;
        public bool Crossing;
        public bool Check;
        public bool Pressed;
        public bool Released;
        public float BufferBefore;
        public float BufferAfterUpdate;
        public float BufferAfterScene;
        public int StateAfter;
        public bool DeadAfter;
        public float[] SpeedAfter;
        public bool OnGroundFieldAfter;
        public bool OnGroundQueryAfter;
        public float JumpGraceTimerAfter;
        public bool BufferConsumedByScene => BufferAfterScene < BufferAfterUpdate;
    }

    static T VirtualButtonField<T>(VirtualButton button, string name)
    {
        var field = typeof(VirtualButton).GetField(name, BindingFlags.NonPublic | BindingFlags.Instance);
        if (field == null || field.GetValue(button) is not T value)
            throw new InvalidOperationException("VirtualButton." + name + " missing");
        return value;
    }

    static JumpInputSample SampleJumpButton(Probe probe, FrameDriver driver, Player player, int tick, int sampleIndex,
        string mode, KeyboardState previous, KeyboardState current)
    {
        probe.Member = "driver-tick";
        SetEngineTick(1f / 60f);
        float deltaTime = Engine.DeltaTime;
        float rawDeltaTime = Engine.RawDeltaTime;
        ulong frameCounter = Engine.FrameCounter;
        float freezeTimerBefore = Engine.FreezeTimer;
        bool freezeBefore = freezeTimerBefore > 0f;
        bool previousCDown = previous.IsKeyDown(Keys.C);
        bool currentCDown = current.IsKeyDown(Keys.C);
        MInput.Keyboard.PreviousState = previous;
        MInput.Keyboard.CurrentState = current;

        bool checkBefore = Input.Jump.Check;
        bool pressedBefore = Input.Jump.Pressed;
        bool releasedBefore = Input.Jump.Released;
        float bufferBefore = VirtualButtonField<float>(Input.Jump, "bufferCounter");
        float repeatBefore = VirtualButtonField<float>(Input.Jump, "repeatCounter");
        bool consumedBefore = VirtualButtonField<bool>(Input.Jump, "consumed");
        bool repeatingBefore = Input.Jump.Repeating;
        int stateBefore = player.StateMachine.State;
        bool deadBefore = player.Dead;
        var positionBefore = new[] { player.Position.X, player.Position.Y };
        var speedBefore = new[] { player.Speed.X, player.Speed.Y };
        bool onGroundFieldBefore = CachedOnGround(player);
        bool onGroundQueryBefore = player.OnGround();
        float jumpGraceTimerBefore = PrivateField<float>(player, "jumpGraceTimer");

        Input.Jump.Update();

        bool checkAfterUpdate = Input.Jump.Check;
        bool pressedAfterUpdate = Input.Jump.Pressed;
        bool releasedAfterUpdate = Input.Jump.Released;
        float bufferAfterUpdate = VirtualButtonField<float>(Input.Jump, "bufferCounter");
        float repeatAfterUpdate = VirtualButtonField<float>(Input.Jump, "repeatCounter");
        bool consumedAfterUpdate = VirtualButtonField<bool>(Input.Jump, "consumed");
        bool repeatingAfterUpdate = Input.Jump.Repeating;

        driver.scene = probe.Level;
        driver.Tick();
        bool sceneRan = !freezeBefore && !driver.DashAssistFreeze;

        bool checkAfterScene = Input.Jump.Check;
        bool pressedAfterScene = Input.Jump.Pressed;
        bool releasedAfterScene = Input.Jump.Released;
        float bufferAfterScene = VirtualButtonField<float>(Input.Jump, "bufferCounter");
        float repeatAfterScene = VirtualButtonField<float>(Input.Jump, "repeatCounter");
        bool repeatingAfterScene = Input.Jump.Repeating;
        int stateAfter = player.StateMachine.State;
        bool deadAfter = player.Dead;
        var positionAfter = new[] { player.Position.X, player.Position.Y };
        var speedAfter = new[] { player.Speed.X, player.Speed.Y };
        bool onGroundFieldAfter = CachedOnGround(player);
        bool onGroundQueryAfter = player.OnGround();
        float jumpGraceTimerAfter = PrivateField<float>(player, "jumpGraceTimer");
        bool crossing = freezeBefore && Engine.FreezeTimer == 0f;

        probe.Write(new { @event = "caller-input-jump-buffer-frame", mode, sampleIndex, tick,
            enginePhase = new { deltaTime, rawDeltaTime, frameCounter },
            keys = new { previousCDown, currentCDown },
            freezeBefore = freezeTimerBefore, freezeAfter = Engine.FreezeTimer, sceneRan, crossing,
            before = new { check = checkBefore, pressed = pressedBefore, released = releasedBefore,
                bufferCounter = bufferBefore, repeatCounter = repeatBefore, consumed = consumedBefore,
                repeating = repeatingBefore, bufferTime = Input.Jump.BufferTime, threshold = Input.Jump.Threshold,
                gamepadIndex = Input.Jump.GamepadIndex },
            afterUpdate = new { check = checkAfterUpdate, pressed = pressedAfterUpdate, released = releasedAfterUpdate,
                bufferCounter = bufferAfterUpdate, repeatCounter = repeatAfterUpdate, consumed = consumedAfterUpdate,
                repeating = repeatingAfterUpdate, bufferTime = Input.Jump.BufferTime, threshold = Input.Jump.Threshold },
            afterScene = new { check = checkAfterScene, pressed = pressedAfterScene, released = releasedAfterScene,
                bufferCounter = bufferAfterScene, repeatCounter = repeatAfterScene, repeating = repeatingAfterScene,
                bufferTime = Input.Jump.BufferTime, threshold = Input.Jump.Threshold },
            playerBefore = new { state = stateBefore, dead = deadBefore, position = positionBefore, speed = speedBefore,
                onGroundField = onGroundFieldBefore, onGroundQuery = onGroundQueryBefore, jumpGraceTimer = jumpGraceTimerBefore },
            playerAfterScene = new { state = stateAfter, dead = deadAfter, position = positionAfter, speed = speedAfter,
                onGroundField = onGroundFieldAfter, onGroundQuery = onGroundQueryAfter, jumpGraceTimer = jumpGraceTimerAfter },
            inputSampled = true, inputSamplingProfile = "source-button-only",
            rawFixtureBoundary = "typed KeyboardState previous/current fixture; Microsoft.Xna.Framework.Input.Keyboard.GetState not invoked",
            fullMInputUpdateExecuted = false, gamepadSampled = false, buttonsSampled = false, keyboardButtonSampled = true,
            controlledEngineFreeze = true,
            sourceOrder = "caller Engine clock setup mirrors original Engine.Update 226-229 -> raw KeyboardState fixture -> original Input.Jump.Update -> original FrameDriver.Tick freeze/Scene branch; no MInput.Update or UpdateVirtualInputs" });
        WriteDriverTick(probe, tick, sceneRan, freezeBefore, "source-button-only");

        return new JumpInputSample {
            Tick = tick, SampleIndex = sampleIndex, PreviousCDown = previousCDown, CurrentCDown = currentCDown,
            FreezeBefore = freezeTimerBefore, FreezeAfter = Engine.FreezeTimer, SceneRan = sceneRan, Crossing = crossing,
            Check = checkAfterUpdate, Pressed = pressedAfterUpdate, Released = releasedAfterUpdate,
            BufferBefore = bufferBefore, BufferAfterUpdate = bufferAfterUpdate, BufferAfterScene = bufferAfterScene,
            StateAfter = stateAfter, DeadAfter = deadAfter, SpeedAfter = speedAfter,
            OnGroundFieldAfter = onGroundFieldAfter, OnGroundQueryAfter = onGroundQueryAfter,
            JumpGraceTimerAfter = jumpGraceTimerAfter
        };
    }

    public static void RunInputJumpBuffer(string[] args)
    {
        string[] modes = { "press-on-crossing", "held-expired-on-crossing", "released-on-crossing" };
        if (args.Length != 3 || !modes.Contains(args[1]))
            throw new ArgumentException("Expected a declared jump-buffer mode and private trace path");
        string mode = args[1];
        using var probe = new Probe(args, 2);
        try
        {
            probe.Bootstrap();
            probe.Invoke("caller-engine-pooler", () => {
                var property = typeof(Engine).GetProperty("Pooler", BindingFlags.Public | BindingFlags.Static);
                property.GetSetMethod(true).Invoke(null, new object[] { new Pooler() });
                probe.Write(new { @event = "caller-pooler", initialized = Engine.Pooler != null });
            });
            probe.Invoke("caller-engine-driver-scene", () => {
                PrepareEngineDriver(probe.Level);
                probe.Write(new { @event = "caller-engine-scene", scene = Identity(Engine.Scene), sameLevel = Engine.Scene == probe.Level });
            });
            probe.Invoke("caller-rumble-profile", () => { Settings.Instance.Rumble = RumbleAmount.Off; });
            LoadGuiAtlas(probe.Content);
            probe.Invoke("caller-level-loader-fields", () => PrepareLevelLoaderFields(probe.Level));

            string[] jumpKeyboardBefore = KeyNames(Settings.Instance.Jump);
            string[] jumpControllerBefore = Settings.Instance.Jump.Controller.Select(button => button.ToString()).ToArray();
            probe.Invoke("caller-input-jump-buffer-controls", () => {
                bool added = Settings.Instance.Jump.Add(Keys.C);
                Input.Initialize();
                bool controllerCleared = Input.Jump.Binding.Controller.Count == 0;
                Input.Jump.Binding.Controller.Clear();
                probe.Write(new { @event = "caller-input-jump-buffer-controls", profile = "source-button-only",
                    added, controllerCleared, jumpKeyboardBefore, jumpKeyboardAfter = KeyNames(Input.Jump.Binding),
                    jumpControllerBefore, jumpControllerAfter = Input.Jump.Binding.Controller.Select(button => button.ToString()).ToArray(),
                    inputJumpBindingIsSettings = ReferenceEquals(Input.Jump.Binding, Settings.Instance.Jump),
                    bufferTime = Input.Jump.BufferTime, threshold = Input.Jump.Threshold, gamepadIndex = Input.Jump.GamepadIndex,
                    defaultKeyboardControlsExecuted = false, inputSampled = false,
                    claim = "Declared original Binding.Add(Keys.C) fixture followed by Input.Initialize and public Binding.Controller.Clear; source default-key setup/AfterLoad is not executed and no gamepad buttons are sampled" });
            });
            if (jumpKeyboardBefore.Length != 0 || !KeyNames(Input.Jump.Binding).SequenceEqual(new[] { "C" })
                || Input.Jump.Binding.Controller.Count != 0 || !ReferenceEquals(Input.Jump.Binding, Settings.Instance.Jump))
                throw new InvalidOperationException("Declared keyboard-only Jump binding fixture did not rebuild Input.Jump");

            probe.Invoke("Celeste.Level.LoadLevel(Respawn)", () => probe.Level.LoadLevel(Player.IntroTypes.Respawn));
            var player = probe.Level.Tracker.GetEntity<Player>();
            if (player == null || player.StateMachine.State != 14)
                throw new InvalidOperationException("Input jump-buffer probe requires the source-created Respawn14 Player");
            var naturalPosition = new[] { player.Position.X, player.Position.Y };
            var naturalSpeed = new[] { player.Speed.X, player.Speed.Y };
            probe.Write(new { @event = "caller-input-jump-buffer-load", state = player.StateMachine.State,
                position = naturalPosition, speed = naturalSpeed, entities = probe.Level.Entities.Count,
                wipe = WipeState(probe.Level), inputSampled = false,
                claim = "Original LoadLevel(Respawn) created the Player; caller records the natural spawn without writing pose or speed" });

            var driver = new FrameDriver { scene = probe.Level };
            int normalTick = -1;
            for (int tick = 0; tick < 360; tick++)
            {
                Tick(probe, driver, tick);
                if (player.StateMachine.State == 0) { normalTick = tick; break; }
            }
            if (normalTick < 0) throw new InvalidOperationException("Respawn14 did not reach Normal0");
            var normalPosition = new[] { player.Position.X, player.Position.Y };
            var normalSpeed = new[] { player.Speed.X, player.Speed.Y };
            bool normalOnGroundField = CachedOnGround(player);
            bool normalOnGroundQuery = player.OnGround();
            float normalJumpGraceTimer = PrivateField<float>(player, "jumpGraceTimer");
            probe.Write(new { @event = "caller-input-jump-buffer-normal0", tick = normalTick, state = player.StateMachine.State,
                position = normalPosition, speed = normalSpeed, dead = player.Dead, scale = new[] { player.Sprite.Scale.X, player.Sprite.Scale.Y },
                wipe = WipeState(probe.Level), onGroundField = normalOnGroundField, onGroundQuery = normalOnGroundQuery,
                jumpGraceTimer = normalJumpGraceTimer, freezeBefore = Engine.FreezeTimer, inputSampled = false,
                claim = "Source Respawn14 transition reached Normal0 at the natural spawn; no jump-buffer input or caller motion write happened yet" });
            if (normalPosition[0] != naturalPosition[0] || normalPosition[1] != naturalPosition[1])
                throw new InvalidOperationException("Natural Respawn position changed before any jump-buffer sample");

            float deltaTime = 1f / 60f;
            const int frozenFrameGuard = 12;
            float freezeDuration = mode == "press-on-crossing" ? deltaTime
                : mode == "held-expired-on-crossing" ? 8f * deltaTime : 2f * deltaTime;
            string freezeFormula = mode == "press-on-crossing" ? "1*RawDeltaTime"
                : mode == "held-expired-on-crossing" ? "8*RawDeltaTime" : "2*RawDeltaTime";
            Engine.FreezeTimer = freezeDuration;
            probe.Write(new { @event = "caller-input-jump-buffer-freeze", mode, duration = freezeDuration,
                formula = freezeFormula, rawDeltaTime = Engine.RawDeltaTime, deltaTime = Engine.DeltaTime,
                frozenFrameGuard, manualFreezeDecrements = 0, callerSceneAdvances = 0,
                sourceProfile = "controlled-engine-freeze-duration-fixture-not-source-dash-freeze",
                claim = "Caller sets the original Engine.FreezeTimer duration once; the untouched original FrameDriver.Tick freeze branch performs every decrement and sets Scene skipping; no player motion, state or jump-buffer field is forced" });

            int sampleTick = normalTick + 1;
            var samples = new List<JumpInputSample>();
            JumpInputSample pressSample;
            JumpInputSample crossingSample;
            JumpInputSample resumedSample;
            if (mode == "press-on-crossing")
            {
                pressSample = SampleJumpButton(probe, driver, player, sampleTick, 0, mode, default(KeyboardState), new KeyboardState(Keys.C));
                samples.Add(pressSample);
                if (!pressSample.Crossing || pressSample.SceneRan || !pressSample.Check || !pressSample.Pressed || pressSample.Released)
                    throw new InvalidOperationException("Press-on-crossing frame did not observe the original buffer/Check/Pressed with Scene skipped");
                resumedSample = SampleJumpButton(probe, driver, player, sampleTick + 1, 1, mode, new KeyboardState(Keys.C), new KeyboardState(Keys.C));
                samples.Add(resumedSample);
                if (!resumedSample.SceneRan || !resumedSample.Check || !resumedSample.Pressed || resumedSample.Released)
                    throw new InvalidOperationException("Held frame after the zero crossing did not resume Scene with the buffered Pressed value");
                crossingSample = pressSample;
            }
            else if (mode == "held-expired-on-crossing")
            {
                int heldIndex = 0;
                crossingSample = null;
                while (crossingSample == null && heldIndex < frozenFrameGuard)
                {
                    var sample = SampleJumpButton(probe, driver, player, sampleTick + heldIndex, heldIndex, mode,
                        heldIndex == 0 ? default(KeyboardState) : new KeyboardState(Keys.C), new KeyboardState(Keys.C));
                    samples.Add(sample);
                    if (sample.Crossing) crossingSample = sample;
                    heldIndex++;
                }
                if (crossingSample == null)
                    throw new InvalidOperationException("Held jump buffer did not observe a freeze zero crossing within the declared guard");
                pressSample = samples[0];
                if (!pressSample.Pressed || pressSample.BufferAfterUpdate <= 0f)
                    throw new InvalidOperationException("Held sequence did not establish the original press buffer");
                if (!crossingSample.Check || crossingSample.Pressed || crossingSample.Released || crossingSample.SceneRan)
                    throw new InvalidOperationException("Held-expired crossing did not observe Check true/Pressed false/Released false with Scene skipped");
                resumedSample = SampleJumpButton(probe, driver, player, sampleTick + heldIndex, heldIndex, mode,
                    new KeyboardState(Keys.C), new KeyboardState(Keys.C));
                samples.Add(resumedSample);
                if (!resumedSample.SceneRan || resumedSample.Pressed || resumedSample.Released || !resumedSample.Check)
                    throw new InvalidOperationException("Held frame after the zero crossing did not resume Scene with an expired buffer");
            }
            else
            {
                pressSample = SampleJumpButton(probe, driver, player, sampleTick, 0, mode, default(KeyboardState), new KeyboardState(Keys.C));
                samples.Add(pressSample);
                if (pressSample.SceneRan || !pressSample.Pressed) throw new InvalidOperationException("Release mode press frame was not buffered");
                crossingSample = SampleJumpButton(probe, driver, player, sampleTick + 1, 1, mode, new KeyboardState(Keys.C), default(KeyboardState));
                samples.Add(crossingSample);
                if (!crossingSample.Crossing || crossingSample.SceneRan || crossingSample.Check || crossingSample.Pressed
                    || !crossingSample.Released || crossingSample.BufferAfterUpdate != 0f)
                    throw new InvalidOperationException("Release-on-crossing frame did not clear the original buffer with Released true and Scene skipped");
                resumedSample = SampleJumpButton(probe, driver, player, sampleTick + 2, 2, mode, default(KeyboardState), default(KeyboardState));
                samples.Add(resumedSample);
                if (!resumedSample.SceneRan || resumedSample.Check || resumedSample.Pressed || resumedSample.Released)
                    throw new InvalidOperationException("Neutral frame after the zero crossing did not resume Scene without a jump press");
            }

            bool bufferConsumedByScene = samples.Any(sample => sample.BufferConsumedByScene);
            if (bufferConsumedByScene)
                throw new InvalidOperationException("Unexpected source Jump/ConsumeBuffer consumed the sampled buffer; stopping instead of shimming the input engine");
            int frozenFrames = samples.Count(sample => sample.FreezeBefore > 0f);
            if (frozenFrames > frozenFrameGuard)
                throw new InvalidOperationException("Controlled freeze exceeded the declared frame guard");

            probe.Write(new { @event = "completed", status = "input-jump-buffer-" + mode + "-button-only-no-source-jump",
                scenario = "input-jump-buffer", mode,
                naturalSpawn = new { state = 14, position = naturalPosition, speed = naturalSpeed },
                normal0 = new { tick = normalTick, state = 0, position = normalPosition, speed = normalSpeed, dead = false,
                    onGroundField = normalOnGroundField, onGroundQuery = normalOnGroundQuery, jumpGraceTimer = normalJumpGraceTimer },
                freeze = new { duration = freezeDuration, formula = freezeFormula, frozenFrameGuard },
                sampledFrames = samples.Count, frozenFrames,
                crossingSampleIndex = crossingSample.SampleIndex, crossingTick = crossingSample.Tick,
                crossingSceneRan = crossingSample.SceneRan,
                press = new { tick = pressSample.Tick, freezeBefore = pressSample.FreezeBefore, freezeAfter = pressSample.FreezeAfter,
                    sceneRan = pressSample.SceneRan, previousCDown = pressSample.PreviousCDown, currentCDown = pressSample.CurrentCDown,
                    bufferBefore = pressSample.BufferBefore, bufferAfterUpdate = pressSample.BufferAfterUpdate,
                    bufferAfterScene = pressSample.BufferAfterScene, check = pressSample.Check, pressed = pressSample.Pressed,
                    released = pressSample.Released },
                crossing = new { tick = crossingSample.Tick, freezeBefore = crossingSample.FreezeBefore,
                    freezeAfter = crossingSample.FreezeAfter, sceneRan = crossingSample.SceneRan,
                    previousCDown = crossingSample.PreviousCDown, currentCDown = crossingSample.CurrentCDown,
                    bufferBefore = crossingSample.BufferBefore, bufferAfterUpdate = crossingSample.BufferAfterUpdate,
                    bufferAfterScene = crossingSample.BufferAfterScene, check = crossingSample.Check,
                    pressed = crossingSample.Pressed, released = crossingSample.Released },
                resumed = new { tick = resumedSample.Tick, freezeBefore = resumedSample.FreezeBefore,
                    freezeAfter = resumedSample.FreezeAfter, sceneRan = resumedSample.SceneRan,
                    previousCDown = resumedSample.PreviousCDown, currentCDown = resumedSample.CurrentCDown,
                    bufferBefore = resumedSample.BufferBefore, bufferAfterUpdate = resumedSample.BufferAfterUpdate,
                    bufferAfterScene = resumedSample.BufferAfterScene, check = resumedSample.Check,
                    pressed = resumedSample.Pressed, released = resumedSample.Released,
                    stateAfter = resumedSample.StateAfter, deadAfter = resumedSample.DeadAfter,
                    speedAfter = resumedSample.SpeedAfter, onGroundField = resumedSample.OnGroundFieldAfter,
                    onGroundQuery = resumedSample.OnGroundQueryAfter, jumpGraceTimer = resumedSample.JumpGraceTimerAfter },
                bufferLifecycle = new { pressBuffer = pressSample.BufferAfterUpdate,
                    expiredBuffer = crossingSample.BufferAfterUpdate,
                    releaseClearedBuffer = crossingSample.Released && crossingSample.BufferAfterUpdate == 0f },
                actualJump = false, bufferConsumedByScene,
                onGroundField = resumedSample.OnGroundFieldAfter, onGroundQuery = resumedSample.OnGroundQueryAfter,
                jumpGraceTimer = resumedSample.JumpGraceTimerAfter,
                inputSampled = true, inputSamplingProfile = "source-button-only",
                rawFixtureBoundary = "typed KeyboardState previous/current fixture for Keys.C; Keyboard.GetState not invoked and no hardware/platform read",
                fullMInputUpdateExecuted = false, gamepadSampled = false, buttonsSampled = false, keyboardButtonSampled = true,
                controlledEngineFreeze = true,
                freezeFixture = "caller-set Engine.FreezeTimer duration only; original FrameDriver freeze branch decrements and skips Scene; not a source Dash freeze",
                callerPositionSpeedWrites = 0, callerFreezeWrites = 1, callerFreezeDecrements = 0, callerSceneAdvances = 0,
                callerWriteGuard = "test_input_jump_buffer_caller_is_keyboard_only_without_full_input_or_motion_writes scans RunInputJumpBuffer",
                sourceProfile = "source-synced-6b-01; actual LoadLevel(Respawn) natural spawn; single-room-header; partial map; SolidTiles null; keyboard-only Jump VirtualButton buffer; no actual jump",
                nativeAttempts = NativeImportGuard.Attempts.Length,
                nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, hazardOrderingDirectionalCollisionDeathParity = false,
                claim = "Actual source LoadLevel Respawn14->Normal0 natural spawn; declared keyboard-only Settings.Instance.Jump.Add(Keys.C) fixture and original Input.Jump.Update buffer sampling before the untouched original FrameDriver freeze branch; caller-set controlled Engine.FreezeTimer only, never decremented or Scene-advanced by caller; "
                    + mode + " observes the original buffer/Check/Pressed/Released on the zero-crossing frame with Scene skipped, then real Normal0 resumes; no actual jump or ConsumeBuffer claim, not full MInput/gamepad/button-hardware/full-family proof" });
        }
        catch (Exception error)
        {
            probe.Write(new { @event = "boundary", member = probe.Member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAtBoundary = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, status = "blocked-input-jump-buffer-prefix-not-source-button-buffer" });
            throw;
        }
    }

    static (string ForegroundSha, string BackgroundSha, int ForegroundTilesets, int BackgroundTilesets, int AtlasMissing, int Overlays) ReadTileContentPins(string root)
    {
        var expected = new Dictionary<string, string> {
            ["ForegroundTiles.xml"] = "1d31280a6ef0a81909186954648aa3e47e30de036404e3117916dbcdd0dfee65",
            ["BackgroundTiles.xml"] = "fa2c03e2b41f72778bacbe2498927a5bfce81112e9645748d371606bd4ed016b",
        };
        int foregroundTilesets = 0, backgroundTilesets = 0, atlasMissing = 0, overlays = 0;
        string foregroundSha = null, backgroundSha = null;
        foreach (var name in expected.Keys)
        {
            string path = Path.Combine(root, "Graphics", name);
            byte[] data = File.ReadAllBytes(path);
            string sha = Convert.ToHexString(SHA256.HashData(data)).ToLowerInvariant();
            if (sha != expected[name]) throw new InvalidDataException("Tile XML hash changed: " + name);
            string text = System.Text.Encoding.UTF8.GetString(data);
            overlays += text.Split(new[] { "overlay=\"" }, StringSplitOptions.None).Length - 1;
            var xml = new XmlDocument();
            xml.Load(path);
            foreach (XmlElement item in xml.GetElementsByTagName("Tileset"))
            {
                string tileset = item.Attr("path");
                if (!GFX.Game.Has("tilesets/" + tileset)) atlasMissing++;
                if (name.StartsWith("Foreground", StringComparison.Ordinal)) foregroundTilesets++;
                else backgroundTilesets++;
            }
            if (name.StartsWith("Foreground", StringComparison.Ordinal)) foregroundSha = sha;
            else backgroundSha = sha;
        }
        if (foregroundTilesets != 24 || backgroundTilesets != 15 || atlasMissing != 0 || overlays != 0)
            throw new InvalidDataException("Tile XML profile changed: FG=" + foregroundTilesets + " BG=" + backgroundTilesets + " missing=" + atlasMissing + " overlays=" + overlays);
        return (foregroundSha, backgroundSha, foregroundTilesets, backgroundTilesets, atlasMissing, overlays);
    }

    static void PrepareContentRoot(string root)
    {
        var content = (ContentManager)RuntimeHelpers.GetUninitializedObject(typeof(ContentManager));
        content.RootDirectory = root;
        var property = typeof(Game).GetProperty("Content", BindingFlags.Public | BindingFlags.Instance);
        if (property?.GetSetMethod(true) == null) throw new InvalidOperationException("Game.Content setter missing");
        property.GetSetMethod(true).Invoke(Engine.Instance, new object[] { content });
        if (Engine.Instance.Content.RootDirectory != root) throw new InvalidOperationException("Content root was not installed");
    }

    static string CharMapSha(VirtualMap<char> data)
    {
        byte[] bytes = new byte[data.Columns * data.Rows * 2];
        int index = 0;
        for (int y = 0; y < data.Rows; y++)
            for (int x = 0; x < data.Columns; x++)
            {
                char value = data[x, y];
                bytes[index++] = (byte)value;
                bytes[index++] = (byte)(value >> 8);
            }
        return Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
    }

    static int[] Rect(Rectangle rectangle) => new[] { rectangle.X, rectangle.Y, rectangle.Width, rectangle.Height };

    static int TileAssignments(TileGrid grid)
    {
        int count = 0;
        for (int y = 0; y < grid.Tiles.Rows; y++)
            for (int x = 0; x < grid.Tiles.Columns; x++)
                if (grid.Tiles[x, y] != null) count++;
        return count;
    }

    static void RequireGround(Probe probe, Player player, string phase, int tick)
    {
        var solidTiles = probe.Level.SolidTiles;
        if (solidTiles == null) throw new InvalidOperationException("SolidTiles missing at " + phase + " tick " + tick);
        if (!CachedOnGround(player) || !player.OnGround()) throw new InvalidOperationException("Player is not grounded at " + phase + " tick " + tick);
        if (!player.OnSafeGround) throw new InvalidOperationException("Ground is not safe at " + phase + " tick " + tick);
        float grace = PrivateField<float>(player, "jumpGraceTimer");
        if (grace <= 0f) throw new InvalidOperationException("jumpGraceTimer not positive at " + phase + " tick " + tick);
        if (player.Position.X != 19f || player.Position.Y != 144f) throw new InvalidOperationException("Natural spawn moved at " + phase + " tick " + tick + ": " + player.Position);
        var hit = player.CollideFirst<Solid>(player.Position + Vector2.UnitY);
        if (!ReferenceEquals(hit, solidTiles)) throw new InvalidOperationException("Source UnitY collision did not identify SolidTiles at " + phase + " tick " + tick);
        var grid = solidTiles.Grid;
        if (!grid[8, 26] || !grid[9, 26] || !grid[10, 26] || !grid[11, 26])
            throw new InvalidOperationException("Original Grid floor cells changed at " + phase + " tick " + tick);
        string row = new string(new[] { probe.Level.SolidsData[8, 26], probe.Level.SolidsData[9, 26], probe.Level.SolidsData[10, 26], probe.Level.SolidsData[11, 26] });
        if (row != "4331") throw new InvalidOperationException("Raw solids row changed at " + phase + " tick " + tick + ": " + row);
    }

    static object GroundTrace(Probe probe, Player player, string phase, int tick, string kind)
    {
        var solidTiles = probe.Level.SolidTiles;
        var hit = player.CollideFirst<Solid>(player.Position + Vector2.UnitY);
        var grid = solidTiles.Grid;
        string row = new string(new[] { probe.Level.SolidsData[8, 26], probe.Level.SolidsData[9, 26], probe.Level.SolidsData[10, 26], probe.Level.SolidsData[11, 26] });
        return new {
            @event = kind == "normal0" ? "caller-ground-normal0" : "caller-ground-live",
            phase, tick, position = new[] { player.Position.X, player.Position.Y }, speed = new[] { player.Speed.X, player.Speed.Y },
            onGroundField = CachedOnGround(player), onGroundQuery = player.OnGround(), onSafeGround = player.OnSafeGround,
            jumpGraceTimer = PrivateField<float>(player, "jumpGraceTimer"), collision = Identity(hit),
            collisionIsSolidTiles = ReferenceEquals(hit, solidTiles), solidTiles = Identity(solidTiles),
            gridCells = new[] { grid[8, 26], grid[9, 26], grid[10, 26], grid[11, 26] },
            worldFloor = new[] { solidTiles.Position.X + 8 * 8, solidTiles.Position.Y + 8 * 26 }, solidsRow = row
        };
    }

    static void WaitNormal(Probe probe, Player player, string phase)
    {
        int normalTick = -1;
        for (int tick = 0; tick < 360; tick++)
        {
            SetEngineTick(1f / 60f);
            probe.Level.BeforeUpdate();
            probe.Level.Update();
            probe.Level.AfterUpdate();
            if (normalTick < 0 && player.StateMachine.State == 0)
            {
                normalTick = tick;
                RequireGround(probe, player, phase, tick);
                probe.Write(GroundTrace(probe, player, phase, tick, "normal0"));
                continue;
            }
            if (normalTick >= 0)
            {
                RequireGround(probe, player, phase, tick);
                probe.Write(GroundTrace(probe, player, phase, tick, "live"));
                return;
            }
        }
        throw new InvalidOperationException("Respawn14 did not reach Normal0: " + phase);
    }

    static (SolidTiles Solid, BackgroundTiles Background, string Sha) PrepareGroundedRoom(Probe probe, string contentRoot)
    {
        string tileContent = Path.GetFullPath(contentRoot);
        string privateRoot = Path.GetFullPath(".audit/native-player-death-respawn") + Path.DirectorySeparatorChar;
        if (!tileContent.StartsWith(privateRoot, StringComparison.Ordinal)) throw new ArgumentException("Tile content must remain private");
        var contentPins = ReadTileContentPins(tileContent);
        probe.Write(new { @event = "caller-tile-content", contentRoot = tileContent,
            foregroundSha256 = contentPins.ForegroundSha, backgroundSha256 = contentPins.BackgroundSha,
            foregroundTilesets = contentPins.ForegroundTilesets, backgroundTilesets = contentPins.BackgroundTilesets,
            atlasMissing = contentPins.AtlasMissing, overlays = contentPins.Overlays,
            claim = "Pinned original PC tile XML; no AnimatedTiles copy, no overlay path" });
        probe.Bootstrap();
        probe.Invoke("caller-engine-pooler", () => {
            var property = typeof(Engine).GetProperty("Pooler", BindingFlags.Public | BindingFlags.Static);
            property.GetSetMethod(true).Invoke(null, new object[] { new Pooler() });
        });
        probe.Invoke("caller-engine-and-content-driver", () => {
            PrepareEngineDriver(probe.Level);
            PrepareContentRoot(tileContent);
        });
        probe.Write(new { @event = "caller-content-root", root = Engine.Instance.Content.RootDirectory,
            same = Engine.Instance.Content.RootDirectory == tileContent });
        LoadGuiAtlas(probe.Content);
        probe.Invoke("caller-level-loader-fields", () => PrepareLevelLoaderFields(probe.Level));
        probe.Invoke("caller-global-autotilers", () => {
            GFX.BGAutotiler = new Autotiler("Graphics/BackgroundTiles.xml");
            GFX.FGAutotiler = new Autotiler("Graphics/ForegroundTiles.xml");
        });
        var map = probe.Level.Session.MapData ?? throw new InvalidOperationException("Session map header missing");
        if (map.Levels.Count != 1) throw new InvalidDataException("Declared single-room header changed");
        var room = map.Levels[0];
        if (room.Name != "1" || room.Bounds.X != 0 || room.Bounds.Y != 0 || room.Bounds.Width != 320 || room.Bounds.Height != 180)
            throw new InvalidDataException("Declared source-normalized room header changed");
        int pad = 64;
        map.Bounds = new Rectangle(room.Bounds.X - pad, room.Bounds.Y - pad, room.Bounds.Width + pad * 2, room.Bounds.Height + pad * 2);
        var tileBounds = map.TileBounds;
        if (tileBounds.X != -8 || tileBounds.Y != -8 || tileBounds.Width != 56 || tileBounds.Height != 39)
            throw new InvalidOperationException("Declared padded TileBounds changed");
        var rngBefore = Calc.Random;
        int rngCallsBefore = RandomCalls();
        probe.Invoke("Celeste.LevelLoader.tile-prefix(95-274)", () => RoomCoreTileBake.Build(probe.Level, map));
        int rngCallsAfter = RandomCalls();
        if (!ReferenceEquals(Calc.Random, rngBefore)) throw new InvalidOperationException("Tile bake changed global RNG identity");
        var solidTiles = probe.Level.SolidTiles ?? throw new InvalidOperationException("Original SolidTiles ctor did not commit");
        var bgTiles = probe.Level.BgTiles ?? throw new InvalidOperationException("Original BackgroundTiles ctor did not commit");
        if (!IsGlobal(solidTiles) || !IsGlobal(bgTiles)) throw new InvalidOperationException("Global tile entities lost Tags.Global");
        var solidsData = probe.Level.SolidsData ?? throw new InvalidOperationException("Level.SolidsData missing after bake");
        string solidsDataSha = CharMapSha(solidsData);
        string solidsRow = new string(new[] { solidsData[8, 26], solidsData[9, 26], solidsData[10, 26], solidsData[11, 26] });
        if (solidsRow != "4331") throw new InvalidOperationException("Raw solids row changed: " + solidsRow);
        if (!solidTiles.Grid[8, 26] || !solidTiles.Grid[9, 26] || !solidTiles.Grid[10, 26] || !solidTiles.Grid[11, 26])
            throw new InvalidOperationException("Original Grid floor cells do not match raw solids");
        probe.Write(new { @event = "caller-global-bake", bakeCount = 1, mapBounds = Rect(map.Bounds), tileBounds = Rect(tileBounds),
            position = new[] { solidTiles.Position.X, solidTiles.Position.Y }, solidTiles = Identity(solidTiles), bgTiles = Identity(bgTiles),
            solidTagGlobal = IsGlobal(solidTiles), bgTagGlobal = IsGlobal(bgTiles), solidDepth = solidTiles.Depth, bgDepth = bgTiles.Depth,
            solidsDataSha, bgDataSha = CharMapSha(probe.Level.BgData), solidsRow,
            gridCells = new[] { solidTiles.Grid[8, 26], solidTiles.Grid[9, 26], solidTiles.Grid[10, 26], solidTiles.Grid[11, 26] },
            worldFloor = new[] { solidTiles.Position.X + 8 * 8, solidTiles.Position.Y + 8 * 26 },
            rngIdentityBefore = Identity(rngBefore), rngIdentityAfter = Identity(Calc.Random), persistentRngCallsBefore = rngCallsBefore,
            persistentRngCallsAfter = rngCallsAfter, mapLoadSeed = map.LoadSeed,
            fgTileAssignments = TileAssignments(solidTiles.Tiles), bgTileAssignments = TileAssignments(bgTiles.Tiles),
            rngScope = "Original Calc.PushRandom(mapData.LoadSeed)/Calc.PopRandom preserved; scoped texture draws use the temporary source Random and the persistent Calc.Random identity/calls remain restored",
            sourceOrder = "original LevelLoader 95-274 then original SolidTiles ctor" });
        return (solidTiles, bgTiles, solidsDataSha);
    }

    public static void RunGroundQuery(string[] args)
    {
        using var probe = new Probe(args);
        try
        {
            if (args.Length != 3) throw new ArgumentException("Expected a private trace path and tile content root");
            var tiles = PrepareGroundedRoom(probe, args[2]);
            var solidTiles = tiles.Solid;
            var bgTiles = tiles.Background;
            string solidsDataSha = tiles.Sha;
            probe.Invoke("Celeste.Level.LoadLevel(Respawn)", () => probe.Level.LoadLevel(Player.IntroTypes.Respawn));
            var firstPlayer = probe.Level.Tracker.GetEntity<Player>() ?? throw new InvalidOperationException("LoadLevel did not create Player");
            if (firstPlayer.StateMachine.State != 14) throw new InvalidOperationException("Respawn did not enter state14");
            WaitNormal(probe, firstPlayer, "first");
            if (probe.Level.SolidTiles != solidTiles || probe.Level.BgTiles != bgTiles)
                throw new InvalidOperationException("First LoadLevel replaced global tile entities");
            string solidsBefore = CharMapSha(probe.Level.SolidsData);
            string solidBefore = Identity(probe.Level.SolidTiles), bgBefore = Identity(probe.Level.BgTiles);
            probe.Invoke("Celeste.Level.Reload(controlled-retention)", () => probe.Level.Reload());
            var reloadPlayer = probe.Level.Tracker.GetEntity<Player>() ?? throw new InvalidOperationException("Controlled Reload did not create second Player");
            if (reloadPlayer.StateMachine.State != 14) throw new InvalidOperationException("Controlled Reload did not enter state14");
            WaitNormal(probe, reloadPlayer, "reload");
            string solidsAfter = CharMapSha(probe.Level.SolidsData);
            if (probe.Level.SolidTiles != solidTiles || probe.Level.BgTiles != bgTiles)
                throw new InvalidOperationException("Controlled Reload rebaked or replaced global tile entities");
            if (solidsBefore != solidsDataSha || solidsAfter != solidsDataSha)
                throw new InvalidOperationException("Global solids data changed across controlled reload");
            probe.Write(new { @event = "caller-controlled-reload", solidTilesBefore = solidBefore, solidTilesAfter = Identity(probe.Level.SolidTiles),
                bgTilesBefore = bgBefore, bgTilesAfter = Identity(probe.Level.BgTiles), solidsDataBefore = solidsBefore,
                solidsDataAfter = solidsAfter, bakeCount = 1, firstPlayer = Identity(firstPlayer), reloadPlayer = Identity(reloadPlayer),
                sourceLoadLevelCalls = 2, claim = "Caller-invoked original Level.Reload retention only; not death/wipe/hazard/family closure" });
            probe.Write(new { @event = "completed", status = "source-ground-query-and-controlled-reload-retention",
                position = new[] { reloadPlayer.Position.X, reloadPlayer.Position.Y }, state = reloadPlayer.StateMachine.State,
                familiesClosed = 0, nativeAttempts = NativeImportGuard.Attempts.Length,
                platformReads = PlatformIdentityFixture.Reads, nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                claim = "Original global tile bake and natural spawn ground query; controlled reload retention only; no sampled Jump/ConsumeBuffer, no full family or hardware closure" });
        }
        catch (Exception error)
        {
            probe.Write(new { @event = "boundary", member = probe.Member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, platformReads = PlatformIdentityFixture.Reads,
                nativeMappingsAtBoundary = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, status = "blocked-ground-query" });
            throw;
        }
    }

    static void WriteDriverTick(Probe probe, int tick, bool sceneRan, bool freezeBefore, string inputProfile = null)
    {
        if (inputProfile != null)
        {
            probe.Write(new { @event = "driver-tick", tick, sceneRan, inputSampled = true,
                inputSamplingProfile = inputProfile,
                rawFixtureBoundary = "caller-declared typed KeyboardState fixture; Keyboard.GetState not invoked",
                fullMInputUpdateExecuted = false, gamepadSampled = false, buttonsSampled = false,
                freezeBefore, freezeAfter = Engine.FreezeTimer, timeActive = probe.Level.TimeActive,
                rawTimeActive = probe.Level.RawTimeActive, player = Identity(probe.Level.Tracker.GetEntity<Player>()),
                state = probe.Level.Tracker.GetEntity<Player>()?.StateMachine.State, entities = probe.Level.Entities.Count,
                corpse = Identity(probe.Level.Entities.FirstOrDefault(entity => entity is PlayerDeadBody)),
                wipe = WipeState(probe.Level), sessionDeaths = probe.Level.Session.Deaths });
            return;
        }
        WriteLegacyDriverTick(probe, tick, sceneRan, freezeBefore);
    }

    static void WriteLegacyDriverTick(Probe probe, int tick, bool sceneRan, bool freezeBefore)
    {
        probe.Write(new { @event = "driver-tick", tick, sceneRan, inputSampled = false,
            freezeBefore, freezeAfter = Engine.FreezeTimer, timeActive = probe.Level.TimeActive,
            rawTimeActive = probe.Level.RawTimeActive, player = Identity(probe.Level.Tracker.GetEntity<Player>()),
            state = probe.Level.Tracker.GetEntity<Player>()?.StateMachine.State, entities = probe.Level.Entities.Count,
            corpse = Identity(probe.Level.Entities.FirstOrDefault(entity => entity is PlayerDeadBody)),
            wipe = WipeState(probe.Level), sessionDeaths = probe.Level.Session.Deaths });
    }

    static bool Tick(Probe probe, FrameDriver driver, int tick, string inputProfile = null)
    {
        probe.Member = "driver-tick";
        SetEngineTick(1f / 60f);
        bool freezeBefore = Engine.FreezeTimer > 0f;
        driver.scene = probe.Level;
        driver.Tick();
        bool sceneRan = !freezeBefore && !driver.DashAssistFreeze;
        WriteDriverTick(probe, tick, sceneRan, freezeBefore, inputProfile);
        return sceneRan;
    }

    static bool TickCommittingFixture(Probe probe, FrameDriver driver, int tick, out int rngCallsAfterBeforeUpdate)
    {
        probe.Member = "driver-tick";
        SetEngineTick(1f / 60f);
        bool freezeBefore = Engine.FreezeTimer > 0f;
        driver.scene = probe.Level;
        rngCallsAfterBeforeUpdate = RandomCalls();
        if (!driver.DashAssistFreeze)
        {
            if (freezeBefore)
            {
                Engine.FreezeTimer = Math.Max(Engine.FreezeTimer - Engine.RawDeltaTime, 0f);
            }
            else if (driver.scene != null)
            {
                driver.scene.BeforeUpdate();
                rngCallsAfterBeforeUpdate = RandomCalls();
                driver.scene.Update();
                driver.scene.AfterUpdate();
            }
        }
        bool sceneRan = !freezeBefore && !driver.DashAssistFreeze;
        WriteDriverTick(probe, tick, sceneRan, freezeBefore);
        probe.Write(new { @event = "caller-simultaneous-rng-phase", tick,
            rngCallsAfterBeforeUpdate, inputSampled = false,
            note = "read after original Scene.BeforeUpdate/EntityList.UpdateLists and before Scene.Update; same FrameDriver tick, no callback or behavior hook" });
        return sceneRan;
    }
}
