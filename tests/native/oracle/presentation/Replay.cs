using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using Microsoft.Xna.Framework;
using Monocle;
using Celeste;

static class Replay
{
    static string Bits(float value) => BitConverter.SingleToUInt32Bits(value).ToString("x8");
    static float Float(string value) => BitConverter.UInt32BitsToSingle(uint.Parse(value, NumberStyles.HexNumber));
    static T Field<T>(object instance, string name)
    {
        for (Type type = instance.GetType(); type != null; type = type.BaseType)
        {
            var field = type.GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance);
            if (field != null) return (T)field.GetValue(instance);
        }
        throw new Exception("Missing original field: " + name);
    }
    static uint hash;
    static int frames, changes, lasts;
    static void Callback(string kind, string animation)
    {
        foreach (char character in kind + ":" + animation + ";") { hash ^= character; hash *= 16777619; }
    }

    public static void Run(string input, string output)
    {
        Player player = null;
        Level level = null;
        string current = null;
        using var writer = new StreamWriter(output);
        foreach (var line in File.ReadLines(input))
        {
            var fields = line.Split('\t');
            if (fields.Length != 26 || fields[0] != "P") throw new InvalidDataException("Only whitelisted P physics/probe projections are accepted; native visual outputs are forbidden");
            if (fields[1] != current)
            {
                current = fields[1];
                Calc.Random = new PresentationOracle.TracedRandom(0);
                level = new Level();
                player = new Player(new Vector2(Float(fields[5]), Float(fields[6])), level);
                hash = 2166136261; frames = changes = lasts = 0;
                var frame = player.Sprite.OnFrameChange;
                player.Sprite.OnFrameChange = animation => { frames++; Callback("frame", animation + "/" + player.Sprite.CurrentAnimationFrame); frame(animation); };
                var change = player.Sprite.OnChange;
                player.Sprite.OnChange = (old, next) => { changes++; Callback("change", old + ">" + next); change(old, next); };
                var last = player.Sprite.OnLastFrame;
                player.Sprite.OnLastFrame = animation => { lasts++; Callback("last", animation + "/" + player.Sprite.CurrentAnimationFrame); last(animation); };
            }
            Engine.DeltaTime = Engine.RawDeltaTime = Float(fields[4]);
            player.Position = new Vector2(Float(fields[5]), Float(fields[6]));
            player.Speed = new Vector2(Float(fields[7]), Float(fields[8]));
            player.Facing = (Facings)int.Parse(fields[9]); player.StateMachine.State = int.Parse(fields[10]);
            player.moveX = int.Parse(fields[11]); Input.MoveX.Value = int.Parse(fields[12]); Input.MoveY.Value = int.Parse(fields[13]);
            player.lastClimbMove = int.Parse(fields[14]); player.wallSlideDir = int.Parse(fields[15]);
            player.dashAttackTimer = fields[16] == "1" ? 1 : 0; player.Dashes = int.Parse(fields[17]);
            player.onGround = fields[18] == "1"; player.Ducking = fields[19] == "1"; player.IsTired = fields[20] == "1";
            player.DashDir = new Vector2(Float(fields[21]), Float(fields[22]));
            var position = player.Position; var facing = (float)player.Facing;
            var body = new Dictionary<(Type, float, float), bool>();
            var point = new Dictionary<(Type, float, float), bool>();
            void Put(Dictionary<(Type, float, float), bool> probes, Type type, float x, float y, char value)
            {
                var key = (type, position.X + x, position.Y + y); var result = value == '1';
                if (probes.TryGetValue(key, out var previous) && previous != result) throw new Exception("Inconsistent exact native probe");
                probes[key] = result;
            }
            Put(body, typeof(Solid), facing, 6, fields[23][0]); Put(body, typeof(Solid), player.moveX, 0, fields[23][1]);
            Put(point, typeof(Solid), facing, 2, fields[24][0]); Put(point, typeof(Solid), facing * 4, 2, fields[24][1]);
            Put(point, typeof(Solid), -facing, 2, fields[24][2]); Put(point, typeof(Solid), -facing * 4, 2, fields[24][3]);
            Put(body, typeof(JumpThru), facing * 4, 2, fields[25][0]); Put(body, typeof(JumpThru), -facing * 4, 2, fields[25][1]);
            level.BodyProbe = (type, at) => body.TryGetValue((type, at.X, at.Y), out var result) ? result : throw new Exception("Unprovided source full-body probe");
            level.PointProbe = (type, at) => point.TryGetValue((type, at.X, at.Y), out var result) ? result : throw new Exception("Unprovided source point probe");
            switch (fields[3])
            {
                case "scene_tick": level.TimeActive += Engine.DeltaTime; player.PreambleIdle(); break;
                case "ground": player.GroundPhase(); break;
                case "components": player.Hair.Update(); player.Sprite.Update(); break;
                case "duck_turn": case "stand": player.StandPhase(); break;
                case "jump": player.JumpPhase(); break;
                case "duck": player.DuckPhase(); break;
                case "fast_fall": player.FastFallPhase(); break;
                case "landing": player.LandingPhase(); break;
                case "select": player.Select(); break;
                case "hair_color": player.UpdateHair(true); break;
                case "after_update": player.Hair.AfterUpdate(); break;
                case "render": Draw.SpriteBatch.Calls.Clear(); Draw.SpriteBatch.Geometry.Calls.Clear(); player.RenderBounded(); break;
                default: throw new Exception("Unknown source phase " + fields[3]);
            }
            var sprite = player.Sprite; var hair = player.Hair;
            var row = new List<object> { "R", fields[1], fields[2], fields[3], sprite.CurrentAnimationID, sprite.LastAnimationID, sprite.CurrentAnimationFrame, sprite.Texture.AtlasPath,
                Bits(Field<float>(sprite, "animationTimer")), Bits(sprite.Rate), Bits(sprite.Scale.X), Bits(sprite.Scale.Y), Bits(sprite.Rotation), Bits(Field<float>(hair, "wave")),
                Bits(Field<float>(player, "idleTimer")), Bits(Field<float>(player, "highestAirY")), Field<bool>(player, "flash") ? 1 : 0, Field<bool>(player, "fastJump") ? 1 : 0,
                Bits(Field<float>(player, "hairFlashTimer")), player.lastDashes, (int)hair.Facing, (int)hair.Color.R, (int)hair.Color.G, (int)hair.Color.B, (int)hair.Color.A };
            foreach (var node in hair.Nodes) { row.Add(Bits(node.X)); row.Add(Bits(node.Y)); }
            row.AddRange(new object[] { frames, changes, lasts, hash, Calc.Random.Calls, Bits(level.TimeActive), sprite.Animating ? 1 : 0 });
            writer.WriteLine(string.Join("\t", row));
            if (fields[3] != "render") continue;
            int index = 0;
            foreach (var draw in Draw.SpriteBatch.Calls)
            {
                writer.WriteLine(string.Join("\t", new object[] { "D", fields[1], fields[2], index, draw.Texture,
                    Bits(draw.Position.X), Bits(draw.Position.Y), Bits(draw.Origin.X), Bits(draw.Origin.Y), Bits(draw.Scale.X), Bits(draw.Scale.Y), Bits(draw.Rotation),
                    (int)draw.Color.R, (int)draw.Color.G, (int)draw.Color.B, (int)draw.Color.A, (int)draw.Effects }));
                var vertices = Draw.SpriteBatch.Geometry.Calls[index];
                writer.WriteLine(string.Join("\t", new object[] { "V", fields[1], fields[2], index, Bits(vertices.Position0.X), Bits(vertices.Position0.Y), Bits(vertices.Position1.X), Bits(vertices.Position1.Y),
                    Bits(vertices.Position3.X), Bits(vertices.Position3.Y), Bits(vertices.Position2.X), Bits(vertices.Position2.Y) }));
                index++;
            }
        }
        if (player == null) throw new Exception("Empty source projection replay");
    }
}
