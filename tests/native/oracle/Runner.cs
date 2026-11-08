using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using Celeste;
using Monocle;
using Microsoft.Xna.Framework;

internal static class Runner
{
    private static Actor actor;
    private static Scene scene;
    private static Dictionary<int, Entity> bodies;
    private static string name;
    private static int step;

    private static float Float(string value) => value.StartsWith("@")
        ? BitConverter.Int32BitsToSingle(unchecked((int)uint.Parse(value.Substring(1), NumberStyles.HexNumber)))
        : float.Parse(value, CultureInfo.InvariantCulture);
    private static string Bits(float value) => unchecked((uint)BitConverter.SingleToInt32Bits(value)).ToString("x8");
    private static int Id(Entity body)
    {
        if (body == null) return -1;
        foreach (var pair in bodies) if (ReferenceEquals(pair.Value, body)) return pair.Key;
        throw new InvalidOperationException("Unknown identity");
    }
    private static void Trace(string kind, string result, CollisionData data = default)
    {
        var p = actor.Position;
        var r = actor.PositionRemainder;
        Console.WriteLine(string.Join("\t", name, step, kind, result, Bits(p.X), Bits(p.Y), Bits(r.X), Bits(r.Y),
            Id(data.Hit), Id(data.Pusher), Bits(data.Direction.X), Bits(data.Direction.Y),
            Bits(data.Moved.X), Bits(data.Moved.Y), Bits(data.TargetPosition.X), Bits(data.TargetPosition.Y)));
    }
    private static void Configure(Entity body, string[] fields, int start)
    {
        body.Position = new Vector2(Float(fields[start]), Float(fields[start + 1]));
        body.Collider = fields[start + 7] == "1"
            ? new Hitbox(Float(fields[start + 2]), Float(fields[start + 3]), Float(fields[start + 4]), Float(fields[start + 5]))
            : null;
        body.Collidable = fields[start + 6] == "1";
        body.Scene = scene;
    }
    private static Collision Callback(string mode, Solid pusher)
    {
        if (mode == "none") return null;
        if (mode != "record" && mode != "mutate" && mode != "reenterH" && mode != "reenterV")
            throw new InvalidOperationException("Unknown callback mode");
        return data =>
        {
            Trace("callback", "-", data);
            if (mode == "mutate")
            {
                actor.Position = new Vector2(-7f, 9f);
                actor.MoveH(0.25f);
                actor.MoveV(-0.25f);
            }
            if (mode == "reenterH" || mode == "reenterV")
            {
                data.Hit.Collidable = false;
                bool result = mode == "reenterH"
                    ? actor.MoveH(1.25f, Callback("record", pusher), pusher)
                    : actor.MoveV(1.25f, Callback("record", pusher), pusher);
                Trace("reentry", result ? "1" : "0");
            }
        };
    }
    public static int Main(string[] args)
    {
        try
        {
#if GRID_ORACLE
            if (args.Length == 3 && args[0] == "--mask") return GridOracle.Mask(args[1], args[2]);
            if (args.Length == 3 && args[0] == "--mask-cases") return GridOracle.MaskCases(args[1], args[2]);
#endif
            if (args.Length != 1) throw new ArgumentException("Expected fixture path");
            foreach (string line in File.ReadLines(args[0]))
            {
                string[] f = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                if (f.Length == 0 || f[0].StartsWith("#")) continue;
                switch (f[0])
                {
                    case "case":
                        name = f[1]; step = 0; scene = new Scene(); actor = new Actor();
                        bodies = new Dictionary<int, Entity> { [0] = actor }; break;
                    case "actor":
                        Configure(actor, f, 1); actor.IgnoreJumpThrus = f[9] == "1"; break;
#if GRID_ORACLE
                    case "grid":
                        var tiled = new Solid { Position = new Vector2(Float(f[2]), Float(f[3])), Collider = GridFixture.Parse(f), Scene = scene, Collidable = f[11] == "1" };
                        bodies.Add(int.Parse(f[1]), tiled);
                        scene.Tracker.Entities[typeof(Solid)].Add(tiled); break;
#endif
                    case "solid":
                    case "jump":
                        Entity body = f[0] == "solid" ? new Solid() : new JumpThru();
                        Configure(body, f, 2); bodies.Add(int.Parse(f[1]), body);
                        scene.Tracker.Entities[f[0] == "solid" ? typeof(Solid) : typeof(JumpThru)].Add(body); break;
                    case "self": scene.Tracker.Entities[typeof(Solid)].Add(actor); break;
                    case "H": case "V": case "HX": case "VX":
                        ++step;
                        Solid pusher = f[3] == "-1" ? null : (Solid)bodies[int.Parse(f[3])];
                        Collision callback = Callback(f[2], pusher);
                        bool result = f[0] switch
                        {
                            "H" => actor.MoveH(Float(f[1]), callback, pusher),
                            "V" => actor.MoveV(Float(f[1]), callback, pusher),
                            "HX" => actor.MoveHExact(int.Parse(f[1]), callback, pusher),
                            "VX" => actor.MoveVExact(int.Parse(f[1]), callback, pusher),
                            _ => throw new InvalidOperationException()
                        };
                        Trace("return", result ? "1" : "0"); break;
                    case "Q": case "O":
                        ++step;
                        Vector2 at = new Vector2(Float(f[1]), Float(f[2]));
                        Entity hit = f[0] == "Q" ? actor.CollideFirst<Solid>(at) : actor.CollideFirstOutside<JumpThru>(at);
                        Trace("query", hit == null ? "0" : "1", new CollisionData { Hit = hit as Platform }); break;
                    default: throw new InvalidOperationException("Unknown fixture operation: " + f[0]);
                }
            }
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
