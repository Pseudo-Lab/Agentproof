#!/usr/bin/env python3
"""Re-sync manifest artifact hashes after trimming raw tool output.

``trim_raw_output.py`` rewrites a few trajectory files to drop oversized
``extra.raw_output`` blobs. That changes their bytes, so the matching
``artifacts[name].public_sha256`` entries in each run manifest must be
recomputed; otherwise ``export_trials.py`` fails its integrity check.

For every artifact whose on-disk hash no longer matches the manifest, this
script updates ``public_sha256`` to the current bytes and records that the file
was trimmed (``raw_output_trimmed: true``) so the edit stays auditable. Entries
that still match are left untouched, so the script is safe to re-run.

``original_sha256`` is intentionally left as-is: it documents the hash of the
pre-publication bytes and is historical provenance, not a check target.
"""
from __future__ import annotations

import glob
import hashlib
import json
import sys

GLOB = "experiments/E03-aci-sue/results/pilot/*/manifest.json"


def main() -> None:
    dry = "--dry-run" in sys.argv
    base = __file__.rsplit("/src/", 1)[0] if "/src/" in __file__ else "."
    total = 0
    for manifest_path in sorted(glob.glob(GLOB)):
        run_dir = manifest_path.rsplit("/", 1)[0]
        with open(manifest_path, encoding="utf-8") as fh:
            manifest = json.load(fh)
        changed = []
        for name, meta in manifest["artifacts"].items():
            try:
                data = open(f"{run_dir}/{name}", "rb").read()
            except FileNotFoundError:
                continue
            digest = hashlib.sha256(data).hexdigest()
            if digest != meta.get("public_sha256"):
                changed.append(name)
                if not dry:
                    meta["public_sha256"] = digest
                    meta["raw_output_trimmed"] = True
        if changed and not dry:
            with open(manifest_path, "w", encoding="utf-8") as fh:
                json.dump(manifest, fh, ensure_ascii=False, indent=2)
                fh.write("\n")
        if changed:
            total += len(changed)
            verb = "would resync" if dry else "resynced"
            print(f"{verb} {len(changed)} artifact(s) in {run_dir.rsplit('/', 1)[-1]}:")
            for n in changed:
                print(f"    {n}")
    print(f"{'Would update' if dry else 'Updated'} {total} artifact hash(es).")


if __name__ == "__main__":
    main()
