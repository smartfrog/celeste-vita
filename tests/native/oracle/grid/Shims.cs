using System;
using System.Collections.Generic;
using System.Globalization;
using Microsoft.Xna.Framework;

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
        public bool Intersects(Rectangle b) => b.Left < Right && Left < b.Right && b.Top < Bottom && Top < b.Bottom;
    }
}

namespace Monocle
{
    public static class GridFixture
    {
        private static float Float(string value) => value.StartsWith("@")
            ? BitConverter.Int32BitsToSingle(unchecked((int)uint.Parse(value.Substring(1), NumberStyles.HexNumber)))
            : float.Parse(value, CultureInfo.InvariantCulture);

        public static Grid Parse(string[] f)
        {
            int columns = int.Parse(f[8]), rows = int.Parse(f[9]);
            string cells = f[10] == "-" ? "" : f[10];
            float width = Float(f[6]), height = Float(f[7]);
            if (columns < 0 || rows < 0 || (long)columns * rows != cells.Length || !float.IsFinite(width) || !float.IsFinite(height) || width <= 0 || height <= 0)
                throw new ArgumentException("Invalid grid dimensions/data");
            var grid = new Grid(columns, rows, width, height) { Position = new(Float(f[4]), Float(f[5])) };
            for (int y = 0; y < rows; y++) for (int x = 0; x < columns; x++)
            {
                char cell = cells[y * columns + x];
                if (cell != '0' && cell != '1') throw new ArgumentException("Invalid grid cell");
                grid[x, y] = cell == '1';
            }
            return grid;
        }
    }

    public sealed class VirtualMap<T>
    {
        private readonly T[,] data;
        public int Columns { get; }
        public int Rows { get; }
        public VirtualMap(int columns, int rows, T emptyValue)
        {
            if (columns < 0 || rows < 0) throw new ArgumentException("Negative storage size");
            Columns = columns; Rows = rows; data = new T[columns, rows];
            for (int x = 0; x < columns; x++) for (int y = 0; y < rows; y++) data[x, y] = emptyValue;
        }
        public T this[int x, int y] { get => data[x, y]; set => data[x, y] = value; }
        public bool AnyInSegmentAtTile(int x, int y)
        {
            if (x < 0 || y < 0 || x >= Columns || y >= Rows) throw new ArgumentException("Invalid segment");
            return true;
        }
    }
}

#if !PLAYER_ORACLE
namespace Celeste
{
    public static class BinaryPacker
    {
        public sealed class Element { public Dictionary<string, object> Attributes = new(); }
    }
    public partial class LevelData
    {
        public string Name, Solids = "", Bg = "";
        public Rectangle Bounds;
    }
    public partial class MapData
    {
        public Rectangle Bounds;
        public List<LevelData> Levels = new();
        public List<Rectangle> Filler = new();
    }
    public static class GFX
    {
        public static readonly Autotiler FGAutotiler = new();
    }
    public sealed class Autotiler { public List<Rectangle> LevelBounds = new(); }
}
#endif
