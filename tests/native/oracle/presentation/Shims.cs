using System;
using System.Collections.Generic;
using System.Xml;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Monocle;

namespace Microsoft.Xna.Framework.Graphics
{
    public sealed class Texture2D
    {
        public string Name;
        public int Width = 4096, Height = 4096;
        public override string ToString() => Name;
    }
}

namespace PrivateRuntime
{
    internal static class Environment
    {
        public static int TickCount => System.Environment.TickCount;
        public static string GetResourceString(string value, params object[] args) => string.Format(value, args);
    }
}

namespace PresentationOracle
{
    public sealed class TracedRandom : PrivateRuntime.Random
    {
        public int Calls;
        public TracedRandom() : base() { }
        public TracedRandom(int seed) : base(seed) { }
        public override double NextDouble() { Calls++; return base.NextDouble(); }
        public override int Next(int max) { Calls++; return base.Next(max); }
    }

    public record RecordedDraw(object Texture, Vector2 Position, Rectangle Clip, Color Color,
                               float Rotation, Vector2 Origin, Vector2 Scale, SpriteEffects Effects);

    public sealed class RecordingBatch
    {
        public readonly List<RecordedDraw> Calls = new();
        public readonly OriginalSpriteBatch Geometry = new();
        public void Draw(Texture2D texture, Vector2 position, Rectangle clip, Color color, float rotation,
                         Vector2 origin, Vector2 scale, SpriteEffects effects, float depth)
        {
            Calls.Add(new(texture, position, clip, color, rotation, origin, scale, effects));
            Geometry.Draw(texture, position, clip, color, rotation, origin, scale, effects, depth);
        }
    }
}

namespace Monocle
{
    [AttributeUsage(AttributeTargets.Class)]
    public sealed class TrackedAttribute : Attribute { public TrackedAttribute(bool inherited) { } }
    public class Component
    {
        public Entity Entity;
        public bool Visible = true;
        public Component(bool active, bool visible) { Visible = visible; }
        public virtual void Update() { }
        public virtual void Render() { }
    }
    public class Entity
    {
        public Vector2 Position;
        public Vector2 Center => Position + new Vector2(0, -5.5f);
        public float Y => Position.Y;
        public Scene Scene;
        public bool CollideCheck<T>(Vector2 position) => Scene.BodyProbe(typeof(T), position);
        public List<Entity> CollideAll<T>(Vector2 position, List<Entity> into) { into.Clear(); return into; }
    }
    public class Scene
    {
        public float TimeActive;
        public Func<Type, Vector2, bool> PointProbe = (_, _) => throw new InvalidOperationException("Point probe not provided");
        public Func<Type, Vector2, bool> BodyProbe = (_, _) => throw new InvalidOperationException("Body probe not provided");
        public bool CollideCheck<T>(Vector2 position) => PointProbe(typeof(T), position);
        public bool OnInterval(float interval) => (int)((TimeActive - Engine.DeltaTime) / interval) < (int)(TimeActive / interval);
    }
    public sealed class StateMachine { public int State; }
    public sealed class Engine { public static float DeltaTime, RawDeltaTime; }
    public sealed class VirtualTexture { public int Width = 4096, Height = 4096; public Texture2D Texture; }
    public static class Draw { public static PresentationOracle.RecordingBatch SpriteBatch = new(); }
    public static partial class Calc
    {
        public static XmlDocument LoadContentXML(string path) { var xml = new XmlDocument(); xml.Load(path); return xml; }
        public static void Log(string message) => throw new NotSupportedException("Unexpected source debug logging");
    }
    public partial class Atlas
    {
        public void AddMetadata(string name, string sheet, int[] rectangle)
        {
            var texture = new VirtualTexture { Texture = new Texture2D { Name = name } };
            this[name] = new MTexture(new MTexture(texture), name, new Rectangle(rectangle[0], rectangle[1], rectangle[2], rectangle[3]),
                                     new Vector2(-rectangle[4], -rectangle[5]), rectangle[6], rectangle[7]);
        }
    }
}

namespace Celeste
{
    public static class GFX { public static Atlas Game; public static SpriteBank SpriteBank; }
    public class Platform : Entity
    {
        public int GetStepSoundIndex(Player player) => 0;
        public int GetWallSoundIndex(Player player, int facing) => 0;
    }
    public class Solid : Platform { }
    public class JumpThru : Platform { }
    public static class SurfaceIndex { public static Platform GetPlatformByPriority(List<Entity> entities) => null; }
    public static class ClimbBlocker { public static bool EdgeCheck(Level level, Player player, int direction) => false; }
    public static class Dust
    {
        public static int Calls;
        public static void BurstFG(Vector2 position, float angle, int count, float range) { Calls++; }
        public static void Burst(Vector2 position, float angle) { Calls++; }
    }
    public static class Audio { public static int Stops; public static void Stop(object handle) { Stops++; } }
    public sealed class VirtualAxis
    {
        public int Value;
        public static implicit operator float(VirtualAxis axis) => axis.Value;
    }
    public static class Input { public static VirtualAxis MoveX = new(), MoveY = new(); }
    public sealed class Session { public enum CoreModes { None, Hot, Cold } }
    public class Level : Scene { public bool InCutscene, InSpace; public Session.CoreModes CoreMode; }
    public partial class Player
    {
        public PlayerSprite Sprite;
        public PlayerHair Hair;
        public StateMachine StateMachine = new();
        public Level level;
        public bool Dead, Ducking, IsTired;
        public Vector2 Speed, DashDir;
        public Facings Facing = Facings.Right;
        public int Dashes = 1, MaxDashes = 1, lastDashes = 1;
        public int moveX, lastClimbMove, wallSlideDir;
        public float dashAttackTimer;
        public bool onGround;
        public object Holding, idleSfx;
        public static Color NormalBadelineHairColor => throw new NotSupportedException("Badeline excluded");
        public object Play(string path, string parameter = null, int value = 0) => path;
        public Player(Vector2 position, Level scene)
        {
            Position = position; level = scene; Scene = scene;
            Sprite = new PlayerSprite(PlayerSpriteMode.Madeline) { Entity = this };
            Hair = new PlayerHair(Sprite) { Entity = this, Facing = Facing };
            startHairCount = Sprite.HairCount;
            BindCallbacks(); StartHair();
        }
        public void Preamble() { PreambleIdle(); GroundPhase(); }
        public void Select() => UpdateSprite();
        public object Inspect() => new
        {
            mode = Sprite.Mode.ToString(), Sprite.HairCount, animation = Sprite.CurrentAnimationID, frame = Sprite.CurrentAnimationFrame,
            texture = Sprite.Texture.AtlasPath, scale = new[] { Sprite.Scale.X, Sprite.Scale.Y }, rotation = Sprite.Rotation,
            nodes = Hair.Nodes.ConvertAll(node => new[] { node.X, node.Y }), color = new[] { Hair.Color.R, Hair.Color.G, Hair.Color.B, Hair.Color.A },
            Hair.StepApproach, step = new[] { Hair.StepPerSegment.X, Hair.StepPerSegment.Y }, Hair.StepInFacingPerSegment,
            Hair.DrawPlayerSpriteOutline, border = new[] { Hair.Border.R, Hair.Border.G, Hair.Border.B, Hair.Border.A },
            idleTimer, highestAirY, flash, rng = Calc.Random.Calls
        };
    }
}
