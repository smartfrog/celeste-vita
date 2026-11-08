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
    }

    private static void Run(string[] f)
    {
        string op = f[0];
        if (op == "case")
        {
            name = f[1]; frame = 0; player = null; ids.Clear();
            world = new Level();
            foreach (var type in new[] { typeof(Platform), typeof(Water), typeof(Spikes), typeof(DreamBlock), typeof(NegaBlock) }) world.Tracker.Entities[type] = new();
            spawn = new(Float(f[2]), Float(f[3])); speed = new(Float(f[4]), Float(f[5]));
            world.Bounds = new Bounds { Left = (int)Float(f[6]), Right = (int)Float(f[7]) };
            Input.Jump = new(new Binding(), 0, 0.08f, 0f);
            Input.MoveX.Value = Input.MoveY.Value = 0;
            MInput.Disabled = false;
            return;
        }
        if (op == "solid" || op == "jump")
        {
            if (player != null) throw new ArgumentException("Platforms must precede frames");
            Platform p = op == "solid" ? new Solid() : new JumpThru();
            p.Position = new(Float(f[2]), Float(f[3]));
            p.Collider = new Hitbox(Float(f[4]), Float(f[5]));
            p.Safe = Flag(f[6]);
            world.Tracker.Entities[p.GetType()].Add(p);
            world.Tracker.Entities[typeof(Platform)].Add(p);
            ids[p] = int.Parse(f[1]);
            return;
        }
        if (op != "tick") throw new ArgumentException("Unknown Player operation");
        player ??= new Player(world, spawn, speed) { Observe = Trace };
        frame++; delta = Float(f[1]); input = f;
        try { player.Frame(delta, int.Parse(f[2]), int.Parse(f[3]), Flag(f[4]), Flag(f[5]), Flag(f[6]), Flag(f[7]), Flag(f[8]), Flag(f[9])); }
        catch (NotSupportedException) { Trace("rejected", null); }
        catch (ArgumentException) { Trace("rejected", null); }
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
