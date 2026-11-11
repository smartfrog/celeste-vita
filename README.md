# Celeste Vita

Experimental native C++ port of a **bounded Celeste PC 1.4.0.0 diagnostic** to
PlayStation Vita. This is **not the complete game**. No original game assets,
assemblies or decompiled implementation files belong in the public repository.
You must supply your own legally obtained compatible game files.

## License and original game ownership

Original project contributions are licensed under the [MIT License](LICENSE).
This does not license Celeste's code, assets, trademarks or any third-party
component; their respective rights and licenses remain unchanged. Do not assume
that translated or extracted original implementation code can be relicensed.

To extract game data or test this diagnostic with it, you must supply your own
legally obtained, licensed, compatible copy of Celeste and comply with its terms
and applicable law. Owning the game does not grant redistribution rights to its
code or assets. This requirement concerns the original game material, not reuse
of our independently authored MIT-licensed tools or code.

## Prepare your game files

Run from a checkout on **Linux**, or inside **WSL2** on Windows. Use a Linux
filesystem for the checkout and build. Python **3.12+** and Git are required.
The first preparation downloads pinned .NET 8.0.425 and ILSpy 9.1.0.7988 tools
into ignored `.audit/` directories, not your global environment. Their normal
Linux runtime prerequisites must be installed; see [the setup guide](docs/SETUP.md).

```sh
python3 -B scripts/prepare_game.py --game /path/to/Celeste
```

A ZIP is also accepted, including a repacked ZIP with one enclosing directory:

```sh
python3 -B scripts/prepare_game.py --game /path/to/celeste-linux.zip
```

Currently recognized inputs are the **bundled-FNA Linux PC 1.4.0.0 distribution**.
Compatibility is determined by the required files' hashes, not by a ZIP filename
or a store label. The Windows OpenGL ZIP alone lacks the bundled framework needed
by this recipe and is **not supported**. Windows users run the preparation under
WSL with their compatible Linux game distribution. No game files are downloaded.

The script regenerates collision data, source-backed tile selection, player/hair
and death animation pages, spike art and the 22 supported static decals. Originals,
local source extractions, converted assets and logs remain under `.audit/`.
It never executes the original game or modifies the supplied installation.
Existing outputs are preserved: use `--output .audit/another-preparation` for a
new run. Once tools are cached, `--offline` forbids tool downloads.

## Build your private Vita package

Install your own VitaSDK and the compatible no-splash vitaGL revision described
in [docs/SETUP.md](docs/SETUP.md). No machine-specific SDK location is assumed.

```sh
python3 -B scripts/build_game.py \
  --vitasdk /path/to/vitasdk \
  --vitagl-library /path/to/vitaGL/libvitaGL.a
```

The default VPK is
`.audit/vita-game/build/src/vita/celeste_native_room.vpk`.
The command verifies its assets and resident build binding. It does **not**
install the VPK or launch an emulator. Install it yourself on your homebrew-enabled
Vita, or your independently configured Vita3K setup; prerequisites and controls
are in [the setup guide](docs/SETUP.md).

**Do not upload this VPK, the converted assets, local source extractions or game
files.** They contain material derived from your copy of Celeste. The repository
is intended to share our code and preparation recipes, not the game.

## Test without the game

Requires CMake 3.16+, Make and a GNU/Clang C++17 compiler, in addition to Python:

```sh
cmake -S . -B .audit/host -DCMAKE_BUILD_TYPE=Release
cmake --build .audit/host --parallel 2
ctest --test-dir .audit/host --output-on-failure -E native_validation_scripts
python3 -B -m unittest discover -s tests/native -p 'test_*game*.py' -v
python3 -B -m unittest discover -s tests/native -p test_public_repository.py -v
```

The exclusion is explicit: `native_validation_scripts` also discovers historical
private-reference integration tests. That aggregate suite is **not globally
validated**; it has known failures involving private prerequisites and existing
output directories. The commands above do not claim that suite passed.

## Scope and publication status

- The public build recipe targets the **first-room diagnostic**, with native
  movement, jump/dash/climb and the bounded automatic death/respawn implementation.
- No complete game, audio, menus, original full-room lifecycle or broad hardware
  compatibility is claimed. Seven animated banners and other unsupported art
  remain omitted.
- The integrated room 1-to-2 transition has **bounded CPU-only** validation. This
  recipe does not enable it or claim graphical/hardware transition acceptance.
- Existing technical checkpoints in `docs/` may describe historical intermediate
  states. See [native lifecycle](docs/NATIVE_LIFECYCLE.md) and
  [room transition](docs/NATIVE_ROOM_TRANSITION_CPU.md) for their narrow scope.
- Local reachable history has been cleaned of project memory. **Keep the hosting
  repository private until its publication checks are complete.** Updating remote
  branches does not itself purge cached historical views or older copies. See
  [docs/PUBLICATION.md](docs/PUBLICATION.md). Do not pull or merge the old history
  back into this cleaned repository.
