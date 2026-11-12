// Strict draw-profile recording surface for the room-transition update+DRAW contract.
// Compiled ONLY by the separate draw profile (and its recorder self-check harness) in
// place of the loose recording shims: scalar SpriteBatch draws are recorded with the
// original FNA vertex geometry instead of throwing, atlas metadata retains the texture
// sheet identity with real registered dimensions, and batch begin/end state is recorded
// in order. Missing sheet metadata fails loudly; no synthetic texture dimensions and no
// silently omitted draws. The accepted CPU/presentation profiles never compile this file.

using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;
using Monocle;

namespace Microsoft.Xna.Framework.Graphics
{
    public class Texture2D : GraphicsResource
    {
        public int Width, Height;
        public override string ToString() => Name;
    }
}

namespace PrivateRuntime
{
    internal static class Environment
    {
        public static int TickCount => System.Environment.TickCount;
        public static string GetResourceString(string value, params object[] args) => string.Format(value, args);
    }
}

namespace PresentationOracle
{
    public sealed class TracedRandom : PrivateRuntime.Random
    {
        public static Action<TracedRandom, string> Observer;
        public int Calls;
        public TracedRandom() : base() { }
        public TracedRandom(int seed) : base(seed) { }
        public override double NextDouble() { Calls++; double value = base.NextDouble(); Observer?.Invoke(this, "NextDouble"); return value; }
        public override int Next(int max) { Calls++; int value = base.Next(max); Observer?.Invoke(this, "Next"); return value; }
    }

    public sealed class SheetDimensions
    {
        static readonly Dictionary<string, (int Width, int Height)> registered = new();

        public static void Register(string sheet, int width, int height)
        {
            if (string.IsNullOrEmpty(sheet) || width <= 0 || height <= 0)
                throw new InvalidOperationException("Atlas sheet dimensions must be positive: " + sheet);
            if (registered.TryGetValue(sheet, out var existing))
            {
                if (existing != (width, height))
                    throw new InvalidOperationException("Conflicting atlas sheet dimensions: " + sheet);
                return;
            }
            registered.Add(sheet, (width, height));
        }

        public static (int Width, int Height) Require(string sheet)
        {
            if (!registered.TryGetValue(sheet, out var dimensions))
                throw new InvalidOperationException("Unregistered atlas sheet: " + sheet);
            return dimensions;
        }

        public static int Count => registered.Count;
    }

    public sealed class BatchState
    {
        public const string Begin = "begin";
        public string Operation = Begin;
        public string SortMode;
        public string Blend, Sampler, DepthStencil, Rasterizer;
        public bool HasEffect;
        public float[] Matrix;
        public int DrawStart, DrawEnd;
    }

    public record RecordedDraw(object Texture, Vector2 Position, Rectangle Clip, Color Color,
                               float Rotation, Vector2 Origin, Vector2 Scale, SpriteEffects Effects);

    public sealed class RecordingBatch
    {
        public readonly List<RecordedDraw> Calls = new();
        public readonly OriginalSpriteBatch Geometry = new();
        public readonly List<BatchState> States = new();
        BatchState open;

        void RequireOpen(string operation)
        {
            if (open == null)
                throw new InvalidOperationException("Excluded SpriteBatch " + operation + " outside an open batch");
        }

        static void RequireSubmissionOrder(SpriteSortMode sortMode, Effect effect)
        {
            if (!Enum.IsDefined(typeof(SpriteSortMode), sortMode))
                throw new InvalidOperationException("Unknown SpriteSortMode: " + sortMode.ToString());
            if (sortMode != SpriteSortMode.Deferred)
                throw new InvalidOperationException("Excluded SpriteBatch sort mode: " + sortMode.ToString());
            if (effect != null)
                throw new InvalidOperationException("Excluded SpriteBatch effect submission");
        }

        public void Begin(SpriteSortMode sortMode, BlendState blendState, SamplerState samplerState,
                          DepthStencilState depthStencilState, RasterizerState rasterizerState, Effect effect,
                          Matrix transformMatrix)
        {
            RequireSubmissionOrder(sortMode, effect);
            if (open != null) throw new InvalidOperationException("Nested SpriteBatch begin");
            open = new BatchState { SortMode = sortMode.ToString(), Blend = blendState?.Name, Sampler = samplerState?.Name,
                DepthStencil = depthStencilState?.Name, Rasterizer = rasterizerState?.Name, HasEffect = effect != null,
                Matrix = new[] { transformMatrix.M11, transformMatrix.M12, transformMatrix.M13, transformMatrix.M14,
                    transformMatrix.M21, transformMatrix.M22, transformMatrix.M23, transformMatrix.M24,
                    transformMatrix.M31, transformMatrix.M32, transformMatrix.M33, transformMatrix.M34,
                    transformMatrix.M41, transformMatrix.M42, transformMatrix.M43, transformMatrix.M44 },
                DrawStart = Calls.Count };
            States.Add(open);
        }

        public void Begin(SpriteSortMode sortMode, BlendState blendState, SamplerState samplerState,
                          DepthStencilState depthStencilState, RasterizerState rasterizerState, Effect effect)
            => Begin(sortMode, blendState, samplerState, depthStencilState, rasterizerState, effect, Matrix.Identity);

        public void End()
        {
            if (open == null) throw new InvalidOperationException("SpriteBatch end without an open batch");
            open.DrawEnd = Calls.Count;
            open = null;
        }

        public void Draw(Texture2D texture, Vector2 position, Rectangle clip, Color color, float rotation,
                         Vector2 origin, float scale, SpriteEffects effects, float depth)
        {
            RequireOpen("draw");
            Vector2 uniform = new(scale, scale);
            Calls.Add(new(texture, position, clip, color, rotation, origin, uniform, effects));
            Geometry.Draw(texture, position, clip, color, rotation, origin, uniform, effects, depth);
        }

        public void Draw(Texture2D texture, Vector2 position, Rectangle clip, Color color, float rotation,
                         Vector2 origin, Vector2 scale, SpriteEffects effects, float depth)
        {
            RequireOpen("draw");
            Calls.Add(new(texture, position, clip, color, rotation, origin, scale, effects));
            Geometry.Draw(texture, position, clip, color, rotation, origin, scale, effects, depth);
        }
    }
}

namespace Monocle
{
    public sealed class VirtualTexture
    {
        public int Width, Height;
        public Texture2D Texture;
        public string Path;
        public void Dispose() { }
    }

    public partial class Atlas
    {
        static readonly Dictionary<string, VirtualTexture> sheets = new();

        public void AddMetadata(string name, string sheet, int[] rectangle)
        {
            var dimensions = PresentationOracle.SheetDimensions.Require(sheet);
            if (!sheets.TryGetValue(sheet, out var texture))
            {
                texture = new VirtualTexture { Width = dimensions.Width, Height = dimensions.Height,
                    Texture = new Texture2D { Name = sheet, Width = dimensions.Width, Height = dimensions.Height } };
                sheets.Add(sheet, texture);
            }
            this[name] = new MTexture(new MTexture(texture), name,
                new Rectangle(rectangle[0], rectangle[1], rectangle[2], rectangle[3]),
                new Vector2(-rectangle[4], -rectangle[5]), rectangle[6], rectangle[7]);
        }
    }
}
