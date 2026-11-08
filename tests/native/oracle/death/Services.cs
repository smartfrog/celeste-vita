using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Monocle;

namespace DeathOracle
{
    public sealed class UnsupportedClosure : Exception
    {
        public UnsupportedClosure(string message) : base(message) { }
    }
    public static class Records
    {
        public static readonly List<string> Events = new();
        public static void Add(string name) => Events.Add(name);
    }
}

namespace Microsoft.Xna.Framework
{
    public struct Vector3
    {
        public float X, Y, Z;
        public Vector3(float x, float y, float z) { X = x; Y = y; Z = z; }
    }
    public struct Matrix
    {
        public float Scale;
        public static Matrix CreateScale(float value) => new() { Scale = value };
    }
}
namespace Microsoft.Xna.Framework.Graphics
{
    public struct VertexPositionColor { public Vector3 Position; public Color Color; }
}
namespace Monocle
{
    public sealed class Camera { }
    public sealed class BitTag { public static int TotalTags = 2; }
    public class Collider
    {
        public float Width, Height, Left, Top;
        public float Right => Left + Width;
        public float Bottom => Top + Height;
        public float CenterX => Left + Width / 2;
        public float CenterY => Top + Height / 2;
        public void Added(Entity entity) { }
        public void Removed() { }
    }
    public static class Engine
    {
        public static float DeltaTime, RawDeltaTime, FreezeTimer, TimeRate = 1;
        public static ulong FrameCounter;
        public static Scene Scene;
        public static GraphicsBoundary Graphics = new();
        public static PoolBoundary Pooler = new();
    }
    public sealed class GraphicsBoundary { public DeviceBoundary GraphicsDevice = new(); }
    public sealed class DeviceBoundary { public ViewportBoundary Viewport = new(); }
    public sealed class ViewportBoundary { public int Width = 1920; }
    public sealed class PoolBoundary { public void EntityRemoved(Entity entity) => DeathOracle.Records.Add("entity-removed:" + entity.GetType().Name); }
    public partial class Entity
    {
        public void DebugRender(Camera camera) => throw new DeathOracle.UnsupportedClosure("Debug rendering excluded");
        public bool CollideCheck<T>(Vector2 at) => throw new DeathOracle.UnsupportedClosure("Live collision closure not linked");
    }
    public static partial class Calc
    {
        public static Delegate GetMethod<T>(object from, string name) => throw new DeathOracle.UnsupportedClosure("ReflectState excluded");
    }
}
namespace Celeste
{
    public static class Tags { public const int Global = 1; }
    public static partial class GFX
    {
        public static readonly List<VertexPositionColor[]> WipeVertices = new();
        public static void DrawVertices(Matrix matrix, VertexPositionColor[] vertices, int length)
        {
            if (matrix.Scale != 1 || length != vertices.Length) throw new DeathOracle.UnsupportedClosure("Unexpected GPU boundary");
            WipeVertices.Add((VertexPositionColor[])vertices.Clone());
        }
    }
    public enum RumbleStrength { Light, Strong }
    public enum RumbleLength { Medium, Long, Short }
    public static class Input
    {
        public static SampledButton MenuConfirm = new();
        public static void Rumble(RumbleStrength strength, RumbleLength length) => DeathOracle.Records.Add("rumble:" + strength);
    }
    public sealed class SampledButton { public bool Pressed; }
    public static class Audio
    {
        public static void Stop(object handle) => DeathOracle.Records.Add("audio-stop");
        public static void Play(string path, Vector2 at) => DeathOracle.Records.Add(path);
        public static void SetMusicParam(string key, float value) => DeathOracle.Records.Add("music:" + key);
    }
    public sealed class VertexLight : Component
    {
        public float Alpha = 1;
        public VertexLight() : base(false, false) { }
    }
    public sealed class AssistProfile { public bool Invincible; }
    public sealed class SaveData
    {
        public static SaveData Instance = new();
        public AssistProfile Assists = new();
        public int Deaths;
        public void AddDeath(int area) { Deaths++; }
    }
    public sealed class Session
    {
        public enum CoreModes { None, Hot, Cold }
        public int Area, Deaths, DeathsInCurrentLevel, Dashes, DashesAtLevelStart;
        public long Time;
        public bool FirstLevel = true, Cassette, HeartGem, HitCheckpoint;
        public List<object> Strawberries = new();
    }
    public sealed class Follower { public Entity Entity; }
    public sealed class Leader
    {
        public readonly List<Follower> Followers = new();
        public void LoseFollowers()
        {
            if (Followers.Count != 0) throw new DeathOracle.UnsupportedClosure("Followers must be absent");
        }
    }
    public sealed class Strawberry : Entity { public bool Golden, Winged; public Entry ID; public sealed class Entry { public string Level; } }
    public sealed class LevelExit : Scene
    {
        public enum Mode { GoldenBerryRestart }
        public string GoldenStrawberryEntryLevel;
        public LevelExit(Mode mode, Session session) => throw new DeathOracle.UnsupportedClosure("Golden strawberry excluded");
    }
    [Tracked(false)]
    public sealed class Lookout : Entity { public void StopInteracting() => throw new DeathOracle.UnsupportedClosure("Lookout excluded"); }
    [Tracked(false)]
    public sealed class Textbox : Entity { }
    public sealed class Booster { public void PlayerDied() => throw new DeathOracle.UnsupportedClosure("Booster excluded"); }
    [Tracked(false)]
    public sealed class CassetteBlockManager : Entity { public void AdvanceMusic(float time) => throw new DeathOracle.UnsupportedClosure("Cassette blocks excluded"); }
    public sealed class Holdable { public void Release(Vector2 direction) => throw new DeathOracle.UnsupportedClosure("Holding excluded"); }
    public sealed class WindController : Entity { public void SnapWind() => throw new DeathOracle.UnsupportedClosure("Wind closure not linked"); }
    public sealed class ClearBoundary { public void Clear() => DeathOracle.Records.Add("clear"); }
    public sealed class CounterDisplay { public float DrawLerp; }
    public static class Glitch { public static float Value; }
    public static class Distort { public static float Anxiety, GameRate; }
    public static class TrailManager { public static void Clear() => DeathOracle.Records.Add("trail-clear"); }
    public sealed class DisplacementBoundary
    {
        public void AddBurst(Vector2 at, float duration, float from, float to) => DeathOracle.Records.Add("displacement-burst");
    }
    public partial class Level
    {
        public Session Session = new();
        public ScreenWipe Wipe;
        public bool InCutscene, Completed, TimerStarted;
        public Rectangle Bounds = new(0, 0, 320, 180);
        public Vector2 Wind;
        public DisplacementBoundary Displacement = new();
        public ClearBoundary ParticlesBG = new(), Particles = new(), ParticlesFG = new();
        CounterDisplay strawberriesDisplay = new();
        public void Shake() => DeathOracle.Records.Add("shake-UNSUPPORTED-RNG");
        public void DoScreenWipe(bool wipeIn, Action onComplete = null)
        {
            DeathOracle.Records.Add("wipe-create:" + wipeIn);
            new AngledWipe(this, wipeIn, onComplete);
        }
#if !PROBE_LOAD_LEVEL
        public void LoadLevel(Player.IntroTypes intro)
        {
            throw new DeathOracle.UnsupportedClosure("Celeste.Level.LoadLevel:357-1387: original room reconstruction, scoped RNG stack, Player constructor/Added, camera, area wipe not yet closed");
        }
#endif
    }
    public partial class Player
    {
        public enum IntroTypes { Respawn }
        public PlayerSprite Sprite;
        public PlayerHair Hair;
        public VertexLight Light = new();
        public StateMachine StateMachine = new(26);
        public Level level;
        public bool Dead;
        public Vector2 Speed;
        public Facings Facing = Facings.Right;
        public Leader Leader = new();
        public Booster LastBooster;
        public Holdable Holding;
        object wallSlideSfx;
        float introEase;
        Vector2 deadOffset;
        Tween respawnTween;
        public Player(Vector2 position, Level owner) : base(position)
        {
            level = owner;
            Sprite = new PlayerSprite(PlayerSpriteMode.Madeline);
            Hair = new PlayerHair(Sprite) { Facing = Facing };
            Add(Hair); Add(Sprite); Add(Light); Add(StateMachine);
            StateMachine.SetCallbacks(14, null, null, IntroRespawnBegin, IntroRespawnEnd);
            Hair.Start();
        }
        void Stop(object handle) => Audio.Stop(handle);
        void Play(string name) => Audio.Play(name, Position);
    }
}
