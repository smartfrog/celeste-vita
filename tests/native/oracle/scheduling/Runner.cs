using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Reflection;
using Monocle;

internal static class Runner
{
    private sealed class SyntheticFailure : Exception { }
    private static StateMachine machine;
    private static Coroutine standalone;
    private static Entity entity;
    private static readonly Dictionary<string, string[]> scripts = new();
    private static string name;
    private static int step;
    private static bool remove;
    private static T Private<T>(object target, string field) =>
        (T)target.GetType().GetField(field, BindingFlags.Instance | BindingFlags.NonPublic).GetValue(target);
    private static Coroutine Coroutine => machine == null ? standalone : Private<Coroutine>(machine, "currentCoroutine");
    private static float Float(string value) => value.StartsWith("@")
        ? BitConverter.Int32BitsToSingle(unchecked((int)uint.Parse(value.Substring(1), NumberStyles.HexNumber)))
        : float.Parse(value, CultureInfo.InvariantCulture);
    private static string Bits(float value) => unchecked((uint)BitConverter.SingleToInt32Bits(value)).ToString("x8");
    private static int Flag(bool value) => value ? 1 : 0;

    private static void Trace(string kind, string detail)
    {
        var c = Coroutine;
        Console.WriteLine(string.Join("\t", name, step, kind, detail, machine?.State ?? -1, machine?.PreviousState ?? -1,
            Flag(machine?.ChangedStates ?? false), Flag(machine?.Locked ?? false), Flag(c.Active), Flag(c.Finished),
            Bits(Private<float>(c, "waitTimer")), Private<Stack<IEnumerator>>(c, "enumerators").Count,
            Flag(Private<bool>(c, "ended")), c.RemovalEvents, Flag(c.UseRawDeltaTime), Bits(Engine.DeltaTime), Bits(Engine.RawDeltaTime)));
    }

    private static void Actions(string spec, int calls)
    {
        foreach (string token in spec.Split(','))
        {
            string[] f = token.Split(':');
            switch (f[0])
            {
                case "set": machine.State = int.Parse(f[1]); break;
                case "secondset": if (calls == 2) machine.State = int.Parse(f[1]); break;
                case "force": machine.ForceState(int.Parse(f[1])); break;
                case "lock": machine.Locked = f[1] == "1"; break;
                case "cancel": Coroutine.Cancel(); break;
                case "replace": Coroutine.Replace(new Script(f[1])); break;
                case "throw": throw new SyntheticFailure();
                case "record": case "return": case "script": case "secondreturn": case "secondscript": break;
                default: throw new InvalidOperationException("Unknown callback action");
            }
        }
    }

    private sealed class Script : IEnumerator
    {
        private readonly string identity;
        private readonly string[] tokens;
        private int index;
        public Script(string identity) { this.identity = identity; tokens = scripts[identity]; }
        public object Current { get; private set; }
        public void Reset() => throw new NotSupportedException("Reset is excluded");
        public bool MoveNext()
        {
            Trace("move", identity + ":" + index);
            if (index == tokens.Length) return false;
            string[] f = tokens[index++].Split(':');
            switch (f[0])
            {
                case "n": Current = null; return true;
                case "done": return false;
                case "throw": throw new SyntheticFailure();
                case "i": Current = int.Parse(f[1]); return true;
                case "f": Current = Float(f[1]); return true;
                case "child": Current = new Script(f[1]); return true;
                case "cancel": Coroutine.Cancel(); break;
                case "replace": Coroutine.Replace(new Script(f[1])); break;
                case "set": machine.State = int.Parse(f[1]); break;
                default: throw new InvalidOperationException("Unknown script token");
            }
            Current = null;
            return f[^1] != "done";
        }
    }

    private static Action Callback(string spec, string kind, int index)
    {
        if (spec == "-") return null;
        int calls = 0;
        return () => { Trace(kind, index.ToString()); Actions(spec, ++calls); };
    }

    private static void Run(string[] f)
    {
        string operation = f[0];
        if (operation == "case")
        {
            name = f[1]; step = 0; machine = null; standalone = null; scripts.Clear();
            Engine.DeltaTime = Engine.RawDeltaTime = 0f;
            remove = f[3] == "1";
            entity = new Entity();
            if (f[2] == "C") standalone = new Coroutine(remove);
            else { machine = new StateMachine(int.Parse(f[3])); machine.Added(entity); }
            return;
        }
        if (operation == "script") { scripts.Add(f[1], f[2..]); return; }
        if (operation == "callbacks")
        {
            int index = int.Parse(f[1]);
            int updateCalls = 0, factoryCalls = 0;
            Func<int> update = f[2] == "-" ? null : () =>
            {
                Trace("update", index.ToString());
                Actions(f[2], ++updateCalls);
                string[] result = f[2].Split(',')[^1].Split(':');
                return result[0] == "secondreturn" && updateCalls != 2 ? machine.State : int.Parse(result[1]);
            };
            Func<IEnumerator> factory = f[3] == "-" ? null : () =>
            {
                Trace("factory", index.ToString());
                Actions(f[3], ++factoryCalls);
                string[] result = f[3].Split(',')[^1].Split(':');
                return new Script(result[result[0] == "secondscript" && factoryCalls == 2 ? 2 : 1]);
            };
            machine.SetCallbacks(index, update, factory, Callback(f[4], "begin", index), Callback(f[5], "end", index));
            return;
        }
        ++step;
        try
        {
            switch (operation)
            {
                case "construct": standalone = new Coroutine(new Script(f[1]), remove); break;
                case "replace": Coroutine.Replace(new Script(f[1])); break;
                case "cancel": Coroutine.Cancel(); break;
                case "raw": Coroutine.UseRawDeltaTime = f[1] == "1"; break;
                case "active": Coroutine.Active = f[1] == "1"; break;
                case "remove": Coroutine.RemoveOnComplete = f[1] == "1"; break;
                case "lock": machine.Locked = f[1] == "1"; break;
                case "set": machine.State = int.Parse(f[1]); break;
                case "force": machine.ForceState(int.Parse(f[1])); break;
                case "added": entity.Scene = f[1] == "1" ? new Scene() : null; machine.Added(entity); break;
                case "entity_added": machine.EntityAdded(new Scene()); break;
                case "snapshot": break;
                case "tick":
                    Engine.DeltaTime = Float(f[1]); Engine.RawDeltaTime = Float(f[2]);
                    int removals = Coroutine.RemovalEvents;
                    if (machine == null) Coroutine.Update(); else machine.Update();
                    if (Coroutine.RemovalEvents != removals) Trace("remove", "-");
                    break;
                default: throw new InvalidOperationException("Unknown scheduling command");
            }
            Trace("return", operation);
        }
        catch (SyntheticFailure) { Trace("throw", operation); }
    }

    public static int Main(string[] args)
    {
        try
        {
            if (args.Length != 1) throw new ArgumentException("Expected fixture path");
            foreach (string line in File.ReadLines(args[0]))
            {
                string[] f = line.Split((char[])null, StringSplitOptions.RemoveEmptyEntries);
                if (f.Length == 0 || f[0].StartsWith("#")) continue;
                int separator = Array.IndexOf(f, "=>");
                Run(separator == -1 ? f : f[..separator]);
            }
            return 0;
        }
        catch (Exception error) { Console.Error.WriteLine(error); return 1; }
    }
}
