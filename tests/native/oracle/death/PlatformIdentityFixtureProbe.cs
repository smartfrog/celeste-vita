using System;
using System.Linq;
using System.Reflection;
using System.Runtime.CompilerServices;
using System.Text.Json;
using Celeste;
using Monocle;

namespace DeathOracle;

static class PlatformIdentityFixtureProbe
{
    static string RngSnapshot() => JsonSerializer.Serialize(typeof(PrivateRuntime.Random)
        .GetFields(BindingFlags.NonPublic | BindingFlags.Instance).ToDictionary(field => field.Name, field => field.GetValue(Calc.Random)));

    static string ClockSnapshot() => JsonSerializer.Serialize(new { Engine.DeltaTime, Engine.RawDeltaTime,
        Engine.FrameCounter, Engine.FreezeTimer, Engine.TimeRate, Engine.TimeRateB });

    [MethodImpl(MethodImplOptions.NoInlining)]
    static object SettingsProbe()
    {
        Calc.Random = new PresentationOracle.TracedRandom(0);
        string rngBefore = RngSnapshot();
        int callsBefore = Calc.Random.Calls;
        string clocksBefore = ClockSnapshot();
        Settings.Instance = new Settings();
        bool rngUnchanged = rngBefore == RngSnapshot() && callsBefore == Calc.Random.Calls;
        bool clocksUnchanged = clocksBefore == ClockSnapshot();
        if (!rngUnchanged || !clocksUnchanged || global::Celeste.Celeste.IsGGP || !Settings.Instance.Fullscreen || !Settings.Instance.VSync)
            throw new InvalidOperationException("Original Settings/platform initializer or RNG/clock state changed");
        return new { isGGP = global::Celeste.Celeste.IsGGP, rngUnchanged, clocksUnchanged };
    }

    public static void Run(string[] args)
    {
        if (args.Length != 2) throw new ArgumentException("Expected a platform fixture diagnostic and original assembly path");
        if (!NativeImportGuard.Installed || NativeImportGuard.Attempts.Length != 0 || PlatformIdentityFixture.Reads.Length != 0)
            throw new InvalidOperationException("Platform fixture diagnostic requires a fresh guarded process");
        var mappingsBefore = NativeImportGuardProbe.NativeMappings();
        if (mappingsBefore.Length != 0) throw new InvalidOperationException("Preloaded native mappings invalidate the platform diagnostic");
        string status;
        object settings = null;
        if (args[0] == "platform-fixture-unsupported")
        {
            bool rejected = false;
            try { PlatformIdentityFixture.Configure("vita"); }
            catch (ArgumentException) { rejected = true; }
            if (!rejected) throw new InvalidOperationException("Unsupported platform fixture was accepted");
            status = "unsupported-platform-profile-rejected";
        }
        else
        {
            PlatformIdentityFixture.Configure("pc-linux");
            if (args[0] == "platform-fixture-settings")
            {
                settings = SettingsProbe();
                if (!PlatformIdentityFixture.Reads.SequenceEqual(new[] { new PlatformIdentityRead("pc-linux", "Linux") }))
                    throw new InvalidOperationException("Original platform initializer did not consume exactly one declared fixture read");
                status = "declared-linux-settings-initializer-not-startup-parity";
            }
            else if (args[0] == "platform-fixture-native-negative" || args[0] == "platform-fixture-other-native-negative")
            {
                string name = args[0] == "platform-fixture-native-negative" ? "INTERNAL_SDL_GetPlatform" : "SDL_ClearHints";
                var method = typeof(SDL2.SDL).GetMethod(name, BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic);
                NativeImportGuardProbe.ExpectGuardedNative(method, null, "SDL2");
                status = "expected-native-sdl-guard-attempt-not-room-core-coverage";
            }
            else throw new ArgumentException("Unknown platform fixture diagnostic: " + args[0]);
        }
        var mappingsAfter = NativeImportGuardProbe.NativeMappings();
        if (mappingsAfter.Length != 0) throw new InvalidOperationException("Platform diagnostic mapped a native SDL/FMOD library");
        Console.WriteLine(JsonSerializer.Serialize(new { status, settings, platformReads = PlatformIdentityFixture.Reads,
            nativeAttempts = NativeImportGuard.Attempts, mappingsBefore, mappingsAfter }));
    }
}
