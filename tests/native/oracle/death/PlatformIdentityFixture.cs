using System;
using System.Collections.Generic;

namespace DeathOracle;

public sealed record PlatformIdentityRead(string Profile, string Platform);

public static class PlatformIdentityFixture
{
    static readonly List<PlatformIdentityRead> reads = new();
    static string profile;

    public static PlatformIdentityRead[] Reads
    {
        get { lock (reads) return reads.ToArray(); }
    }

    public static void Configure(string referenceProfile)
    {
        if (referenceProfile != "pc-linux") throw new ArgumentException("Unsupported declared platform fixture profile: " + referenceProfile);
        lock (reads)
        {
            if (profile != null) throw new InvalidOperationException("Platform fixture profile already configured");
            profile = referenceProfile;
        }
    }

    public static string ReadPlatform()
    {
        lock (reads)
        {
            if (profile == null) throw new UnsupportedClosure("Managed platform fixture requires an explicit reference profile");
            reads.Add(new PlatformIdentityRead(profile, "Linux"));
            return "Linux";
        }
    }
}
