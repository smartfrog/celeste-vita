using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Monocle;
using Celeste;

namespace Microsoft.Xna.Framework
{
    public partial struct Vector2
    {
        public static Vector2 Zero => new(0f, 0f);
        public static Vector2 operator -(Vector2 a, Vector2 b) => new(a.X - b.X, a.Y - b.Y);
        public static bool operator ==(Vector2 a, Vector2 b) => a.X == b.X && a.Y == b.Y;
        public static bool operator !=(Vector2 a, Vector2 b) => !(a == b);
        public override bool Equals(object other) => other is Vector2 v && this == v;
        public override int GetHashCode() => HashCode.Combine(X, Y);
        public float LengthSquared() => X * X + Y * Y;
    }
    public static class MathHelper
    {
        public static float Lerp(float a, float b, float amount) => a + (b - a) * amount;
    }
}

namespace Monocle
{
    public static partial class Engine { public static float RawDeltaTime; }
    public static partial class Calc
    {
        public static float Approach(float val, float target, float maxMove) => val > target ? Math.Max(val - maxMove, target) : Math.Min(val + maxMove, target);
    }
    public static class VectorExtensions
    {
        public static float Angle(this Vector2 v) => (float)Math.Atan2(v.Y, v.X);
    }
    public partial class Scene
    {
        public virtual void EnforceBounds(Celeste.Player player) => throw new NotSupportedException("Bounds enforcement excluded");
    }
    public sealed partial class Tracker
    {
        public List<Entity> GetEntities<T>() where T : Entity => Entities[typeof(T)];
#if HAZARD_ORACLE
        public IEnumerable<T> GetComponents<T>()
        {
            if (typeof(T) == typeof(LedgeBlocker) || typeof(T) == typeof(PlayerCollider)) return HazardComponents<T>();
            if (typeof(T) != typeof(Holdable) && typeof(T) != typeof(SafeGroundBlocker))
                throw new NotSupportedException("Unvalidated component category");
            return new List<T>();
        }
#else
        public List<T> GetComponents<T>()
        {
            if (typeof(T) != typeof(Holdable) && typeof(T) != typeof(SafeGroundBlocker) && typeof(T) != typeof(LedgeBlocker) && typeof(T) != typeof(PlayerCollider))
                throw new NotSupportedException("Unvalidated component category");
            return new();
        }
#endif
    }
    public partial class Entity
    {
        public float Left => Collider.AbsoluteLeft;
        public float Right => Collider.AbsoluteRight;
        public Vector2 Center => new((Collider.AbsoluteLeft + Collider.AbsoluteRight) / 2f, (Collider.AbsoluteTop + Collider.AbsoluteBottom) / 2f);
        public Vector2 BottomCenter => new(Center.X, Collider.AbsoluteBottom);
    }
}

namespace Celeste
{
    public enum Facings { Left = -1, Right = 1 }
    public enum DashCollisionResults { NormalCollision, NormalOverride, Rebound, Bounce, Ignore }
    public enum RumbleStrength { Light, Medium, Strong }
    public enum RumbleLength { Short, Medium }
    public sealed class Axis
    {
        public int Value;
        public static explicit operator float(Axis axis) => axis.Value;
    }
    public static class Input
    {
        public static readonly Axis MoveX = new(), MoveY = new(), GliderMoveY = new();
        public static VirtualButton Jump = new(new Binding(), 0, 0.08f, 0f);
        public static readonly VirtualButton Talk = new(new Binding(), 0, 0f, 0f);
        public static bool GrabCheck => false;
        public static bool CrouchDashPressed => false;
        public static bool DashPressed => false;
        public static Vector2 GetAimVector(Facings facing) => new((int)facing, 0f);
        public static void Rumble(RumbleStrength strength, RumbleLength length) { }
    }
    public sealed class Assists
    {
        public enum DashModes { Normal, Infinite }
        public DashModes DashMode;
        public bool NoGrabbing, LowFriction, Invincible;
    }
    public sealed class SaveData
    {
        public static readonly SaveData Instance = new();
        public readonly Assists Assists = new();
        public ulong TotalJumps;
#if HAZARD_ORACLE
        public int DeathCalls;
        public void AddDeath(object area) { DeathCalls++; }
#endif
    }
    public sealed class Session
    {
        public enum CoreModes { None, Cold }
        public PlayerInventory Inventory = PlayerInventory.Default;
#if HAZARD_ORACLE
        public int Deaths, DeathsInCurrentLevel;
        public object Area;
#endif
    }
    public struct Bounds { public int Left, Right; }
    public sealed class Level : Scene
    {
        public readonly Session Session = new();
        public Bounds Bounds = new() { Left = -10000, Right = 10000 };
        public Vector2 Wind;
        public Session.CoreModes CoreMode;
        public bool InSpace, InCutscene;
        public readonly Displacement Displacement = new();
#if HAZARD_ORACLE
        public void Shake() { }
#endif
    }
    public sealed class Displacement
    {
        public void AddBurst(Vector2 at, float duration, float from, float to, float alpha, Func<float, float> ease1, Func<float, float> ease2) => throw new NotSupportedException("Dash displacement excluded");
    }
    public static class Ease { public static float QuadOut(float v) => throw new NotSupportedException("Dash excluded"); }
    public sealed class PresentationSprite
    {
        public Vector2 Scale;
        public void Play(string name) { }
    }
    public partial class Platform
    {
        public bool Safe = true;
        public Func<Player, Vector2, DashCollisionResults> OnDashCollide;
        public Action<Vector2> OnCollide;
        public int GetLandSoundIndex(Player player) => -1;
    }
    public partial class Actor
    {
        public Vector2 LiftSpeed => Vector2.Zero;
    }
    public class Holdable
    {
        public bool SlowRun, SlowFall;
        public bool Check(Player player) => throw new NotSupportedException("Holding excluded");
#if HAZARD_ORACLE
        public void Release(Vector2 direction) => throw new NotSupportedException("Holding excluded");
#endif
    }
    public class SafeGroundBlocker { public bool Check(Player player) => throw new NotSupportedException("Blockers excluded"); }
#if !HAZARD_ORACLE
    public class LedgeBlocker { public bool JumpThruBoostCheck(Player player) => throw new NotSupportedException("Blockers excluded"); }
    public class PlayerCollider { public bool Check(Player player) => throw new NotSupportedException("Hazards excluded"); }
#endif
    public static class ClimbBlocker
    {
        public static bool Check(Scene scene, Player player, Vector2 at) => false;
        public static bool EdgeCheck(Level level, Player player, int dir) => false;
    }
#if !HAZARD_ORACLE
    public class Spikes : Entity { public enum Directions { Left, Right } public Directions Direction; }
#endif
    public class NegaBlock : Entity { }
    public class Water : Entity
    {
        public readonly Surface TopSurface = new();
        public sealed class Surface { public void DoRipple(Vector2 at, float strength) => throw new NotSupportedException("Water excluded"); }
    }
    public class DreamBlock : Solid { public void FootstepRipple(Vector2 at) => throw new NotSupportedException("Dream blocks excluded"); }
    public static class TalkComponent { public static object PlayerOver => null; }
    public sealed class Booster { public bool Ch9HubTransition, BoostingPlayer;
#if HAZARD_ORACLE
        public void PlayerDied() => throw new NotSupportedException("Booster excluded");
#endif
    }
    public static class SurfaceIndex
    {
        public static Platform GetPlatformByPriority(List<Entity> entities) => entities.Count == 0 ? null : (Platform)entities[0];
    }
    public static class Dust { public static void Burst(Vector2 at, float angle, int count, object particle) { } }

    public partial class Player
    {
        public Vector2 Speed, PreviousPosition, DashDir;
        public Facings Facing = Facings.Right;
        public StateMachine StateMachine;
        public int Dashes = 1;
        public float Stamina = 110f;
        public Holdable Holding { get; set; }
        public bool AutoJump, Dead;
        public float AutoJumpTimer;
        private Hitbox hurtbox;
        private readonly Level level;
        private readonly PresentationSprite Sprite = new(), sweatSprite = new();
        private readonly List<Entity> temp = new();
        private Collision onCollideH, onCollideV;
        private float jumpGraceTimer, varJumpTimer, varJumpSpeed, maxFall;
        private float wallSlideTimer = 1.2f, wallSpeedRetentionTimer, wallSpeedRetained;
        private int wallSlideDir, moveX;
        private bool onGround, wasOnGround, launched, dreamJump, canCurveDash, holdCannotDuck, windMovedUp;
        private bool dashStartedOnGround, MuffleLanding;
        private float wallBoostTimer, dashAttackTimer, gliderBoostTimer, dashCooldownTimer, dashRefillCooldownTimer;
        private float lowFrictionStopTimer, forceMoveXTimer, noWindTimer, minHoldTimer, highestAirY, playFootstepOnLand;
        private float starFlyTimer;
        private int wallBoostDir, forceMoveX, hopWaitX, climbTriggerDir, lastClimbMove;
        private Solid climbHopSolid;
        private Vector2 climbHopSolidPosition, lastAim;
        private Booster LastBooster;
        private DreamBlock dreamBlock;
        public Action<string, CollisionData?> Observe;

        public Player(Level scene, Vector2 position, Vector2 initialSpeed)
        {
            level = scene;
            Scene = scene;
            Position = new((int)position.X, (int)position.Y);
            PreviousPosition = Position;
            Speed = initialSpeed;
            Collider = normalHitbox;
            hurtbox = normalHurtbox;
            onCollideH = data => { Observe?.Invoke("collision_h", data); OnCollideH(data); Observe?.Invoke("collided_h", data); };
            onCollideV = data => { Observe?.Invoke("collision_v", data); OnCollideV(data); Observe?.Invoke("collided_v", data); };
            StateMachine = new StateMachine(26);
            for (int i = 1; i < 26; i++) StateMachine.SetCallbacks(i, () => throw new NotSupportedException("State excluded"), null, () => throw new NotSupportedException("State excluded"));
            StateMachine.SetCallbacks(0, NormalUpdate, null, NormalBegin, NormalEnd);
            StateMachine.Added(this);
        }
        public void Frame(float delta, int x, int y, bool held, bool pressed, bool released, bool disabled, bool grab, bool dash)
        {
            if (!float.IsFinite(delta) || delta < 0f || !float.IsFinite(1000f * delta) || x < -1 || x > 1 || y < -1 || y > 1) throw new ArgumentException("Invalid frame input");
            if (grab || dash) throw new NotSupportedException("Grab/Dash excluded");
            ValidateProfile();
#if HAZARD_ORACLE
            level.Tracker.Checks.Clear();
            level.Tracker.Overlaps.Clear();
            RefillCalls = 0;
#endif
            Engine.DeltaTime = Engine.RawDeltaTime = delta;
            Input.MoveX.Value = x;
            Input.MoveY.Value = y;
            Input.Jump.Binding.Held = held;
            Input.Jump.Binding.RawPressed = pressed;
            Input.Jump.Binding.RawReleased = released;
            MInput.Disabled = disabled;
            Input.Jump.Update();
            Observe?.Invoke("input", null);
            SourceGround();
            Observe?.Invoke("ground", null);
            SourcePreamble();
            Observe?.Invoke("preamble", null);
            StateMachine.Update();
            Observe?.Invoke("normal", null);
            SourceBoost();
            Observe?.Invoke("boost", null);
            SourceUnduck();
            Observe?.Invoke("unduck", null);
            SourceHorizontal();
            Observe?.Invoke("horizontal", null);
            SourceVertical();
            Observe?.Invoke("vertical", null);
#if HAZARD_ORACLE
            SourceFinish();
            if (Dead) Observe?.Invoke("removed", null);
#else
            SourceHazards();
            Observe?.Invoke("hazards", null);
            SourceComplete();
            Observe?.Invoke("complete", null);
#endif
        }
        private void ValidateProfile()
        {
#if HAZARD_ORACLE
            if (Leader.Followers.Count != 0) throw new NotSupportedException("Followers excluded");
#endif
            var a = SaveData.Instance.Assists;
            var i = Inventory;
            if (a.DashMode != Assists.DashModes.Normal || a.NoGrabbing || a.LowFriction || a.Invincible ||
                i.Dashes != 1 || !i.DreamDash || !i.Backpack || i.NoRefills || level.InSpace || level.InCutscene ||
                level.CoreMode != Session.CoreModes.None || level.Wind != Vector2.Zero || Holding != null || StateMachine.State != 0 ||
                AutoJump || AutoJumpTimer != 0f || wallBoostTimer != 0f || dashAttackTimer != 0f || gliderBoostTimer != 0f ||
                dashCooldownTimer != 0f || dashRefillCooldownTimer != 0f || forceMoveXTimer != 0f || lowFrictionStopTimer != 0f ||
                climbHopSolid != null || minHoldTimer != 0f || launched || dreamJump || DashDir != Vector2.Zero || Dead ||
                holdCannotDuck || windMovedUp || dashStartedOnGround || hopWaitX != 0 || noWindTimer != 0f ||
                starFlyTimer != 0f || Stamina != 110f || Dashes != 1 || LastBooster != null || dreamBlock != null ||
                wallBoostDir != 0 || forceMoveX != 0 || lastClimbMove != 0)
                throw new NotSupportedException("Unsupported Player profile/invariant");
            foreach (var pair in level.Tracker.Entities)
                foreach (var entity in pair.Value)
                {
#if HAZARD_ORACLE
                    if (pair.Key == typeof(Spikes) && entity is Spikes spike &&
                        (spike.Direction == Spikes.Directions.Up || spike.Direction == Spikes.Directions.Left)) continue;
#endif
                    if (pair.Key != typeof(Solid) && pair.Key != typeof(JumpThru) && pair.Key != typeof(Platform))
                        throw new NotSupportedException("Unsupported entity category");
                    if (entity.GetType() != typeof(Solid) && entity.GetType() != typeof(JumpThru))
                        throw new NotSupportedException("Unsupported platform type");
                    var p = (Platform)entity;
                    if (p.OnCollide != null || p.OnDashCollide != null || (p.Collider is not Hitbox && p.Collider is not Grid))
                        throw new NotSupportedException("Platform hooks/unsupported collider excluded");
                }
        }
        private bool Pickup(Holdable holdable) => throw new NotSupportedException("Holding excluded");
        private int StartDash() => throw new NotSupportedException("Dash excluded");
        private void Throw() => throw new NotSupportedException("Holding excluded");
#if !HAZARD_ORACLE
        private void Drop() => throw new NotSupportedException("Holding excluded");
#endif
        private void ClimbTrigger(int dir) => throw new NotSupportedException("Grab excluded");
        private void ClimbJump() => throw new NotSupportedException("Climb jump excluded");
        private void WallJump(int dir) => throw new NotSupportedException("Wall jump excluded");
        private void SuperWallJump(int dir) => throw new NotSupportedException("Super wall jump excluded");
        private void Rebound(int dir = 0) => throw new NotSupportedException("Rebound excluded");
        private void ReflectBounce(Vector2 direction) => throw new NotSupportedException("Bounce excluded");
        private bool DashCorrectCheck(Vector2 at) => throw new NotSupportedException("Dash excluded");
        private bool OnGround(Vector2 at) => throw new NotSupportedException("Dash ground check excluded");
        private void CreateWallSlideParticles(int dir) { }
        private void Play(string sound) { }
        private void Play(string sound, string parameter, int value) { }
        private object DustParticleFromSurfaceIndex(int index) => null;
    }
}
