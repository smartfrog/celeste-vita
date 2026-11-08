using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Monocle;
using Celeste;
using SpikeOracle;

static class Runner
{
    sealed record Hazard(string Direction, int X, int Y, int Size);
    sealed record RunResult(int Seed, int Prefix, List<object> Hazards, int Draws, List<object> Pieces,
                            int NextCalls, List<int> NextMaximums, List<int> Results);

    static string Bits(float value) => BitConverter.SingleToUInt32Bits(value).ToString("x8");
    static int Exact(float value, string name)
    {
        int rounded = (int)MathF.Round(value);
        if (MathF.Abs(value - rounded) > 0.00001f) throw new Exception("Nonintegral " + name + ": " + value);
        return rounded;
    }

    static Dictionary<string, int[]> LoadAtlas(string path)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        foreach (var entry in document.RootElement.EnumerateObject())
        {
            var fields = entry.Value.EnumerateArray().ToArray();
            string sheet = fields[0].GetString();
            if (sheet != "Gameplay0") throw new Exception("Spike source sheet changed: " + sheet);
            GFX.Game.AddMetadata(entry.Name, sheet, fields.Skip(1).Select(value => value.GetInt32()).ToArray());
        }
        return document.RootElement.EnumerateObject().ToDictionary(entry => entry.Name,
            entry => entry.Value.EnumerateArray().Skip(1).Select(value => value.GetInt32()).ToArray());
    }

    static List<Hazard> LoadHazards(string path)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        return document.RootElement.EnumerateArray().Select(entry => new Hazard(
            entry.GetProperty("direction").GetString(), entry.GetProperty("x").GetInt32(),
            entry.GetProperty("y").GetInt32(), entry.GetProperty("size").GetInt32())).ToList();
    }

    static Spikes.Directions Direction(string direction) => direction switch
    {
        "up" => Spikes.Directions.Up,
        "left" => Spikes.Directions.Left,
        _ => throw new Exception("Unsupported selected room spike direction: " + direction)
    };

    static bool SameRect(Rectangle rect, int[] values) =>
        rect.X == values[0] && rect.Y == values[1] && rect.Width == values[2] && rect.Height == values[3];

    static object Family(string key, Dictionary<string, int[]> metadata)
    {
        var textures = GFX.Game.GetAtlasSubtextures(key);
        if (textures.Count != 1) throw new Exception("Spike family is not a singleton: " + key + " count=" + textures.Count);
        var texture = textures[0];
        string expected = key + "00";
        if (texture.AtlasPath != expected) throw new Exception("Unexpected singleton family identity: " + texture.AtlasPath);
        if (!metadata.TryGetValue(expected, out var rectangle)) throw new Exception("Missing pinned atlas metadata: " + expected);
        if (!SameRect(texture.ClipRect, rectangle) || texture.Width != rectangle[6] || texture.Height != rectangle[7] ||
            texture.DrawOffset.X != -rectangle[4] || texture.DrawOffset.Y != -rectangle[5])
            throw new Exception("Singleton family does not match pinned atlas metadata: " + expected);
        return new { key, count = textures.Count, entry = expected,
                     rectangle = rectangle.Take(4).ToArray(), trim = new[] { rectangle[4], rectangle[5] },
                     frame = new[] { rectangle[6], rectangle[7] },
                     draw_offset = new[] { texture.DrawOffset.X, texture.DrawOffset.Y },
                     clip = new[] { texture.ClipRect.X, texture.ClipRect.Y, texture.ClipRect.Width, texture.ClipRect.Height } };
    }

    static RunResult Run(int seed, int prefix, List<Hazard> hazards, bool recordPieces)
    {
        var rng = new TracedRandom(seed);
        Calc.Random = rng;
        for (int i = 0; i < prefix; i++) rng.Next(1);
        rng.ResetTrace();
        var scene = new Scene();
        var hazardsRecord = new List<object>();
        var pieces = new List<object>();
        int hazardIndex = 0;
        foreach (var hazard in hazards)
        {
            var spikes = new Spikes(new Vector2(hazard.X, hazard.Y), hazard.Size, Direction(hazard.Direction), "default");
            if (spikes.Depth != -1) throw new Exception("Spike depth is not source -1");
            if (spikes.Direction != Direction(hazard.Direction)) throw new Exception("Spike direction changed");
            if (spikes.Collider == null) throw new Exception("Spike collider missing");
            bool colliderMatches = hazard.Direction == "up"
                ? spikes.Collider.Width == hazard.Size && spikes.Collider.Height == 3 && spikes.Collider.Offset.X == 0 && spikes.Collider.Offset.Y == -3
                : spikes.Collider.Width == 3 && spikes.Collider.Height == hazard.Size && spikes.Collider.Offset.X == -3 && spikes.Collider.Offset.Y == 0;
            if (!colliderMatches) throw new Exception("Spike source collider physics changed");
            spikes.Added(scene);
            Draw.SpriteBatch.Calls.Clear();
            Draw.SpriteBatch.Geometry.Calls.Clear();
            spikes.Render();
            var images = spikes.Components.OfType<Image>().ToList();
            if (images.Count != hazard.Size / 8 || images.Count != Draw.SpriteBatch.Calls.Count)
                throw new Exception("Spike image count differs from size/8 source pieces");
            for (int index = 0; index < images.Count; index++)
            {
                var draw = Draw.SpriteBatch.Calls[index];
                var vertices = Draw.SpriteBatch.Geometry.Calls[index];
                int x = Exact(vertices.Position0.X, "x");
                int y = Exact(vertices.Position0.Y, "y");
                int width = Exact(vertices.Position1.X - vertices.Position0.X, "width");
                int height = Exact(vertices.Position3.Y - vertices.Position0.Y, "height");
                if (width != draw.Clip.Width || height != draw.Clip.Height)
                    throw new Exception("Spike source clip and destination size differ");
                if (draw.Scale.X != 1f || draw.Scale.Y != 1f || draw.Rotation != 0f ||
                    draw.Effects != Microsoft.Xna.Framework.Graphics.SpriteEffects.None)
                    throw new Exception("Spike image unexpectedly scaled/rotated/flipped");
                if (recordPieces)
                {
                    pieces.Add(new
                    {
                        direction = hazard.Direction, hazard = hazardIndex, index,
                        texture = ((Microsoft.Xna.Framework.Graphics.Texture2D)draw.Texture).Name,
                        clip = new[] { draw.Clip.X, draw.Clip.Y, draw.Clip.Width, draw.Clip.Height },
                        position_bits = new[] { Bits(draw.Position.X), Bits(draw.Position.Y) },
                        origin_bits = new[] { Bits(draw.Origin.X), Bits(draw.Origin.Y) },
                        scale_bits = new[] { Bits(draw.Scale.X), Bits(draw.Scale.Y) },
                        rotation_bits = Bits(draw.Rotation),
                        vertices_bits = new[]
                        {
                            Bits(vertices.Position0.X), Bits(vertices.Position0.Y), Bits(vertices.Position1.X), Bits(vertices.Position1.Y),
                            Bits(vertices.Position2.X), Bits(vertices.Position2.Y), Bits(vertices.Position3.X), Bits(vertices.Position3.Y)
                        },
                        texcoords_bits = new[]
                        {
                            Bits(vertices.TextureCoordinate0.X), Bits(vertices.TextureCoordinate0.Y),
                            Bits(vertices.TextureCoordinate1.X), Bits(vertices.TextureCoordinate1.Y),
                            Bits(vertices.TextureCoordinate2.X), Bits(vertices.TextureCoordinate2.Y),
                            Bits(vertices.TextureCoordinate3.X), Bits(vertices.TextureCoordinate3.Y)
                        },
                        x, y, width, height
                    });
                }
            }
            hazardsRecord.Add(new { direction = hazard.Direction, position = new[] { hazard.X, hazard.Y }, size = hazard.Size,
                                    depth = spikes.Depth, pieces = images.Count,
                                    collider_width = spikes.Collider.Width, collider_height = spikes.Collider.Height,
                                    collider_offset = new[] { spikes.Collider.Offset.X, spikes.Collider.Offset.Y } });
            hazardIndex++;
        }
        if (rng.NextCalls != 19 || rng.NextMaximums.Any(maximum => maximum != 1) || rng.Results.Any(result => result != 0))
            throw new Exception("Original Calc.Random.Choose did not perform 19 Next(1)->0 calls");
        return new RunResult(seed, prefix, hazardsRecord, 19, pieces, rng.NextCalls, rng.NextMaximums, rng.Results);
    }

    static void Main(string[] args)
    {
        GFX.Game = new Atlas();
        var hazards = LoadHazards(args[0]);
        var metadata = LoadAtlas(args[1]);
        if (hazards.Count != 5) throw new Exception("Selected room spike count changed");
        var up = Family("danger/spikes/default_up", metadata);
        var left = Family("danger/spikes/default_left", metadata);
        var runs = new List<RunResult>
        {
            Run(0, 0, hazards, true),
            Run(49, 3, hazards, false),
            Run(12345, 7, hazards, false)
        };
        var first = runs[0];
        var result = new
        {
            status = "source-spike-art-executed",
            area_profile = new { spike = "default", override_type = "default",
                                 source = "Celeste.AreaData.cs:56 default Spike field",
                                 family_keys = new[] { "danger/spikes/default_up", "danger/spikes/default_left" } },
            families = new { up, left },
            hazards = first.Hazards,
            pieces = first.Pieces,
            draws = first.Draws,
            runs = runs.Select(run => new { seed = run.Seed, prefix = run.Prefix, draws = run.Draws,
                                            rng = new { next_calls = run.NextCalls, next_maximums = run.NextMaximums, results = run.Results } }),
            diagnostics = new { traced_random = "unchanged bundled mscorlib System.Random with tracing subclass",
                                choose = "unchanged Monocle.Calc.Choose(List<T>) extension",
                                added = "unchanged Celeste.Spikes.Added body",
                                ctor = "unchanged Celeste.Spikes constructor body with recording physics shims" },
            claim = "Narrow unchanged-source spike constructor/Added/Atlas/Calc/Random/Image/MTexture/FNA vertex proof; not full game or engine execution"
        };
        Directory.CreateDirectory(args[2]);
        File.WriteAllText(Path.Combine(args[2], "spike-oracle.json"), JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
    }
}
