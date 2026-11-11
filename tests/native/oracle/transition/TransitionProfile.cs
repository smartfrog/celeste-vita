using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Celeste;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Input;
using Monocle;

namespace DeathOracle;

static class TransitionProfile
{
    public static string DataRoot;
}

static partial class RoomCoreExecution
{
    static void PrepareTransitionRoom(Probe probe, string content)
    {
        ReadTileContentPins(content);
        probe.Bootstrap();
        SaveData.Instance.StartSession(probe.Level.Session);
        typeof(Engine).GetProperty("Pooler").GetSetMethod(true).Invoke(null, new object[] { new Pooler() });
        PrepareEngineDriver(probe.Level);
        PrepareContentRoot(content);
        LoadGuiAtlas(probe.Content);
        PrepareLevelLoaderFields(probe.Level);
        GFX.BGAutotiler = new Autotiler("Graphics/BackgroundTiles.xml");
        GFX.FGAutotiler = new Autotiler("Graphics/ForegroundTiles.xml");
        RoomCoreTileBake.Build(probe.Level, probe.Level.Session.MapData);
        Settings.Instance.Rumble = RumbleAmount.Off;
        Settings.Instance.Right.Add(Keys.Right);
        Settings.Instance.Left.Add(Keys.Left);
        Settings.Instance.Up.Add(Keys.Up);
        Settings.Instance.Down.Add(Keys.Down);
        Settings.Instance.Jump.Add(Keys.C);
        Settings.Instance.Dash.Add(Keys.X);
        Settings.Instance.Grab.Add(Keys.Z);
        Input.Initialize();
        Input.Jump.Binding.Controller.Clear();
        Input.Dash.Binding.Controller.Clear();
        Input.CrouchDash.Binding.Controller.Clear();
        RoomCoreParticleInput.Configure();
        probe.Level.LoadLevel(Player.IntroTypes.Respawn);
    }

    static void Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "native-abi-metadata-audit") { NativeAbiMetadataAudit.Run(args); return; }
        if (args.Length > 0 && args[0].StartsWith("native-abi-", StringComparison.Ordinal)) { NativeImportGuardProbe.Run(args); return; }
        if (args.Length == 1 && args[0] == "unsupported-closure-negative")
        {
            if (!NativeImportGuard.Installed || NativeImportGuard.Attempts.Length != 0) throw new InvalidOperationException("Fresh native guard required");
            var method = typeof(Spring).GetMethod("OnCollide", BindingFlags.Instance | BindingFlags.NonPublic);
            try
            {
                method.Invoke(RuntimeHelpers.GetUninitializedObject(typeof(Spring)), new object[] { null });
                throw new InvalidOperationException("Unsupported Spring collision bypassed the source closure guard");
            }
            catch (TargetInvocationException error) when (error.InnerException is UnsupportedClosure)
            {
                Console.WriteLine(JsonSerializer.Serialize(new { status = "expected-unsupported-closure-not-route-coverage", member = error.InnerException.Message,
                    nativeAttempts = NativeImportGuard.Attempts.Length, nativeMappings = NativeImportGuardProbe.NativeMappings() }));
                return;
            }
        }
        if (args.Length != 4) throw new ArgumentException("Expected trace, existing tile content, data directory, input stream");
        TransitionProfile.DataRoot = Path.GetFullPath(args[2]);
        using var input = JsonDocument.Parse(File.ReadAllText(args[3]));
        var root = input.RootElement;
        if (root.EnumerateObject().Select(value => value.Name).OrderBy(value => value).SequenceEqual(new[] { "runs", "schema", "seed" }) == false
            || root.GetProperty("schema").GetInt32() != 1)
            throw new InvalidDataException("Only seed and legal input runs are accepted");
        Calc.Random = new PresentationOracle.TracedRandom(root.GetProperty("seed").GetInt32());
        using var probe = new Probe(args, 0);
        string phase = "bootstrap";
        int tick = -1;
        PresentationOracle.TracedRandom.Observer = (random, operation) => probe.Write(new {
            @event = "rng", tick, phase, operation, random = Identity(random), random.Calls });
        try
        {
            PrepareTransitionRoom(probe, Path.GetFullPath(args[1]));
            var level = probe.Level;
            var first = level.Tracker.GetEntity<Player>();
            probe.Write(new { @event = "transition-profile", status = "open-loop-source-experiment-not-acceptance", seed = root.GetProperty("seed").GetInt32(),
                timeStep = "float32 1/60", mapRooms = level.Session.MapData.Levels.Select(room => new { room.Name, room.LoadSeed, bounds = Rect(room.Bounds),
                    spawns = room.Spawns.Select(position => new[] { position.X, position.Y }), entities = room.Entities.Select(entity => entity.Name) }),
                player = Identity(first), sprite = Identity(first.Sprite), hair = Identity(first.Hair),
                sourceOrder = "declared clock and raw keyboard -> original virtual inputs -> original FrameDriver freeze/Scene order",
                hardware = false, graphics = "not rendered", completedTransitions = 0 });
            var driver = new TransitionFrameDriver { scene = level };
            object State() => new {
                room = level.Session.Level, bounds = Rect(level.Bounds), previousBounds = level.PreviousBounds.HasValue ? Rect(level.PreviousBounds.Value) : null,
                level = Identity(level), player = Identity(first), sprite = Identity(first.Sprite), hair = Identity(first.Hair),
                sameTrackedPlayer = ReferenceEquals(first, level.Tracker.GetEntity<Player>()),
                sameSpriteOwner = ReferenceEquals(first.Sprite.Entity, first), sameHairOwner = ReferenceEquals(first.Hair.Entity, first),
                position = new[] { first.Position.X, first.Position.Y }, speed = new[] { first.Speed.X, first.Speed.Y },
                center = new[] { first.CenterX, first.CenterY }, upProbe = new[] { first.CenterX, first.CenterY - 12f },
                remainder = new[] { first.PositionRemainder.X, first.PositionRemainder.Y },
                state = first.StateMachine.State, previousState = first.StateMachine.PreviousState, first.StateMachine.Locked,
                first.Dead, first.Dashes, first.Stamina, first.AutoJump, first.AutoJumpTimer,
                varJumpTimer = PrivateField<float>(first, "varJumpTimer"), jumpGraceTimer = PrivateField<float>(first, "jumpGraceTimer"),
                wallSlideTimer = PrivateField<float>(first, "wallSlideTimer"), forceMoveXTimer = PrivateField<float>(first, "forceMoveXTimer"),
                chaserCount = first.ChaserStates.Count, onGround = CachedOnGround(first), groundQuery = first.OnGround(),
                camera = new[] { level.Camera.X, level.Camera.Y }, level.Transitioning, level.NextTransitionDuration,
                transition = TransitionObserver.Coroutine(level), endOfFrame = TransitionObserver.EndOfFrame(level),
                entities = TransitionObserver.Entities(level), pending = PendingEntities(level).Select(Identity),
                colliderOrder = level.Tracker.GetComponents<PlayerCollider>().Select(component => Identity(component.Entity)),
                animation = first.Sprite.CurrentAnimationID, animationFrame = first.Sprite.CurrentAnimationFrame,
                spriteScale = new[] { first.Sprite.Scale.X, first.Sprite.Scale.Y }, hairNodes = first.Hair.Nodes.Select(node => new[] { node.X, node.Y }),
                respawn = level.Session.RespawnPoint.HasValue ? new[] { level.Session.RespawnPoint.Value.X, level.Session.RespawnPoint.Value.Y } : null,
                level.TimeActive, level.RawTimeActive, Engine.FrameCounter, Engine.FreezeTimer, Engine.TimeRate, Engine.TimeRateB,
                sessionTime = level.Session.Time, saveTime = SaveData.Instance.Time,
                roomDeaths = level.Session.DeathsInCurrentLevel, sessionDeaths = level.Session.Deaths, saveDeaths = SaveData.Instance.TotalDeaths,
                sessionDashes = level.Session.Dashes, saveDashes = SaveData.Instance.TotalDashes, saveJumps = SaveData.Instance.TotalJumps,
                rng = TransitionObserver.RandomState(), nativeAttempts = NativeImportGuard.Attempts.Length };
            driver.Observe = point => { phase = point; probe.Write(new { @event = "phase", tick, phase, state = State() }); };
            KeyboardState previous = default;
            tick = 0;
            foreach (var run in root.GetProperty("runs").EnumerateArray())
            {
                if (!run.EnumerateObject().Select(value => value.Name).OrderBy(value => value).SequenceEqual(new[] { "frames", "keys" }))
                    throw new InvalidDataException("Input runs permit frames/keys only");
                int frames = run.GetProperty("frames").GetInt32();
                if (frames <= 0 || tick + frames > 3600) throw new InvalidDataException("Input stream exceeds bounded 3600-frame experiment");
                var keys = run.GetProperty("keys").EnumerateArray().Select(value => Enum.Parse<Keys>(value.GetString())).ToArray();
                if (keys.Any(key => key is not (Keys.Left or Keys.Right or Keys.Up or Keys.Down or Keys.C or Keys.X or Keys.Z)))
                    throw new InvalidDataException("Only Dpad/Jump/Dash/Climb are legal");
                for (int frame = 0; frame < frames; frame++, tick++)
                {
                    probe.Member = "input-only-frame-" + tick;
                    phase = "input";
                    SetEngineTick(1f / 60f);
                    MInput.Keyboard.PreviousState = previous;
                    MInput.Keyboard.CurrentState = new KeyboardState(keys);
                    Input.MoveX.Update(); Input.MoveY.Update(); Input.Aim.Update();
                    Input.Jump.Update(); Input.Dash.Update(); Input.CrouchDash.Update();
                    probe.Write(new { @event = "input", tick, keys = keys.Select(key => key.ToString()),
                        moveX = Input.MoveX.Value, moveY = Input.MoveY.Value, aim = new[] { Input.Aim.Value.X, Input.Aim.Value.Y },
                        jumpCheck = Input.Jump.Check, jumpPressed = Input.Jump.Pressed, jumpReleased = Input.Jump.Released,
                        jumpBuffer = VirtualButtonField<float>(Input.Jump, "bufferCounter"), dashCheck = Input.Dash.Check,
                        dashPressed = Input.Dash.Pressed, dashBuffer = VirtualButtonField<float>(Input.Dash, "bufferCounter"), climb = Input.GrabCheck });
                    bool frozen = Engine.FreezeTimer > 0f;
                    phase = "before-frame";
                    probe.Write(new { @event = "phase", tick, phase, state = State() });
                    driver.Tick();
                    phase = "after-frame";
                    probe.Write(new { @event = "phase", tick, phase, state = State() });
                    var player = level.Tracker.GetEntity<Player>();
                    probe.Write(new { @event = "frame", tick, keys = keys.Select(key => key.ToString()), frozen,
                        room = level.Session.Level, bounds = Rect(level.Bounds), level = Identity(level), player = Identity(player),
                        playerRetained = ReferenceEquals(first, player), spriteRetained = ReferenceEquals(first.Sprite, player?.Sprite), hairRetained = ReferenceEquals(first.Hair, player?.Hair),
                        state = player?.StateMachine.State, position = player == null ? null : new[] { player.Position.X, player.Position.Y },
                        speed = player == null ? null : new[] { player.Speed.X, player.Speed.Y },
                        remainder = player == null ? null : new[] { player.PositionRemainder.X, player.PositionRemainder.Y },
                        camera = new[] { level.Camera.X, level.Camera.Y }, level.Transitioning, level.TimeActive, level.RawTimeActive,
                        sessionTime = level.Session.Time, roomDeaths = level.Session.DeathsInCurrentLevel, sessionDeaths = level.Session.Deaths,
                        saveDeaths = SaveData.Instance.TotalDeaths, rngCalls = RandomCalls(), entities = EntityTypes(level),
                        nativeAttempts = NativeImportGuard.Attempts.Length });
                    previous = MInput.Keyboard.CurrentState;
                    if (player == null || player.Dead) throw new InvalidOperationException("Input route died; no transition closure");
                }
            }
            probe.Write(new { @event = "experiment-ended", status = "not-transition-acceptance", ticks = tick,
                nativeAttempts = NativeImportGuard.Attempts.Length, nativeMappings = NativeImportGuardProbe.NativeMappings() });
        }
        catch (Exception error)
        {
            probe.Write(new { @event = "boundary", status = "blocked-not-transition-acceptance", member = probe.Member,
                error = error.ToString(), nativeAttempts = NativeImportGuard.Attempts });
            throw;
        }
        finally
        {
            PresentationOracle.TracedRandom.Observer = null;
        }
    }
}
