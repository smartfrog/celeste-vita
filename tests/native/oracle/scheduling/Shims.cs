using System;

namespace Monocle
{
#if !PLAYER_ORACLE
    public class Scene { }
    public class Entity { public Scene Scene; }
#endif
    public class Component
    {
        public bool Active;
        public bool Visible;
        public Entity Entity;
        public int RemovalEvents;
        public Component(bool active, bool visible) { Active = active; Visible = visible; }
        public virtual void Update() { }
        public virtual void Added(Entity entity) { Entity = entity; }
        public virtual void EntityAdded(Scene scene) { Entity.Scene = scene; }
        public void RemoveSelf() { ++RemovalEvents; }
    }
#if !PLAYER_ORACLE
    public static class Engine { public static float DeltaTime; public static float RawDeltaTime; }
#endif
    public static partial class Calc
    {
        public static void Log(string message) => throw new NotSupportedException("Diagnostics are excluded");
        public static T GetMethod<T>(Entity from, string name) => throw new NotSupportedException("Reflection is excluded");
    }
}
