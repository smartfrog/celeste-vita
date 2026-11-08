using System;
using System.Globalization;
using System.IO;
using System.Reflection;
using Microsoft.Xna.Framework.Input;
using Monocle;

internal static class Runner
{
    private static VirtualButton button;
    private static string name;
    private static int step;
    private static T Private<T>(string field) =>
        (T)typeof(VirtualButton).GetField(field, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(button);
    private static float Float(string value) => value.StartsWith("@")
        ? BitConverter.Int32BitsToSingle(unchecked((int)uint.Parse(value.Substring(1), NumberStyles.HexNumber)))
        : float.Parse(value, CultureInfo.InvariantCulture);
    private static string Bits(float value) => unchecked((uint)BitConverter.SingleToInt32Bits(value)).ToString("x8");
    private static int Flag(bool value) => value ? 1 : 0;
    private static bool Flag(string value) => value switch
    {
        "0" => false, "1" => true, _ => throw new ArgumentException("Invalid sample flag")
    };

    private static void Trace(string phase, string operation)
    {
        var s = button.Binding;
        Console.WriteLine(string.Join("\t", name, step, phase, operation,
            Bits(button.BufferTime), Bits(Private<float>("firstRepeatTime")), Bits(Private<float>("multiRepeatTime")),
            Bits(Private<float>("bufferCounter")), Bits(Private<float>("repeatCounter")), Flag(Private<bool>("canRepeat")),
            Flag(Private<bool>("consumed")), Flag(button.Repeating), Flag(s.Held), Flag(s.RawPressed), Flag(s.RawReleased),
            Flag(MInput.Disabled), Flag(MInput.Keyboard.DebugHeld), Flag(button.Check), Flag(button.Pressed),
            Flag(button.Released), Bits(Engine.DeltaTime)));
    }

    private static void Run(string[] f)
    {
        string operation = f[0];
        if (operation == "case")
        {
            name = f[1]; step = 0;
            Engine.DeltaTime = 0f;
            MInput.Disabled = MInput.Keyboard.DebugHeld = false;
            button = new VirtualButton(new Binding(), 0, Float(f[2]), 0f);
            button.DebugOverridePressed = Keys.SampledDebug;
            return;
        }
        ++step;
        if (operation == "tick") Engine.DeltaTime = Float(f[1]);
        Trace("before", operation);
        switch (operation)
        {
            case "sample":
                button.Binding.Held = Flag(f[1]); button.Binding.RawPressed = Flag(f[2]);
                button.Binding.RawReleased = Flag(f[3]); MInput.Disabled = Flag(f[4]);
                MInput.Keyboard.DebugHeld = Flag(f[5]); break;
            case "tick": button.Update(); break;
            case "repeat": button.SetRepeat(Float(f[1])); break;
            case "repeat_pair": button.SetRepeat(Float(f[1]), Float(f[2])); break;
            case "buffer": button.BufferTime = Float(f[1]); break;
            case "consume_buffer": button.ConsumeBuffer(); break;
            case "consume_press": button.ConsumePress(); break;
            case "query": break;
            default: throw new ArgumentException("Unknown input operation");
        }
        Trace("after", operation);
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
