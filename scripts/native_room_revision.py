"""Current repository state shared by diagnostic staging and verification."""

from pathlib import Path
import hashlib
import json
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
COORDINATION_PATHS = frozenset({".opencode/orchestrator.md", ".opencode/memory/memory.db",
                               ".opencode/memory/memory.db-shm", ".opencode/memory/memory.db-wal"})


def file_identity(path):
    data = path.read_bytes()
    return {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}


def canonical_digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def source_binding(state):
    return {"schema": 1, "base_head": state["base_head"], "state_sha256": canonical_digest(state),
            "files_sha256": state["sha256"], "count": state["count"], "bytes": state["bytes"]}


def staging_binding(manifest, state):
    source = source_binding(state)
    digest = canonical_digest({"source": source, "manifest": {k: v for k, v in manifest.items() if k != "binding"}})
    mode = "wip" if state["changes"] else "clean"
    return {"schema": 1, "source": source, "staging_sha256": digest,
            "revision_label": f"{state['base_head']}-{mode}-{digest}"}


def verify_file_identities(identities):
    for path, expected in identities.items():
        if file_identity(Path(path)) != expected:
            raise ValueError("Pinned input/artifact changed: " + path)


def source_state(root=REPO_ROOT):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"],cwd=root,text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"],cwd=root)
    changes = [entry.decode("utf-8",errors="surrogateescape") for entry in status.split(b"\0") if entry]
    return revision, [entry for entry in changes if not (entry[:3] == "?? " and entry[3:] in COORDINATION_PATHS)]


def source_identity(root=REPO_ROOT):
    head, changes = source_state(root)
    raw = subprocess.check_output(["git", "ls-files", "-co", "--exclude-standard", "-z"], cwd=root)
    paths = sorted(set(raw.decode("utf-8", errors="surrogateescape").split("\0")) - {""})
    tracked = subprocess.check_output(["git", "ls-files", "--cached", "-z"], cwd=root)
    untracked_coordination = COORDINATION_PATHS - set(tracked.decode("utf-8", errors="surrogateescape").split("\0"))
    digest, records, total = hashlib.sha256(), {}, 0
    for name in paths:
        if name in untracked_coordination:
            continue
        path = root / name
        if path.is_symlink() or not path.is_file():
            raise ValueError("Exact source-state paths must be existing regular files: " + name)
        data = path.read_bytes()
        identity = hashlib.sha256(data)
        records[name] = {"bytes": len(data), "sha256": identity.hexdigest(), "mode": path.stat().st_mode & 0o777}
        digest.update(name.encode("utf-8", errors="surrogateescape") + b"\0" + identity.digest())
        total += len(data)
    return {"schema": 1, "base_head": head, "changes": changes, "paths": records,
            "sha256": digest.hexdigest(), "count": len(records), "bytes": total}


def validate_source_state(expected=None, root=REPO_ROOT):
    if expected is None:
        _, changes = source_state(root)
        if changes:
            raise ValueError("Exact committed source/config is required: " + "; ".join(changes))
    actual = source_identity(root)
    if expected is not None and actual != expected:
        raise ValueError("Expected exact source state changed (base, paths, status, modes or bytes)")
    return actual
