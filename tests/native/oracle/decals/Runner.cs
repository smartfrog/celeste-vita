using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Monocle;
using Celeste;
using DecalOracle;

static class Runner
{
    sealed record Instance(string Group, int Index, string Texture, float X, float Y, float ScaleX, float ScaleY, int Depth);

    static string Bits(float value) => BitConverter.SingleToUInt32Bits(value).ToString("x8");

    static string NormalizedName(string texture)
    {
        string extension = Path.GetExtension(texture);
        string input = Path.Combine("decals", texture.Replace(extension, "")).Replace('\\', '/');
        return System.Text.RegularExpressions.Regex.Replace(input, "\\d+$", string.Empty);
    }

    static List<Instance> LoadRoom(string path)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        var root = document.RootElement;
        if (root.GetProperty("name").GetString() != "level") throw new Exception("Raw room root is not the level element");
        var result = new List<Instance>();
        foreach (var groupName in new[] { "fgdecals", "bgdecals" })
        {
            var group = root.GetProperty("children").EnumerateArray()
                .Single(child => child.GetProperty("name").GetString() == groupName);
            int index = 0;
            foreach (var child in group.GetProperty("children").EnumerateArray())
            {
                if (child.GetProperty("name").GetString() != "decal") throw new Exception("Unexpected decal child element");
                var attributes = child.GetProperty("attributes");
                var keys = attributes.EnumerateObject().Select(property => property.Name).OrderBy(name => name).ToArray();
                if (!keys.SequenceEqual(new[] { "scaleX", "scaleY", "texture", "x", "y" }))
                    throw new Exception("Decal attributes differ from the source LevelData field set: " + groupName + " " + index);
                result.Add(new Instance(groupName, index, attributes.GetProperty("texture").GetString(),
                                        attributes.GetProperty("x").GetSingle(), attributes.GetProperty("y").GetSingle(),
                                        attributes.GetProperty("scaleX").GetSingle(), attributes.GetProperty("scaleY").GetSingle(),
                                        groupName == "fgdecals" ? -10500 : 9000));
                index++;
            }
        }
        return result;
    }

    static void LoadAtlas(string path)
    {
        using var document = JsonDocument.Parse(File.ReadAllText(path));
        foreach (var entry in document.RootElement.EnumerateObject())
        {
            var fields = entry.Value.EnumerateArray().ToArray();
            string sheet = fields[0].GetString();
            if (sheet != "Gameplay0") throw new Exception("Decal source sheet changed: " + sheet);
            GFX.Game.AddMetadata(entry.Name, sheet, fields.Skip(1).Select(value => value.GetInt32()).ToArray());
        }
    }

    static List<MTexture> Textures(Decal decal) =>
        (List<MTexture>)typeof(Decal).GetField("textures", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(decal);

    static float Frame(Decal decal) =>
        (float)typeof(Decal).GetField("frame", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(decal);

    static (float x, float y, float u, float v) FnaCorner(Vector2 position, Vector2 origin, Vector2 scale, Rectangle clip, int cornerX, int cornerY)
    {
        float sourceX = (float)clip.X / 4096f;
        float sourceY = (float)clip.Y / 4096f;
        float sourceW = (float)Math.Sign(clip.Width) * Math.Max(Math.Abs(clip.Width), MathHelper.MachineEpsilonFloat) / 4096f;
        float sourceH = (float)Math.Sign(clip.Height) * Math.Max(Math.Abs(clip.Height), MathHelper.MachineEpsilonFloat) / 4096f;
        float destinationW = scale.X * clip.Width;
        float destinationH = scale.Y * clip.Height;
        float originX = origin.X / sourceW / 4096f;
        float originY = origin.Y / sourceH / 4096f;
        float num = (cornerX - originX) * destinationW;
        float num2 = (cornerY - originY) * destinationH;
        return (num + position.X, num2 + position.Y, cornerX * sourceW + sourceX, cornerY * sourceH + sourceY);
    }

    static void SameBits(float actual, float expected, string label)
    {
        if (BitConverter.SingleToUInt32Bits(actual) != BitConverter.SingleToUInt32Bits(expected))
            throw new Exception($"{label} differs: {actual:R} != {expected:R}");
    }

    static object VerifyStatic(Instance instance, Decal decal, MTexture texture, int calls)
    {
        if (calls != 0) throw new Exception("Static DecalImage construction/Added consumed shared RNG: " + instance.Group + " " + instance.Index);
        if (texture.AtlasPath != decal.Name) throw new Exception("Decal singleton family identity changed");
        if (decal.Depth != instance.Depth) throw new Exception("Decal depth differs from source Level.cs depth");
        Draw.SpriteBatch.Calls.Clear();
        Draw.SpriteBatch.Geometry.Calls.Clear();
        decal.Render();
        if (Draw.SpriteBatch.Calls.Count != 1 || Draw.SpriteBatch.Geometry.Calls.Count != 1)
            throw new Exception("Static DecalImage did not execute exactly one original draw");
        if (calls != 0) throw new Exception("Static DecalImage render consumed RNG");
        var draw = Draw.SpriteBatch.Calls[0];
        var vertices = Draw.SpriteBatch.Geometry.Calls[0];
        if (!Equals(draw.Texture, texture.Texture.Texture)) throw new Exception("DecalImage drew an unexpected source MTexture");
        if (draw.Position != new Vector2(instance.X, instance.Y)) throw new Exception("DecalImage position changed");
        if (draw.Clip.X != texture.ClipRect.X || draw.Clip.Y != texture.ClipRect.Y ||
            draw.Clip.Width != texture.ClipRect.Width || draw.Clip.Height != texture.ClipRect.Height)
            throw new Exception("DecalImage source clip changed");
        if (draw.Origin != texture.Center - texture.DrawOffset) throw new Exception("DecalImage origin is not Center-DrawOffset");
        if (draw.Scale != new Vector2(instance.ScaleX, instance.ScaleY)) throw new Exception("DecalImage signed scale changed");
        if (draw.Rotation != 0f || draw.Effects != SpriteEffects.None) throw new Exception("DecalImage rotation/effects changed");
        if (draw.Color != Color.White) throw new Exception("DecalImage color is not source White");
        var corners = new[]
        {
            FnaCorner(draw.Position, draw.Origin, draw.Scale, draw.Clip, 0, 0),
            FnaCorner(draw.Position, draw.Origin, draw.Scale, draw.Clip, 1, 0),
            FnaCorner(draw.Position, draw.Origin, draw.Scale, draw.Clip, 0, 1),
            FnaCorner(draw.Position, draw.Origin, draw.Scale, draw.Clip, 1, 1)
        };
        SameBits(vertices.Position0.X, corners[0].x, "p0x"); SameBits(vertices.Position0.Y, corners[0].y, "p0y");
        SameBits(vertices.Position1.X, corners[1].x, "p1x"); SameBits(vertices.Position1.Y, corners[1].y, "p1y");
        SameBits(vertices.Position2.X, corners[2].x, "p2x"); SameBits(vertices.Position2.Y, corners[2].y, "p2y");
        SameBits(vertices.Position3.X, corners[3].x, "p3x"); SameBits(vertices.Position3.Y, corners[3].y, "p3y");
        SameBits(vertices.TextureCoordinate0.X, corners[0].u, "tc0u"); SameBits(vertices.TextureCoordinate0.Y, corners[0].v, "tc0v");
        SameBits(vertices.TextureCoordinate1.X, corners[1].u, "tc1u"); SameBits(vertices.TextureCoordinate1.Y, corners[1].v, "tc1v");
        SameBits(vertices.TextureCoordinate2.X, corners[2].u, "tc2u"); SameBits(vertices.TextureCoordinate2.Y, corners[2].v, "tc2v");
        SameBits(vertices.TextureCoordinate3.X, corners[3].u, "tc3u"); SameBits(vertices.TextureCoordinate3.Y, corners[3].v, "tc3v");
        return new
        {
            group = instance.Group, source_index = instance.Index, name = decal.Name, texture = instance.Texture,
            behavior = "DecalImage", depth = decal.Depth,
            atlas_clip = new[] { draw.Clip.X, draw.Clip.Y, draw.Clip.Width, draw.Clip.Height },
            frame = new[] { texture.Width, texture.Height },
            draw_offset = new[] { texture.DrawOffset.X, texture.DrawOffset.Y },
            center = new[] { texture.Center.X, texture.Center.Y },
            origin = new[] { texture.Center.X - texture.DrawOffset.X, texture.Center.Y - texture.DrawOffset.Y },
            position = new[] { instance.X, instance.Y },
            scale = new[] { instance.ScaleX, instance.ScaleY },
            position_bits = new[] { Bits(draw.Position.X), Bits(draw.Position.Y) },
            origin_bits = new[] { Bits(draw.Origin.X), Bits(draw.Origin.Y) },
            scale_bits = new[] { Bits(draw.Scale.X), Bits(draw.Scale.Y) },
            rotation_bits = Bits(draw.Rotation),
            effects = (int)draw.Effects,
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
            rng_next_calls = calls
        };
    }

    static object VerifyBanner(Instance instance, Decal decal, MTexture texture, int calls)
    {
        if (calls != 1) throw new Exception("Banner sineTimer field initializer did not consume exactly one NextFloat");
        if (texture.AtlasPath != decal.Name) throw new Exception("Banner singleton family identity changed");
        return new
        {
            group = instance.Group, source_index = instance.Index, name = decal.Name, texture = instance.Texture,
            behavior = "Banner", depth = decal.Depth, component = "Banner", static_draws = 0,
            frame = new[] { texture.Width, texture.Height },
            rng_next_calls = calls,
            rng_maximums = new[] { 0 },
            exclusion = "Explicitly rejected from the static 22 profile; time-driven sine slices are not frozen or rendered"
        };
    }

    static void Main(string[] args)
    {
        if (args.Length != 3) throw new Exception("usage: Runner raw-room.json atlas.json output-directory");
        GFX.Game = new Atlas();
        LoadAtlas(args[1]);
        var instances = LoadRoom(args[0]);
        if (instances.Count != 29) throw new Exception("Selected room decal instance count changed");
        var staticDraws = new List<object>();
        var bannerAttempts = new List<object>();
        var textureNames = new HashSet<string>();
        foreach (var instance in instances)
        {
            var rng = new TracedRandom(49);
            Calc.Random = rng;
            rng.ResetTrace();
            var scene = new Scene();
            var decal = new Decal(instance.Texture, new Vector2(instance.X, instance.Y),
                                  new Vector2(instance.ScaleX, instance.ScaleY), instance.Depth);
            if (decal.Name != NormalizedName(instance.Texture)) throw new Exception("Decal name normalization changed");
            decal.Added(scene);
            if (decal.Components.Count != 1) throw new Exception("Decal.Added did not add exactly one component");
            var textures = Textures(decal);
            if (textures.Count != 1) throw new Exception("Decal source family is not a single frame");
            var component = decal.Components[0].GetType().Name;
            if (component != "DecalImage" && component != "Banner")
                throw new Exception("Decal.Added selected an unexpected component: " + component);
            int calls = rng.NextCalls;
            if (component == "DecalImage")
            {
                decal.Update();
                if (rng.NextCalls != 0 || Frame(decal) != 0f) throw new Exception("Static DecalImage advanced a frame or consumed RNG");
                staticDraws.Add(VerifyStatic(instance, decal, textures[0], calls));
                textureNames.Add(decal.Name);
            }
            else
            {
                bannerAttempts.Add(VerifyBanner(instance, decal, textures[0], calls));
            }
        }
        var staticKeys = staticDraws.Select(draw => (ValueTuple<string, int>)(
            (string)draw.GetType().GetProperty("group").GetValue(draw), (int)draw.GetType().GetProperty("source_index").GetValue(draw))).ToHashSet();
        var bannerKeys = bannerAttempts.Select(draw => (ValueTuple<string, int>)(
            (string)draw.GetType().GetProperty("group").GetValue(draw), (int)draw.GetType().GetProperty("source_index").GetValue(draw))).ToHashSet();
        var expectedStatic = new HashSet<(string, int)>();
        expectedStatic.Add(("fgdecals", 0)); expectedStatic.Add(("fgdecals", 1));
        for (int index = 0; index < 20; index++) expectedStatic.Add(("bgdecals", index));
        var expectedBanner = new HashSet<(string, int)> { ("fgdecals", 2), ("fgdecals", 3) };
        for (int index = 20; index < 25; index++) expectedBanner.Add(("bgdecals", index));
        if (!staticKeys.SetEquals(expectedStatic) || !bannerKeys.SetEquals(expectedBanner))
            throw new Exception("Unchanged Decal.Added classification differs from the pinned 22 static / 7 banner split");
        if (textureNames.Count != 15) throw new Exception("Static unique texture count changed");
        var result = new
        {
            status = "source-static-decals-executed",
            room = new
            {
                level = "lvl_1", bounds = new[] { 0, 0, 320, 184 },
                creation_order = new[] { "fgdecals", "bgdecals" },
                decal_order = instances.Select(instance => new { group = instance.Group, index = instance.Index, depth = instance.Depth })
            },
            static_profile = new
            {
                count = staticDraws.Count, bg = staticKeys.Count(key => key.Item1 == "bgdecals"),
                fg = staticKeys.Count(key => key.Item1 == "fgdecals"), unique_textures = textureNames.Count,
                unique_texture_names = textureNames.OrderBy(name => name),
                rng = new { next_calls = 0, note = "No shared Random call in any static ctor/Added/Update/Render; not whole-Level RNG parity" },
                draws = staticDraws
            },
            banner_exclusion = new
            {
                count = bannerAttempts.Count,
                attempts = bannerAttempts,
                rng = new { next_calls = 7, note = "Seven sineTimer field initializers execute in isolated classification runs; shared prefix/phase remains unproven and no banner is frozen or drawn" }
            },
            surface = new
            {
                method = "Unchanged Celeste.Decal ctor/Added/Update/Render and DecalImage.Render executed with original Monocle MTexture/Atlas lookup, bundled mscorlib Random, and FNA GenerateVertexInfo",
                static_component = "DecalImage", banner_component = "Banner",
                no_parallax = true, no_scared_animal = true, no_mirror = true, no_smoke = true,
                no_banner_render = true, no_rng_phase_claim = true
            },
            claim = "Narrow unchanged-source static DecalImage execution for the 22 source-proven instances; 7 Banner instances explicitly classified and omitted; not full game/engine execution"
        };
        Directory.CreateDirectory(args[2]);
        File.WriteAllText(Path.Combine(args[2], "decals-oracle.json"),
                          JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine($"STATIC DECAL SOURCE EXECUTED: {staticDraws.Count} images ({textureNames.Count} unique), {bannerAttempts.Count} banners explicitly omitted");
    }
}
