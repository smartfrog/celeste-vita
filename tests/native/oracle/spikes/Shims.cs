using System;
using System.Collections.Generic;
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

namespace SpikeOracle
{
    public sealed class TracedRandom : PrivateRuntime.Random
    {
        public int NextCalls;
        public readonly List<int> NextMaximums = new();
        public readonly List<int> Results = new();
        public TracedRandom(int seed) : base(seed) { }
        public override int Next(int maxValue)
        {
            int result = base.Next(maxValue);
            NextCalls++;
            NextMaximums.Add(maxValue);
            Results.Add(result);
            return result;
        }
        public override double NextDouble()
        {
            double result = base.NextDouble();
            NextCalls++;
            NextMaximums.Add(0);
            Results.Add(-1);
            return result;
        }
        public void ResetTrace()
        {
            NextCalls = 0;
            NextMaximums.Clear();
            Results.Clear();
        }
    }

    public record RecordedDraw(object Texture, Vector2 Position, Rectangle Clip, Color Color,
                               float Rotation, Vector2 Origin, Vector2 Scale, SpriteEffects Effects);

    public sealed class RecordingBatch
    {
        public readonly List<RecordedDraw> Calls = new();
        public readonly PresentationOracle.OriginalSpriteBatch Geometry = new();
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
    using Random = PrivateRuntime.Random;

    [AttributeUsage(AttributeTargets.Class)]
    public sealed class TrackedAttribute : Attribute { public TrackedAttribute(bool inherited) { } }

    public sealed class Hitbox
    {
        public float Width, Height;
        public Vector2 Offset;
        public Hitbox(float width, float height, float offsetX = 0, float offsetY = 0)
        {
            Width = width; Height = height; Offset = new Vector2(offsetX, offsetY);
        }
    }

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
        public Entity() { }
        public Entity(Vector2 position) { Position = position; }
        public Scene Scene;
        public Hitbox Collider;
        public int Depth;
        public bool Active = true, Visible = true, Collidable = true;
        public readonly List<Component> Components = new();
        public float Bottom => Position.Y;
        public void Add(Component component) { component.Entity = this; Components.Add(component); }
        public virtual void Added(Scene scene) { Scene = scene; }
        public virtual void Render()
        {
            foreach (var component in Components)
            {
                if (component.Visible) component.Render();
            }
        }
        public bool CollideCheckOutside<T>(T entity, Vector2 position) =>
            throw new NotSupportedException("Spike riding/blocker callbacks are outside the art oracle boundary");
        public bool CollideCheck<T>(T entity, Vector2 position) =>
            throw new NotSupportedException("Spike riding/blocker callbacks are outside the art oracle boundary");
    }

    public class Scene { }

    public sealed class VirtualTexture
    {
        public int Width = 4096, Height = 4096;
        public string Path;
        public Texture2D Texture;
        public void Dispose() { }
    }

    public static class Draw { public static SpikeOracle.RecordingBatch SpriteBatch = new(); }

    public static partial class Calc
    {
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
    public static class GFX
    {
        public static Atlas Game;
        public static SpriteBank SpriteBank;
    }

    public sealed class AreaData
    {
        public string Spike = "default";
        public static AreaData Get(Scene scene) => new AreaData();
    }

    public sealed class LedgeBlocker : Component
    {
        public LedgeBlocker() : base(true, true) { }
    }

    public sealed class PlayerCollider : Component
    {
        public PlayerCollider(Action<Player> onCollide) : base(true, true) { }
    }

    public sealed class StaticMover : Component
    {
        public StaticMover() : base(true, true) { }
        public Action<Vector2> OnShake;
        public Func<Solid, bool> SolidChecker;
        public Func<JumpThru, bool> JumpThruChecker;
        public Action OnEnable;
        public Action OnDisable;
    }

    public class Player
    {
        public Vector2 Speed;
        public float Bottom => 0;
        public void Die(Vector2 direction) => throw new NotSupportedException("Hazard callback excluded from art oracle");
    }

    public class Solid : Entity { }
    public class JumpThru : Entity { }
    public sealed class Sprite : Component
    {
        public Sprite() : base(true, true) { }
        public Vector2 Position;
        public Vector2 Scale = Vector2.One;
        public float Rotation;
        public float X { get => Position.X; set => Position.X = value; }
        public float Y { get => Position.Y; set => Position.Y = value; }
        public int CurrentAnimationTotalFrames => 1;
        public void Play(string id, bool restart = false, bool randomizeFrame = false) { }
        public void SetAnimationFrame(int frame) { }
    }
    public sealed class SpriteBank { public Sprite Create(string id) => new Sprite(); }
    public sealed class EntityData
    {
        public Vector2 Position;
        public int Width, Height;
        public string Attr(string name, string fallback) => fallback;
    }
}
