using System;
using System.Linq;
using Celeste;
using Microsoft.Xna.Framework.Input;
using Monocle;

namespace DeathOracle;

static partial class RoomCoreExecution
{
    static object LifecyclePresentation(Level level)
    {
        Entity owner = level.Tracker.GetEntity<Player>();
        owner ??= CommittedCorpses(level).FirstOrDefault();
        if (owner == null) return null;
        var hair = owner.Get<PlayerHair>();
        var sprite = owner.Get<PlayerSprite>();
        var effect = owner.Get<DeathEffect>();
        var tween = owner.Get<Tween>();
        return new { owner = Identity(owner), position = new[] { owner.Position.X, owner.Position.Y },
            animation = sprite?.CurrentAnimationID, frame = sprite?.CurrentAnimationFrame,
            hairOwner = Identity(hair?.Entity), spriteOwner = Identity(sprite?.Entity),
            hairNodes = hair?.Nodes.Select(node => new[] { node.X, node.Y }).ToArray(),
            hairColor = hair == null ? null : new[] { hair.Color.R, hair.Color.G, hair.Color.B, hair.Color.A },
            effectPercent = effect?.Percent, tweenPercent = tween?.Percent };
    }

    sealed class LifecycleDriver
    {
        readonly Probe probe;
        readonly FrameDriver driver;
        readonly ContractProbe contract;
        KeyboardState previous;
        public int Tick;

        public LifecycleDriver(Probe probe, ContractProbe contract = null)
        {
            this.probe = probe;
            driver = new FrameDriver { scene = probe.Level };
            this.contract = contract;
        }

        public void Step(params Keys[] keys)
        {
            probe.Member = "natural-input-frame";
            SetEngineTick(1f / 60f);
            var player = probe.Level.Tracker.GetEntity<Player>();
            bool ground = player != null && player.OnGround();
            float grace = player == null ? 0f : PrivateField<float>(player, "jumpGraceTimer");
            int jumps = SaveData.Instance.TotalJumps;
            MInput.Keyboard.PreviousState = previous;
            var current = new KeyboardState(keys);
            MInput.Keyboard.CurrentState = current;
            Input.MoveX.Update();
            Input.Jump.Update();
            float buffer = VirtualButtonField<float>(Input.Jump, "bufferCounter");
            bool pressed = Input.Jump.Pressed;
            bool released = Input.Jump.Released;
            bool freezeBefore = Engine.FreezeTimer > 0f;
            float timeBefore = probe.Level.TimeActive;
            int rngBefore = RandomCalls();
            var presentationBefore = LifecyclePresentation(probe.Level);
            contract?.BeforeFrame(Tick, freezeBefore);
            driver.Tick();
            contract?.AfterFrame(Tick, freezeBefore);
            if (SaveData.Instance.TotalJumps != jumps)
                probe.Write(new { @event = "natural-jump", tick = Tick, player = Identity(player),
                    groundBefore = ground, graceBefore = grace, bufferBeforeScene = buffer,
                    bufferAfterScene = VirtualButtonField<float>(Input.Jump, "bufferCounter"),
                    position = new[] { player.Position.X, player.Position.Y }, speed = new[] { player.Speed.X, player.Speed.Y },
                    totalJumps = SaveData.Instance.TotalJumps });
            probe.Write(new { @event = "natural-frame", tick = Tick, frameCounter = Engine.FrameCounter,
                keys = keys.Select(key => key.ToString()).ToArray(), moveX = Input.MoveX.Value,
                jumpCheck = Input.Jump.Check, jumpPressedBeforeScene = pressed, jumpReleased = released,
                bufferBeforeScene = buffer, bufferAfterScene = VirtualButtonField<float>(Input.Jump, "bufferCounter"),
                freezeBefore, freezeAfter = Engine.FreezeTimer, sceneRan = !freezeBefore,
                timeBefore, timeActive = probe.Level.TimeActive, rawTimeActive = probe.Level.RawTimeActive,
                player = Identity(player), state = player?.StateMachine.State, dead = player?.Dead,
                position = player == null ? null : new[] { player.Position.X, player.Position.Y },
                speed = player == null ? null : new[] { player.Speed.X, player.Speed.Y },
                rngBefore, rngCalls = RandomCalls(), pendingCorpses = PendingCorpses(probe.Level).Length,
                committedCorpses = CommittedCorpses(probe.Level).Length, wipe = WipeState(probe.Level),
                presentationBefore, presentationAfter = LifecyclePresentation(probe.Level) });
            previous = current;
            Tick++;
        }

        public Player WaitNormal(bool held = false, bool bufferAtEnd = false)
        {
            bool buffering = false;
            for (int guard = 0; guard < 360; guard++)
            {
                var player = probe.Level.Tracker.GetEntity<Player>();
                if (player != null && player.StateMachine.State == 0)
                {
                    RequireGround(probe, player, "natural", Tick);
                    return player;
                }
                var tween = player?.Get<Tween>();
                buffering |= bufferAtEnd && tween != null && tween.TimeLeft <= Engine.DeltaTime;
                int stateBefore = player?.StateMachine.State ?? -1;
                Step(held || buffering ? new[] { Keys.C } : Array.Empty<Keys>());
                if (buffering && stateBefore == 14 && player.StateMachine.State == 0)
                    probe.Write(new { @event = "natural-buffer-before-normal", tick = Tick - 1,
                        stateBefore, stateAfter = player.StateMachine.State,
                        buffer = VirtualButtonField<float>(Input.Jump, "bufferCounter") });
            }
            throw new InvalidOperationException("Natural lifecycle Respawn14 did not reach grounded Normal0");
        }
    }

    public static void RunNaturalLifecycle(string[] args)
    {
        bool integrated = args.Length > 0 && args[0] == "room-core-source-contract";
        if (args.Length != 4 || (args[1] != "repeat" && args[1] != "checkpoint-repeat" && args[1] != "render-boundary" && !(integrated && args[1] == "gpu-negative")))
            throw new ArgumentException("Expected repeat|checkpoint-repeat|render-boundary or integrated gpu-negative, private trace path and tile content root");
        using var probe = new Probe(args, 2);
        using var contract = integrated ? new ContractProbe(probe) : null;
        try
        {
            var tiles = PrepareGroundedRoom(probe, args[3]);
            Settings.Instance.Rumble = RumbleAmount.Off;
            Settings.Instance.Right.Add(Keys.Right);
            Settings.Instance.Left.Add(Keys.Left);
            Settings.Instance.Jump.Add(Keys.C);
            Input.Initialize();
            Input.Jump.Binding.Controller.Clear();
            bool checkpoint = args[1] == "checkpoint-repeat";
            if (checkpoint) probe.Level.Session.HitCheckpoint = true;
            probe.Write(new { @event = "natural-profile", mode = args[1],
                profile = "single-room-presentation-stripped-source-default-save",
                checkpointFlagFixture = checkpoint, checkpointAcquisitionExecuted = false,
                keyboard = new[] { "Right", "Left", "C" }, controllerButtons = Input.Jump.Binding.Controller.Count,
                defaultKeyboardControlsExecuted = false, fullMInputUpdateExecuted = false, hardwareInput = false,
                originalStartupRngParity = false, renderingExecuted = integrated,
                sourceOrder = "Engine clock fixture -> typed previous/current KeyboardState -> original MoveX.Update -> original Jump.Update -> original FrameDriver freeze/Scene order",
                inheritedSeededEvidence = "4309dadc36d66a5473de49611ae7458c93ef47164f5261422e75e1659c559fe6",
                claim = "Source preparation only; no native implementation, full Engine/MInput/GFX startup, full game or completed family claim" });
            probe.Invoke("caller-original-dust-startup-prefix(22-47)", RoomCoreParticleInput.Configure);
            probe.Invoke("Celeste.Level.LoadLevel(Respawn)", () => probe.Level.LoadLevel(Player.IntroTypes.Respawn));
            contract?.Loaded();
            var rng = Calc.Random;
            var jumpInput = Input.Jump;
            var moveInput = Input.MoveX;
            var grid = tiles.Solid.Grid;
            var solidsData = probe.Level.SolidsData;
            var driver = new LifecycleDriver(probe, contract);
            for (int cycle = 0; cycle < 2; cycle++)
            {
                var player = driver.WaitNormal(held: cycle == 1);
                if (cycle == 1)
                {
                    probe.Write(new { @event = "natural-held-after-reload", check = Input.Jump.Check,
                        pressed = Input.Jump.Pressed, buffer = VirtualButtonField<float>(Input.Jump, "bufferCounter"),
                        grounded = player.OnGround() });
                    driver.Step();
                }
                int jumps = SaveData.Instance.TotalJumps;
                driver.Step(Keys.Right, Keys.C);
                if (SaveData.Instance.TotalJumps != jumps + 1 || player.Speed.Y >= 0f)
                    throw new InvalidOperationException("Original NormalUpdate did not execute a grounded Jump");
                for (int guard = 0; !player.Dead && guard < 180; guard++)
                    driver.Step(player.Position.X < 59f ? new[] { Keys.Right } : Array.Empty<Keys>());
                if (!player.Dead) throw new InvalidOperationException("Natural input never reached a raw room spike");
                var corpse = PendingCorpse(probe.Level) ?? throw new InvalidOperationException("Natural hazard did not queue a corpse");
                long sessionTimeAtDeath = probe.Level.Session.Time;
                probe.Write(new { @event = "natural-death", cycle, tick = driver.Tick - 1,
                    position = new[] { player.Position.X, player.Position.Y }, deathDirection = Bounce(corpse),
                    pendingCorpses = PendingCorpses(probe.Level).Length, committedCorpses = CommittedCorpses(probe.Level).Length,
                    sessionDeaths = probe.Level.Session.Deaths, roomDeaths = probe.Level.Session.DeathsInCurrentLevel,
                    saveDeaths = SaveData.Instance.TotalDeaths, spriteTransferred = corpse.Get<PlayerSprite>() == player.Sprite,
                    hairTransferred = corpse.Get<PlayerHair>() == player.Hair,
                    lightTransferred = corpse.Get<VertexLight>() == player.Light });
                Player next = null;
                bool releasedOnCrossing = false;
                bool effectObserved = false;
                bool wipeObserved = false;
                for (int guard = 0; guard < 480; guard++)
                {
                    releasedOnCrossing |= cycle == 1 && Engine.FreezeTimer > 0f && Engine.FreezeTimer <= Engine.RawDeltaTime;
                    driver.Step(!releasedOnCrossing ? new[] { Keys.C } : Array.Empty<Keys>());
                    var effect = corpse.Get<DeathEffect>();
                    if (!effectObserved && effect != null)
                    {
                        effectObserved = true;
                        probe.Write(new { @event = "natural-death-effect", cycle, tick = driver.Tick - 1,
                            duration = effect.Duration, percent = effect.Percent });
                    }
                    if (!wipeObserved && probe.Level.Wipe != null && !probe.Level.Wipe.WipeIn)
                    {
                        wipeObserved = true;
                        probe.Write(new { @event = "natural-death-wipe", cycle, tick = driver.Tick - 1,
                            wipe = WipeState(probe.Level), corpseInScene = corpse.Scene == probe.Level });
                    }
                    next = probe.Level.Tracker.GetEntity<Player>();
                    if (next != null && next != player) break;
                }
                if (next == null || next == player || next.StateMachine.State != 14)
                    throw new InvalidOperationException("Original death wipe did not automatically Reload into Respawn14");
                bool retained = probe.Level.SolidTiles == tiles.Solid && probe.Level.BgTiles == tiles.Background
                    && CharMapSha(probe.Level.SolidsData) == tiles.Sha;
                if (!retained || !ReferenceEquals(rng, Calc.Random))
                    throw new InvalidOperationException("Natural Reload replaced global tiles or RNG");
                probe.Write(new { @event = "natural-reload", cycle, tick = driver.Tick - 1,
                    state = next.StateMachine.State, previousPlayer = Identity(player), player = Identity(next),
                    corpseRemoved = corpse.Scene == null && !probe.Level.Entities.Contains(corpse),
                    tilesRetained = retained, rngRetained = ReferenceEquals(rng, Calc.Random),
                    sessionDeaths = probe.Level.Session.Deaths, roomDeaths = probe.Level.Session.DeathsInCurrentLevel,
                    saveDeaths = SaveData.Instance.TotalDeaths, rngCalls = RandomCalls(),
                    hairReconstructed = next.Hair != player.Hair, spriteReconstructed = next.Sprite != player.Sprite,
                    inputRetained = Input.Jump == jumpInput && Input.MoveX == moveInput,
                    gridRetained = probe.Level.SolidTiles.Grid == grid, rawHazards = RawSpikes(probe.Level, null).Count,
                    solidsDataRetained = probe.Level.SolidsData == solidsData,
                    hitCheckpoint = probe.Level.Session.HitCheckpoint, sessionTimeAtDeath,
                    sessionTimeAfter = probe.Level.Session.Time });
            }
            var resumed = driver.WaitNormal(bufferAtEnd: true);
            driver.Step(Keys.Right, Keys.C);
            if (resumed.Dead || resumed.Speed.Y >= 0f || SaveData.Instance.TotalJumps != 3)
                throw new InvalidOperationException("Second Reload did not permit the first actual grounded Jump");
            if (args[1] == "render-boundary")
                probe.Invoke("original-Player.Render-after-natural-repeat", resumed.Render);
            if (args[1] == "gpu-negative")
                probe.Invoke("excluded-Distort.Render-after-integrated-repeat", () => Distort.Render(null, null, false));
            probe.Write(new { @event = "completed", status = integrated ? "integrated-original-source-lifecycle-contract" : "natural-input-jump-hazard-reload-repeat",
                cycles = 2, reloads = 2, bakeCount = 1, completedLifecycleFamilies = 0,
                inputSamplingProfile = "declared-raw-keyboard-source-axis-and-button",
                fullMInputUpdateExecuted = false, hardwareInput = false, renderingExecuted = integrated,
                unsupportedHits = 0, renderBoundary = integrated ? "recording-only; Distort.Render remains excluded" : "Monocle.Draw.SpriteBatch",
                nativeAttempts = NativeImportGuard.Attempts.Length, nativeMappingsAfter = NativeImportGuardProbe.NativeMappings() });
        }
        catch (Exception error)
        {
            probe.Write(new { @event = "boundary", member = probe.Member, exception = error.ToString(),
                nativeAttempts = NativeImportGuard.Attempts, nativeMappingsAfter = NativeImportGuardProbe.NativeMappings(),
                completedLifecycleFamilies = 0, status = "blocked-natural-lifecycle" });
            throw;
        }
    }
}
