#!/usr/bin/env python3
"""Trim oversized raw tool output from trajectory logs.

mini-swe-agent stores the full, pre-truncation tool stdout under
``messages[*].extra.raw_output``. The model only ever sees the already
truncated ``content`` field, so the raw copy is not needed to reproduce or
analyze a run. A few runs (e.g. a pytest error storm) blow this field up to
megabytes and bloat the repository. This script truncates any raw_output
longer than ``MAX_CHARS`` while keeping a short head/tail and a marker so the
log stays self-explanatory.

Idempotent: re-running it leaves already-trimmed files unchanged.
"""
from __future__ import annotations

import glob
import json
import os
import sys

MAX_CHARS = 20_000
HEAD = 8_000
TAIL = 4_000
GLOB = "experiments/E03-aci-sue/results/pilot/*/*/*.traj.json"


def trim(value: str) -> str:
    omitted = len(value) - HEAD - TAIL
    marker = (
        f"\n\n... [raw_output truncated: {omitted:,} chars omitted; "
        f"reproduce locally to regenerate the full log] ...\n\n"
    )
    return value[:HEAD] + marker + value[-TAIL:]


def process(path: str) -> int:
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    changed = 0
    for msg in data.get("messages", []):
        extra = msg.get("extra")
        if not isinstance(extra, dict):
            continue
        raw = extra.get("raw_output")
        if isinstance(raw, str) and len(raw) > MAX_CHARS and "raw_output truncated" not in raw:
            extra["raw_output"] = trim(raw)
            changed += 1
    if changed:
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False, indent=2)
            fh.write("\n")
    return changed


def main() -> None:
    dry = "--dry-run" in sys.argv
    total_msgs = total_files = 0
    for path in sorted(glob.glob(GLOB)):
        before = os.path.getsize(path)
        if dry:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
            n = sum(
                1
                for m in data.get("messages", [])
                if isinstance(m.get("extra"), dict)
                and isinstance(m["extra"].get("raw_output"), str)
                and len(m["extra"]["raw_output"]) > MAX_CHARS
                and "raw_output truncated" not in m["extra"]["raw_output"]
            )
        else:
            n = process(path)
        if n:
            after = os.path.getsize(path)
            total_files += 1
            total_msgs += n
            rel = os.path.relpath(path)
            tag = "would trim" if dry else "trimmed"
            print(f"{tag} {n} msg(s)  {before/1048576:.2f}MB -> {after/1048576:.2f}MB  {rel}")
    verb = "Would modify" if dry else "Modified"
    print(f"{verb} {total_files} file(s), {total_msgs} message(s).")


if __name__ == "__main__":
    main()
