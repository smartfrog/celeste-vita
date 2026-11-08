namespace Microsoft.Xna.Framework.Input
{
    public enum Keys { SampledDebug }
}

namespace Monocle
{
    public abstract class VirtualInput
    {
        public abstract void Update();
    }

    public sealed class Binding
    {
        public bool Held, RawPressed, RawReleased;
        public bool Check(int gamepadIndex, float threshold) => Held;
        public bool Pressed(int gamepadIndex, float threshold) => RawPressed;
        public bool Released(int gamepadIndex, float threshold) => RawReleased;
    }

    public static class MInput
    {
        public static bool Disabled;
        public static readonly SampledKeyboard Keyboard = new();
    }

    public sealed class SampledKeyboard
    {
        public bool DebugHeld;
        public bool Check(Microsoft.Xna.Framework.Input.Keys key) => DebugHeld;
    }

    public static class Engine
    {
        public static float DeltaTime;
    }
}
