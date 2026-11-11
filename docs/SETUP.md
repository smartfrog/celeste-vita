# Reproduce the private Vita diagnostic

## Host and compatible input

The preparation is standard-library Python 3.12+ on Linux x86_64 or aarch64.
Windows users use WSL2 and Linux tools, not native Windows Python or .NET.
Linux x86_64 is the end-to-end verification target; WSL and aarch64 execution
must not be inferred from that check.

Install Git, Python, CMake, Make and a GNU/Clang C++17 compiler using your host's
package manager. .NET 8 additionally needs its normal distribution-specific
native dependencies, including ICU, OpenSSL and zlib. Consult Microsoft's
[Linux prerequisites](https://learn.microsoft.com/dotnet/core/install/linux).
Allow several GiB of free disk space for tools, source extractions and builds.
If your system temporary directory has a quota, set `TMPDIR` to a writable private
directory with enough space before running the tools. Build subprocesses get a
temporary directory under their fresh private output.

Provide an unmodified **Celeste PC 1.4.0.0 Linux bundled-FNA** installation or ZIP
that you own. Required files include `Celeste.exe`, `Celeste.Content.dll`,
`FNA.dll`, `mscorlib.dll`, `System.dll`, `System.Core.dll`, `System.Xml.dll`,
`Content/Maps/1-ForsakenCity.bin` and the graphics members pinned in
`scripts/prepare_room_visuals.py`. Store/version labels alone do not prove
compatibility. Other distributions, mods, Everest and the Windows OpenGL package
without the bundled framework are not accepted by this recipe.

The directory must directly contain `Celeste.exe` and `Content/`. A ZIP may have
one enclosing directory. Duplicate names, ambiguous game roots, traversal paths,
symlink entries, excessive file sizes and changed required files are rejected.
Unused files are not extracted. No PS4 package is needed.

## Preparation

Run from your checkout:

```sh
python3 -B scripts/prepare_game.py --game /path/to/your/Celeste
```

The first run may download only these public development tools:

| Tool | Identity / location |
| --- | --- |
| .NET SDK | 8.0.425 / runtime 8.0.31, architecture-selected SHA-512 pins in `bootstrap_native_oracle.py` |
| ILSpy | 9.1.0.7988, complete NuGet package SHA-256 in `bootstrap_game_tools.py` |

No global .NET tool install, `sudo`, game download, firmware download, original
game launch or emulator launch is performed. Existing changed ILSpy files fail
verification rather than being overwritten.

Preparation copies only verified required members into a small local normalized
ZIP and local assembly reference directory. It extracts the pinned named source
types locally with ILSpy, compiles the existing narrow recording oracles, runs
those oracles and converts the results into bounded native textures/metadata.
This **does execute locally extracted methods inside our preparation harnesses**;
it does not load or run the complete original game. Those generated sources and
assemblies must remain private, just like the converted assets.

Everything is under `.audit/prepared-game/`, including `preparation.json`,
stage-specific logs, source manifests and converted assets. A failed stage returns
nonzero and retains its log and failure report. Do not copy another developer's
`.audit/` directory to make preparation succeed. Historical private evidence is
not an input to this recipe.

For a second run or an offline run:

```sh
python3 -B scripts/prepare_game.py --game /path/to/celeste-linux.zip \
  --output .audit/prepared-game-second --offline
```

Outputs must be fresh; no existing run is overwritten. The original installation
is read-only. Do not edit this checkout during preparation or build: source drift
is a failure, not an excuse to weaken provenance checks.

## Vita toolchain

Use an SDK installation you control; do not modify another project's shared SDK
to reproduce this repository. Follow [VitaSDK's installation guide](https://vitasdk.org/)
and its package manager for the toolchain and libraries. The available verification
toolchain is VitaSDK Linux x64 **2026.08.1**, GNU 15.2.0. The SDK must provide
`vitashark`, `SceShaccCgExt`, `mathneon` and the normal Vita
weak stub libraries linked by `src/vita/CMakeLists.txt`.

The supported vitaGL source revision is
`cd3791e29ff7f1c0ab349f12c7231f4871ce6a75` from
[Rinnegatamante/vitaGL](https://github.com/Rinnegatamante/vitaGL).
Build it in a new dependency checkout with the matching SDK:

```sh
export VITASDK=/path/to/your/vitasdk
export PATH="$VITASDK/bin:$PATH"
git clone https://github.com/Rinnegatamante/vitaGL.git /path/to/new/vitaGL
git -C /path/to/new/vitaGL switch --detach cd3791e29ff7f1c0ab349f12c7231f4871ce6a75
make -C /path/to/new/vitaGL -j2 NO_SPLASHSCREEN=1
```

Use the headers from this revision. The build script finds `source/vitaGL.h`
beside the supplied source-checkout archive, or an already installed SDK header.
For other layouts, pass `--vitagl-include /path/to/matching/headers`; there is no
need to install headers into a shared SDK. Do not add speed-hack
flags or substitute the normal splash-enabled archive for the checked setup.
These are explicit dependency setup instructions, not steps executed by our scripts.

## Build and inspect

```sh
python3 -B scripts/build_game.py \
  --prepared .audit/prepared-game/preparation.json \
  --output .audit/vita-game \
  --vitasdk "$VITASDK" \
  --vitagl-library /path/to/new/vitaGL/libvitaGL.a
```

The build uses fresh staging, Unix Makefiles, the existing resident source/build
binding and existing VPK verification. Textured tiles, animated player with death
frames, hair, spike art and the bounded static decals are enabled. Scripted replay
and Dash probes are not enabled. The source and prepared artifacts must remain
unchanged through verification. `build.json`, logs and the private VPK remain
beneath the output directory. Verification proves packaging and build consistency,
**not target execution, graphics correctness or performance**.

Normally the checkout must be committed-clean. Developers testing uncommitted
changes can explicitly add `--allow-dirty`: this snapshots the entire exact source
state and uses the existing WIP binding mechanism. It does not create a commit or
mislabel dirty bytes as a clean revision. Never commit just to satisfy this script
without the repository owner's permission.

## Install and test manually

Use your own homebrew-enabled Vita installation workflow to install
`.audit/vita-game/build/src/vita/celeste_native_room.vpk` (title ID `CELR00001`).
This can replace an earlier installation of that diagnostic; preserve any local
diagnostic files you want to keep first. vitaGL requires the shader compiler
`libshacccg.suprx` provisioned on your own device through the upstream documented
process. Neither it nor firmware is supplied by this repository.

Controls: D-pad/left stick move and aim, Cross jumps, Square dashes, L climbs,
Triangle performs the diagnostic manual reset, Start exits. Normal death/respawn
uses the bounded native lifecycle when animated-player mode is enabled. It is
not a claim of complete original-game lifecycle parity.

The normal interactive `initial_respawn` profile claims a fresh output namespace
before opening its log. Files share the prefix
`ux0:data/celeste_native_room-run-<16-hex-process-token>-<2-hex-candidate>`:
`.log`, `.ready`, `.ppm`, `.ppm.txt`, and `-failure.txt` on failure. The token is
an opaque run identifier, not elapsed time or game RNG. Up to 32 candidates are
checked across all five destinations; occupied candidates are preserved and
skipped. A racing exclusive claim or other IO error is fatal. Partial claims
remain for recovery; do not delete old files to make a repeated launch work.
This profile never writes the legacy fixed log/readiness paths. The claim,
readiness, capture sidecar and failure records bind the run ID and full source
revision; an older image cannot satisfy the required fresh initial-respawn export.

This is an **instrumented diagnostic**, not a performance benchmark. Before any
graphics, session, player or input construction, clock calibration requests
three 100 ms waits and one 1 s wait (about 1.3 s, plus scheduler overshoot).
There are no calibration waits after gameplay starts. Successful calibration
checks blocked elapsed time against a separate RTC API; it does not establish
independent hardware accuracy, suspend behavior or clock-read overhead.
Fixed-storage duration summaries are emitted every 300 sampled frames and on
Start. They cover loop intervals, step calls, rendering including swap/capture,
and successful in-loop log calls. Capture and summary frames remain in measured
totals but are excluded from the separately labeled steady series. No GPU-time,
full-session FPS, uninstrumented-performance or hardware-performance claim is made.
Guest automatic/replay, Dash-probe and explicit legacy capture profiles keep
their existing output and completion contracts.

Vita3K may be used with an independently provisioned installation. There is no
portable one-command emulator launch in this recipe. Older `feedback_native_room.py`
and smoke-launcher documentation describes historical development environments;
those commands are not the public setup path. No synthetic host input, automatic
installation, desktop capture or shared emulator configuration changes are needed
to prepare and build.

The default first-room build does not enable the CPU-only room transition
experiment. Audio, menus, seven animated Banner decals, broad room coverage and
full-game behavior remain outside this diagnostic.
