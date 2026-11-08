using System;
using System.Collections.Generic;

namespace Microsoft.Xna.Framework
{
    public partial struct Vector2
    {
        public float X, Y;
        public Vector2(float x, float y) { X = x; Y = y; }
        public static Vector2 UnitX => new Vector2(1f, 0f);
        public static Vector2 UnitY => new Vector2(0f, 1f);
        public static Vector2 operator +(Vector2 a, Vector2 b) => new Vector2(a.X + b.X, a.Y + b.Y);
        public static Vector2 operator *(Vector2 a, float b) => new Vector2(a.X * b, a.Y * b);
    }
}

namespace Monocle
{
    using Microsoft.Xna.Framework;
    public partial class Entity
    {
        public Vector2 Position;
        public bool Collidable = true;
        public Scene Scene;
        public float X { get => Position.X; set => Position.X = value; }
        public float Y { get => Position.Y; set => Position.Y = value; }
        private Collider collider;
        public Collider Collider
        {
            get => collider;
            set { collider = value; if (value != null) value.Added(this); }
        }
    }
    public partial class Scene
    {
        public Tracker Tracker = new Tracker();
    }
    public sealed partial class Tracker
    {
        public Dictionary<Type, List<Entity>> Entities = new Dictionary<Type, List<Entity>>
        {
            [typeof(Celeste.Solid)] = new List<Entity>(),
            [typeof(Celeste.JumpThru)] = new List<Entity>()
        };
    }
    public abstract partial class Collider
    {
        // Shape dispatch is a stub boundary: only the extracted Hitbox path is supported.
        public bool Collide(Entity other)
        {
            if (this is Hitbox own && other.Collider is Hitbox target)
                return own.Collide(target);
            throw new NotSupportedException("Only Hitbox is supported by this oracle");
        }
        public abstract bool Collide(Hitbox other);
    }
}

namespace Celeste
{
    using Monocle;
    using Microsoft.Xna.Framework;
    public partial class Platform : Entity { }
    public class Solid : Platform { }
    public class JumpThru : Platform { }
    public delegate void Collision(CollisionData data);
    public partial class Actor : Entity
    {
        private Vector2 movementCounter;
        public bool IgnoreJumpThrus;
        public Vector2 PositionRemainder => movementCounter;
    }
}
