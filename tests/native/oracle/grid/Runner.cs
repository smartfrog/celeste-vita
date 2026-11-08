using System;
using System.IO;
using System.Text;
using System.Text.Json;
using Celeste;
using Microsoft.Xna.Framework;
using Monocle;

internal static class GridOracle
{
    public static int Mask(string input, string output)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(input));
        File.WriteAllText(output, BuildMask(document.RootElement));
        return 0;
    }

    public static int MaskCases(string input, string output)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(input));
        using var writer = new StreamWriter(output);
        foreach (var driver in document.RootElement.GetProperty("cases").EnumerateArray())
        {
            string[] mask = BuildMask(driver).Split('\n');
            string[] geometry = mask[3].Split(' ');
            int x = int.Parse(geometry[0]), y = int.Parse(geometry[1]), columns = int.Parse(geometry[2]), rows = int.Parse(geometry[3]);
            for (int row = 0; row < rows; row++)
                writer.WriteLine(string.Join("\t", driver.GetProperty("case").GetString(), row, x, y + row * 8, columns, mask[4].Substring(row * columns, columns)));
        }
        return 0;
    }

    private static string BuildMask(JsonElement driver)
    {
        var map = new MapData();
        foreach (var room in driver.GetProperty("levels").EnumerateArray())
        {
            var data = new BinaryPacker.Element();
            foreach (string key in new[] { "name", "x", "y", "width", "height" })
                data.Attributes.Add(key, key == "name" ? room.GetProperty(key).GetString() : room.GetProperty(key).GetInt32());
            map.Levels.Add(new LevelData(data) { Solids = room.GetProperty("solids").GetString(), Bg = room.GetProperty("bg").GetString() });
        }
        foreach (var rect in driver.GetProperty("filler").EnumerateArray())
            map.Filler.Add(new Rectangle(rect.GetProperty("x").GetInt32(), rect.GetProperty("y").GetInt32(), rect.GetProperty("w").GetInt32(), rect.GetProperty("h").GetInt32()));
        map.ComputeBounds();
        var chars = new MaskLoader().Build(map);
        var tiles = new SolidTiles(chars);
        var cells = new StringBuilder();
        for (int y = 0; y < chars.Rows; y++) for (int x = 0; x < chars.Columns; x++) cells.Append(tiles.Grid[x, y] ? '1' : '0');
        var bounds = map.TileBounds;
        string text = $"CSTM1\nfd73f8a2311fa5737ded550cbad4b75c85b7686b36432f59185e940fcb65fcfe\nace1892261c03aa766f45aaa38cb2cd60a8823c34eda673f5b2ed8ab31c890ab\n{bounds.X * 8} {bounds.Y * 8} {chars.Columns} {chars.Rows}\n{cells}\n";
        return text;
    }
}
