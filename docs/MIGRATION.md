# Moving to another machine

Clone the intended code revision, read [SETUP.md](SETUP.md), provide your own
compatible game installation and regenerate the private preparation outputs.
There is no dependency on an old developer's home directory, copied `.audit/`
evidence, old OpenCode sessions or an exported project-memory database.

Project memory is **local-only**. `.opencode/memory/` is ignored, including its
live store, WAL/SHM sidecars and snapshots. Do not add, commit, push or publish
any of it. Existing local stores and snapshots must be preserved, not overwritten
or deleted during code migration. Any private transfer of that state is a separate
owner-controlled operation, not part of cloning or publicly distributing this repo.

The owner-authorized local history rewrite removed tracked memory from reachable
refs while preserving local snapshots and all worktree files. Older hosted or
private validation copies may still contain the original history. Do not pull
or merge that history back into the cleaned repository. Use the maintainer's
private old-to-new commit map for historical checkpoints and read
[PUBLICATION.md](PUBLICATION.md) before any remote update or visibility change.
Private recovery bundles are not code-migration or publication artifacts.

For baseline host checks without the game, use the commands in [README.md](../README.md).
Historical source-oracle integration tests require additional private inputs and
their aggregate is not globally validated. The new preparation recipe regenerates
the first-room package inputs; it does not reconstruct every historical experiment.

The integrated transition has bounded CPU-only acceptance. Full-game, GPU transition,
hardware performance and untested host/platform claims remain out of scope.
