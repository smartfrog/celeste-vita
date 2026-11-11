# Celeste Vita — new-machine handoff

Use the announced delivery commit. Before continuing, verify `HEAD`, the memory snapshot, and the private prerequisites; this guide does not assert that a merge or export has already occurred.

## 1. Clone and verify

Clone `main` after the delivery commit is announced, then:

```sh
git clone --branch main https://github.com/smartfrog/celeste-vita.git
cd celeste-vita
git rev-parse HEAD
git status --short
```

Compare `HEAD` with the announced delivery commit; stop if it differs. Repository visibility/auth is unknown: use your own GitHub credentials if required. Never copy credentials, tokens, or key files into the project. Read the cloned `README.md` and `docs/` at that commit; pre-migration working-tree drafts are not authoritative.

## 2. Recreate work state, not sessions

Recorded session IDs and absolute `/tmp/...` or old workspace paths are evidence from the old machine, not live workers. Do not resume them. List refs and recreate branches/worktrees from Git:

```sh
git branch -a
git tag
```

Feature code is on `main`/`development`; checkpoint refs are retained. Verify `git rev-parse HEAD` in each workspace before editing. Do not auto-merge unreviewed branches.

## 3. Restore memory before OpenCode

The delivery commit should contain the portable snapshot at `.opencode/memory/memory.snapshot.db`; the live canonical store is `.opencode/memory/memory.db`. Restore only on a fresh clone, with OpenCode and any process holding the store closed. If the snapshot is absent or empty, stop rather than creating it from a live database.

```sh
CLONE_ROOT=/path/to/verified/celeste-vita
cd "$CLONE_ROOT" || { echo "VERIFIED CLONE ROOT UNAVAILABLE - stop" >&2; exit 1; }
[ -e .git ] || { echo "NOT THE VERIFIED CLONE ROOT - stop" >&2; exit 1; }
for p in .opencode/memory/memory.db .opencode/memory/memory.db-wal .opencode/memory/memory.db-shm; do
  if [ -e "$p" ] || [ -L "$p" ]; then
    echo "ACTIVE STORE EXISTS: $p - preserve and stop" >&2
    exit 1
  fi
done
[ -s .opencode/memory/memory.snapshot.db ] || { echo "SNAPSHOT MISSING OR EMPTY - stop" >&2; exit 1; }
cp --no-clobber .opencode/memory/memory.snapshot.db .opencode/memory/memory.db ||
  { echo "RESTORE COPY FAILED - stop" >&2; exit 1; }
cmp -s .opencode/memory/memory.snapshot.db .opencode/memory/memory.db ||
  { echo "RESTORE VERIFY FAILED - active store preserved" >&2; exit 1; }
echo "memory restored"
```

The guard rejects existing paths and dangling symlinks for the database and both sidecars before copying. Never overwrite, merge, delete, move, or migrate an existing active store. Do not use direct SQL or schema edits. Start OpenCode only after the copy and comparison succeed. The delivery commit should track the portable snapshot, not the live DB or its sidecars.

## 4. Private prerequisites (not in Git)

`.gitignore` excludes `/game/` and `/.audit/`, so a clone contains neither private payload nor evidence. Provision separately and verify versions:

| Need | Verified location / version |
|---|---|
| VitaSDK | `/home/fred/cloudpunk-vita/tools/vitasdk` (GCC 15.2.0) |
| vitaGL no-splash | `/home/fred/cloudpunk-vita/tools/vita3k/vitagl-source/libvitaGL.a`, revision `cd3791e29ff7f1c0ab349f12c7231f4871ce6a75` |
| Vita3K procedure | `/home/fred/cloudpunk-vita/docs/VITA3K.md` |
| .NET SDK | Host-selected pinned path: `.audit/native-oracle/tools/dotnet-8.0.425-linux-x64/dotnet` on Linux x86_64, legacy `.audit/native-oracle/tools/dotnet-8.0.425/dotnet` on Linux aarch64; SDK 8.0.425 / runtime 8.0.31; `scripts/bootstrap_native_oracle.py` installs the pinned hash-verified archive for the current host |
| ILSpy | `.audit/ilspy/tools/ilspycmd-9.1.0.7988/tools/net8.0/any/ilspycmd.dll`; private inputs `.audit/ilspy/inputs/Celeste.exe` |
| Node / REA | Node `v24.22.1`; `rea-agents@6.8.0` checkout `/home/fred/projects/rea` at `015a02d57b567bc9a1ed792d1e4b3ec083fa0ae3` (npm `11.16.0` only for a rebuild) |
| Game/private inputs | `game/celeste-linux.zip`, `game/celeste-win-opengl.zip`, `game/Celeste-CUSA11302.pkg`; `.audit/ilspy`, `.audit/rea-input`, other `.audit/` evidence |

Copy private inputs/evidence only if needed. Do not copy credentials, auth files, live WAL/SHM files, or the original game payload into Git. The SDK, vitaGL, and REA checkout are shared outside this repo; verify the listed versions rather than assuming a fresh clone builds.

## 5. Baseline host build/test

Per `docs/NATIVE_KERNEL.md`; requires Python 3.12+ and GNU/Clang C++17. Invoke absolute tools; do not add wrapper scripts or change global PATH:

```sh
/usr/bin/cmake -S . -B .audit/native-kernel-host \
  -DCMAKE_BUILD_TYPE=Release -DCMAKE_CXX_COMPILER=/usr/bin/c++
/usr/bin/cmake --build .audit/native-kernel-host -j2
/usr/bin/ctest --test-dir .audit/native-kernel-host --output-on-failure
```

The pure headless kernel and basic recipe/unit/fixture checks need no game files, .NET SDK, or VitaSDK. Source-oracle, guard, and parity Python tests require the pinned private `.audit` inputs plus the .NET/ILSpy setup above; without them those tests are skipped, and skipped coverage is not full proof. Do not claim the full merged suite executed on a fresh clone unless those private prerequisites were copied separately. Vita3K/feedback runs also need the private prerequisites. Do not disable desktop security, force input permissions, or add screenshot workarounds for the baseline.

## 6. Known limits

- Physical 6b: two launches, user-confirmed; no new physical-hardware proof here.
- New analog code is source-validated; physical stick, calibration, Climb, and FPS remain unproven.
- Source-controlled Die→Reload roundtrip is ORACLE ONLY. Native C++ automatic respawn is unimplemented; lifecycle completion remains 0/8 families.
- No full-game, audio, or 7-Banner fidelity. Rendering is a bounded diagnostic.
- Vita3K host exit 133 after guest shutdown remains partial/unknown; not all-green.
- Development is paused after migration. Do not start a new feature phase until the user resumes.

Project model config is `.opencode/orchestrator.md`: `normal` → `opencode-go/deepseek-v4.1-flash#high`, `complex` → `opencode-go/deepseek-v4.1-flash#max`. Operator policy: GPT for orchestration/review only. That policy is not a new repo dependency.
