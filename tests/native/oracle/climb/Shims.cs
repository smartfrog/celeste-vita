using System;
using Microsoft.Xna.Framework;
using Monocle;

namespace Monocle
{
    public abstract partial class Collider
    {
        public abstract bool Collide(Vector2 point);
    }
    public partial class Entity
    {
        public Vector2 TopLeft => new(Left, Top);
        public Vector2 TopRight => new(Right, Top);
    }
}

namespace Celeste
{
    public static partial class Input
    {
        public static VirtualButton Grab = new(new Binding(), 0, 0f, 0.2f);
        private static bool grabToggle;
    }
    public enum GrabModes { Hold, Invert, Toggle }
    public sealed partial class Settings { public GrabModes GrabMode = GrabModes.Hold; }
    public sealed class StrawberrySeed : Entity { }
    public sealed class WallBooster : Entity { public Facings Facing; }
    public sealed class ExcludedConveyorSound
    {
        public void setParameterValue(string name, float value) => throw new NotSupportedException("Wall boosters excluded");
        public void release() => throw new NotSupportedException("Wall boosters excluded");
    }
    public static class Audio
    {
        public static ExcludedConveyorSound Play(string sound, Vector2 at, string parameter, float value) => throw new NotSupportedException("Wall boosters excluded");
        public static void Position(ExcludedConveyorSound sound, Vector2 at) => throw new NotSupportedException("Wall boosters excluded");
    }
    public sealed partial class PresentationSprite
    {
        public string CurrentAnimationID;
        public void Play(string name, bool restart) { }
    }
    public partial class Player
    {
        private float climbNoMoveTimer, hopWaitXSpeed;
        private bool wallBoosting, fastJump;
        private ExcludedConveyorSound conveyorLoopSfx;
        private void PlaySweatEffectDangerOverride(string animation) { }
    }
}
