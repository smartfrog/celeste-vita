using System;
using System.Collections;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Security.Cryptography;
using System.Text.Json;
using Celeste;
using Monocle;

namespace DeathOracle;

static class TransitionObserver
{
    static readonly Dictionary<object, string> identities = new(ReferenceEqualityComparer.Instance);

    public static string Identity(object value)
    {
        if (value == null) return null;
        if (!identities.TryGetValue(value, out var id))
            identities.Add(value, id = value.GetType().Name + "#" + identities.Count);
        return id;
    }

    public static object Field(object value, string name)
    {
        for (Type type = value.GetType(); type != null; type = type.BaseType)
        {
            var field = type.GetField(name, BindingFlags.Public | BindingFlags.NonPublic | BindingFlags.Instance | BindingFlags.DeclaredOnly);
            if (field != null) return field.GetValue(value);
        }
        throw new InvalidOperationException("Required source observer field missing: " + value.GetType().Name + "." + name);
    }

    static object IteratorValue(object iterator, string name)
    {
        var fields = iterator.GetType().GetFields(BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
        var values = fields.Where(field => field.Name.StartsWith("<" + name + ">", StringComparison.Ordinal))
            .Select(field => field.GetValue(iterator)).ToList();
        foreach (var field in fields.Where(field => field.FieldType.Name.Contains("DisplayClass", StringComparison.Ordinal)))
        {
            var member = field.FieldType.GetField(name, BindingFlags.Instance | BindingFlags.Public | BindingFlags.NonPublic);
            if (member != null) values.Add(field.GetValue(iterator) == null ? null : member.GetValue(field.GetValue(iterator)));
        }
        if (values.Count != 1) throw new InvalidOperationException("Required source iterator field missing or ambiguous: " + name);
        object value = values[0];
        if (value is Microsoft.Xna.Framework.Vector2 vector) return new[] { vector.X, vector.Y };
        if (value is List<Entity> entities) return entities.Select(Identity).ToArray();
        if (value is List<Component> components) return components.Select(Identity).ToArray();
        return value;
    }

    public static object Coroutine(Level level)
    {
        var coroutine = (Coroutine)Field(level, "transition");
        if (coroutine == null) return null;
        var stack = (IEnumerable)Field(coroutine, "enumerators");
        object iterator = stack.Cast<object>().FirstOrDefault();
        return new { identity = Identity(coroutine), coroutine.Active, coroutine.Finished,
            waitTimer = Field(coroutine, "waitTimer"), iterator = iterator == null ? null : new {
                state = Field(iterator, "<>1__state"),
                cameraAt = IteratorValue(iterator, "cameraAt"), cameraFrom = IteratorValue(iterator, "cameraFrom"),
                cameraTo = IteratorValue(iterator, "cameraTo"), playerTo = IteratorValue(iterator, "playerTo"),
                outgoing = IteratorValue(iterator, "toRemove"), transitionOut = IteratorValue(iterator, "transitionOut"),
                transitionIn = IteratorValue(iterator, "transitionIn") } };
    }

    public static object RandomState()
    {
        var random = Calc.Random;
        var array = (int[])Field(random, "SeedArray");
        var values = new[] { (int)Field(random, "inext"), (int)Field(random, "inextp") }.Concat(array).ToArray();
        return new { identity = Identity(random), calls = ((PresentationOracle.TracedRandom)random).Calls,
            state = Convert.ToHexString(SHA256.HashData(JsonSerializer.SerializeToUtf8Bytes(values))).ToLowerInvariant() };
    }

    public static object[] Entities(Level level) => level.Entities.Select(entity => (object)new {
        id = Identity(entity), type = entity.GetType().Name, entity.Tag, entity.Active, entity.Visible, entity.Collidable,
        position = new[] { entity.Position.X, entity.Position.Y }, scene = Identity(entity.Scene),
        components = entity.Components.Select(component => new { id = Identity(component), type = component.GetType().Name, component.Active, component.Visible }),
        strawberryWobble = entity is Strawberry ? Field(entity, "wobble") : null,
        springWiggler = entity is Spring ? (object)((Wiggler)Field(entity, "wiggler")).Counter : null }).ToArray();

    public static string[] EndOfFrame(Level level)
    {
        var callback = (Delegate)Field(level, "OnEndOfFrame");
        return callback?.GetInvocationList().Select(value => value.Method.Name).ToArray() ?? Array.Empty<string>();
    }
}
