using System;
using System.Collections.Generic;
using Microsoft.Xna.Framework;
using Microsoft.Xna.Framework.Graphics;

namespace PresentationOracle
{
    public struct SourceVector3 { public float X, Y, Z; }
    public struct VertexPositionColorTexture4
    {
        public SourceVector3 Position0, Position1, Position2, Position3;
        public Color Color0, Color1, Color2, Color3;
        public Vector2 TextureCoordinate0, TextureCoordinate1, TextureCoordinate2, TextureCoordinate3;
    }
    public unsafe partial class OriginalSpriteBatch
    {
        public readonly List<VertexPositionColorTexture4> Calls = new();
        void CheckBegin(string method)
        {
            if (method != "Draw") throw new Exception("Unprovided original GPU service");
        }
        void PushSprite(Texture2D texture, float sourceX, float sourceY, float sourceW, float sourceH, float destinationX, float destinationY,
                        float destinationW, float destinationH, Color color, float originX, float originY, float rotationSin, float rotationCos, float depth, byte effects)
        {
            VertexPositionColorTexture4 vertices = default;
            GenerateVertexInfo(&vertices, sourceX, sourceY, sourceW, sourceH, destinationX, destinationY, destinationW, destinationH,
                               color, originX, originY, rotationSin, rotationCos, depth, effects);
            Calls.Add(vertices);
        }
    }
}
