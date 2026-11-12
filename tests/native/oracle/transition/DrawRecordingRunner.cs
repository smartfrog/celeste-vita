// Self-check harness for the strict draw recorder (DrawRecording.cs). This file is
// compiled only by the recorder support harness: it supplies minimal harness-only
// framework stubs (GraphicsResource/Matrix/state classes) that the real draw profile
// obtains from the frozen original-source extraction, then proves recorder semantics
// and writes recorder-support.json. It is never compiled into any accepted oracle.

using System;
using System.Collections.Generic;
using System.IO;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Monocle;
using PresentationOracle;

namespace Microsoft.Xna.Framework
{
    public struct Matrix
    {
        public float M11, M12, M13, M14, M21, M22, M23, M24;
        public float M31, M32, M33, M34, M41, M42, M43, M44;
        public static Matrix Identity = new() { M11 = 1f, M22 = 1f, M33 = 1f, M44 = 1f };
    }
}

namespace Microsoft.Xna.Framework.Graphics
{
    public class GraphicsResource : IDisposable
    {
        public string Name { get; set; }
        public void Dispose() { }
    }

    public class Effect { }

    public enum SpriteSortMode { Deferred, Texture, BackToFront, FrontToBack, Immediate }

    public class BlendState : GraphicsResource { public BlendState(string name) { Name = name; } }
    public class SamplerState : GraphicsResource { public SamplerState(string name) { Name = name; } }
    public class DepthStencilState : GraphicsResource { public DepthStencilState(string name) { Name = name; } }
    public class RasterizerState : GraphicsResource { public RasterizerState(string name) { Name = name; } }
}

namespace Monocle
{
    public static class Draw
    {
        public static RecordingBatch SpriteBatch = new();
    }
}

static class DrawRecordingRunner
{
    static readonly List<object> checks = new();
    static readonly List<string> failures = new();

    static void Check(string name, bool ok, object evidence)
    {
        Dictionary<string, object> entry = new() { ["name"] = name, ["ok"] = ok };
        if (evidence != null)
            foreach (var property in (Dictionary<string, object>)evidence)
                entry[property.Key] = property.Value;
        checks.Add(entry);
        if (!ok) failures.Add(name);
    }

    static Dictionary<string, object> Evidence(params (string Key, object Value)[] fields)
    {
        var result = new Dictionary<string, object>();
        foreach (var (key, value) in fields) result[key] = value;
        return result;
    }

    static bool Throws(Action action) => Throws(action, out _);

    static bool Throws(Action action, out string message)
    {
        try { action(); message = null; return false; }
        catch (InvalidOperationException error) { message = error.Message; return true; }
    }

    static bool Same(float a, float b) => BitConverter.SingleToUInt32Bits(a) == BitConverter.SingleToUInt32Bits(b);

    static bool Same(Vector2 a, Vector2 b) => Same(a.X, b.X) && Same(a.Y, b.Y);

    static bool Same(VertexPositionColorTexture4 a, VertexPositionColorTexture4 b) =>
        Same(a.Position0, b.Position0) && Same(a.Position1, b.Position1) && Same(a.Position2, b.Position2) && Same(a.Position3, b.Position3)
        && Same(a.TextureCoordinate0, b.TextureCoordinate0) && Same(a.TextureCoordinate1, b.TextureCoordinate1)
        && Same(a.TextureCoordinate2, b.TextureCoordinate2) && Same(a.TextureCoordinate3, b.TextureCoordinate3)
        && a.Color0.Equals(b.Color0) && a.Color1.Equals(b.Color1) && a.Color2.Equals(b.Color2) && a.Color3.Equals(b.Color3);

    static bool Same(SourceVector3 a, SourceVector3 b) => Same(a.X, b.X) && Same(a.Y, b.Y) && Same(a.Z, b.Z);

    static void Main(string[] args)
    {
        string output = args.Length > 0 ? args[0] : ".";
        var atlas = new Atlas();
        SheetDimensions.Register("Gameplay0", 4096, 4096);
        SheetDimensions.Register("Half0", 2048, 2048);
        var batch = Draw.SpriteBatch;

        atlas.AddMetadata("decals/generic/grass_a", "Gameplay0", new[] { 16, 16, 32, 32, 16, 16, 32, 32 });
        atlas.AddMetadata("decals/generic/grass_b", "Gameplay0", new[] { 16, 16, 32, 32, 16, 16, 32, 32 });
        atlas.AddMetadata("decals/generic/half", "Half0", new[] { 16, 16, 32, 32, 16, 16, 32, 32 });
        var grassA = atlas["decals/generic/grass_a"];
        var sheet = grassA.Texture.Texture;

        Check("sheet-identity-and-real-dimensions",
            sheet.Name == "Gameplay0" && sheet.Width == 4096 && sheet.Height == 4096
            && grassA.ClipRect.X == 16 && grassA.ClipRect.Width == 32,
            Evidence(("texture_name", sheet.Name), ("sheet_dimensions", new[] { sheet.Width, sheet.Height }),
                     ("subtexture", "decals/generic/grass_a")));

        Check("unknown-sheet-fails-loud", Throws(() => atlas.AddMetadata("x", "Unknown0", new[] { 0, 0, 8, 8, 0, 0, 8, 8 }), out var unknown),
            Evidence(("sheet", "Unknown0"), ("error", "System.InvalidOperationException: " + unknown)));

        Check("conflicting-sheet-registration-fails",
            Throws(() => SheetDimensions.Register("Gameplay0", 2048, 2048), out var conflict),
            Evidence(("sheet", "Gameplay0"), ("error", "System.InvalidOperationException: " + conflict)));

        var position = new Vector2(10f, 12f);
        var origin = new Vector2(16f, 16f);
        var color = new Color(255, 255, 255, 128);
        batch.Begin(SpriteSortMode.Deferred, new BlendState("BlendState.AlphaBlend"), new SamplerState("SamplerState.PointWrap"),
                    new DepthStencilState("DepthStencilState.None"), new RasterizerState("RasterizerState.CullNone"), null,
                    Matrix.Identity);
        grassA.Draw(position, origin, color, 2f);
        atlas["decals/generic/grass_b"].Draw(position, origin, color, new Vector2(2f, 2f));
        var uv4096 = batch.Geometry.Calls[^2].TextureCoordinate0;
        var halfClip = atlas["decals/generic/half"];
        halfClip.Draw(position, origin, color, 1f);
        var uv2048 = batch.Geometry.Calls[^1].TextureCoordinate0;
        batch.End();

        var scalar = batch.Calls[^3];
        var vector = batch.Calls[^2];
        bool identicalGeometry = Same(batch.Geometry.Calls[^3], batch.Geometry.Calls[^2]);
        Check("scalar-vector-draw-fidelity",
            scalar.Equals(vector) && Same(scalar.Scale, new Vector2(2f, 2f)) && identicalGeometry,
            Evidence(("identical_records", scalar.Equals(vector)),
                     ("identical_geometry_bits", identicalGeometry),
                     ("scale", new[] { scalar.Scale.X, scalar.Scale.Y })));

        bool uv4096Exact = Same(uv4096, new Vector2(16f / 4096f, 16f / 4096f));
        bool uv2048Exact = Same(uv2048, new Vector2(16f / 2048f, 16f / 2048f));
        Check("real-dimensions-drive-uv",
            uv4096Exact && uv2048Exact && !Same(uv4096, uv2048),
            Evidence(("uv_4096", new[] { uv4096.X, uv4096.Y }), ("uv_2048", new[] { uv2048.X, uv2048.Y })));

        var ordered = new RecordingBatch();
        var first = Matrix.Identity;
        first.M41 = -8f;
        var second = Matrix.Identity;
        second.M42 = -4f;
        ordered.Begin(SpriteSortMode.Deferred, new BlendState("BlendState.AlphaBlend"), new SamplerState("SamplerState.PointWrap"),
                      new DepthStencilState("DepthStencilState.None"), new RasterizerState("RasterizerState.CullNone"), null, first);
        ordered.Draw(sheet, position, grassA.ClipRect, color, 0f, origin, 1f, SpriteEffects.None, 0f);
        ordered.Draw(sheet, position, grassA.ClipRect, color, 0f, origin, new Vector2(1f, 1f), SpriteEffects.None, 0f);
        ordered.End();
        ordered.Begin(SpriteSortMode.Deferred, new BlendState("BlendState.AlphaBlend"), new SamplerState("SamplerState.PointWrap"),
                      new DepthStencilState("DepthStencilState.None"), new RasterizerState("RasterizerState.CullNone"), null, second);
        ordered.Draw(sheet, position, grassA.ClipRect, color, 0f, origin, 1f, SpriteEffects.None, 0f);
        ordered.End();
        Check("ordered-batch-state-recording",
            ordered.States.Count == 2
            && ordered.States[0].Operation == "begin" && ordered.States[1].Operation == "begin"
            && ordered.States[0].SortMode == "Deferred" && ordered.States[1].SortMode == "Deferred"
            && ordered.States[0].Matrix[12] == -8f && ordered.States[1].Matrix[13] == -4f
            && ordered.States[0].DrawStart == 0 && ordered.States[0].DrawEnd == 2
            && ordered.States[1].DrawStart == 2 && ordered.States[1].DrawEnd == 3
            && ordered.States[0].Blend == "BlendState.AlphaBlend" && ordered.States[0].HasEffect == false,
            Evidence(("operations", new[] { ordered.States[0].Operation, ordered.States[1].Operation }),
                     ("sort_modes", new[] { ordered.States[0].SortMode, ordered.States[1].SortMode }),
                     ("matrices", new[] { ordered.States[0].Matrix, ordered.States[1].Matrix }),
                     ("draw_ranges", new[] { new[] { ordered.States[0].DrawStart, ordered.States[0].DrawEnd },
                                              new[] { ordered.States[1].DrawStart, ordered.States[1].DrawEnd } }),
                     ("unmatched_end_rejected", Throws(() => new RecordingBatch().End()))));

        var closed = new RecordingBatch();
        bool beforeBegin = Throws(() => closed.Draw(sheet, position, grassA.ClipRect, color, 0f, origin, 1f, SpriteEffects.None, 0f))
            && Throws(() => closed.Draw(sheet, position, grassA.ClipRect, color, 0f, origin, new Vector2(1f, 1f), SpriteEffects.None, 0f));
        var nested = new RecordingBatch();
        nested.Begin(SpriteSortMode.Deferred, new BlendState("BlendState.AlphaBlend"), new SamplerState("SamplerState.PointWrap"),
                     new DepthStencilState("DepthStencilState.None"), new RasterizerState("RasterizerState.CullNone"), null, Matrix.Identity);
        bool nestedRejected = Throws(() => nested.Begin(SpriteSortMode.Deferred, new BlendState("BlendState.AlphaBlend"),
                     new SamplerState("SamplerState.PointWrap"), new DepthStencilState("DepthStencilState.None"),
                     new RasterizerState("RasterizerState.CullNone"), null, Matrix.Identity));
        nested.End();
        bool afterEnd = Throws(() => nested.Draw(sheet, position, grassA.ClipRect, color, 0f, origin, 1f, SpriteEffects.None, 0f));
        Check("draw-requires-open-batch", beforeBegin && nestedRejected && afterEnd,
            Evidence(("draw_before_begin_rejected", beforeBegin), ("nested_begin_rejected", nestedRejected),
                     ("draw_after_end_rejected", afterEnd)));

        var sorted = new RecordingBatch();
        bool textureModeRejected = Throws(() => sorted.Begin(SpriteSortMode.Texture, new BlendState("BlendState.AlphaBlend"),
            new SamplerState("SamplerState.PointWrap"), new DepthStencilState("DepthStencilState.None"),
            new RasterizerState("RasterizerState.CullNone"), null, Matrix.Identity), out var sortError);
        bool sortedUntouched = sorted.States.Count == 0;
        sorted.Begin(SpriteSortMode.Deferred, new BlendState("BlendState.AlphaBlend"), new SamplerState("SamplerState.PointWrap"),
                     new DepthStencilState("DepthStencilState.None"), new RasterizerState("RasterizerState.CullNone"), null, Matrix.Identity);
        sorted.Draw(sheet, position, grassA.ClipRect, color, 0f, origin, 1f, SpriteEffects.None, 0f);
        sorted.End();
        Check("non-deferred-sort-rejected-state-unchanged",
            textureModeRejected && sortError.Contains("Excluded SpriteBatch sort mode") && sortedUntouched
            && sorted.States.Count == 1 && sorted.States[0].DrawStart == 0 && sorted.States[0].DrawEnd == 1,
            Evidence(("error", "System.InvalidOperationException: " + sortError), ("states_after_rejection", 0),
                     ("states_after_valid_submission", sorted.States.Count),
                     ("valid_submission_draw_range", new[] { sorted.States[0].DrawStart, sorted.States[0].DrawEnd })));

        var effected = new RecordingBatch();
        effected.Begin(SpriteSortMode.Deferred, new BlendState("BlendState.AlphaBlend"), new SamplerState("SamplerState.PointWrap"),
                       new DepthStencilState("DepthStencilState.None"), new RasterizerState("RasterizerState.CullNone"), null, Matrix.Identity);
        bool effectRejected = Throws(() => effected.Begin(SpriteSortMode.Deferred, new BlendState("BlendState.AlphaBlend"),
            new SamplerState("SamplerState.PointWrap"), new DepthStencilState("DepthStencilState.None"),
            new RasterizerState("RasterizerState.CullNone"), new Effect(), Matrix.Identity), out var effectError);
        bool effectUntouched = effected.States.Count == 1 && effected.States[0].DrawEnd == 0;
        effected.Draw(sheet, position, grassA.ClipRect, color, 0f, origin, 1f, SpriteEffects.None, 0f);
        effected.End();
        Check("effect-submission-rejected-state-unchanged",
            effectRejected && effectError.Contains("Excluded SpriteBatch effect submission") && effectUntouched
            && effected.States[0].DrawEnd == 1,
            Evidence(("error", "System.InvalidOperationException: " + effectError), ("states_unchanged", effected.States.Count),
                     ("draw_range_after_rejection", new[] { effected.States[0].DrawStart, effected.States[0].DrawEnd })));

        Check("invalid-sort-enum-rejected",
            Throws(() => new RecordingBatch().Begin((SpriteSortMode)99, new BlendState("BlendState.AlphaBlend"),
                new SamplerState("SamplerState.PointWrap"), new DepthStencilState("DepthStencilState.None"),
                new RasterizerState("RasterizerState.CullNone"), null, Matrix.Identity), out var enumError)
            && enumError.Contains("Unknown SpriteSortMode: 99"),
            Evidence(("error", "System.InvalidOperationException: " + enumError)));

        Check("no-draw-omitted", batch.Calls.Count == batch.Geometry.Calls.Count && batch.Calls.Count == 3,
            Evidence(("recorded_calls", batch.Calls.Count), ("geometry_calls", batch.Geometry.Calls.Count)));

        var result = new Dictionary<string, object>
        {
            ["status"] = failures.Count == 0 ? "draw-recording-support-verified" : "draw-recording-support-failed",
            ["checks"] = checks,
            ["failures"] = failures,
            ["scope"] = new Dictionary<string, string>
            {
                ["sorting"] = "deferred-submission-order-only; other SpriteSortMode values, invalid enum values and non-null Effect submissions are rejected before any state change",
                ["owner_attribution"] = "unsupported-not-observed; per-draw owner is not recorded by this recorder",
                ["scissor_state"] = "unsupported-not-observed; recorded Clip is the atlas source rectangle, not a GPU scissor rect",
                ["camera_source"] = "recorded matrix is the exact effective transform passed to Begin, never a CPU camera or Level.Zoom assumption",
                ["parity"] = "not full source parity; only the currently needed original GameplayRenderer.Begin Deferred/null submission is accepted",
            },
        };
        File.WriteAllText(Path.Combine(output, "recorder-support.json"), JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
        Console.WriteLine(result["status"]);
        Environment.Exit(failures.Count == 0 ? 0 : 1);
    }
}
