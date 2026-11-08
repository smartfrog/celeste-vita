using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Monocle;
using Celeste;

static class GeometryRunner
{
    static string Bits(float value) => BitConverter.SingleToUInt32Bits(value).ToString("x8");

    static void Main(string[] args)
    {
        GFX.Game = new Atlas();
        using var atlas = JsonDocument.Parse(File.ReadAllText(args[0]));
        foreach (var entry in atlas.RootElement.EnumerateObject())
        {
            var fields = entry.Value.EnumerateArray().ToArray();
            GFX.Game.AddMetadata(entry.Name, fields[0].GetString(), fields.Skip(1).Select(value => value.GetInt32()).ToArray());
        }
        using var bank = JsonDocument.Parse(File.ReadAllText(args[1]));
        var idle = bank.RootElement.GetProperty("animations").EnumerateArray().Single(animation => animation.GetProperty("id").GetString() == "idle");
        var names = new[] { idle.GetProperty("frames")[0].GetString(), bank.RootElement.GetProperty("bangs")[0].GetString(), bank.RootElement.GetProperty("hair").GetString() };
        int index = 0;
        foreach (int facing in new[] { -1, 1 })
        foreach (float rotation in new[] { 0f, 0.37f })
        for (int role = 0; role < names.Length; role++)
        {
            var scale = role == 0 ? new Vector2(facing * 0.6f, 1.4f) : role == 1 ? new Vector2(facing * 0.6f, 1) : new Vector2(0.375f, 0.625f);
            GFX.Game[names[role]].Draw(new Vector2(20.75f, -5.125f), role == 0 ? new Vector2(16, 32) : new Vector2(5, 5),
                                      role == 0 ? Color.White : new Color(172, 50, 50), scale, rotation, SpriteEffects.None);
            var draw = Draw.SpriteBatch.Calls[index];
            Console.WriteLine(string.Join("\t", new object[] { "D", "geometry", 1, index, draw.Texture,
                Bits(draw.Position.X), Bits(draw.Position.Y), Bits(draw.Origin.X), Bits(draw.Origin.Y), Bits(draw.Scale.X), Bits(draw.Scale.Y), Bits(draw.Rotation),
                (int)draw.Color.R, (int)draw.Color.G, (int)draw.Color.B, (int)draw.Color.A, (int)draw.Effects }));
            var vertices = Draw.SpriteBatch.Geometry.Calls[index];
            Console.WriteLine(string.Join("\t", new object[] { "V", "geometry", 1, index,
                Bits(vertices.Position0.X), Bits(vertices.Position0.Y), Bits(vertices.Position1.X), Bits(vertices.Position1.Y),
                Bits(vertices.Position3.X), Bits(vertices.Position3.Y), Bits(vertices.Position2.X), Bits(vertices.Position2.Y) }));
            index++;
        }
    }
}
