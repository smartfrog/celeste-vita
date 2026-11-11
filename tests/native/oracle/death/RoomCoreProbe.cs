using System;

namespace Microsoft.Xna.Framework.Graphics
{
    internal static partial class FNA3D
    {
        internal struct FNA3D_Viewport
        {
            public int x, y, w, h;
            public float minDepth, maxDepth;
        }
    }
}

static class RoomCoreProbe
{
    static void Main(string[] args)
    {
        if (args.Length > 0 && args[0] == "native-abi-metadata-audit")
            DeathOracle.NativeAbiMetadataAudit.Run(args);
        else if (args.Length > 0 && args[0].StartsWith("native-abi-", StringComparison.Ordinal))
            DeathOracle.NativeImportGuardProbe.Run(args);
        else if (args.Length > 0 && args[0].StartsWith("platform-fixture-", StringComparison.Ordinal))
            DeathOracle.PlatformIdentityFixtureProbe.Run(args);
        else if (args.Length > 0 && args[0] == "room-core-execute")
            DeathOracle.RoomCoreExecution.Run(args);
        else if (args.Length > 0 && args[0] == "room-core-death-respawn")
            DeathOracle.RoomCoreExecution.RunDeathRespawn(args);
        else if (args.Length > 0 && args[0] == "room-core-ground-query")
            DeathOracle.RoomCoreExecution.RunGroundQuery(args);
        else if (args.Length > 0 && args[0] == "room-core-natural-lifecycle")
            DeathOracle.RoomCoreExecution.RunNaturalLifecycle(args);
        else if (args.Length > 0 && args[0] == "room-core-source-contract")
            DeathOracle.RoomCoreExecution.RunNaturalLifecycle(args);
        else if (args.Length > 0 && args[0] == "room-core-up-spike")
            DeathOracle.RoomCoreExecution.RunStaticSpike(args);
        else if (args.Length > 0 && args[0] == "room-core-input-right")
            DeathOracle.RoomCoreExecution.RunInputRight(args);
        else if (args.Length > 0 && args[0] == "room-core-input-jump-buffer")
            DeathOracle.RoomCoreExecution.RunInputJumpBuffer(args);
        else throw new InvalidOperationException("Compile-only dependency probe; room-core lifecycle execution is not established");
    }
}
