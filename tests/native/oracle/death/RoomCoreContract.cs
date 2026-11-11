using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Celeste;
using Microsoft.Xna.Framework;
using Monocle;
using PresentationOracle;

namespace DeathOracle;

static partial class RoomCoreExecution
{
    sealed class ContractProbe : IDisposable
    {
        readonly Probe probe;
        readonly HashSet<Player> players = new();
        readonly HashSet<ScreenWipe> wipes = new();
        PlayerDeadBody pending;
        int pendingCount;
        Player lastPlayer;
        int tick = -1;
        bool frozen;

        public ContractProbe(Probe probe)
        {
            this.probe = probe;
            if (TracedRandom.Observer != null) throw new InvalidOperationException("RNG observer already installed");
            TracedRandom.Observer = ObserveRandom;
        }

        public void Dispose() => TracedRandom.Observer = null;

        static float[] XY(Vector2 value) => new[] { value.X, value.Y };
        static int[] RGBA(Color value) => new[] { (int)value.R, value.G, value.B, value.A };

        static T ReadField<T>(object value, string name)
        {
            for (var type = value.GetType(); type != null; type = type.BaseType)
            {
                var field = type.GetField(name, BindingFlags.Instance | BindingFlags.NonPublic | BindingFlags.DeclaredOnly);
                if (field != null) return (T)field.GetValue(value);
            }
            throw new InvalidOperationException("Missing observed field: " + value.GetType().FullName + "." + name);
        }

        void ObserveRandom(TracedRandom random, string operation)
        {
            if (probe.Level == null) return;
            var stack = new StackTrace().GetFrames().Select(frame => frame.GetMethod()).ToArray();
            bool levelUpdate = stack.Any(method => method.DeclaringType == typeof(Level) && method.Name == "Update");
            var hairs = probe.Level.Tracker.GetComponents<PlayerHair>().Cast<PlayerHair>().ToArray();
            bool headMatches = hairs.Length > 0 && hairs.All(hair => hair.Nodes[0] == hair.Sprite.RenderPosition
                + new Vector2(0f, -9f * hair.Sprite.Scale.Y) + hair.Sprite.HairOffset * new Vector2((float)hair.Facing, 1f));
            probe.Write(new { @event = "contract-rng", tick, operation, calls = random.Calls,
                rng = Identity(random), levelUpdate, duringRender = LifecycleRecording.Active,
                freezeBeforeUpdate = frozen, hairHeadMatchesPostUpdate = headMatches,
                postUpdateHooks = probe.Level.Tracker.GetComponents<PostUpdateHook>().Count,
                stack = stack.Where(method => method.DeclaringType?.Namespace is "Celeste" or "Monocle")
                    .Select(method => method.DeclaringType.FullName + "." + method.Name).ToArray(),
                hair = hairs.Select(hair => new { owner = Identity(hair.Entity), hair.Active,
                    entityActive = hair.Entity.Active, head = XY(hair.Nodes[0]),
                    spriteRenderPosition = XY(hair.Sprite.RenderPosition) }).ToArray() });
        }

        public void Loaded()
        {
            var graphics = (GraphicsDeviceManager)RuntimeHelpers.GetUninitializedObject(typeof(GraphicsDeviceManager));
            typeof(GraphicsDeviceManager).GetField("graphicsDevice", BindingFlags.Instance | BindingFlags.NonPublic)
                .SetValue(graphics, new Microsoft.Xna.Framework.Graphics.GraphicsDevice());
            typeof(Engine).GetProperty("Graphics").GetSetMethod(true).Invoke(null, new object[] { graphics });
            probe.Write(new { @event = "contract-profile",
                instrumentation = "Read-only endpoints/RNG recording leaf; transparent wrappers forward each observed existing Tween.OnComplete and wipe.OnComplete invocation exactly once, never suppressing it. Original source bodies unchanged.",
                rendering = "Visible Player/PlayerDeadBody projection of the actual depth-sorted EntityList, then current Level.Wipe; same live instances each frame including Engine freeze crossing. Other world renderers/GPU passes excluded.",
                viewport = "Declared field-only GraphicsDeviceManager with existing recording GraphicsDevice at 1920x1080; original Engine.Graphics and GraphicsDeviceManager.GraphicsDevice reads, no manager/device/library initialization.",
                renderMutations = "Original PlayerHair.Render floors Nodes[0]; PlayerDeadBody.Render sets sprite scale/facing. These are source render side effects, not updates or caller poses.",
                sourcePhaseProof = "source-manifest.json: bounded_phase_sources; callback labels below are observed delegate invocations, other phase order is pinned source plus runtime pre/post witnesses, not a general profiler." });
            ObservePlayer();
            ObserveWipe();
            Render(false);
        }

        void ObservePlayer()
        {
            var player = probe.Level.Tracker.GetEntity<Player>();
            if (player == null || !players.Add(player)) return;
            lastPlayer = player;
            var tween = player.Get<Tween>() ?? throw new InvalidOperationException("Missing original respawn tween");
            var callback = tween.OnComplete ?? throw new InvalidOperationException("Missing original respawn completion");
            var begin = ReadField<Action[]>(player.StateMachine, "begins")[0];
            probe.Write(new { @event = "contract-player-added", tick, player = Identity(player),
                state = player.StateMachine.State, previousState = player.StateMachine.PreviousState,
                startHairCalled = ReadField<bool>(player, "startHairCalled"),
                componentsOwned = player.Components.All(component => component.Entity == player),
                pendingAwake = ReadField<List<Entity>>(probe.Level.Entities, "toAwake").Count,
                awakeImplementation = player.GetType().GetMethod("Awake").DeclaringType.FullName,
                components = player.Components.Select(component => new { type = component.GetType().FullName,
                    entityAdded = component.GetType().GetMethod("EntityAdded").DeclaringType.FullName,
                    entityAwake = component.GetType().GetMethod("EntityAwake").DeclaringType.FullName }).ToArray(),
                hair = player.Hair.Nodes.Select(XY).ToArray(), normalBegin = begin.Method.Name,
                completion = callback.Method.Name, completionTarget = Identity(callback.Target) });
            int invocations = 0;
            tween.OnComplete = value => {
                int stateBefore = player.StateMachine.State;
                callback(value);
                probe.Write(new { @event = "contract-callback", callback = "respawn-tween", tick,
                    player = Identity(player), tween = Identity(value), invocations = ++invocations,
                    stateBefore, stateAfter = player.StateMachine.State, scaleAfter = XY(player.Sprite.Scale),
                    normalBegin = begin.Method.Name, sourceCallback = callback.Method.Name,
                    maxFall = PrivateField<float>(player, "maxFall"),
                    timeLeft = value.TimeLeft, percent = value.Percent });
            };
        }

        void ObserveWipe()
        {
            var wipe = probe.Level.Wipe;
            if (wipe == null || !wipes.Add(wipe)) return;
            probe.Write(new { @event = "contract-wipe-created", tick, wipe = Identity(wipe), wipe.WipeIn,
                corpseFinished = CommittedCorpses(probe.Level).Select(corpse => ReadField<bool>(corpse, "finished")).ToArray(),
                sourceCallback = wipe.OnComplete?.Method.Name, target = Identity(wipe.OnComplete?.Target) });
            if (wipe.WipeIn) return;
            var callback = wipe.OnComplete ?? throw new InvalidOperationException("Death wipe has no completion");
            if (callback.Target != probe.Level || callback.Method.Name != "Reload")
                throw new InvalidOperationException("Death wipe callback is not the original Level.Reload");
            int invocations = 0;
            wipe.OnComplete = () => {
                string playerBefore = Identity(lastPlayer);
                callback();
                probe.Write(new { @event = "contract-callback", callback = "wipe-reload", tick,
                    wipe = Identity(wipe), invocations = ++invocations, playerBefore,
                    playerAfter = Identity(probe.Level.Tracker.GetEntity<Player>()),
                    wipe.Completed, ending = ReadField<bool>(wipe, "ending"),
                    sourceCallback = callback.Method.Name });
            };
        }

        public void BeforeFrame(int tick, bool frozen)
        {
            this.tick = tick;
            this.frozen = frozen;
            pending = PendingCorpse(probe.Level);
            pendingCount = PendingCorpses(probe.Level).Length;
        }

        public void AfterFrame(int tick, bool freezeBefore)
        {
            if (pending != null && probe.Level.Entities.Contains(pending))
                probe.Write(new { @event = "contract-corpse-commit", tick, corpse = Identity(pending),
                    pendingBefore = pendingCount, committedAfter = CommittedCorpses(probe.Level).Length,
                    sceneOwned = pending.Scene == probe.Level, spriteOwner = Identity(pending.Get<PlayerSprite>()?.Entity),
                    hairOwner = Identity(pending.Get<PlayerHair>()?.Entity),
                    animation = pending.Get<PlayerSprite>()?.CurrentAnimationID,
                    pendingAwake = ReadField<List<Entity>>(probe.Level.Entities, "toAwake").Count });
            var queued = PendingCorpse(probe.Level);
            if (queued != null && queued != pending)
                probe.Write(new { @event = "contract-deferred-corpse", tick, corpse = Identity(queued),
                    pendingCorpses = PendingCorpses(probe.Level).Length,
                    committedCorpses = CommittedCorpses(probe.Level).Length,
                    corpseScene = Identity(queued.Scene), playerStillListed = probe.Level.Entities.Contains(lastPlayer),
                    hairOwner = Identity(lastPlayer.Hair.Entity), spriteOwner = Identity(lastPlayer.Sprite.Entity),
                    lightOwner = Identity(lastPlayer.Light.Entity), lastPlayer.Dead });
            ObservePlayer();
            ObserveWipe();
            Render(freezeBefore);
        }

        object UpdateState() => new {
            probe.Level.TimeActive, probe.Level.RawTimeActive, Engine.FrameCounter, Engine.FreezeTimer,
            buffer = VirtualButtonField<float>(Input.Jump, "bufferCounter"), moveX = Input.MoveX.Value,
            jump = Input.Jump.Check, input = Identity(Input.Jump), rng = Identity(Calc.Random),
            menuConfirmPressed = Input.MenuConfirm.Pressed,
            entities = probe.Level.Entities.Where(entity => entity is Player or PlayerDeadBody).Select(entity => new {
                owner = Identity(entity), position = XY(entity.Position),
                state = (entity as Player)?.StateMachine.State,
                wave = entity.Get<PlayerHair>() is PlayerHair hair ? ReadField<float>(hair, "wave") : (float?)null,
                animationTimer = entity.Get<PlayerSprite>() is PlayerSprite sprite ? ReadField<float>(sprite, "animationTimer") : (float?)null,
                effectPercent = entity.Get<DeathEffect>()?.Percent,
                tweenTime = entity.Get<Tween>()?.TimeLeft }).ToArray(),
            wipePercent = probe.Level.Wipe?.Percent };

        static object Vertex(PresentationOracle.SourceVector3 position, Vector2 uv, Color color) => new {
            position = new[] { position.X, position.Y, position.Z }, uv = XY(uv), color = RGBA(color) };

        void Render(bool freezeBefore)
        {
            probe.Member = "original-live-lifecycle-render";
            var owners = probe.Level.Entities.Where(entity => entity.Visible && !entity.TagCheck(Tags.HUD)
                && (entity is Player or PlayerDeadBody)).ToArray();
            if (owners.Length != 1) throw new InvalidOperationException("Lifecycle rendering requires one committed visible owner");
            var owner = owners[0];
            string phase = owner is Player player ? (player.StateMachine.State == 14 ? "respawn14" : "live")
                : owner.Get<DeathEffect>() == null ? "corpse" : "death-effect";
            object updateBefore = UpdateState();
            int rngBefore = RandomCalls();
            var ranges = new List<object>();
            LifecycleRecording.Begin();
            try
            {
                foreach (var entity in owners)
                {
                    int start = LifecycleRecording.Batch.Calls.Count;
                    entity.Render();
                    ranges.Add(new { owner = Identity(entity), start, end = LifecycleRecording.Batch.Calls.Count });
                }
                var wipe = probe.Level.Wipe;
                if (wipe != null) wipe.Render(probe.Level);
                object updateAfter = UpdateState();
                if (RandomCalls() != rngBefore || JsonSerializer.Serialize(updateBefore) != JsonSerializer.Serialize(updateAfter))
                    throw new InvalidOperationException("Recording render changed update timers/input/RNG");
                var batch = LifecycleRecording.Batch;
                if (batch.Calls.Count != batch.Geometry.Calls.Count) throw new InvalidOperationException("Missing original draw geometry");
                probe.Write(new { @event = "contract-render", tick, phase, owner = Identity(owner),
                    freezeBeforeUpdate = freezeBefore, freezeAfterUpdate = Engine.FreezeTimer,
                    rngBefore, rngAfter = RandomCalls(), updateStateBefore = updateBefore, updateStateAfter = updateAfter,
                    position = XY(owner.Position), animation = owner.Get<PlayerSprite>()?.CurrentAnimationID,
                    spriteScale = owner.Get<PlayerSprite>() is PlayerSprite sprite ? XY(sprite.Scale) : null,
                    spriteRotation = owner.Get<PlayerSprite>()?.Rotation,
                    hasHair = owner.Get<PlayerSprite>()?.HasHair, hairCount = owner.Get<PlayerSprite>()?.HairCount,
                    hairFacing = owner.Get<PlayerHair>() is PlayerHair renderedHair ? (int)renderedHair.Facing : (int?)null,
                    hairOutline = owner.Get<PlayerHair>()?.DrawPlayerSpriteOutline,
                    hairColor = owner.Get<PlayerHair>() is PlayerHair colorHair ? RGBA(colorHair.Color) : null,
                    hairNodes = owner.Get<PlayerHair>()?.Nodes.Select(XY).ToArray(),
                    introEase = owner is Player live ? PrivateField<float>(live, "introEase") : (float?)null,
                    deadOffset = owner is Player alive ? XY(PrivateField<Vector2>(alive, "deadOffset")) : null,
                    center = XY(owner.Center), effectPercent = owner.Get<DeathEffect>()?.Percent,
                    effectOrigin = owner.Get<DeathEffect>() is DeathEffect effect ? XY(owner.Position + effect.Position) : null,
                    effectColor = owner.Get<DeathEffect>() is DeathEffect coloredEffect ? RGBA(coloredEffect.Color) : null,
                    ranges, wipe = wipe == null ? null : new { owner = Identity(wipe), wipe.WipeIn, wipe.Percent },
                    draws = batch.Calls.Select((draw, index) => new { texture = draw.Texture.ToString(),
                        textureSize = new[] { ((Microsoft.Xna.Framework.Graphics.Texture2D)draw.Texture).Width,
                            ((Microsoft.Xna.Framework.Graphics.Texture2D)draw.Texture).Height },
                        position = XY(draw.Position), clip = new[] { draw.Clip.X, draw.Clip.Y, draw.Clip.Width, draw.Clip.Height },
                        color = RGBA(draw.Color), draw.Rotation, origin = XY(draw.Origin), scale = XY(draw.Scale), effects = (int)draw.Effects,
                        vertices = new[] {
                            Vertex(batch.Geometry.Calls[index].Position0, batch.Geometry.Calls[index].TextureCoordinate0, batch.Geometry.Calls[index].Color0),
                            Vertex(batch.Geometry.Calls[index].Position1, batch.Geometry.Calls[index].TextureCoordinate1, batch.Geometry.Calls[index].Color1),
                            Vertex(batch.Geometry.Calls[index].Position2, batch.Geometry.Calls[index].TextureCoordinate2, batch.Geometry.Calls[index].Color2),
                            Vertex(batch.Geometry.Calls[index].Position3, batch.Geometry.Calls[index].TextureCoordinate3, batch.Geometry.Calls[index].Color3) } }).ToArray(),
                    wipeDraws = LifecycleRecording.Wipes.Select(draw => new { vertexCount = draw.Count,
                        matrix = new[] { draw.Matrix.M11, draw.Matrix.M12, draw.Matrix.M13, draw.Matrix.M14,
                            draw.Matrix.M21, draw.Matrix.M22, draw.Matrix.M23, draw.Matrix.M24,
                            draw.Matrix.M31, draw.Matrix.M32, draw.Matrix.M33, draw.Matrix.M34,
                            draw.Matrix.M41, draw.Matrix.M42, draw.Matrix.M43, draw.Matrix.M44 } }).ToArray(),
                    wipeVertices = LifecycleRecording.Wipes.Select(draw => draw.Vertices.Select(vertex => new {
                        position = new[] { vertex.Position.X, vertex.Position.Y, vertex.Position.Z }, color = RGBA(vertex.Color) }).ToArray()).ToArray() });
            }
            finally { LifecycleRecording.End(); }
        }
    }
}
