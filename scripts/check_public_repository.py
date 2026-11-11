#!/usr/bin/env python3
"""Check candidate files and optionally reachable Git history without exposing secret values."""

import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess

PRIVATE_PREFIXES = ("game/", ".audit/", ".opencode/memory/")
PAYLOAD_SUFFIXES = {".exe", ".dll", ".zip", ".pkg", ".vpk", ".bank", ".ogg", ".rgba", ".mask", ".data", ".db"}
SECRET = re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----|gh[pousr]_[A-Za-z0-9]{30,}|github_pat_[A-Za-z0-9_]{30,}|AKIA[0-9A-Z]{16}")


def git(root, *arguments, input=None):
    return subprocess.run(["git", *arguments], cwd=root, input=input, check=True, capture_output=True).stdout


def path_findings(name):
    if name.startswith(PRIVATE_PREFIXES):
        return ["private path"]
    path = PurePosixPath(name)
    if path.suffix.lower() in PAYLOAD_SUFFIXES:
        return ["binary/game payload requires removal or explicit provenance review"]
    if path.name == "Extracted.cs" or (path.suffix == ".cs" and path.name.startswith(("Celeste.", "Monocle.", "Microsoft.Xna.Framework.", "System."))):
        return ["generated or original source body"]
    return []


def content_findings(data):
    findings = []
    if data.startswith((b"MZ", b"\x7fELF", b"\x89PNG\r\n\x1a\n", b"OggS", b"SQLite format 3\0")) or b"\0" in data:
        findings.append("binary payload requires provenance review")
    if SECRET.search(data):
        findings.append("possible secret; value redacted")
    return findings


def check_blobs(root, objects, scope, record):
    if not objects:
        return 0
    metadata = git(root, "cat-file", "--batch-check", input=("\n".join(objects) + "\n").encode())
    selected = []
    for row in metadata.decode().splitlines():
        oid, kind, size = row.split()
        if kind != "blob":
            continue
        if int(size) > 4 * 1024 * 1024:
            for name in objects[oid]:
                record(scope, name, ["large blob requires manual provenance review"])
        else:
            selected.append(oid)
    if selected:
        batch = git(root, "cat-file", "--batch", input=("\n".join(selected) + "\n").encode())
        offset = 0
        for oid in selected:
            end = batch.index(b"\n", offset)
            header = batch[offset:end].split()
            if header[:2] != [oid.encode(), b"blob"]:
                raise ValueError("Unexpected Git object response")
            size = int(header[2])
            reasons = content_findings(batch[end + 1:end + 1 + size])
            for name in objects[oid]:
                record(scope, name, reasons)
            offset = end + size + 2
    return len(selected)


def audit(root, history=False):
    root = root.resolve()
    names = sorted(set(git(root, "ls-files", "-co", "--exclude-standard", "-z").decode().split("\0")) - {""})
    findings = []

    def record(scope, name, reasons):
        findings.extend({"scope": scope, "path": name, "reason": reason} for reason in reasons)

    for name in names:
        reasons = path_findings(name)
        path = root / name
        if not reasons:
            if path.is_symlink() or not path.is_file():
                reasons = ["candidate must be an existing regular file"]
            elif path.stat().st_size > 4 * 1024 * 1024:
                reasons = ["large candidate requires manual provenance review"]
            else:
                reasons = content_findings(path.read_bytes())
        record("candidate", name, reasons)
    indexed = {}
    for row in git(root, "ls-files", "--stage", "-z").decode().split("\0"):
        if not row:
            continue
        header, name = row.split("\t", 1)
        mode, oid, stage = header.split()
        reasons = path_findings(name)
        if not reasons and (stage != "0" or mode not in {"100644", "100755"}):
            reasons = ["indexed candidate must be a resolved regular file"]
        record("index", name, reasons)
        if not reasons:
            indexed.setdefault(oid, []).append(name)
    indexed_blobs = check_blobs(root, indexed, "index", record)
    history_blobs = 0
    if history:
        objects = {}
        for row in git(root, "rev-list", "--objects", "--all").decode().splitlines():
            oid, _, name = row.partition(" ")
            if name:
                reasons = path_findings(name)
                record("history", name, reasons)
                if not reasons:
                    objects.setdefault(oid, []).append(name)
        history_blobs = check_blobs(root, objects, "history", record)
    return {"candidate_files": len(names), "indexed_blobs_checked": indexed_blobs,
            "history_checked": history, "historical_blobs_checked": history_blobs,
            "findings": findings, "limits": "Heuristic checks, not legal clearance or publication approval. Review provenance, licenses and remote artifacts separately."}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--history", action="store_true", help="Also inspect all locally reachable refs; never rewrite anything")
    args = parser.parse_args()
    result = audit(Path(__file__).resolve().parents[1], args.history)
    print(json.dumps(result, indent=2))
    raise SystemExit(1 if result["findings"] else 0)
