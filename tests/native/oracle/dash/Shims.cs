using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Monocle;

namespace Microsoft.Xna.Framework
{
    public partial struct Vector2
    {
        public static Vector2 One => new(1f, 1f);
        public static Vector2 operator -(Vector2 v) => new(-v.X, -v.Y);
        public static float Dot(Vector2 a, Vector2 b) => a.X * b.X + a.Y * b.Y;
    }
}

namespace Monocle
{
    public static partial class Engine
    {
        public static float TimeRate = 1f, TimeRateB = 1f, FreezeTimer;
        public static ulong FrameCounter;
        public static bool DashAssistFreeze, DashAssistFreezePress;
        public static readonly EngineActivity Instance = new();
        public static readonly CommandState Commands = new();
    }
    public sealed class EngineActivity { public bool IsActive = true; }
    public sealed class CommandState { public bool Open; }
    public partial class FrameDriver
    {
        private readonly Scene scene;
        public FrameDriver(Scene scene) { this.scene = scene; }
    }
    public partial class Scene
    {
        public Action Simulate;
        public void BeforeUpdate() { }
        public void Update() => Simulate?.Invoke();
        public void AfterUpdate() { }
        public bool OnInterval(float interval) => false;
        public void Add(Celeste.PlayerDashAssist assist) => throw new NotSupportedException("Dash assist excluded");
    }
    public partial class Entity
    {
        public float Top => Collider.AbsoluteTop;
        public T SceneAs<T>() where T : Scene => (T)Scene;
    }
    public static partial class MInput
    {
        public static bool Active = true, ControllerHasFocus;
        public static readonly SampledKeyboard Mouse = new();
        public static readonly SampledGamepad[] GamePads = { new(), new(), new(), new() };
        public static readonly List<VirtualInput> VirtualInputs = new();
    }
    public sealed partial class SampledKeyboard
    {
        public void Update() { }
        public void UpdateNull() { }
        public bool HasAnyInput() => false;
    }
    public sealed class SampledGamepad
    {
        public bool Attached;
        public void Update() { }
        public void UpdateNull() { }
        public bool HasAnyInput() => false;
    }
    public static partial class Calc
    {
        public static readonly CosmeticRandom Random = new();
        public static float AbsAngleDiff(float a, float b)
        {
            float diff = (b - a + (float)Math.PI) % ((float)Math.PI * 2f);
            if (diff < 0f) diff += (float)Math.PI * 2f;
            return Math.Abs(diff - (float)Math.PI);
        }
    }
    public sealed class CosmeticRandom { public Vector2 Range(Vector2 a, Vector2 b) => throw new NotSupportedException("Particles excluded"); }
    public static class DashVectorExtensions
    {
        public static Vector2 SafeNormalize(this Vector2 value)
        {
            if (value == Vector2.Zero) return value;
            float scale = 1f / (float)Math.Sqrt(value.X * value.X + value.Y * value.Y);
            return value * scale;
        }
        public static Vector2 RotateTowards(this Vector2 value, float angle, float max) => throw new NotSupportedException("Super dashing excluded");
    }
}

namespace Celeste
{
    public enum CrouchDashModes { Press, Hold }
    public sealed partial class Settings
    {
        public static readonly Settings Instance = new();
        public CrouchDashModes CrouchDashMode = CrouchDashModes.Press;
    }
    public sealed class AimSample { public Vector2 Value; }
    public static partial class Input
    {
        public static VirtualButton Dash = new(new Binding(), 0, 0.08f, 0.2f);
        public static readonly VirtualButton CrouchDash = new(new Binding(), 0, 0.08f, 0.2f);
        public static readonly AimSample Aim = new();
        public static Vector2 LastAim;
    }
    public sealed partial class Assists { public bool DashAssist, SuperDashing, ThreeSixtyDashing; }
    public sealed partial class SaveData { public ulong TotalDashes; }
    public sealed partial class Session { public int Dashes; }
    public enum Stat { DASHES }
    public static class Stats { public static ulong Dashes; public static void Increment(Stat stat) { Dashes++; } }
    public class CassetteBlockManager : Entity { public void AdvanceMusic(float time) => throw new NotSupportedException("Cassette blocks excluded"); }
    public class PlayerDashAssist : Entity { public float Direction, Scale; public Vector2 Offset; }
    public class DashListener { public Action<Vector2> OnDash; }
    public class SwapBlock : Solid { public Vector2 Direction; public bool Swapping; }
    public class ParticleType { }
    public enum PlayerSpriteMode { MadelineAsBadeline }
    public sealed partial class PresentationSprite { public PlayerSpriteMode Mode; }
    public sealed class ParticleEmitter
    {
        public void Emit(ParticleType type, Vector2 at, float angle) => throw new NotSupportedException("Particles excluded");
        public void Emit(ParticleType type, int count, Vector2 at, Vector2 range, float angle) => throw new NotSupportedException("Particles excluded");
    }
    public static class FlyFeather { public static ParticleType P_Boost; }
    public static class SlashFx { public static void Burst(Vector2 at, float angle) { } }
    public sealed partial class Level
    {
        public readonly ParticleEmitter Particles = new(), ParticlesFG = new();
        public void DirectionalShake(Vector2 direction, float duration) { }
    }
    public sealed partial class Booster { public void PlayerBoosted(Player player, Vector2 direction) => throw new NotSupportedException("Booster excluded"); }
    public partial class Player
    {
        private bool wasDashB, demoDashed, calledDashEvents;
        private float dashTrailTimer;
        private int dashTrailCounter;
        private Vector2 beforeDashSpeed, gliderBoostDir;
        public Vector2? OverrideDashDirection;
        public Booster CurrentBooster;
        public static ParticleType P_DashA, P_DashB, P_DashBadB;
        private void CreateTrail() { }
        public void Sampled() => Observe?.Invoke("input", null);
        public void Frozen() => Observe?.Invoke("freeze", null);
    }
}
