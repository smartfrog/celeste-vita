using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Xna.Framework;
using Monocle;

namespace Microsoft.Xna.Framework
{
    public struct Rectangle
    {
        public int X, Y, Width, Height;
        public Rectangle(int x, int y, int width, int height) { X = x; Y = y; Width = width; Height = height; }
        public int Left => X;
        public int Top => Y;
        public int Right => checked(X + Width);
        public int Bottom => checked(Y + Height);
        public static Rectangle Empty => default;
        public bool Contains(int x, int y) => x >= Left && x < Right && y >= Top && y < Bottom;
    }

    public struct Vector2
    {
        public float X, Y;
        public Vector2(float x, float y) { X = x; Y = y; }
        public static Vector2 operator *(Vector2 a, float b) => new(a.X * b, a.Y * b);
    }

    public static class TitleContainer
    {
        public static Stream OpenStream(string path) => File.OpenRead(path);
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

namespace VisualOracle
{
    public sealed class RandomCall
    {
        public int ordinal { get; set; }
        public string api { get; set; }
        public int[] arguments { get; set; }
        public double result { get; set; }
        public string layer { get; set; }
        public int x { get; set; }
        public int y { get; set; }
        public string purpose { get; set; }
    }

    public static class Trace
    {
        public static bool Enabled;
        public static string Layer;
        public static int X = -1, Y = -1;
        public static readonly List<RandomCall> Calls = new();
        public static void Add(string api, int[] arguments, double result)
        {
            if (Enabled) Calls.Add(new() { ordinal = Calls.Count, api = api, arguments = arguments, result = result,
                layer = Layer, x = X, y = Y, purpose = "overlay-auxiliary" });
        }
    }

    public sealed class TracedRandom : PrivateRuntime.Random
    {
        public TracedRandom() : base() { }
        public TracedRandom(int seed) : base(seed) { Trace.Add(".ctor", new[] { seed }, 0); }
        public override int Next(int max)
        {
            int result = base.Next(max);
            Trace.Add("Next", new[] { max }, result);
            return result;
        }
        public override int Next() { int result = base.Next(); Trace.Add("Next", Array.Empty<int>(), result); return result; }
        public override int Next(int min, int max)
        {
            int result = base.Next(min, max);
            Trace.Add("Next", new[] { min, max }, result);
            return result;
        }
        public override double NextDouble() { double result = base.NextDouble(); Trace.Add("NextDouble", Array.Empty<int>(), result); return result; }
        public override void NextBytes(byte[] buffer) => throw new NotSupportedException("Unexpected RNG API in bake");
    }
}

namespace Monocle
{
    public class Component
    {
        public Component(bool active, bool visible) { }
    }

    public sealed class Engine
    {
        public sealed class ContentInfo { public string RootDirectory; }
        public static readonly Engine Instance = new();
        public readonly ContentInfo Content = new();
    }

    public sealed class MTexture
    {
        public string Name;
        public int X, Y, Width, Height;
        public MTexture(string name, int x, int y, int width, int height) { Name = name; X = x; Y = y; Width = width; Height = height; }
        public MTexture(MTexture parent, int x, int y, int width, int height)
        {
            if (x < 0 || y < 0 || x + width > parent.Width || y + height > parent.Height)
                throw new ArgumentException("Subtexture outside source rectangle");
            Name = parent.Name; X = parent.X + x; Y = parent.Y + y; Width = width; Height = height;
        }
    }

    public sealed class TileAssignment
    {
        public string layer { get; set; }
        public int x { get; set; }
        public int y { get; set; }
        public int rng { get; set; }
        public MTexture Texture;
    }

    public sealed class TileAssignments
    {
        private readonly int columns, rows;
        public readonly List<TileAssignment> Commands = new();
        public TileAssignments(int columns, int rows) { this.columns = columns; this.rows = rows; }
        public MTexture this[int x, int y]
        {
            set
            {
                if (x < 0 || y < 0 || x >= columns || y >= rows) throw new ArgumentException("Tile assignment outside grid");
                var call = VisualOracle.Trace.Calls[^1];
                call.x = VisualOracle.Trace.X = x; call.y = VisualOracle.Trace.Y = y; call.purpose = "texture-variant";
                Commands.Add(new() { layer = VisualOracle.Trace.Layer, x = x, y = y, rng = call.ordinal, Texture = value });
            }
        }
    }

    public sealed class TileGrid
    {
        public readonly TileAssignments Tiles;
        public TileGrid(int width, int height, int columns, int rows)
        {
            if (width != 8 || height != 8) throw new ArgumentException("Unexpected tile size");
            Tiles = new(columns, rows);
        }
    }
}

namespace Celeste
{
    public static class BinaryPacker
    {
        public sealed class Element { public Dictionary<string, object> Attributes = new(); }
    }
    public partial class LevelData
    {
        public string Name, Solids, Bg;
        public Rectangle Bounds;
    }
    public partial class MapData
    {
        public sealed class AreaInfo { public string Name = "area_1"; }
        public AreaInfo Data = new();
        public Rectangle Bounds;
        public List<LevelData> Levels = new();
        public List<Rectangle> Filler = new();
    }
    public static class GFX
    {
        public static Autotiler FGAutotiler, BGAutotiler;
        public static Dictionary<string, MTexture> Game = new();
        public static AnimatedTilesBank AnimatedTilesBank = new();
    }
    public sealed class LoaderLayers
    {
        public VirtualMap<char> Foreground, Background;
        public Vector2 Position;
        public LoaderLayers(VirtualMap<char> foreground, VirtualMap<char> background, Vector2 position)
        { Foreground = foreground; Background = background; Position = position; }
    }
}
