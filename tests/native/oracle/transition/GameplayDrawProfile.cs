using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Celeste;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Monocle;
using PresentationOracle;

namespace DeathOracle;

static class GameplayDrawProfile
{
    static Entity entity;
    static Component component;
    static readonly List<object> ranges = new();
    static int entityStart;
    static RecordingBatch Batch => LifecycleRecording.Batch;
    static string Identity(object value) => TransitionObserver.Identity(value);
    static float[] Vector(Vector2 value) => new[] { value.X, value.Y };
    static int[] Rectangle(Rectangle value) => new[] { value.X, value.Y, value.Width, value.Height };
    static int[] Color(Color value) => new[] { (int)value.R, value.G, value.B, value.A };

    static object[] GraphicsState(Level level) => level.Entities.OfType<Spring>().SelectMany(value => value.Components)
        .OfType<GraphicsComponent>().Select(value => (object)new { component = Identity(value),
            position = Vector(value.Position), color = Color(value.Color) }).ToArray();

    public static void RegisterSheets()
    {
        using var sheets = JsonDocument.Parse(File.ReadAllText(Path.Combine(TransitionProfile.DataRoot, "sheets.json")));
        foreach (var sheet in sheets.RootElement.EnumerateObject())
            SheetDimensions.Register(sheet.Name, sheet.Value[0].GetInt32(), sheet.Value[1].GetInt32());
        typeof(Engine).GetProperty("Commands").GetSetMethod(true).Invoke(null,
            new[] { RuntimeHelpers.GetUninitializedObject(typeof(Commands)) });
    }

    public static void EnterEntity(Entity value)
    {
        if (entity != null || component != null) throw new InvalidOperationException("Nested entity render dispatch");
        entity = value;
        entityStart = Batch.Calls.Count;
    }

    public static void ExitEntity(Entity value)
    {
        if (!ReferenceEquals(value, entity) || component != null) throw new InvalidOperationException("Unbalanced entity render dispatch");
        ranges.Add(new { entity = Identity(value), type = value.GetType().Name, depth = value.Depth, value.actualDepth,
            value.Visible, tag = (int)value.Tag, drawStart = entityStart, drawEnd = Batch.Calls.Count });
        entity = null;
    }

    public static void EnterComponent(Component value)
    {
        if (component != null || !ReferenceEquals(value.Entity, entity)) throw new InvalidOperationException("Unexpected component render owner");
        component = value;
    }

    public static void ExitComponent(Component value)
    {
        if (!ReferenceEquals(value, component)) throw new InvalidOperationException("Unbalanced component render dispatch");
        component = null;
    }

    static object Owner()
    {
        if (entity == null) throw new InvalidOperationException("Draw outside observed original entity dispatch");
        return new { entity = Identity(entity), type = entity.GetType().Name, depth = entity.Depth, entity.actualDepth,
            component = Identity(component), componentType = component?.GetType().Name,
            componentAttribution = component == null ? "direct entity render; no ComponentList dispatch observed" : "original ComponentList.Render dispatch" };
    }

    static float[][] Vertices(VertexPositionColorTexture4 value) => new[] {
        new[] { value.Position0.X, value.Position0.Y, value.Position0.Z, value.TextureCoordinate0.X, value.TextureCoordinate0.Y },
        new[] { value.Position1.X, value.Position1.Y, value.Position1.Z, value.TextureCoordinate1.X, value.TextureCoordinate1.Y },
        new[] { value.Position2.X, value.Position2.Y, value.Position2.Z, value.TextureCoordinate2.X, value.TextureCoordinate2.Y },
        new[] { value.Position3.X, value.Position3.Y, value.Position3.Z, value.TextureCoordinate3.X, value.TextureCoordinate3.Y } };

    public static void Render(Level level, int tick, Action<object> write)
    {
        if (!ReferenceEquals(level.Camera, level.GameplayRenderer.Camera)) throw new InvalidOperationException("Gameplay camera alias lost");
        if (Engine.Commands.Open) throw new UnsupportedClosure("Gameplay command profile requires closed debug console");
        LifecycleRecording.Begin();
        Batch.States.Clear();
        Batch.Owners.Clear();
        Batch.ObserveOwner = Owner;
        ranges.Clear();
        entity = null;
        component = null;
        try
        {
            var outlineBefore = GraphicsState(level);
            write(new { @event = "draw-roster", tick, cameraAlias = true, cameraViewport = new[] { level.Camera.Viewport.Width, level.Camera.Viewport.Height },
                scope = "GameplayRenderer.Render only; no Level.BeforeRender/Render hooks, buffers/effects, GPU or scissor observation",
                geometry = "Original FNA pre-batch-transform XY/Z/UV as IEEE754 float32 bits; effective transform recorded per batch",
                live = level.Entities.Select(value => new { entity = Identity(value), type = value.GetType().Name,
                    depth = value.Depth, value.actualDepth, value.Active, value.Visible, tag = (int)value.Tag,
                    position = Vector(value.Position), hudExcluded = value.TagCheck(Tags.HUD),
                    decal = value is Decal decal ? new { decal.Name, image = TransitionObserver.Field(decal, "image").GetType().Name } : null }).ToArray() });
            level.GameplayRenderer.Render(level);
            if (entity != null || component != null || Batch.Calls.Count != Batch.Geometry.Calls.Count || Batch.Owners.Count != Batch.Calls.Count)
                throw new InvalidOperationException("Incomplete original draw dispatch/geometry");
            for (int index = 0; index < Batch.Calls.Count; index++)
            {
                var draw = Batch.Calls[index];
                var texture = (Texture2D)draw.Texture;
                var vertices = Vertices(Batch.Geometry.Calls[index]);
                write(new { @event = "draw-command", tick, index, owner = Batch.Owners[index], sheet = texture.Name,
                    dimensions = new[] { texture.Width, texture.Height }, position = Vector(draw.Position), sourceRectangle = Rectangle(draw.Clip),
                    clipping = "atlas source rectangle; GPU scissor not observed", color = Color(draw.Color), rotation = draw.Rotation,
                    origin = Vector(draw.Origin), scale = Vector(draw.Scale), effects = draw.Effects.ToString(),
                    finiteGeometry = vertices.SelectMany(value => value).All(float.IsFinite),
                    verticesFloat32Bits = vertices.Select(vertex => vertex.Select(BitConverter.SingleToInt32Bits).ToArray()).ToArray() });
            }
            write(new { @event = "draw-dispatch", tick, entities = ranges.ToArray(), commands = Batch.Calls.Count,
                outlineBefore, outlineAfter = GraphicsState(level),
                batches = Batch.States.Select(state => new { state.Operation, state.SortMode, state.Blend, state.Sampler,
                    state.DepthStencil, state.Rasterizer, state.HasEffect, state.Matrix, state.DrawStart, state.DrawEnd }) });
        }
        finally
        {
            Batch.ObserveOwner = null;
            LifecycleRecording.End();
        }
    }
}
