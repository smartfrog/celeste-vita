# Public repository boundary

## Local history cleaned; hosting still requires review

The local working tree no longer tracks `.opencode/memory/memory.snapshot.db`;
the snapshot and live database remain on disk under ignored `.opencode/memory/`.
They must never be committed or published. Do not restore memory from a public
checkout or add it to a migration commit.

An owner-authorized local rewrite removed `.opencode/memory/` from all locally
reachable references. Every historical non-memory file tree was preserved.
All seven registered worktrees kept their non-memory files and index contents;
tracked snapshots were untracked without deleting their local files.

Private recovery bundles, workspace/index backups, old local reflogs and
unreachable Git objects remain local for recovery. They are **not** publication
artifacts. Never upload `.audit/`, `.git/`, memory files or recovery bundles.

**Keep the hosting repository private until its publication review is complete.**
Any remote history update needs explicit owner approval and checks against the
saved server ref identities. Use exact expected-old protections, not a blind
force push. Local remote-tracking refs were also rewritten during cleanup;
they are not a reliable record of the original server values.

Even after the remote branches have been updated, a successful push does not
prove that cached historical views, pull-request refs, releases or other copies
have been cleaned. Those require separate hosting checks before a visibility
change. Do not publish private recovery artifacts to resolve such a discrepancy.

Do not fetch, pull or merge the old history back into the cleaned repository.
Old clones and private validation clones can reintroduce the removed snapshot.
Preserve historical evidence as evidence, not as a branch to merge. Maintainers
must use the retained old-to-new commit map when interpreting older checkpoints.

Run the read-only checks:

```sh
python3 -B scripts/check_public_repository.py
python3 -B scripts/check_public_repository.py --history
```

The first checks candidate tracked and non-ignored files, including new work,
and separately checks indexed blobs so an unstaged edit cannot conceal a staged secret.
The second also scans locally reachable Git history. A finding returns nonzero;
secret values are not printed. Local candidate, index and reachable-history
checks now pass. These are heuristic checks, **not proof of copyright clearance
or an exhaustive secret audit**. They do not inspect remote-only branches, release
attachments, caches, CI artifacts, Git LFS storage or existing hosting copies.
Those must be checked before changing visibility.

## What may be shared

Share maintained project source, scripts, synthetic tests and reviewed technical
documentation, within the license scope below. File hashes, type names,
format descriptions and counts in the historical audit reports are metadata,
not bundled game content. Do not use those reports as authorization to distribute
the original implementation or assets.

Keep these local:

- Original installations, ZIPs, executables, DLLs, maps, graphics and audio.
- Decompiled sources, extracted method bodies and generated reference assemblies.
- Converted maps, textures, animation banks, placement data and other game-derived
  outputs, even if their format differs from the original.
- Diagnostic VPKs containing those assets, private logs and captures other than
  the reviewed README images below.
- All project memory, snapshots and database sidecars.

The existing `/game/` and `/.audit/` ignore rules, plus the memory/build ignore
rules, reduce accidental additions. **Ignore rules do not protect already tracked
files**, nor prevent forced additions. Inspect the index before any future commit.

### Reviewed README media exception

The owner approved only the two presentation images documented in
[media provenance and attribution](images/README.md): the generated fan-art logo
and the unchanged historical Vita3K frame. These are documentation media, not
runtime assets. The checker pins their exact paths and SHA-256 hashes across
candidate files, the index and reachable history; other captures and changed
image bytes remain blocked, and secret detection still applies to approved media.

This exception does not permit publishing `.audit/`, private logs, raw game art,
textures, sprites, maps, VPKs or memory. It does not grant copyright or trademark
clearance, authorize additional images or change the repository's visibility.

## Licensing and attribution

This is an unofficial experimental project, not a product endorsed by Celeste's
rights holders. Owning the PC game does not transfer distribution rights to its
assets or code. Each tester must obtain their own compatible files and comply
with the applicable terms and laws.

The owner selected the standard [MIT License](../LICENSE) for original project
contributions, attributed to Celeste Vita contributors. No game-ownership
restriction has been added to the MIT text: reuse of independently authored
MIT-licensed code does not require purchasing Celeste.

Preparing or using the original game data requires the tester's own legally
obtained, licensed, compatible copy of Celeste, in accordance with its terms and
applicable law. This repository grants no rights to Celeste's code, assets or
trademarks. Extracted or translated original implementation code is not
automatically eligible for MIT relicensing. Review source provenance and
third-party obligations separately; this notice is not legal clearance.

Preparation uses external .NET tools and ILSpy (MIT-licensed upstream), and the
Vita executable links external VitaSDK libraries and vitaGL. vitaGL carries
upstream LGPL notices and additional component notices in its source tree.
Consult the exact dependency revisions' licenses, especially before any binary
distribution. Tools/dependencies are not vendored here and their licenses are
not replaced by the project's MIT license.

## Release gate

Before publishing: resolve historical/private-content findings, review remote
artifacts and secrets, review source provenance and third-party notices,
verify preparation on a fresh checkout using only an owned game input and public
tools, and report the actual host/package/runtime checks separately. Never turn
a known failing private aggregate suite into a claim that all tests passed.
