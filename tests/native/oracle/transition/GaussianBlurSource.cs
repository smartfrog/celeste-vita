using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Monocle;
using Celeste;

namespace DeathOracle
{
    public static class RoomCoreExecution
    {
        public static void Main(string[] args)
        {
            if (args.Length != 1) throw new ArgumentException("Expected verified Gaussian effect metadata path");
            RendergraphOracle.GaussianSource.Run(args[0]);
        }
    }
}

namespace RendergraphOracle
{
    public static class GaussianSource
    {
        static readonly List<string> checks = new();
        static void Check(bool condition, string name)
        {
            if (!condition) throw new InvalidOperationException("Failed Gaussian observer check: " + name);
            checks.Add(name);
        }
        static void Reject(Action operation, string name)
        {
            int count = Capture.Events.Count;
            try { operation(); }
            catch (Exception error) when (error is InvalidOperationException || error is KeyNotFoundException)
            {
                Check(Capture.Events.Count == count, name + " rejected before trace mutation");
                return;
            }
            throw new InvalidOperationException("Expected rejection: " + name);
        }
        static void Returned(Texture2D returned, Texture2D expected)
        {
            Check(ReferenceEquals(returned, expected), "original return target");
            Capture.Add("blur-return", new { returned = returned.Id });
        }
        static void DirectionFailure(GaussianBlur.Direction direction, string name)
        {
            int count = Capture.Events.Count;
            try { GaussianBlur.Blur(GameplayBuffers.Light, GameplayBuffers.TempA, GameplayBuffers.TempB, direction: direction); }
            catch (InvalidOperationException error) when (error.Message == "Unsupported default SpriteBatch shader")
            {
                Check(Capture.Events.Count > count, name + " original prefix executed");
                var prefix = Capture.Events.Skip(count).Select(entry => JsonSerializer.SerializeToElement(entry)).ToArray();
                Check(prefix.Last().GetProperty("operation").GetString() == "batch-begin", name + " stopped before unverified draw enqueue");
                Check(prefix.Count(row => row.GetProperty("operation").GetString() == "batch-flush") ==
                    (direction == GaussianBlur.Direction.Horizontal ? 1 : 0), name + " verified prefix pass count");
                Capture.Owner = "observer fixture unsupported direction cleanup";
                Reject(() => Draw.SpriteBatch.Draw(GameplayBuffers.Light, new Rectangle(0, 0, 320, 180), Color.White), name);
                Draw.SpriteBatch.End();
                return;
            }
            throw new InvalidOperationException("Expected original direction default shader rejection");
        }
        public static void Run(string path)
        {
            using var metadata = JsonDocument.Parse(File.ReadAllText(path));
            var definition = metadata.RootElement.GetProperty("GaussianBlur");
            GFX.FxGaussianBlur = new Effect("GFX.FxGaussianBlur", definition);
            var device = new GraphicsDevice(320, 180);
            Engine.Instance = new Engine { GraphicsDevice = device };
            Draw.SpriteBatch = new SpriteBatch(device);
            Capture.Owner = "original GameplayBuffers.Create Gaussian fixture";
            GameplayBuffers.Create();
            Check(GameplayBuffers.TempA.Target != GameplayBuffers.TempB.Target && GameplayBuffers.Light.Target != GameplayBuffers.TempA.Target,
                "distinct original allocations");

            Capture.Owner = "original GaussianBlur.Blur default";
            Returned(GaussianBlur.Blur(GameplayBuffers.Light, GameplayBuffers.TempA, GameplayBuffers.TempB), GameplayBuffers.TempB);
            foreach (var sample in new[] { GaussianBlur.Samples.Three, GaussianBlur.Samples.Five, GaussianBlur.Samples.Nine })
                foreach (bool clear in new[] { true, false })
                {
                    int number = sample == GaussianBlur.Samples.Three ? 3 : sample == GaussianBlur.Samples.Five ? 5 : 9;
                    Capture.Owner = $"original GaussianBlur.Blur samples={number} clear={clear.ToString().ToLowerInvariant()}";
                    Returned(GaussianBlur.Blur(GameplayBuffers.Light, GameplayBuffers.TempA, GameplayBuffers.TempB,
                        0.375f, clear, sample, 1.75f, GaussianBlur.Direction.Both, 0.125f), GameplayBuffers.TempB);
                }
            Capture.Owner = "original GaussianBlur.Blur asymmetric dimensions";
            Returned(GaussianBlur.Blur(GameplayBuffers.Light, GameplayBuffers.LightBuffer, GameplayBuffers.MirrorSources,
                0.625f, true, GaussianBlur.Samples.Five, 2.25f, alpha: 0.25f), GameplayBuffers.MirrorSources);
            Capture.Owner = "original GaussianBlur.Blur nonfinite";
            Returned(GaussianBlur.Blur(GameplayBuffers.Light, GameplayBuffers.TempA, GameplayBuffers.TempB,
                BitConverter.Int32BitsToSingle(unchecked((int)0xffc00001)), false, sampleScale: float.PositiveInfinity), GameplayBuffers.TempB);

            Capture.Owner = "observer rejection checks";
            Reject(() => new Effect("unknown", definition), "unknown shader");
            Reject(() => GFX.FxGaussianBlur.CurrentTechnique = GFX.FxGaussianBlur.Techniques["unknown"], "unknown technique");
            Reject(() => GFX.FxGaussianBlur.Parameters["unknown"].SetValue(0f), "unknown parameter");
            Reject(() => GFX.FxGaussianBlur.Parameters["fade"].SetValue(Vector2.Zero), "wrong parameter type");
            Reject(() => new RenderTarget2D(device, 1, 1, false, (SurfaceFormat)99, DepthFormat.None, 0, RenderTargetUsage.DiscardContents), "unknown target format");
            Reject(() => Draw.SpriteBatch.Begin(SpriteSortMode.Immediate, null, null, null, null, GFX.FxGaussianBlur), "unsupported batch operation");
            device.SetRenderTarget(GameplayBuffers.TempA);
            Draw.SpriteBatch.Begin(SpriteSortMode.Deferred, BlendState.AlphaBlend, SamplerState.PointClamp, DepthStencilState.Default,
                RasterizerState.CullNone, GFX.FxGaussianBlur);
            Reject(() => Draw.SpriteBatch.Draw(GameplayBuffers.TempA, new Rectangle(0, 0, 320, 180), Color.White), "target alias");
            Draw.SpriteBatch.End();

            Capture.Owner = "original GaussianBlur.Blur horizontal unsupported prefix";
            DirectionFailure(GaussianBlur.Direction.Horizontal, "horizontal default shader");
            Capture.Owner = "original GaussianBlur.Blur vertical unsupported prefix";
            DirectionFailure(GaussianBlur.Direction.Vertical, "vertical default shader");

            Capture.Owner = "original GaussianBlur.Blur null effect branch";
            var verifiedEffect = GFX.FxGaussianBlur;
            GFX.FxGaussianBlur = null;
            int before = Capture.Events.Count;
            var unchanged = GaussianBlur.Blur(GameplayBuffers.Light, GameplayBuffers.TempA, GameplayBuffers.TempB);
            Check(Capture.Events.Count == before && ReferenceEquals(unchanged, GameplayBuffers.Light.Target), "original null effect returns input without API calls");
            Capture.Owner = "observer fixture final cleanup";
            GFX.FxGaussianBlur = verifiedEffect;

            device.Texture = null;
            device.SetRenderTarget(null);
            Capture.Owner = "original GameplayBuffers.Unload Gaussian fixture";
            GameplayBuffers.Unload();
            Capture.Owner = "observer fixture foreign target lifetime";
            var foreign = new RenderTarget2D(new GraphicsDevice(1, 1), 1, 1, false, SurfaceFormat.Color, DepthFormat.None, 0, RenderTargetUsage.DiscardContents);
            foreign.Dispose();
            foreach (object entry in Capture.Events) Console.WriteLine(JsonSerializer.Serialize(entry));
            Console.WriteLine(JsonSerializer.Serialize(new { operation = "gaussian-summary", data = new { verifiedChecks = checks,
                claim = "Original GaussianBlur API only; default shader H/V unsupported; no BeforeRender, full Level, FNA quad, GPU, pixels or Vita" } }));
        }
    }
}
