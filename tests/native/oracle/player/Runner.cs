using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using Celeste;
using Microsoft.Xna.Framework;
using Monocle;

internal static class Runner
{
    private static Player player;
    private static Level world;
    private static readonly Dictionary<Entity, int> ids = new();
    private static string name;
    private static int frame;
    private static float delta;
    private static Vector2 spawn, speed;
    private static string[] input;
#if HAZARD_ORACLE
    private static readonly List<int> spikeIds = new();
    private static readonly List<string> phases = new();
    private static string operation, result, sample;
    private static void Observe(string phase, CollisionData? data)
    {
        phases.Add(data.HasValue ? phase + ":" + ids[data.Value.Hit] : phase);
    }
    private static string Identities(List<int> indices) => indices.Count == 0 ? "-" : string.Join(",", indices.ConvertAll(i => spikeIds[i]));
#endif
    private static T Private<T>(object owner, string field) => (T)owner.GetType().GetField(field, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(owner);
    private static float Float(string value) => value.StartsWith("@")
        ? BitConverter.Int32BitsToSingle(unchecked((int)uint.Parse(value.Substring(1), NumberStyles.HexNumber)))
        : float.Parse(value, CultureInfo.InvariantCulture);
    private static string Bits(float value) => unchecked((uint)BitConverter.SingleToInt32Bits(value)).ToString("x8");
    private static int Flag(bool value) => value ? 1 : 0;
    private static bool Flag(string value) => value switch { "0" => false, "1" => true, _ => throw new ArgumentException("Invalid Player flag") };

    private static void Trace(string phase, CollisionData? data)
    {
        var p = player;
#if HAZARD_ORACLE
        string collider = ReferenceEquals(p.Collider, Private<Hitbox>(p, "normalHitbox")) ? "normal" : ReferenceEquals(p.Collider, Private<Hitbox>(p, "duckHitbox")) ? "duck" : "hurt";
        if (world.Session.Deaths != Flag(p.Dead) || world.Session.DeathsInCurrentLevel != Flag(p.Dead) || SaveData.Instance.DeathCalls != Flag(p.Dead))
            throw new InvalidOperationException("Isolated death counters differ from source guard");
        Console.WriteLine(string.Join("\t", name, frame, operation, result, Bits(delta), Bits(p.X), Bits(p.Y), Bits(p.PositionRemainder.X), Bits(p.PositionRemainder.Y),
            Bits(p.Speed.X), Bits(p.Speed.Y), Flag(p.Ducking), collider, Flag(Private<bool>(p, "onGround")), Flag(Private<bool>(p, "wasOnGround")), Flag(p.Dead), p.Depth,
            Flag(p.StateMachine.Locked), Flag(p.Collidable), Flag(p.Removed), Bits(p.DeathDirection.X), Bits(p.DeathDirection.Y), world.Events.Count == 0 ? "-" : string.Join(",", world.Events),
            Flag(p.RefillCalls > 0), Identities(world.Tracker.Checks), Identities(world.Tracker.Overlaps), phases.Count == 0 ? "-" : string.Join(",", phases), p.Dashes, Bits(p.Stamina), p.StateMachine.State,
            p.StateMachine.PreviousState, Flag(p.StateMachine.ChangedStates), Bits(p.PreviousPosition.X), Bits(p.PreviousPosition.Y), Bits(Private<float>(p, "jumpGraceTimer")),
            Bits(Private<float>(p, "varJumpTimer")), Bits(Private<float>(p, "varJumpSpeed")), Bits(Private<float>(p, "maxFall")), sample));
#else
        var d = data ?? default;
        Console.WriteLine(string.Join("\t", name, frame, phase, Bits(delta), input[2], input[3], input[4], input[5], input[6], input[7], input[8], input[9],
            Bits(p.X), Bits(p.Y), Bits(p.PositionRemainder.X), Bits(p.PositionRemainder.Y), Bits(p.PreviousPosition.X), Bits(p.PreviousPosition.Y),
            Bits(p.Speed.X), Bits(p.Speed.Y), (int)p.Facing, Private<int>(p, "moveX"), Flag(Private<bool>(p, "onGround")), Flag(Private<bool>(p, "wasOnGround")),
            Flag(p.OnSafeGround), Flag(p.Ducking), p.Ducking ? "duck" : "normal", Bits(Private<float>(p, "jumpGraceTimer")), Bits(Private<float>(p, "varJumpTimer")),
            Bits(Private<float>(p, "varJumpSpeed")), Bits(Private<float>(p, "maxFall")), Bits(Private<float>(p, "wallSlideTimer")), Private<int>(p, "wallSlideDir"),
            Bits(Private<float>(p, "wallSpeedRetentionTimer")), Bits(Private<float>(p, "wallSpeedRetained")), Bits(p.Stamina), p.Dashes, p.StateMachine.State,
            p.StateMachine.PreviousState, Flag(p.StateMachine.ChangedStates), Bits(Private<float>(Input.Jump, "bufferCounter")), Flag(Input.Jump.Pressed),
            Flag(Private<bool>(Input.Jump, "consumed")), Flag(Private<bool>(p, "launched")), d.Hit == null ? -1 : ids[d.Hit],
             Bits(d.Direction.X), Bits(d.Direction.Y), Bits(d.Moved.X), Bits(d.Moved.Y), Bits(d.TargetPosition.X), Bits(d.TargetPosition.Y)));
#endif
    }

    private static void Run(string[] f)
    {
        string op = f[0];
        if (op == "case")
        {
            name = f[1]; frame = 0; player = null; ids.Clear();
            world = new Level();
#if HAZARD_ORACLE
            spikeIds.Clear(); phases.Clear(); SaveData.Instance.DeathCalls = 0;
#endif
            foreach (var type in new[] { typeof(Platform), typeof(Water), typeof(Spikes), typeof(DreamBlock), typeof(NegaBlock) }) world.Tracker.Entities[type] = new();
            spawn = new(Float(f[2]), Float(f[3])); speed = new(Float(f[4]), Float(f[5]));
            world.Bounds = new Bounds { Left = (int)Float(f[6]), Right = (int)Float(f[7]) };
            Input.Jump = new(new Binding(), 0, 0.08f, 0f);
            Input.MoveX.Value = Input.MoveY.Value = 0;
            MInput.Disabled = false;
            return;
        }
#if HAZARD_ORACLE
        if (op == "spike")
        {
            if (player != null) throw new ArgumentException("Spikes must precede frames");
            var direction = f[5] switch { "up" => Spikes.Directions.Up, "left" => Spikes.Directions.Left, _ => throw new ArgumentException("Unsupported spike") };
            var spike = new Spikes(world, new(Float(f[2]), Float(f[3])), int.Parse(f[4]), direction) { Collidable = Flag(f[6]) };
            world.Tracker.Entities[typeof(Spikes)].Add(spike);
            spikeIds.Add(int.Parse(f[1]));
            return;
        }
        if (op == "die")
        {
            player ??= new Player(world, spawn, speed) { Observe = Observe };
            frame++; delta = 0; phases.Clear(); operation = "die";
            sample = Bits(Float(f[1])) + "," + Bits(Float(f[2]));
            result = player.Die(new(Float(f[1]), Float(f[2]))) != null ? "accepted" : "ignored";
            Trace("", null);
            return;
        }
#endif
        if (op == "solid" || op == "jump" || op == "grid")
        {
            if (player != null) throw new ArgumentException("Platforms must precede frames");
            Platform p = op == "jump" ? new JumpThru() : new Solid();
            p.Position = new(Float(f[2]), Float(f[3]));
            p.Collider = op == "grid" ? GridFixture.Parse(f) : new Hitbox(Float(f[4]), Float(f[5]));
            p.Safe = Flag(f[op == "grid" ? 11 : 6]);
            world.Tracker.Entities[p.GetType()].Add(p);
            world.Tracker.Entities[typeof(Platform)].Add(p);
            ids[p] = int.Parse(f[1]);
            return;
        }
        if (op != "tick") throw new ArgumentException("Unknown Player operation");
        player ??= new Player(world, spawn, speed) { Observe =
#if HAZARD_ORACLE
            Observe
#else
            Trace
#endif
        };
        frame++; delta = Float(f[1]); input = f;
#if HAZARD_ORACLE
        phases.Clear(); operation = "tick"; result = "frame";
        sample = string.Join(",", f[2..10]);
        try { player.Frame(delta, int.Parse(f[2]), int.Parse(f[3]), Flag(f[4]), Flag(f[5]), Flag(f[6]), Flag(f[7]), Flag(f[8]), Flag(f[9])); if (player.Dead) result = "removed"; }
        catch (NotSupportedException) { result = "rejected"; }
        catch (ArgumentException) { result = "rejected"; }
        Trace("", null);
#else
        try { player.Frame(delta, int.Parse(f[2]), int.Parse(f[3]), Flag(f[4]), Flag(f[5]), Flag(f[6]), Flag(f[7]), Flag(f[8]), Flag(f[9])); }
        catch (NotSupportedException) { Trace("rejected", null); }
        catch (ArgumentException) { Trace("rejected", null); }
#endif
    }

    public static int Main(string[] args)
    {
        try
        {
            if (args.Length != 1) throw new ArgumentException("Expected fixture path");
            foreach (string line in File.ReadLines(args[0]))
            {
                string[] fields = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                if (fields.Length == 0 || fields[0].StartsWith("#")) continue;
                Run(fields);
            }
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
