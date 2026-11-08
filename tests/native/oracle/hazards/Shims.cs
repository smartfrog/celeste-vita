using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Monocle;
using Celeste;

namespace Monocle
{
    public partial class Entity
    {
        public int Depth;
        public void Add(Component component)
        {
            component.Entity = this;
            if (!Scene.Tracker.Components.TryGetValue(component.GetType(), out var values))
                Scene.Tracker.Components[component.GetType()] = values = new();
            values.Add(component);
            if (component is PlayerCollider pc)
            {
                var callback = pc.OnCollide;
                pc.OnCollide = player => { Scene.Tracker.Overlaps.Add(values.IndexOf(pc)); callback(player); };
            }
        }
    }
    public partial class Scene
    {
        public readonly List<string> Events = new();
        public void Add(PlayerDeadBody body) { Events.Add("corpse_added"); }
        public void Remove(Player player) { Events.Add("player_removed"); player.Removed = true; }
    }
    public sealed partial class Tracker
    {
        public readonly Dictionary<Type, List<Component>> Components = new();
        public readonly List<int> Checks = new(), Overlaps = new();
        private IEnumerable<T> HazardComponents<T>()
        {
            if (!Components.TryGetValue(typeof(T), out var values)) yield break;
            for (int i = 0; i < values.Count; i++)
            {
                if (typeof(T) == typeof(PlayerCollider)) Checks.Add(i);
                yield return (T)(object)values[i];
            }
        }
        public T GetEntity<T>() where T : Entity
        {
            if (typeof(T) != typeof(Lookout)) throw new NotSupportedException("Unvalidated entity lookup");
            if (Entities.TryGetValue(typeof(T), out var values) && values.Count != 0) throw new NotSupportedException("Lookout excluded");
            return null;
        }
    }
    public static partial class Engine { public static Scene Scene; }
    public sealed class Follower { public Entity Entity; }
    public sealed class Leader
    {
        public readonly List<Follower> Followers = new();
        public void LoseFollowers()
        {
            if (Followers.Count != 0) throw new NotSupportedException("Followers excluded");
        }
    }
}
namespace Celeste
{
    public partial class Spikes
    {
        private PlayerCollider pc;
    }
    public sealed class Strawberry : Entity
    {
        public bool Golden, Winged;
        public EntityID ID;
    }
    public struct EntityID { public string Level; }
    public sealed class Lookout : Entity { public void StopInteracting() => throw new NotSupportedException("Lookout excluded"); }
    public sealed class LevelExit : Scene
    {
        public enum Mode { GoldenBerryRestart }
        public string GoldenStrawberryEntryLevel;
        public LevelExit(Mode mode, Session session) => throw new NotSupportedException("Golden follower excluded");
    }
    public sealed class PlayerDeadBody : Entity
    {
        public bool HasGolden;
        public Action DeathAction;
        public PlayerDeadBody(Player player, Vector2 direction)
        {
            if (!player.Dead || player.Depth != -1000000 || player.Speed != Vector2.Zero || !player.StateMachine.Locked || player.Collidable)
                throw new InvalidOperationException("Immediate source effects must precede corpse creation boundary");
            player.DeathDirection = direction;
            player.Scene.Events.Add("corpse_created");
        }
    }
    public partial class Player
    {
        public readonly Leader Leader = new();
        public bool Removed;
        public Vector2 DeathDirection;
        private object wallSlideSfx;
        private void Stop(object sound) { }
    }
}
