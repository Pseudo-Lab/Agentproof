#!/usr/bin/env python3
"""Line-level fault localization measured on exploration trajectories.

A base source line counts as *seen* only if its exact text was shown to the
model in a tool observation. This uses what the model actually saw after mini's
output truncation (head/tail 5000 chars), so `cat` of a long file does not
count the elided middle. Gold lines are the lines a gold patch changes, in
base-commit coordinates; a pure insertion uses its two neighbouring base lines.

Per trial, with h the first tool call whose observation shows a gold line:
  located               h exists
  steps_to_locate       h
  lines_to_locate       source lines shown in calls 1..h (repeats counted)
  hit_precision         gold lines in call h / source lines in call h   (aim)
  cumulative_precision  gold lines in call h / lines_to_locate         (search cost)
  location_coverage     gold change blocks seen anywhere / all blocks  (multi-location)

Base files are read once per task from the local SWE-bench instance image with
`git archive <base_commit>` and cached under .cache/base-src/ (git-ignored).
"""
import argparse
import io
import json
import re
import shlex
import statistics
import subprocess
import tarfile
from collections import defaultdict
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1]
CACHE = PACKAGE / ".cache" / "base-src"
MAX_CANDIDATES = 20

HUNK = re.compile(r"^@@ -(\d+)(?:,\d+)? \+\d+(?:,\d+)? @@")
SEGMENT = re.compile(r"<(output|output_head|output_tail)>(.*?)</\1>", re.S)
FILE_TAG = re.compile(r"<file>\s*(?:/testbed/)?([^<\s]+)\s*</file>")
TOKEN = re.compile(r"(?:/testbed/|\./)?([A-Za-z_][\w.-]*(?:/[\w.-]+)*\.[A-Za-z]\w{0,4})(?!\w)")
GREP_PATH = re.compile(r"^(?:/testbed/|\./)?([\w./-]+\.\w+)[:-](\d+)[:-](.*)$")
NUMBERED = [re.compile(r"^\s*(\d+)\t(.*)$"),   # nl -ba, cat -n
            re.compile(r"^(\d+)[:-](.*)$"),     # grep -n on one file
            re.compile(r"^(\d+) (.*)$")]        # get_code_around_line, readCode
TRACE = re.compile(r'^\s*File "(?:/testbed/)?([^"]+)", line (\d+)')


def norm(text):
    return text.rstrip()


def nontrivial(text):
    stripped = (text or "").strip()
    return len(stripped) >= 6 and any(c.isalnum() for c in stripped)


def split_lines(raw):
    lines = raw.decode("utf-8", errors="replace").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line.removesuffix("\r") for line in lines]


class Source:
    """Repository files at one base commit, with path resolution and a line index."""

    def __init__(self, files, loader):
        self.files, self.fetched, self._loader = set(files), set(files), loader
        self.by_name = defaultdict(list)
        for path in sorted(self.files):
            self.by_name[path.rsplit("/", 1)[-1]].append(path)
        self._lines, self._index = {}, {}

    def resolve(self, token, fetched_only=True):
        token = token.removeprefix("/testbed/").removeprefix("./")
        if token in self.files:
            found = [token]
        else:
            name = token.rsplit("/", 1)[-1]
            found = [p for p in self.by_name.get(name, []) if p == token or p.endswith("/" + token)]
        found = found[:MAX_CANDIDATES]
        return [p for p in found if p in self.fetched] if fetched_only else found

    def lines(self, path):
        if path not in self._lines:
            self._lines[path] = self._loader(path)
        return self._lines[path]

    def index(self, path):
        if path not in self._index:
            positions = defaultdict(list)
            for i, line in enumerate(self.lines(path)):
                if nontrivial(line):
                    positions[norm(line)].append(i)
            self._index[path] = positions
        return self._index[path]


def image_name(instance_id):
    repo, number = instance_id.rsplit("-", 1)
    owner, name = repo.split("__")
    return f"swebench/sweb.eval.x86_64.{owner}_1776_{name}-{number}:latest"


def docker(image, script):
    command = ["docker", "run", "--rm", image, "bash", "-c", script]
    return subprocess.run(command, capture_output=True, check=True).stdout


class BaseSource(Source):
    def __init__(self, task):
        self.task_id, self.base = task["instance_id"], task["base_commit"]
        self.root, self.image = CACHE / self.task_id, image_name(self.task_id)
        listing = self.root / "files.txt"
        if not listing.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            listing.write_bytes(docker(self.image, f"cd /testbed && git ls-tree -r --name-only {self.base}"))
        super().__init__(set(listing.read_text().split("\n")) - {""}, self._read)
        self.fetched = {p for p in self.files if (self.root / "src" / p).is_file()}

    def _read(self, path):
        return split_lines((self.root / "src" / path).read_bytes())

    def fetch(self, paths):
        missing = sorted(p for p in paths if p in self.files and p not in self.fetched)
        if missing:
            script = f"cd /testbed && git archive {self.base} -- " + " ".join(map(shlex.quote, missing))
            with tarfile.open(fileobj=io.BytesIO(docker(self.image, script))) as tar:
                tar.extractall(self.root / "src", filter="data")
            self.fetched |= {p for p in missing if (self.root / "src" / p).is_file()}


def diff_lines(patch):
    """Yield (kind, path, base_line, text); kind is ' ', '-', '+', 'hunk' or 'file'."""
    path, old, header = None, None, False
    for line in patch.split("\n"):
        if line.startswith("diff --git"):
            header, old = True, None
            yield "file", None, None, None
            continue
        if header:
            if line.startswith("+++ "):
                target = line[4:].strip()
                path = None if target == "/dev/null" else target.removeprefix("b/")
            elif match := HUNK.match(line):
                header, old = False, int(match.group(1))
                yield "hunk", path, None, None
            continue
        if match := HUNK.match(line):
            old = int(match.group(1))
            yield "hunk", path, None, None
            continue
        if old is None or path is None or not line or line[0] not in " -+":
            continue
        yield line[0], path, old, line[1:]
        if line[0] in " -":
            old += 1


def gold_blocks(patch):
    """{path: [set of base lines, ...]} with one set per contiguous change block."""
    blocks, state = defaultdict(list), {"minus": [], "plus": None, "path": None}

    def flush():
        if state["minus"]:
            blocks[state["path"]].append(set(state["minus"]))
        elif state["plus"] is not None:
            anchor = state["plus"]
            blocks[state["path"]].append({n for n in (anchor - 1, anchor) if n >= 1})
        state["minus"], state["plus"] = [], None

    for kind, path, old, _ in diff_lines(patch):
        if kind in ("file", "hunk", " "):
            flush()
        elif kind == "-":
            state["path"] = path
            state["minus"].append(old)
        elif state["plus"] is None:
            state["path"], state["plus"] = path, old
    flush()
    return {path: [b for b in sets if b] for path, sets in blocks.items()}


def verify_gold(patch, source):
    """(mismatched, checked) patch context/removed lines against the fetched base."""
    bad = checked = 0
    for kind, path, old, text in diff_lines(patch):
        if kind in " -" and path in source.fetched:
            lines = source.lines(path)
            checked += 1
            bad += not (old <= len(lines) and norm(lines[old - 1]) == norm(text))
    return bad, checked


def shown(source, path, number, text):
    lines = source.lines(path)
    if not 1 <= number <= len(lines):
        return False
    base = lines[number - 1]
    return norm(base) == norm(text) or base.strip() == text.strip()


def align(lines, path, source):
    """Base line numbers of `path` reproduced verbatim as contiguous runs in `lines`."""
    base, index = source.lines(path), source.index(path)
    anchors = [j for j, text in enumerate(lines) if nontrivial(text)]
    votes = defaultdict(list)
    for j in anchors:
        positions = index.get(norm(lines[j]), ())
        if 0 < len(positions) <= 3:
            for p in positions:
                votes[p - j].append(j)

    def same(j, offset):
        k = j + offset
        return lines[j] is not None and 0 <= k < len(base) and norm(base[k]) == norm(lines[j])

    found = set()
    for offset, support in votes.items():
        single = len(anchors) == 1 and len(index[norm(lines[support[0]])]) == 1
        if len(support) < 2 and not single:
            continue
        lo, hi = min(support), max(support)
        while lo > 0 and same(lo - 1, offset):
            lo -= 1
        while hi + 1 < len(lines) and same(hi + 1, offset):
            hi += 1
        found |= {j + offset + 1 for j in range(lo, hi + 1) if same(j, offset)}
    return found


def observation_text(content):
    if isinstance(content, list):
        return "\n".join(part.get("text", "") for part in content if isinstance(part, dict))
    return content or ""


def visible_lines(command, content, source, extra_paths=()):
    """(path, line) pairs whose exact base text appeared in the observation."""
    command_paths = {p for token in TOKEN.findall(command) for p in source.resolve(token)}
    seen = set()
    for segment in SEGMENT.finditer(observation_text(content)):
        # The template puts a newline right after the opening tag and before the
        # closing one; they are not output lines.
        body = segment.group(2).removeprefix("\n").removesuffix("\n")
        lines = body.split("\n")
        tag_paths = {p for token in FILE_TAG.findall(body) for p in source.resolve(token)}
        context = sorted(command_paths | tag_paths)
        rest, current, skip = list(lines), None, False
        for i, line in enumerate(lines):
            if skip:
                rest[i], skip = None, False
                continue
            if match := FILE_TAG.search(line):
                hits = source.resolve(match.group(1))
                current, rest[i] = (hits[0] if hits else None), None
                continue
            if match := TRACE.match(line):
                number, following = int(match.group(2)), lines[i + 1] if i + 1 < len(lines) else ""
                for path in source.resolve(match.group(1)):
                    if shown(source, path, number, following):
                        seen.add((path, number))
                        rest[i], skip = None, True
                        break
                continue
            if match := GREP_PATH.match(line):
                number = int(match.group(2))
                for path in source.resolve(match.group(1)):
                    if shown(source, path, number, match.group(3)):
                        seen.add((path, number))
                        rest[i] = None
                        break
                if rest[i] is None:
                    continue
            for pattern in NUMBERED:
                if match := pattern.match(line):
                    number = int(match.group(1))
                    for path in ([current] if current else []) + context:
                        if shown(source, path, number, match.group(2)):
                            seen.add((path, number))
                            rest[i] = None
                            break
                if rest[i] is None:
                    break
        for path in sorted(set(context) | set(extra_paths)):
            seen |= {(path, n) for n in align(rest, path, source)}
    return seen


def tool_steps(trajectory):
    """[(command, observation content)] in tool-call order."""
    commands = {}
    for message in trajectory["messages"]:
        for call in message.get("tool_calls") or []:
            try:
                commands[call["id"]] = json.loads(call["function"]["arguments"]).get("command", "")
            except (KeyError, TypeError, ValueError):
                commands[call["id"]] = ""
    return [(commands.get(m.get("tool_call_id"), ""), m.get("content"))
            for m in trajectory["messages"] if m.get("role") == "tool"]


def trial_metrics(steps, patch, source):
    blocks = {p: b for p, b in gold_blocks(patch).items() if p in source.fetched and b}
    gold = {(p, n) for p, sets in blocks.items() for b in sets for n in b}
    seen_all, cumulative, located = set(), 0, None
    for step, (command, content) in enumerate(steps, 1):
        seen = visible_lines(command, content, source, blocks)
        seen_all |= seen
        if located is None:
            cumulative += len(seen)
            hit = seen & gold
            if hit:
                located = {"steps_to_locate": step, "lines_to_locate": cumulative,
                           "hit_precision": round(len(hit) / len(seen), 4),
                           "cumulative_precision": round(len(hit) / cumulative, 4)}
    total = sum(len(sets) for sets in blocks.values())
    covered = sum(any((p, n) in seen_all for n in b) for p, sets in blocks.items() for b in sets)
    return {"located": located is not None, **(located or {}), "gold_blocks": total,
            "location_coverage": round(covered / total, 4) if total else None,
            "tool_calls": len(steps)}


def summarize(rows):
    found = [r for r in rows if r["located"]]
    covered = [r["location_coverage"] for r in rows if r["location_coverage"] is not None]

    def median(key):
        return statistics.median(r[key] for r in found) if found else None

    def mean(key):
        return round(statistics.fmean(r[key] for r in found), 4) if found else None

    return {"located": f"{len(found)}/{len(rows)}", "median_steps_to_locate": median("steps_to_locate"),
            "median_lines_to_locate": median("lines_to_locate"), "mean_hit_precision": mean("hit_precision"),
            "mean_cumulative_precision": mean("cumulative_precision"),
            "mean_location_coverage": round(statistics.fmean(covered), 4) if covered else None}


def trajectory_path(run, task_id):
    return Path(run) / task_id / f"{task_id}.traj.json"


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--tasks", required=True, help="evaluator task JSON with patch and base_commit")
    parser.add_argument("--run", action="append", required=True, metavar="LABEL=DIR")
    parser.add_argument("--out", help="write per-trial metrics and summaries as JSON")
    args = parser.parse_args()
    tasks = json.loads(Path(args.tasks).read_text())
    runs = dict(item.split("=", 1) for item in args.run)

    sources, gold_check = {}, {}
    for task in tasks:
        source = BaseSource(task)
        wanted = set(gold_blocks(task["patch"]))
        for run in runs.values():
            trajectory = json.loads(trajectory_path(run, task["instance_id"]).read_text())
            for command, content in tool_steps(trajectory):
                for token in TOKEN.findall(command + "\n" + observation_text(content)):
                    wanted |= set(source.resolve(token, fetched_only=False))
        source.fetch(wanted)
        bad, checked = verify_gold(task["patch"], source)
        gold_check[task["instance_id"]] = {"mismatched": bad, "checked": checked}
        sources[task["instance_id"]] = source

    report = {"definition": __doc__.strip(), "gold_check": gold_check, "runs": {}}
    for label, run in runs.items():
        rows = []
        for task in tasks:
            trajectory = json.loads(trajectory_path(run, task["instance_id"]).read_text())
            metrics = trial_metrics(tool_steps(trajectory), task["patch"], sources[task["instance_id"]])
            rows.append({"instance_id": task["instance_id"], **metrics})
        report["runs"][label] = {"run": Path(run).name, "summary": summarize(rows), "trials": rows}
        print(label, json.dumps(report["runs"][label]["summary"], ensure_ascii=False))
    if args.out:
        Path(args.out).write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")


if __name__ == "__main__":
    main()
