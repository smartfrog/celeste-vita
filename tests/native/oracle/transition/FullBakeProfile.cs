using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using Celeste;
using Microsoft.Xna.Framework;
using Monocle;

namespace DeathOracle;

static class FullBakeProfile
{
    static JsonElement Inputs()
    {
        using var document = JsonDocument.Parse(File.ReadAllText(Path.Combine(TransitionProfile.DataRoot, "full-bake-input.json")));
        return document.RootElement.Clone();
    }

    public static string RoomsPath => Inputs().GetProperty("rooms").GetString();

    public static object Build(Level level)
    {
        byte[] bytes = File.ReadAllBytes(Inputs().GetProperty("driver").GetString());
        if (Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() != "2f7555abf2d9dd6d4e56429009d674551b2857304fd794d00e18958eef2563c6")
            throw new InvalidDataException("Pinned full-terrain driver changed");
        using var document = JsonDocument.Parse(bytes);
        var driver = document.RootElement;
        var gameplay = level.Session.MapData;
        var terrain = (MapData)RuntimeHelpers.GetUninitializedObject(typeof(MapData));
        terrain.Data = gameplay.Data;
        terrain.Levels = new List<LevelData>();
        terrain.Filler = new List<Rectangle>();
        foreach (var room in driver.GetProperty("levels").EnumerateArray())
        {
            var element = new BinaryPacker.Element { Attributes = new(), Children = new() };
            foreach (string key in new[] { "name", "x", "y", "width", "height" })
                element.Attributes.Add(key, key == "name" ? room.GetProperty(key).GetString() : room.GetProperty(key).GetInt32());
            terrain.Levels.Add(new LevelData(element) { Solids = room.GetProperty("solids").GetString(), Bg = room.GetProperty("bg").GetString() });
        }
        foreach (var rectangle in driver.GetProperty("filler").EnumerateArray())
            terrain.Filler.Add(new Rectangle(rectangle.GetProperty("x").GetInt32(), rectangle.GetProperty("y").GetInt32(),
                                            rectangle.GetProperty("w").GetInt32(), rectangle.GetProperty("h").GetInt32()));
        if (terrain.Levels.Count != 38 || terrain.Filler.Count != 22 || gameplay.Levels.Count != 2)
            throw new InvalidDataException("Full terrain and bounded gameplay catalogs changed");
        var bounds = terrain.Levels.Select(room => room.Bounds).Concat(terrain.Filler).ToArray();
        int left = bounds.Min(rectangle => rectangle.Left) - 64;
        int top = bounds.Min(rectangle => rectangle.Top) - 64;
        terrain.Bounds = new Rectangle(left, top, bounds.Max(rectangle => rectangle.Right) - left + 64,
                                      bounds.Max(rectangle => rectangle.Bottom) - top + 64);
        gameplay.Bounds = terrain.Bounds;
        RoomCoreTileBake.Build(level, terrain);
        var collision = (Grid)level.SolidTiles.Collider;
        if (level.SolidTiles.Position != new Vector2(-64, -3272) || collision.CellsX != 541 || collision.CellsY != 440)
            throw new InvalidDataException("SOURCE full collision bounds differ from the shipped profile");
        var cells = new StringBuilder(collision.CellsX * collision.CellsY);
        for (int y = 0; y < collision.CellsY; y++)
            for (int x = 0; x < collision.CellsX; x++) cells.Append(collision[x, y] ? '1' : '0');
        return new { @event = "full-bake-terrain", origin = new[] { level.SolidTiles.X, level.SolidTiles.Y },
            dimensions = new[] { collision.CellsX, collision.CellsY }, cells = cells.ToString(), seed = terrain.LoadSeed };
    }
}
