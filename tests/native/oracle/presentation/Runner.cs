using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using System.Xml;
using Microsoft.Xna.Framework;
using Monocle;
using Celeste;

static class Runner
{
    static readonly string[] Ids = "idle idleA idleB idleC runSlow runFast runStumble flip skid jumpSlow jumpFast fallSlow fallFast duck edge edgeBack push lookUp climbUp climbLookBackStart climbLookBack dangling wallslide dash".Split(' ');

    static void Main(string[] args)
    {
        GFX.Game = new Atlas();
        using var atlas = JsonDocument.Parse(File.ReadAllText(args[0]));
        foreach (var entry in atlas.RootElement.EnumerateObject())
        {
            var fields = entry.Value.EnumerateArray().ToArray();
            GFX.Game.AddMetadata(entry.Name, fields[0].GetString(), fields.Skip(1).Select(value => value.GetInt32()).ToArray());
        }
        var xml = new XmlDocument(); xml.Load(args[1]);
        GFX.SpriteBank = new SpriteBank(GFX.Game, xml);
        PlayerSprite.CreateFramesMetadata("player");
        if (args.Length == 5) { Replay.Run(args[3], args[4]); return; }
        ExportBank(args[2]);
        Calc.Random = new PresentationOracle.TracedRandom(0);
        var scene = new Level();
        scene.PointProbe = (type, position) => type == typeof(Solid) && position.Y >= 160;
        scene.BodyProbe = (type, position) => type == typeof(Solid) && position.Y > 160;
        var player = new Player(new Vector2(20, 160), scene) { onGround = true };
        var trace = new List<object>();
        for (int tick = 0; tick < 360; tick++)
        {
            Engine.RawDeltaTime = Engine.DeltaTime = 1f / 60f;
            scene.TimeActive += Engine.DeltaTime;
            player.Preamble(); player.Hair.Update(); player.Sprite.Update();
            if (tick >= 30 && tick < 90) { player.Speed = new Vector2(90, 0); player.moveX = 1; player.Position.X += 1.5f; }
            else { player.Speed = Vector2.Zero; player.moveX = 0; }
            player.Select(); player.UpdateHair(true); player.Hair.AfterUpdate(); player.RenderBounded();
            trace.Add(player.Inspect());
        }
        if (player.Sprite.HairCount != 4 || Draw.SpriteBatch.Calls.Count == 0) throw new Exception("Body/hair did not execute");
        File.WriteAllText(Path.Combine(args[2], "gate-trace.json"), JsonSerializer.Serialize(trace));
        File.WriteAllText(Path.Combine(args[2], "gate-result.json"), JsonSerializer.Serialize(new
        {
            status = "unchanged-body-and-hair-source-executed", diagnosticSeed = 0, originalStartupRngParity = false,
            ticks = trace.Count, recordedDraws = Draw.SpriteBatch.Calls.Count, current = player.Inspect(),
            sourceLocalMathAssembly = typeof(Vector2).Assembly.FullName
        }));
    }

    static void ExportBank(string output)
    {
        var sprite = new PlayerSprite(PlayerSpriteMode.Madeline);
        var animations = (IDictionary)typeof(Sprite).GetField("animations", BindingFlags.NonPublic | BindingFlags.Instance).GetValue(sprite);
        var names = new Dictionary<string, object>();
        void Frame(MTexture texture)
        {
            sprite.Texture = texture;
            names[texture.AtlasPath] = new
            {
                name = texture.AtlasPath,
                rectangle = new[] { texture.ClipRect.X, texture.ClipRect.Y, texture.ClipRect.Width, texture.ClipRect.Height },
                trim = new[] { texture.DrawOffset.X, texture.DrawOffset.Y }, size = new[] { texture.Width, texture.Height },
                hairOffset = new[] { sprite.HairOffset.X, sprite.HairOffset.Y }, hairFrame = sprite.HairFrame, hasHair = sprite.HasHair
            };
        }
        var exported = new List<object>();
        foreach (var id in Ids)
        {
            object animation = animations[id];
            var type = animation.GetType();
            var frames = (MTexture[])type.GetField("Frames").GetValue(animation);
            foreach (var frame in frames) Frame(frame);
            var next = (Chooser<string>)type.GetField("Goto").GetValue(animation);
            if (next != null && next.Count != 1) throw new Exception("Unexpected reachable weighted goto");
            exported.Add(new { id, delay = (float)type.GetField("Delay").GetValue(animation), next = next == null ? "" : next[0], frames = frames.Select(frame => frame.AtlasPath).ToArray() });
        }
        var bangs = GFX.Game.GetAtlasSubtextures("characters/player/bangs");
        foreach (var frame in bangs) Frame(frame);
        Frame(GFX.Game["characters/player/hair00"]);
        File.WriteAllText(Path.Combine(output, "bank.json"), JsonSerializer.Serialize(new
        {
            mode = "Madeline", bank = "player", hairCount = sprite.HairCount, origin = new[] { 16, 32 },
            frames = names.Values, animations = exported, bangs = bangs.Select(frame => frame.AtlasPath).ToArray(), hair = "characters/player/hair00"
        }));
    }
}
