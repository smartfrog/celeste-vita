using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Text.Json;
using System.Xml;
using Celeste;
using Microsoft.Xna.Framework;
using Monocle;
using VisualOracle;

internal static class Program
{
    private static object Field(object owner, string name) => owner.GetType().GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance).GetValue(owner);

    private static object Describe(Autotiler autotiler, VirtualMap<char> chars, TileAssignment command, bool padding)
    {
        var behaviour = new Autotiler.Behaviour { EdgesExtend = true, PaddingIgnoreOutOfLevel = padding };
        object tiles = typeof(Autotiler).GetMethod("TileHandler", BindingFlags.NonPublic | BindingFlags.Instance)
            .Invoke(autotiler, new object[] { chars, command.x, command.y, Rectangle.Empty, '0', behaviour });
        object terrain = ((IDictionary)Field(autotiler, "lookup"))[chars[command.x, command.y]];
        string rule;
        if (ReferenceEquals(tiles, Field(terrain, "Center"))) rule = "center";
        else if (ReferenceEquals(tiles, Field(terrain, "Padded"))) rule = "padding";
        else
        {
            object masked = ((IEnumerable)Field(terrain, "Masked")).Cast<object>().Single(item => ReferenceEquals(Field(item, "Tiles"), tiles));
            rule = string.Concat(((byte[])Field(masked, "Mask")).Select(value => value == 2 ? 'x' : (char)('0' + value)));
        }
        var textures = (List<MTexture>)Field(tiles, "Textures");
        return new { command.layer, command.x, command.y, character = chars[command.x, command.y].ToString(), rule,
            rng = command.rng, variant = textures.IndexOf(command.Texture), source = command.Texture.Name,
            rectangle = new[] { command.Texture.X, command.Texture.Y, command.Texture.Width, command.Texture.Height } };
    }

    private static string Cells(VirtualMap<char> chars)
    {
        var cells = new StringBuilder(chars.Columns * chars.Rows);
        for (int y = 0; y < chars.Rows; y++) for (int x = 0; x < chars.Columns; x++) cells.Append(chars[x, y]);
        return cells.ToString();
    }

    private static int Main(string[] args)
    {
        if (args.Length != 4) throw new ArgumentException("Expected driver, atlas metadata JSON, content directory, output directory");
        string output = args[3];
        Engine.Instance.Content.RootDirectory = args[2];
        using var atlas = JsonDocument.Parse(File.ReadAllText(args[1]));
        foreach (var entry in atlas.RootElement.EnumerateObject())
        {
            var values = entry.Value;
            if (values[5].GetInt32() != 0 || values[6].GetInt32() != 0)
            {
                if (entry.Name.StartsWith("tilesets/")) throw new ArgumentException("Trimmed tileset needs source MTexture closure");
            }
            GFX.Game.Add(entry.Name, new(entry.Name, values[1].GetInt32(), values[2].GetInt32(), values[7].GetInt32(), values[8].GetInt32()));
        }
        GFX.BGAutotiler = new("BackgroundTiles.xml");
        GFX.FGAutotiler = new("ForegroundTiles.xml");
        var animations = new XmlDocument();
        animations.Load(Path.Combine(args[2], "AnimatedTiles.xml"));
        foreach (XmlElement element in animations.GetElementsByTagName("sprite"))
        {
            string prefix = element.GetAttribute("path");
            var frames = GFX.Game.Where(pair => pair.Key.StartsWith(prefix)).OrderBy(pair => pair.Key, StringComparer.Ordinal).Select(pair => pair.Value).ToList();
            if (frames.Count == 0) throw new ArgumentException("Missing overlay animation frames");
            GFX.AnimatedTilesBank.Add(element.GetAttribute("name"), 0, default, default, frames);
        }
        using var document = JsonDocument.Parse(File.ReadAllText(args[0]));
        var driver = document.RootElement;
        var map = new MapData();
        foreach (var room in driver.GetProperty("levels").EnumerateArray())
        {
            var data = new BinaryPacker.Element();
            foreach (string key in new[] { "name", "x", "y", "width", "height" })
                data.Attributes.Add(key, key == "name" ? room.GetProperty(key).GetString() : room.GetProperty(key).GetInt32());
            map.Levels.Add(new(data) { Solids = room.GetProperty("solids").GetString(), Bg = room.GetProperty("bg").GetString() });
        }
        foreach (var rect in driver.GetProperty("filler").EnumerateArray())
            map.Filler.Add(new(rect.GetProperty("x").GetInt32(), rect.GetProperty("y").GetInt32(), rect.GetProperty("w").GetInt32(), rect.GetProperty("h").GetInt32()));
        map.ComputeBounds();
        var layers = new MaskLoader().Build(map);
        string foreground = Cells(layers.Foreground), background = Cells(layers.Background);
        File.WriteAllText(Path.Combine(output, "layers.json"), JsonSerializer.Serialize(new {
            origin = new[] { (int)layers.Position.X, (int)layers.Position.Y }, columns = layers.Foreground.Columns, rows = layers.Foreground.Rows,
            foreground, background, bounds = GFX.FGAutotiler.LevelBounds.Select(r => new[] { r.X, r.Y, r.Width, r.Height }).ToArray() }));
        Trace.Enabled = true;
        Trace.Layer = "BG";
        Calc.PushRandom(map.LoadSeed);
        var bg = GFX.BGAutotiler.GenerateMap(layers.Background, false);
        int bgCalls = Trace.Calls.Count;
        Trace.Layer = "FG";
        Trace.X = Trace.Y = -1;
        var fg = GFX.FGAutotiler.GenerateMap(layers.Foreground, true);
        Calc.PopRandom();
        Trace.Enabled = false;
        var commands = new List<object>();
        commands.AddRange(bg.TileGrid.Tiles.Commands.Select(c => Describe(GFX.BGAutotiler, layers.Background, c, false)));
        commands.AddRange(fg.TileGrid.Tiles.Commands.Select(c => Describe(GFX.FGAutotiler, layers.Foreground, c, true)));
        File.WriteAllText(Path.Combine(output, "commands.json"), JsonSerializer.Serialize(commands));
        File.WriteAllText(Path.Combine(output, "rng.json"), JsonSerializer.Serialize(Trace.Calls));
        File.WriteAllText(Path.Combine(output, "bake.json"), JsonSerializer.Serialize(new { seed = map.LoadSeed, bgCalls, totalCalls = Trace.Calls.Count,
            bgCommands = bg.TileGrid.Tiles.Commands.Count, fgCommands = fg.TileGrid.Tiles.Commands.Count }));
        Console.WriteLine($"BAKED {layers.Foreground.Columns}x{layers.Foreground.Rows}; seed {map.LoadSeed}; BG {bg.TileGrid.Tiles.Commands.Count}, FG {fg.TileGrid.Tiles.Commands.Count}; {Trace.Calls.Count} RNG calls");
        return 0;
    }
}
