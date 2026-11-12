using System;
using System.Collections.Generic;
using System.Linq;
using System.Reflection;
using System.Text.Json;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

namespace DeathOracle
{
    public sealed class UnsupportedClosure : InvalidOperationException
    { public UnsupportedClosure(string message) : base(message) { } }
}

namespace PresentationOracle
{
    public sealed class TracedRandom
    { public TracedRandom() => throw new InvalidOperationException("Random excluded from render API slice"); }
}

namespace RendergraphOracle
{
    public static class Capture
    {
        public static readonly List<object> Events = new();
        public static string Owner = "fixture";
        public static int[] Bits(params float[] values) => values.Select(BitConverter.SingleToInt32Bits).ToArray();
        public static int[] MatrixBits(Matrix m) => Bits(m.M11, m.M12, m.M13, m.M14, m.M21, m.M22, m.M23, m.M24,
            m.M31, m.M32, m.M33, m.M34, m.M41, m.M42, m.M43, m.M44);
        public static void Add(string operation, object data) => Events.Add(new { sequence = Events.Count, operation, owner = Owner, data });

        public static Dictionary<string, object> State(object state)
        {
            if (state == null || state.GetType() != typeof(BlendState) && state.GetType() != typeof(SamplerState)
                && state.GetType() != typeof(DepthStencilState) && state.GetType() != typeof(RasterizerState))
                throw new InvalidOperationException("Excluded graphics state type");
            var result = new Dictionary<string, object>();
            foreach (var property in state.GetType().GetProperties(BindingFlags.Public | BindingFlags.Instance)
                .Where(p => p.DeclaringType == state.GetType()).OrderBy(p => p.Name))
            {
                object value = property.GetValue(state);
                if (value is Enum enumeration)
                {
                    var type = value.GetType();
                    long bits = Convert.ToInt64(value);
                    long mask = Enum.GetValues(type).Cast<object>().Aggregate(0L, (a, b) => a | Convert.ToInt64(b));
                    if (type.IsDefined(typeof(FlagsAttribute), false) ? (bits & ~mask) != 0 : !Enum.IsDefined(type, value))
                        throw new InvalidOperationException("Unknown graphics state enum: " + property.Name);
                    value = enumeration.ToString();
                }
                else if (value is float f) value = new { float32Bits = BitConverter.SingleToInt32Bits(f) };
                else if (value is Color c) value = c.PackedValue;
                else if (!(value is int || value is bool || state is SamplerState && property.Name == "Filter" && value is string))
                    throw new InvalidOperationException("Excluded graphics state value: " + property.Name);
                result.Add(property.Name, value);
            }
            return result;
        }
    }
}

namespace Microsoft.Xna.Framework.Graphics
{
    public enum SurfaceFormat { Color }
    public enum DepthFormat { None, Depth24Stencil8 }
    public enum RenderTargetUsage { DiscardContents, PreserveContents }
    public enum PrimitiveType { TriangleList, TriangleStrip }

    public sealed class SamplerState
    {
        public static readonly SamplerState PointClamp = new("Point", TextureAddressMode.Clamp);
        public static readonly SamplerState LinearClamp = new("Linear", TextureAddressMode.Clamp);
        public static readonly SamplerState LinearWrap = new("Linear", TextureAddressMode.Wrap);
        public string Filter { get; }
        public TextureAddressMode AddressU { get; }
        public TextureAddressMode AddressV => AddressU;
        public TextureAddressMode AddressW => AddressU;
        public int MaxAnisotropy => 4;
        public int MaxMipLevel => 0;
        public float MipMapLevelOfDetailBias => 0f;
        SamplerState(string filter, TextureAddressMode address) { Filter = filter; AddressU = address; }
    }
    public class Texture2D
    {
        public string Id { get; internal set; }
        public int Width { get; internal set; }
        public int Height { get; internal set; }
        public bool IsDisposed { get; internal set; }
        public GraphicsDevice GraphicsDevice { get; internal set; }
        public Rectangle Bounds => new(0, 0, Width, Height);
    }

    public sealed class RenderTarget2D : Texture2D
    {
        public RenderTarget2D(GraphicsDevice device, int width, int height, bool mipMap, SurfaceFormat format,
            DepthFormat depthFormat, int multiSampleCount, RenderTargetUsage usage)
        {
            if (device == null || width <= 0 || height <= 0 || mipMap || format != SurfaceFormat.Color
                || depthFormat != DepthFormat.None || multiSampleCount != 0 || usage != RenderTargetUsage.DiscardContents)
                throw new InvalidOperationException("Excluded render target allocation");
            GraphicsDevice = device;
            Width = width;
            Height = height;
            Id = device.AllocateId();
            RendergraphOracle.Capture.Add("create-render-target", new { Id, Width, Height, mipMap,
                format = format.ToString(), depthFormat = depthFormat.ToString(), multiSampleCount, usage = usage.ToString() });
        }

        public void Dispose()
        {
            GraphicsDevice.Require(this);
            if (GraphicsDevice.Target == this) throw new InvalidOperationException("Cannot dispose bound target");
            IsDisposed = true;
            RendergraphOracle.Capture.Add("dispose-render-target", new { Id });
        }
    }

    public sealed class GraphicsDevice
    {
        static int nextId;
        Viewport viewport;
        Rectangle scissor;
        readonly int backWidth, backHeight;
        internal void AddResourceReference(WeakReference resource) => throw new InvalidOperationException("Excluded resource registration");
        internal void RemoveResourceReference(WeakReference resource) => throw new InvalidOperationException("Excluded resource removal");
        public bool IsDisposed => false;
        public RenderTarget2D Target { get; private set; }
        public BlendState BlendState = BlendState.Opaque;
        public SamplerState SamplerState = SamplerState.LinearWrap;
        public DepthStencilState DepthStencilState = DepthStencilState.Default;
        public RasterizerState RasterizerState = RasterizerState.CullCounterClockwise;
        internal EffectPass Applied;
        internal object AppliedSnapshot;
        internal bool BatchOpen;
        public Texture2D Texture;

        public GraphicsDevice(int width, int height)
        {
            if (width <= 0 || height <= 0) throw new InvalidOperationException("Invalid declared backbuffer");
            backWidth = width; backHeight = height;
            viewport = new Viewport(0, 0, width, height);
            scissor = new Rectangle(0, 0, width, height);
        }

        internal string AllocateId() => "target-" + ++nextId;
        public void Require(Texture2D texture)
        {
            if (texture == null || texture.GetType() != typeof(RenderTarget2D) || texture.GraphicsDevice != this || texture.IsDisposed)
                throw new InvalidOperationException("Unknown, foreign or disposed texture");
        }

        public Viewport Viewport
        {
            get => viewport;
            set
            {
                if (value.Width <= 0 || value.Height <= 0) throw new InvalidOperationException("Invalid viewport");
                viewport = value;
                RendergraphOracle.Capture.Add("viewport", Context());
            }
        }

        public Rectangle ScissorRectangle
        {
            get => scissor;
            set
            {
                if (value.Width < 0 || value.Height < 0) throw new InvalidOperationException("Invalid scissor");
                scissor = value;
                RendergraphOracle.Capture.Add("scissor", Context());
            }
        }

        public object Context() => new { target = Target?.Id ?? "declared-backbuffer", viewport = new[] { viewport.X, viewport.Y, viewport.Width, viewport.Height },
            depthRangeFloat32Bits = RendergraphOracle.Capture.Bits(viewport.MinDepth, viewport.MaxDepth),
            scissor = new[] { scissor.X, scissor.Y, scissor.Width, scissor.Height } };

        public void SetRenderTarget(RenderTarget2D target)
        {
            if (target != null) Require(target);
            if (BatchOpen) throw new InvalidOperationException("Excluded target switch inside batch");
            if (Target != target)
            {
                Target = target;
                viewport = new Viewport(0, 0, target?.Width ?? backWidth, target?.Height ?? backHeight);
                scissor = new Rectangle(0, 0, viewport.Width, viewport.Height);
            }
            RendergraphOracle.Capture.Add("set-render-target", Context());
        }

        public void Clear(Color color) => RendergraphOracle.Capture.Add("clear", new { context = Context(), rgba = color.PackedValue });

        public object States() => new { blend = RendergraphOracle.Capture.State(BlendState), sampler = RendergraphOracle.Capture.State(SamplerState),
            depthStencil = RendergraphOracle.Capture.State(DepthStencilState), rasterizer = RendergraphOracle.Capture.State(RasterizerState) };

        public void DrawUserIndexedPrimitives<T>(PrimitiveType type, T[] vertices, int vertexOffset, int vertexCount,
            int[] indices, int indexOffset, int primitiveCount) where T : struct, IVertexType
        {
            if (BatchOpen || type != PrimitiveType.TriangleList || typeof(T) != typeof(VertexPositionColor)
                || vertices == null || indices == null || vertexOffset < 0 || vertexCount <= 0 || vertexOffset > vertices.Length - vertexCount
                || indexOffset < 0 || primitiveCount <= 0 || primitiveCount > (indices.Length - indexOffset) / 3)
                throw new InvalidOperationException("Excluded indexed primitive operation/type/range");
            var selected = indices.Skip(indexOffset).Take(checked(primitiveCount * 3)).ToArray();
            if (selected.Any(i => i < 0 || i >= vertexCount)) throw new InvalidOperationException("Index outside submitted vertices");
            if (Applied == null) throw new InvalidOperationException("Verified applied effect required");
            var states = States();
            var effect = AppliedSnapshot;
            var geometry = ((VertexPositionColor[])(object)vertices).Skip(vertexOffset).Take(vertexCount)
                .Select(v => new { positionFloat32Bits = RendergraphOracle.Capture.Bits(v.Position.X, v.Position.Y, v.Position.Z), rgba = v.Color.PackedValue }).ToArray();
            RendergraphOracle.Capture.Add("indexed-primitives", new { context = Context(), states, effect,
                primitiveType = type.ToString(), vertexOffset, vertexCount, indexOffset, primitiveCount, indices = selected, vertices = geometry });
        }
    }

    public sealed class EffectParameter
    {
        readonly JsonElement definition;
        object value;
        internal EffectParameter(JsonElement definition)
        {
            this.definition = definition;
            int type = definition.GetProperty("type").GetInt32();
            if (type == 3) value = definition.GetProperty("default_float32_bits").EnumerateArray().Select(v => v.GetInt32()).ToArray();
            else if (type == 10) value = definition.GetProperty("default_sampler_states");
            else if (type != 5) throw new InvalidOperationException("Excluded effect parameter type");
        }
        public void SetValue(Vector2 vector)
        {
            if (definition.GetProperty("type").GetInt32() != 3 || definition.GetProperty("class").GetInt32() != 1
                || definition.GetProperty("columns").GetInt32() != 2 || definition.GetProperty("rows").GetInt32() != 1)
                throw new InvalidOperationException("Effect parameter is not float2");
            value = RendergraphOracle.Capture.Bits(vector.X, vector.Y);
        }
        public void SetValue(float scalar)
        {
            if (definition.GetProperty("type").GetInt32() != 3 || definition.GetProperty("class").GetInt32() != 0
                || definition.GetProperty("columns").GetInt32() != 1 || definition.GetProperty("rows").GetInt32() != 1)
                throw new InvalidOperationException("Effect parameter is not float");
            value = RendergraphOracle.Capture.Bits(scalar);
        }
        public void SetValue(Matrix matrix)
        {
            if (definition.GetProperty("type").GetInt32() != 3 || definition.GetProperty("rows").GetInt32() != 4
                || definition.GetProperty("columns").GetInt32() != 4 || definition.GetProperty("class").GetInt32() != 2)
                throw new InvalidOperationException("Effect parameter is not float4x4");
            value = RendergraphOracle.Capture.MatrixBits(matrix);
        }
        internal object Snapshot() => new { definition, value };
    }

    public sealed class Effect
    {
        public readonly string Identity;
        internal readonly JsonElement Definition;
        public readonly Dictionary<string, EffectParameter> Parameters = new();
        public readonly Dictionary<string, EffectTechnique> Techniques = new();
        EffectTechnique technique;
        public EffectTechnique CurrentTechnique
        {
            get => technique;
            set
            {
                if (value == null || value.Effect != this) throw new InvalidOperationException("Unknown effect technique");
                technique = value;
            }
        }
        internal Effect(string identity, JsonElement definition)
        {
            string expected = identity switch {
                "GFX.FxDither" => "4e572804560609ef9a3e035a3f7fe6dc8b3802ebcee1dbeb05d1552b9813bf4d",
                "GFX.FxPrimitive" => "37b3975f2d860d95bbbb7ce7a4e7233c3e0508bd672627c967d63768de005c6f",
                "GFX.FxGaussianBlur" => "4bc39e8b3498a87c6143e601cd2894e06522c42e7262a54e7cf1bbfb37240944",
                _ => throw new InvalidOperationException("Unknown shader identity") };
            if (definition.GetProperty("resource_sha256").GetString() != expected)
                throw new InvalidOperationException("Unverified shader resource");
            Identity = identity; Definition = definition;
            foreach (var item in definition.GetProperty("parameters").EnumerateObject()) Parameters.Add(item.Name, new EffectParameter(item.Value));
            foreach (var item in definition.GetProperty("techniques").EnumerateObject()) Techniques.Add(item.Name, new EffectTechnique(this, item.Name, item.Value));
            technique = Techniques.Values.First();
        }
    }

    public sealed class EffectTechnique
    {
        internal readonly Effect Effect;
        internal readonly string Name;
        public readonly List<EffectPass> Passes = new();
        internal EffectTechnique(Effect effect, string name, JsonElement definition)
        {
            Effect = effect; Name = name;
            int index = 0;
            foreach (var pass in definition.EnumerateArray()) Passes.Add(new EffectPass(this, index++, pass));
        }
    }

    public sealed class EffectPass
    {
        readonly EffectTechnique technique;
        readonly int index;
        readonly JsonElement definition;
        internal EffectPass(EffectTechnique technique, int index, JsonElement definition)
        { this.technique = technique; this.index = index; this.definition = definition; }
        internal object Snapshot()
        {
            if (technique.Effect.CurrentTechnique != technique) throw new InvalidOperationException("Effect technique changed before apply/submission");
            return new { identity = technique.Effect.Identity, resource = technique.Effect.Definition.GetProperty("resource"),
                resourceSha256 = technique.Effect.Definition.GetProperty("resource_sha256"),
                effectSha256 = technique.Effect.Definition.GetProperty("effect_sha256"), technique = technique.Name,
                passIndex = index, pass = definition, parameters = technique.Effect.Parameters.ToDictionary(p => p.Key, p => p.Value.Snapshot()) };
        }
        public void Apply()
        {
            object snapshot = Snapshot();
            var device = Monocle.Engine.Instance.GraphicsDevice;
            var states = device.States();
            if (device.Texture != null) device.Require(device.Texture);
            device.Applied = this;
            device.AppliedSnapshot = snapshot;
            RendergraphOracle.Capture.Add("effect-apply", new { effect = snapshot, context = device.Context(), states,
                textureSlot0 = device.Texture?.Id, binding = "API texture slot; shader CTAB registers in pass provenance" });
        }
    }

    public sealed class SpriteBatch
    {
        readonly GraphicsDevice device;
        readonly List<(Texture2D Texture, Vector2 Position, Color Color, string Owner, Rectangle? Destination)> pending = new();
        Effect effect;
        Matrix matrix;
        BlendState blend;
        SamplerState sampler;
        DepthStencilState depth;
        RasterizerState rasterizer;
        bool open;
        public SpriteBatch(GraphicsDevice device) { this.device = device; }
        public void Begin(SpriteSortMode mode, BlendState blend, SamplerState sampler, DepthStencilState depth,
            RasterizerState rasterizer, Effect effect) => Begin(mode, blend, sampler, depth, rasterizer, effect, Matrix.Identity);
        public void Begin(SpriteSortMode mode, BlendState blend, SamplerState sampler, DepthStencilState depth,
            RasterizerState rasterizer, Effect effect, Matrix matrix)
        {
            if (open || mode != SpriteSortMode.Deferred) throw new InvalidOperationException("Excluded batch mode or nested Begin");
            var resolvedBlend = blend ?? BlendState.AlphaBlend;
            var resolvedSampler = sampler ?? SamplerState.LinearClamp;
            var resolvedDepth = depth ?? DepthStencilState.None;
            var resolvedRasterizer = rasterizer ?? RasterizerState.CullCounterClockwise;
            var states = new { blend = RendergraphOracle.Capture.State(resolvedBlend), sampler = RendergraphOracle.Capture.State(resolvedSampler),
                depthStencil = RendergraphOracle.Capture.State(resolvedDepth), rasterizer = RendergraphOracle.Capture.State(resolvedRasterizer) };
            if (effect != null) foreach (var pass in effect.CurrentTechnique.Passes) pass.Snapshot();
            this.effect = effect; this.matrix = matrix; this.blend = resolvedBlend; this.sampler = resolvedSampler;
            this.depth = resolvedDepth; this.rasterizer = resolvedRasterizer;
            open = true; device.BatchOpen = true;
            RendergraphOracle.Capture.Add("batch-begin", new { sortMode = mode.ToString(), effect = effect?.Identity, states,
                matrixFloat32Bits = RendergraphOracle.Capture.MatrixBits(matrix), context = device.Context() });
        }
        public void Draw(Texture2D texture, Vector2 position, Color color)
        {
            if (!open) throw new InvalidOperationException("Draw outside batch");
            if (effect == null || pending.Count != 0) throw new InvalidOperationException("Only single-command verified-effect batch is closed");
            device.Require(texture);
            pending.Add((texture, position, color, RendergraphOracle.Capture.Owner, null));
            RendergraphOracle.Capture.Add("batch-enqueue", new { texture = texture.Id, dimensions = new[] { texture.Width, texture.Height },
                positionFloat32Bits = RendergraphOracle.Capture.Bits(position.X, position.Y), rgba = color.PackedValue });
        }
        public void Draw(Texture2D texture, Rectangle destination, Color color)
        {
            if (!open) throw new InvalidOperationException("Draw outside batch");
            if (effect == null) throw new InvalidOperationException("Unsupported default SpriteBatch shader");
            if (pending.Count != 0 || destination.Width <= 0 || destination.Height <= 0)
                throw new InvalidOperationException("Excluded rectangle batch/range");
            device.Require(texture);
            if (texture == device.Target) throw new InvalidOperationException("Unsupported target alias hazard");
            pending.Add((texture, Vector2.Zero, color, RendergraphOracle.Capture.Owner, destination));
            RendergraphOracle.Capture.Add("batch-enqueue", new { texture = texture.Id, dimensions = new[] { texture.Width, texture.Height },
                destinationRectangle = new[] { destination.X, destination.Y, destination.Width, destination.Height }, rgba = color.PackedValue,
                boundary = "observer-owned RectangleDraw API adapter; no original FNA quad generation" });
        }
        public void End()
        {
            if (!open) throw new InvalidOperationException("End outside batch");
            foreach (var draw in pending) device.Require(draw.Texture);
            if (effect != null) foreach (var pass in effect.CurrentTechnique.Passes) pass.Snapshot();
            RendergraphOracle.Capture.State(blend); RendergraphOracle.Capture.State(sampler);
            RendergraphOracle.Capture.State(depth); RendergraphOracle.Capture.State(rasterizer);
            device.BlendState = blend; device.SamplerState = sampler; device.DepthStencilState = depth; device.RasterizerState = rasterizer;
            if (pending.Count > 0)
            {
                foreach (var pass in effect.CurrentTechnique.Passes)
                    foreach (var draw in pending)
                    {
                        device.Texture = draw.Texture;
                        pass.Apply();
                         if (draw.Destination is Rectangle destination)
                             RendergraphOracle.Capture.Add("batch-flush", new { owner = draw.Owner, texture = draw.Texture.Id,
                                 dimensions = new[] { draw.Texture.Width, draw.Texture.Height },
                                 destinationRectangle = new[] { destination.X, destination.Y, destination.Width, destination.Height }, rgba = draw.Color.PackedValue,
                                 effect = pass.Snapshot(), states = device.States(), context = device.Context(), matrixFloat32Bits = RendergraphOracle.Capture.MatrixBits(matrix),
                                 boundary = "observer-owned RectangleDraw API adapter; built-in vertex shader, original FNA quad and GPU not executed" });
                         else RendergraphOracle.Capture.Add("batch-flush", new { owner = draw.Owner, texture = draw.Texture.Id,
                            dimensions = new[] { draw.Texture.Width, draw.Texture.Height },
                            positionFloat32Bits = RendergraphOracle.Capture.Bits(draw.Position.X, draw.Position.Y), rgba = draw.Color.PackedValue,
                            effect = pass.Snapshot(), states = device.States(), context = device.Context(), matrixFloat32Bits = RendergraphOracle.Capture.MatrixBits(matrix),
                            boundary = "SpriteBatch API command only; built-in vertex shader and GPU geometry not executed" });
                    }
            }
            RendergraphOracle.Capture.Add("batch-end", new { commands = pending.Count, context = device.Context() });
            pending.Clear(); open = false; device.BatchOpen = false;
        }
    }
}

namespace Monocle
{
    public abstract class VirtualAsset
    {
        public string Name;
        public int Width, Height;
        internal abstract void Unload();
        internal abstract void Reload();
        public abstract void Dispose();
    }
    public static class VirtualContent
    {
        static readonly HashSet<VirtualRenderTarget> assets = new();
        public static VirtualRenderTarget CreateRenderTarget(string name, int width, int height)
        {
            if (string.IsNullOrEmpty(name) || width <= 0 || height <= 0) throw new InvalidOperationException("Invalid virtual target");
            var target = new VirtualRenderTarget(name, width, height, 0, false, false);
            assets.Add(target);
            RendergraphOracle.Capture.Add("virtual-target-add", new { name, width, height, target = target.Target.Id });
            return target;
        }
        public static void Remove(VirtualAsset asset)
        {
            if (!(asset is VirtualRenderTarget target) || !assets.Remove(target)) throw new InvalidOperationException("Unknown virtual target");
            RendergraphOracle.Capture.Add("virtual-target-remove", new { target.Name });
        }
    }
    public sealed class Engine
    {
        public static Engine Instance;
        public static Engine Graphics => Instance;
        public GraphicsDevice GraphicsDevice;
    }
    public static class Draw { public static SpriteBatch SpriteBatch; }
    public class Scene { }
    public class Renderer { public virtual void Render(Scene scene) => throw new InvalidOperationException("Excluded renderer"); }
}
