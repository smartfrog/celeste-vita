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

namespace DecalOracle
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
        public void Draw(Texture2D texture, Vector2 position, Rectangle clip, Color color, float rotation,
                         Vector2 origin, float scale, SpriteEffects effects, float depth) =>
            Draw(texture, position, clip, color, rotation, origin, new Vector2(scale, scale), effects, depth);
    }
}

namespace Monocle
{
    using Random = PrivateRuntime.Random;

    public class Component
    {
        public Entity Entity;
        public bool Active = true;
        public bool Visible = true;
        public Component(bool active, bool visible) { Active = active; Visible = visible; }
        public Scene Scene => Entity?.Scene;
        public virtual void Update() { }
        public virtual void Render() { }
    }

    public class Entity
    {
        public Vector2 Position;
        public Scene Scene;
        public int Depth;
        public bool Active = true, Visible = true;
        public readonly List<Component> Components = new();
        public Entity() { }
        public Entity(Vector2 position) { Position = position; }
        public void Add(Component component) { component.Entity = this; Components.Add(component); }
        public virtual void Added(Scene scene) { Scene = scene; }
        public virtual void Update()
        {
            foreach (var component in Components)
            {
                if (component.Active) component.Update();
            }
        }
        public virtual void Render()
        {
            foreach (var component in Components)
            {
                if (component.Visible) component.Render();
            }
        }
    }

    public class Scene
    {
        public readonly Tracker Tracker = new();
        public virtual void Add(Entity entity) =>
            throw new NotSupportedException("Decal scene entity creation is outside the static art oracle boundary");
    }

    public sealed class Tracker
    {
        public T GetEntity<T>() =>
            throw new NotSupportedException("Scared-animal player tracking is outside the static art oracle boundary");
    }

    public sealed class VirtualTexture
    {
        public int Width = 4096, Height = 4096;
        public string Path;
        public Texture2D Texture;
        public void Dispose() { }
    }

    public static class Draw { public static DecalOracle.RecordingBatch SpriteBatch = new(); }

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

    public static class Engine { public static float DeltaTime = 1f / 60f; }

    public sealed class Camera { public Vector2 Position; }

    public class Level : Scene
    {
        public Vector2 Wind;
        public readonly Camera Camera = new();
        public Session.CoreModes CoreMode;
        public ParticleSystem ParticlesBG = new();
        public ParticleSystem ParticlesFG = new();
    }

    public static class Session
    {
        public enum CoreModes { Hot, Cold }
    }

    public enum ParticleTypes { Chimney }

    public sealed class ParticleSystem { }

    public sealed class ParticleEmitter : Component
    {
        public ParticleEmitter(ParticleSystem system, ParticleTypes type, Vector2 offset, Vector2 direction,
                               float angle, int count, float interval)
            : base(true, true) =>
            throw new NotSupportedException("Smoke emitter creation is outside the static art oracle boundary");
        public void SimulateCycle() =>
            throw new NotSupportedException("Smoke simulation is outside the static art oracle boundary");
    }

    public sealed class BloomPoint : Component
    {
        public BloomPoint(Vector2 position, float alpha, float radius) : base(true, true) =>
            throw new NotSupportedException("Bloom point creation is outside the static art oracle boundary");
    }

    public sealed class SoundSource : Component
    {
        public SoundSource(string path) : base(true, true) =>
            throw new NotSupportedException("Sound source creation is outside the static art oracle boundary");
    }

    public sealed class MirrorSurface : Component
    {
        public Vector2 ReflectionOffset;
        public Color ReflectionColor;
        public Action OnRender;
        public MirrorSurface() : base(true, true) { }
    }

    public sealed class SineWave : Component
    {
        public float Value;
        public SineWave(float frequency, float phase) : base(true, true) =>
            throw new NotSupportedException("Floaty sine wave creation is outside the static art oracle boundary");
    }

    public class Solid : Entity
    {
        public bool BlockWaterfalls;
        public int SurfaceSoundIndex;
        public Solid(Vector2 position, float width, float height, bool safe) : base(position) =>
            throw new NotSupportedException("Decal-created solid is outside the static art oracle boundary");
    }

    public sealed class Sprite : Component
    {
        public Vector2 Position;
        public Vector2 Scale = Vector2.One;
        public string CurrentAnimationID;
        public Sprite(SpriteBank bank, string id) : base(true, true) { }
        public void AddLoop(string id, float delay, params MTexture[] textures) { }
        public void Add(string id, float delay, string next, params MTexture[] textures) { }
        public void Play(string id, bool restart = false, bool randomizeFrame = false) { }
        public void CenterOrigin() { }
    }

    public sealed class SpriteBank { }

    public sealed class Player
    {
        public Vector2 Position;
        public void Die(Vector2 direction) =>
            throw new NotSupportedException("Hazard callback excluded from the static art oracle boundary");
    }

    public sealed class Wiggler : Component
    {
        public Wiggler() : base(true, true) { }
        public static Wiggler Create(float duration, float frequency, Action<float> onUpdate, bool start = false) =>
            throw new NotSupportedException("Final flag wiggle is outside the static art oracle boundary");
    }

    public static class SummitCheckpoint
    {
        public sealed class ConfettiRenderer : Entity
        {
            public ConfettiRenderer(Vector2 position) : base(position) =>
                throw new NotSupportedException("Final flag confetti is outside the static art oracle boundary");
        }
    }
}
