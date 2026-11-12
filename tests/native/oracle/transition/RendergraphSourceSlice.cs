using System;
using System.IO;
using System.Linq;
using System.Text.Json;

namespace DeathOracle
{
    public static class RoomCoreExecution
    {
        public static void Main(string[] args)
        {
            if (args.Length != 1) throw new ArgumentException("Expected verified effect metadata path");
            RendergraphOracle.SourceSlice.Run(args[0]);
        }

    }
}

namespace RendergraphOracle
{
    using Microsoft.Xna.Framework;
    using Microsoft.Xna.Framework.Graphics;
    using Monocle;
    using Celeste;

    public static class SourceSlice
    {
        static readonly System.Collections.Generic.List<string> checks = new();
        static void Check(bool condition, string name)
        {
            if (!condition) throw new InvalidOperationException("Failed observer check: " + name);
            checks.Add(name);
        }
        static void Reject(Action operation, string name)
        {
            int count = Capture.Events.Count;
            try { operation(); }
            catch (Exception error) when (error is InvalidOperationException || error is System.Collections.Generic.KeyNotFoundException)
            {
                Check(Capture.Events.Count == count, name + " must fail before trace mutation");
                return;
            }
            throw new InvalidOperationException("Expected rejection: " + name);
        }

        public static void Run(string effectsPath)
        {
            using var metadata = JsonDocument.Parse(File.ReadAllText(effectsPath));
            GFX.FxDither = new Effect("GFX.FxDither", metadata.RootElement.GetProperty("Dither"));
            GFX.FxPrimitive = new Effect("GFX.FxPrimitive", metadata.RootElement.GetProperty("Primitive"));
            var device = new GraphicsDevice(320, 180);
            Engine.Instance = new Engine { GraphicsDevice = device };
            Draw.SpriteBatch = new SpriteBatch(device);

            Capture.Owner = "original GameplayBuffers.Create";
            GameplayBuffers.Create();
            Check(GameplayBuffers.Light.Width == 320 && GameplayBuffers.Light.Height == 180, "original light dimensions");
            Check(GameplayBuffers.LightBuffer.Width == 1024 && GameplayBuffers.LightBuffer.Height == 1024, "original light buffer dimensions");
            Check(GameplayBuffers.MirrorSources.Width == 384 && GameplayBuffers.MirrorSources.Height == 244, "original mirror dimensions");
            string firstId = GameplayBuffers.Gameplay.Target.Id;

            Capture.Owner = "observer target/viewport prerequisites";
            device.SetRenderTarget(GameplayBuffers.LightBuffer);
            Check(device.Viewport.Width == 1024 && device.Viewport.Height == 1024, "target binds viewport dimensions");
            device.Viewport = new Viewport(7, 9, 100, 80);
            device.ScissorRectangle = new Rectangle(2, 3, 40, 50);
            var savedViewport = device.Viewport;
            var savedScissor = device.ScissorRectangle;
            device.SetRenderTarget(GameplayBuffers.LightBuffer);
            Check(device.Viewport.X == 7 && device.ScissorRectangle.X == 2, "same-target bind preserves viewport/scissor");
            device.SetRenderTarget(GameplayBuffers.Light);
            Check(device.Viewport.Width == 320 && device.ScissorRectangle.Width == 320, "new target resets viewport/scissor");
            device.Clear(Color.Black);
            device.SetRenderTarget(null);
            Check(device.Viewport.Width == 320 && device.Viewport.X == 0, "backbuffer dimensions restored, not previous custom viewport");
            device.Viewport = savedViewport;
            device.ScissorRectangle = savedScissor;
            Check(device.Viewport.X == 7 && device.ScissorRectangle.X == 2, "explicit viewport/scissor restoration");
            device.SetRenderTarget(GameplayBuffers.Gameplay);

            Capture.Owner = "original LightingRenderer.Render";
            new LightingRenderer().Render(new Scene());

            Capture.Owner = "original GFX.DrawIndexedVertices fixture";
            var vertices = new[] {
                new VertexPositionColor { Position = new Vector3(0, 0, 0), Color = Color.Red },
                new VertexPositionColor { Position = new Vector3(8, 0, 0), Color = Color.Green },
                new VertexPositionColor { Position = new Vector3(0, 8, 0), Color = Color.Blue } };
            GFX.DrawIndexedVertices(Matrix.Identity, vertices, 3, new[] { 0, 1, 2 }, 1);

            Capture.Owner = "observer rejection and snapshot checks";
            Reject(() => Draw.SpriteBatch.Begin(SpriteSortMode.Immediate, null, null, null, null, null, Matrix.Identity), "excluded batch mode");
            Reject(() => GFX.FxDither.CurrentTechnique = GFX.FxPrimitive.CurrentTechnique, "foreign technique");
            Reject(() => GFX.FxDither.Parameters["unknown"].SetValue(Vector2.Zero), "unknown parameter");
            Reject(() => GFX.FxDither.Parameters["size"].SetValue(Matrix.Identity), "wrong parameter type");
            Reject(() => device.DrawUserIndexedPrimitives(PrimitiveType.TriangleStrip, vertices, 0, 3, new[] { 0, 1, 2 }, 0, 1), "excluded primitive mode");
            Reject(() => device.DrawUserIndexedPrimitives(PrimitiveType.TriangleList, new VertexPositionColorTexture[3], 0, 3, new[] { 0, 1, 2 }, 0, 1), "excluded vertex type");
            Reject(() => device.DrawUserIndexedPrimitives(PrimitiveType.TriangleList, vertices, 0, 3, new[] { 0, 1, 3 }, 0, 1), "invalid index");
            var invalidRasterizer = new RasterizerState { CullMode = (CullMode)99 };
            Reject(() => Draw.SpriteBatch.Begin(SpriteSortMode.Deferred, null, null, null, invalidRasterizer, GFX.FxDither, Matrix.Identity), "unknown rasterizer state");
            var foreign = new RenderTarget2D(new GraphicsDevice(1, 1), 1, 1, false, SurfaceFormat.Color, DepthFormat.None, 0, RenderTargetUsage.DiscardContents);
            Reject(() => device.SetRenderTarget(foreign), "foreign target");
            foreign.Dispose();
            Check(foreign.IsDisposed && !GameplayBuffers.Gameplay.Target.IsDisposed && foreign.Id != GameplayBuffers.Gameplay.Target.Id,
                "foreign disposal preserves original target lifetime");
            Draw.SpriteBatch.Begin(SpriteSortMode.Deferred, null, null, null, null, null, Matrix.Identity);
            Reject(() => Draw.SpriteBatch.Draw(GameplayBuffers.Light, Vector2.Zero, Color.White), "unverified default sprite program");
            Draw.SpriteBatch.End();

            Draw.SpriteBatch.Begin(SpriteSortMode.Deferred, null, null, null, null, GFX.FxDither, Matrix.Identity);
            Draw.SpriteBatch.Draw(GameplayBuffers.Light, Vector2.Zero, Color.White);
            Reject(() => Draw.SpriteBatch.Draw(GameplayBuffers.Light, Vector2.Zero, Color.White), "unclosed multi-command batching");
            GFX.FxDither.Parameters["size"].SetValue(new Vector2(11, 13));
            Draw.SpriteBatch.End();
            var latest = JsonSerializer.Serialize(Capture.Events.Last(e => JsonSerializer.Serialize(e).Contains("\"operation\":\"batch-flush\"")));
            Check(latest.Contains(BitConverter.SingleToInt32Bits(11f).ToString()), "effect captured at flush, not Begin");

            var nonfinite = vertices.ToArray();
            nonfinite[0].Position.X = BitConverter.Int32BitsToSingle(unchecked((int)0xffc00001));
            nonfinite[1].Position.Y = float.PositiveInfinity;
            GFX.DrawIndexedVertices(Matrix.Identity, nonfinite, 3, new[] { 0, 1, 2 }, 1);
            string command = JsonSerializer.Serialize(Capture.Events.Last());
            Check(command.Contains(unchecked((int)0xffc00001).ToString()) && command.Contains("2139095040"), "nonfinite vertex payload bits retained");
            nonfinite[0].Position.X = 123;
            Check(command == JsonSerializer.Serialize(Capture.Events.Last()), "vertex storage snapshotted, not aliased");

            Capture.Owner = "observer apply-time parameter snapshot";
            GFX.FxPrimitive.Parameters["World"].SetValue(Matrix.Identity);
            GFX.FxPrimitive.CurrentTechnique.Passes[0].Apply();
            string applied = JsonSerializer.Serialize(device.AppliedSnapshot);
            GFX.FxPrimitive.Parameters["World"].SetValue(Matrix.CreateScale(7f));
            device.DrawUserIndexedPrimitives(PrimitiveType.TriangleList, vertices, 0, 3, new[] { 0, 1, 2 }, 0, 1);
            Check(applied == JsonSerializer.Serialize(device.AppliedSnapshot), "primitive uses apply-time parameters, not later values");

            device.SetRenderTarget(null);
            Capture.Owner = "original GameplayBuffers.Create repeated lifecycle";
            var oldTarget = GameplayBuffers.Gameplay.Target;
            GameplayBuffers.Create();
            Check(oldTarget.IsDisposed && GameplayBuffers.Gameplay.Target.Id != firstId, "recreation has new lifetime identity");
            Reject(() => device.SetRenderTarget(oldTarget), "disposed target bind");
            Capture.Owner = "original GameplayBuffers.Unload";
            GameplayBuffers.Unload();
            GameplayBuffers.Unload();
            Check(GameplayBuffers.Gameplay.Target == null, "original unload clears target");
            foreach (object entry in Capture.Events) Console.WriteLine(JsonSerializer.Serialize(entry));
            Console.WriteLine(JsonSerializer.Serialize(new { operation = "slice-summary", checks = checks.Count, verifiedChecks = checks,
                claim = "Original target lifecycle, Lighting.Render and indexed helper API slice; not BeforeRender, full Level, GPU or pixels" }));
        }
    }
}
