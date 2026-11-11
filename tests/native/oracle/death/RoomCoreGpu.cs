using System;
using System.Collections.Generic;
using System.IO;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

namespace DeathOracle
{
    public static class GpuRecords
    {
        public static readonly List<(string Operation, object[] Arguments)> Commands = new();
        public static void Add(string operation, params object[] arguments) => Commands.Add((operation, arguments));
    }

    public static class LifecycleRecording
    {
        static readonly PresentationOracle.RecordingBatch batch = new();
        public static bool Active { get; private set; }
        public static readonly List<(Matrix Matrix, VertexPositionColor[] Vertices, int Count)> Wipes = new();
        public static PresentationOracle.RecordingBatch Batch => Active ? batch
            : throw new UnsupportedClosure("Recording render scope required: Monocle.Draw.cs:SpriteBatch");

        public static void Begin()
        {
            if (Active) throw new InvalidOperationException("Nested lifecycle render");
            batch.Calls.Clear();
            batch.Geometry.Calls.Clear();
            Wipes.Clear();
            Active = true;
        }

        public static void End()
        {
            if (!Active) throw new InvalidOperationException("No lifecycle render scope");
            Active = false;
        }

        public static void Vertices<T>(Matrix matrix, T[] vertices, int count, Effect effect, BlendState blend) where T : struct, IVertexType
        {
            if (!Active || typeof(T) != typeof(VertexPositionColor) || count != 36 || vertices.Length != count
                || effect != null || blend != null || matrix.M11 != 1f || matrix.M22 != 1f || matrix.M33 != 1f || matrix.M44 != 1f
                || matrix.M12 != 0f || matrix.M13 != 0f || matrix.M14 != 0f || matrix.M21 != 0f || matrix.M23 != 0f || matrix.M24 != 0f
                || matrix.M31 != 0f || matrix.M32 != 0f || matrix.M34 != 0f || matrix.M41 != 0f || matrix.M42 != 0f || matrix.M43 != 0f)
                throw new UnsupportedClosure("Excluded recording GPU vertex operation");
            Wipes.Add((matrix, (VertexPositionColor[])((VertexPositionColor[])(object)vertices).Clone(), count));
        }
    }
}

namespace Microsoft.Xna.Framework
{
    public static class TitleContainer
    {
        public static Stream OpenStream(string path) => File.OpenRead(path);
    }
}

namespace Microsoft.Xna.Framework.Graphics
{
    internal static partial class FNA3D
    {
        internal struct FNA3D_BlendState
        {
            public BlendFunction alphaBlendFunction, colorBlendFunction;
            public Blend alphaDestinationBlend, alphaSourceBlend, colorDestinationBlend, colorSourceBlend;
            public ColorWriteChannels colorWriteEnable, colorWriteEnable1, colorWriteEnable2, colorWriteEnable3;
            public Color blendFactor;
            public int multiSampleMask;
        }

        internal struct FNA3D_RasterizerState
        {
            public CullMode cullMode;
            public FillMode fillMode;
            public float depthBias, slopeScaleDepthBias;
            public byte multiSampleAntiAlias, scissorTestEnable;
        }

        internal struct FNA3D_DepthStencilState
        {
            public byte depthBufferEnable, depthBufferWriteEnable, stencilEnable, twoSidedStencilMode;
            public CompareFunction depthBufferFunction, stencilFunction, ccwStencilFunction;
            public StencilOperation stencilPass, stencilFail, stencilDepthBufferFail;
            public StencilOperation ccwStencilPass, ccwStencilFail, ccwStencilDepthBufferFail;
            public int stencilMask, stencilWriteMask, referenceStencil;
        }

        internal struct FNA3D_PresentationParameters
        {
            public int backBufferWidth, backBufferHeight, multiSampleCount;
            public SurfaceFormat backBufferFormat;
            public IntPtr deviceWindowHandle;
            public byte isFullScreen;
            public DepthFormat depthStencilFormat;
            public PresentInterval presentationInterval;
            public DisplayOrientation displayOrientation;
            public RenderTargetUsage renderTargetUsage;
        }
    }

    public sealed class GraphicsDevice
    {
        private readonly HashSet<WeakReference> resources = new();
        public Viewport Viewport = new(0, 0, 1920, 1080);
        public bool IsDisposed { get; private set; }
        public RenderTarget2D RenderTarget { get; private set; }

        internal void AddResourceReference(WeakReference resource)
        {
            if (!resources.Add(resource)) throw new InvalidOperationException("Duplicate GPU resource registration");
            DeathOracle.GpuRecords.Add("resource-add", resource);
        }

        internal void RemoveResourceReference(WeakReference resource)
        {
            if (!resources.Remove(resource)) throw new InvalidOperationException("Unknown GPU resource removal");
            DeathOracle.GpuRecords.Add("resource-remove", resource);
        }

        public void SetRenderTarget(RenderTarget2D target)
        {
            RenderTarget = target;
            DeathOracle.GpuRecords.Add("set-render-target", target);
        }

        public void Clear(Color color) => DeathOracle.GpuRecords.Add("clear", RenderTarget, color);
    }

    public enum SurfaceFormat { Color }
    public enum DepthFormat { None, Depth24Stencil8 }
    public enum RenderTargetUsage { DiscardContents, PreserveContents }

    public sealed class RenderTarget2D : Texture2D
    {
        public Rectangle Bounds => new(0, 0, Width, Height);

        public RenderTarget2D(GraphicsDevice device, int width, int height, bool mipMap, SurfaceFormat format,
            DepthFormat depthFormat, int multiSampleCount, RenderTargetUsage usage)
        {
            GraphicsDevice = device;
            Width = width;
            Height = height;
            DeathOracle.GpuRecords.Add("create-render-target", this, width, height, mipMap, format, depthFormat, multiSampleCount, usage);
        }
    }

    public sealed class SamplerState : GraphicsResource
    {
        public static readonly SamplerState PointClamp = new("PointClamp");
        public static readonly SamplerState PointWrap = new("PointWrap");
        public static readonly SamplerState LinearClamp = new("LinearClamp");
        private SamplerState(string name) { Name = name; }
    }
}

namespace Celeste
{
    public static class Distort
    {
        public static Vector2 AnxietyOrigin;
        public static float Anxiety;
        public static float GameRate = 1f;
        public static float WaterSine;
        public static float WaterCameraY;
        public static float WaterAlpha = 1f;
        public static float WaterSineDirection = 1f;
        public static void Render(Texture2D source, Texture2D map, bool hasDistortion) =>
            throw new DeathOracle.UnsupportedClosure("Recording GPU distortion boundary: rendering excluded");
    }
}

namespace Monocle
{
    public static class VirtualContent
    {
        private static readonly HashSet<VirtualAsset> assets = new();

        public static VirtualRenderTarget CreateRenderTarget(string name, int width, int height, int multiSampleCount = 0,
            bool depth = false, bool preserve = false)
        {
            var asset = new VirtualRenderTarget(name, width, height, multiSampleCount, depth, preserve);
            if (!assets.Add(asset)) throw new InvalidOperationException("Duplicate virtual GPU resource");
            DeathOracle.GpuRecords.Add("virtual-resource-add", asset);
            return asset;
        }

        internal static void Remove(VirtualAsset asset)
        {
            if (!assets.Remove(asset)) throw new InvalidOperationException("Unknown virtual GPU resource removal");
            DeathOracle.GpuRecords.Add("virtual-resource-remove", asset);
        }
    }
}
