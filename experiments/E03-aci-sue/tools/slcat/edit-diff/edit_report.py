"""Condition E': after a command changes tracked files, show the change and whether Python still compiles.

Runs from the EXIT trap of the command's shell (hook.sh), in the repository root. A file counts as
changed when its content differs from what the last report showed, or from HEAD if it has not been
reported. The last reported content is kept in the repository's git directory (aci-edit-shadow), so
it is never in the work tree or the patch. New untracked files (scratch scripts, and the
intent-to-add entries of mini's patch command) are not reported.

Per file: `[edit] PATH: +A -R lines`, git's diff hunks of this change (3 context lines, git's
default), and for Python `[syntax] PATH: OK` or the first error, from the repository's own
`python` (the test interpreter) compiling the file. Everything fits in what the model is shown
(grep_dispatch.WHOLE_OUTPUT_CHARS); diff lines that do not fit are counted and the raw command named.
"""
import os
import subprocess
import sys
from pathlib import Path

# Runs under the repository's python, which may be old: no f-strings or newer syntax.
COMPILE = ("import sys\n"
           "try:\n"
           "    compile(open(sys.argv[1], 'rb').read(), sys.argv[1], 'exec', dont_inherit=True)\n"
           "except SyntaxError as e:\n"
           "    print('line {}: {}'.format(e.lineno, e.msg))\n"
           "    print((e.text or '').rstrip())\n")


def g_module():
    roots = (os.environ.get("ACI_G_PATH"), "/opt/aci-g", Path(__file__).resolve().parents[1] / "search-grep")
    for root in roots:
        if root and (Path(root) / "grep_dispatch.py").is_file():
            sys.path.insert(0, str(root))
            import grep_dispatch
            return grep_dispatch
    raise ImportError("grep_dispatch not found")


def git(*args):
    return subprocess.run(["git", *args], capture_output=True).stdout


def hunk_lines(diff):
    lines = diff.decode(errors="replace").split("\n")
    start = next((i for i, line in enumerate(lines) if line.startswith("@@")), len(lines))
    return [line for line in lines[start:] if line]


def changes(context=3, snapshots=None):
    """[(path, deleted, diff lines)] for tracked files changed since the last report; updates it."""
    shadow_root = Path(git("rev-parse", "--git-path", "aci-edit-shadow").decode().strip())
    tracked = [p for p in git("diff", "--name-only", "--diff-filter=MD", "-z", "HEAD").decode().split("\0") if p]
    if os.environ.get('ACI_TESTS_CONTEXT') in ('impact', 'testmon'):
        tracked = [p for p in (git('diff', '--name-only', '-z', 'HEAD') +
                               git('ls-files', '--others', '--exclude-standard', '-z')).decode().split('\0') if p]
    shadowed = [str(p.relative_to(shadow_root)) for p in shadow_root.rglob("*") if p.is_file()]
    out = []
    for path in dict.fromkeys(tracked + shadowed):
        shadow, current = shadow_root / path, Path(path)
        after = current.read_bytes() if current.is_file() else None
        before_known = True
        if shadow.is_file():
            before = shadow.read_bytes()
            if after == before:
                continue
            diff = git("diff", "--no-index", "--no-color", f"-U{context}", str(shadow), path if after is not None else "/dev/null")
        else:
            diff = git("diff", "--no-color", f"-U{context}", "HEAD", "--", path)
            if not diff and after is not None and os.environ.get('ACI_TESTS_CONTEXT') in ('impact', 'testmon'):
                diff = git('diff', '--no-index', '--no-color', f'-U{context}', '/dev/null', path)
            before = None
            if snapshots is not None:
                previous = subprocess.run(["git", "show", "HEAD:" + path], capture_output=True)
                if previous.returncode == 0:
                    before = previous.stdout
                else:
                    # Unknown is not an empty/absent file. Do not fabricate a comparison.
                    before_known = False
        if snapshots is not None and before_known and path.endswith('.py'):
            snapshots.append((path, before, after, 'previous report' if shadow.is_file() else 'HEAD'))
        out.append((path, after is None, hunk_lines(diff)))
        if after is None or path not in tracked:    # deleted, or back to HEAD
            shadow.unlink(missing_ok=True)
        else:
            shadow.parent.mkdir(parents=True, exist_ok=True)
            shadow.write_bytes(after)
    return out


def syntax(path):
    out = subprocess.run(["python", "-c", COMPILE, path], capture_output=True, text=True).stdout.rstrip("\n")
    if not out:
        return [f"[syntax] {path}: OK"]
    first, *rest = out.split("\n")
    return [f"[syntax] {path}: {first}", *rest]


def report(g, entries):
    files = []
    for path, deleted, diff in entries:
        added = sum(1 for line in diff if line.startswith("+"))
        removed = sum(1 for line in diff if line.startswith("-"))
        head = f"[edit] {path}: " + ("deleted" if deleted else f"+{added} -{removed} lines")
        files.append((head, [g.clip(line) for line in diff], [] if deleted or not path.endswith(".py") else syntax(path)))
    raw = "[raw] git diff HEAD -- " + " ".join(path for path, _, _ in entries)
    total = sum(len(diff) for _, diff, _ in files)
    note = f"[edit] {total} more diff lines not shown"            # its longest form
    budget = g.WHOLE_OUTPUT_CHARS - len(raw) - len(note) - 2 - sum(
        len(head) + 1 + sum(len(s) + 1 for s in syn) for head, _, syn in files)
    lines, hidden = [], 0
    for head, diff, syn in files:                  # diff lines in order while they fit
        lines.append(head)
        for line in diff:
            if hidden or len(line) + 1 > budget:
                hidden += 1
                continue
            lines.append(line)
            budget -= len(line) + 1
        lines += syn
    if hidden:
        lines += [f"[edit] {hidden} more diff lines not shown", raw]
    return lines


DIFF_BEGIN = "[edit diff] tracked changes since the previous report"
DIFF_END = "[edit diff] end"
DIFF_OMITTED = "[edit diff] additional diff lines omitted"


def diff_only(entries, budget):
    """Bounded, whole-line incremental diff; no compile or other validation."""
    records = []
    for path, deleted, diff in entries:
        added = sum(line.startswith("+") for line in diff)
        removed = sum(line.startswith("-") for line in diff)
        state = "deleted" if deleted else f"+{added} -{removed} lines"
        if not diff:
            state += "; no textual hunk available"
        records.extend([f"[edit] {path}: {state}", *diff])
    lines = [DIFF_BEGIN]
    remaining = budget - sum(len(x) + 1 for x in [DIFF_BEGIN, DIFF_END, DIFF_OMITTED])
    if remaining < 0:
        return []
    for record in records:
        if len(record) + 1 > remaining:
            lines.append(DIFF_OMITTED)
            break
        lines.append(record)
        remaining -= len(record) + 1
    return [*lines, DIFF_END]


def main():
    """ACI_EDIT_DIFF=only shows exact diff lines without syntax checks; 0 hides them."""
    mode = os.environ.get("ACI_EDIT_DIFF")
    context = int(os.environ.get("ACI_EDIT_DIFF_CONTEXT", "3")) if mode == "only" else 3
    snapshots = [] if any(os.environ.get(key) == "1" for key in ("ACI_EDIT_EFFECTS", "ACI_EDIT_SCOPE")) else None
    entries = changes(context=context, snapshots=snapshots)
    if not entries:
        return
    lines = report(g_module(), entries) if mode not in ("0", "only") else []
    impact = os.environ.get('ACI_TESTS_CONTEXT') in ('impact', 'testmon')
    if os.environ.get("ACI_EDIT_TESTS") == "1" and (impact or any(p.endswith(".py") for p, _, _ in entries)):
        sys.path.insert(0, str(Path(__file__).resolve().parent))   # -I leaves the script directory out
        import related_tests
        tracked = git("diff", "--name-only", "--diff-filter=M", "-z", "HEAD", "--", "*.py").decode().split("\0")
        sources = [p for p in tracked if p and not related_tests.TEST_FILE.search(p)]
        if impact:
            sources = [p for p, _, _ in entries]
        if sources:
            lines += related_tests.schedule(sources)
    if (snapshots and os.environ.get("ACI_EDIT_SCOPE") == "1"
            and os.environ.get("ACI_EDIT_SCOPE_APPLY") != "1" and os.environ.get("ACI_EDIT_BOUND") != "1"):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import edit_scope
        remaining = g_module().WHOLE_OUTPUT_CHARS - sum(len(s) + 1 for s in lines)
        lines += edit_scope.render(edit_scope.assess(snapshots), remaining)
    if snapshots and os.environ.get("ACI_EDIT_EFFECTS") == "1":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import source_effects
        records = [source_effects.analyze(before, after, path, baseline)
                   for path, before, after, baseline in snapshots]
        remaining = g_module().WHOLE_OUTPUT_CHARS - sum(len(s) + 1 for s in lines)
        lines += source_effects.render(records, remaining)
    if mode == "only":
        remaining = g_module().WHOLE_OUTPUT_CHARS - sum(len(s) + 1 for s in lines)
        lines += diff_only(entries, remaining)
    if os.environ.get("ACI_EDIT_READBACK") == "1":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import source_readback
        remaining = g_module().WHOLE_OUTPUT_CHARS - sum(len(s) + 1 for s in lines)
        readback = source_readback.render(entries, remaining)
        if readback:
            lines.append(readback.rstrip("\n"))
    if os.environ.get("ACI_CHANGE_RELATIONS") == "1":
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import relation_report
        remaining = int(os.environ.get("ACI_OUTPUT_CHARS", "5000")) - sum(len(s) + 1 for s in lines) - 1
        relation_text = relation_report.report(entries, remaining)
        if relation_text:
            lines.append(relation_text)
    if os.environ.get("ACI_EDIT_GRAPH") == "1":
        import json
        remaining = int(os.environ.get("ACI_OUTPUT_CHARS", "5000")) - sum(len(s) + 1 for s in lines) - 1
        bundle = Path(__file__).resolve().parents[1] / "change-graph"
        try:
            result = subprocess.run([str(bundle / ".venv/bin/python"), "-I", str(bundle / "graph_report.py")],
                                    input=json.dumps({"paths": [p for p, deleted, _ in entries if not deleted and p.endswith(".py")],
                                                      "budget": remaining}),
                                    capture_output=True, text=True, timeout=30)
            if result.returncode == 0 and result.stdout.strip():
                lines.append(result.stdout.rstrip("\n"))
            elif result.returncode:
                lines.append("[code graph] analysis unavailable; " + result.stderr[-300:].strip())
        except subprocess.TimeoutExpired:
            lines.append("[code graph] analysis timed out")
    if lines:
        sys.stdout.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
