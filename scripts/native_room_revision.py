"""Current repository state shared by diagnostic staging and verification."""

from pathlib import Path
import subprocess

REPO_ROOT = Path(__file__).resolve().parents[1]
COORDINATION_PATHS = frozenset({".opencode/orchestrator.md", ".opencode/memory/memory.db",
                               ".opencode/memory/memory.db-shm", ".opencode/memory/memory.db-wal"})


def source_state(root=REPO_ROOT):
    revision = subprocess.check_output(["git", "rev-parse", "HEAD"],cwd=root,text=True).strip()
    status = subprocess.check_output(["git", "status", "--porcelain=v1", "-z", "--untracked-files=all", "--no-renames"],cwd=root)
    changes = [entry.decode("utf-8",errors="surrogateescape") for entry in status.split(b"\0") if entry]
    return revision, [entry for entry in changes if not (entry[:3] == "?? " and entry[3:] in COORDINATION_PATHS)]
