"""Condition V': after an edit to repository source, run the repository's existing tests for the edited
modules in the background, and show the outcome at the start of a later command's output.

The model spends its time generating (B full-solve: 97-98% of wall time) while tools sit idle, and it
rarely runs the repository's own tests (1-3 of 50 tasks). This moves that check to the environment and
overlaps it with generation. There is nothing new to call: hook.sh schedules a run when a command
changes tracked source files (edit_report.py) and prints a finished, unshown result before a later
command (never before the submit or patch-recovery command, whose output is the patch).

Selection (no gold labels): tracked test files that import an edited module, or whose path shares
words with the module path (`sphinx/util/inspect.py` -> `tests/test_util_inspect.py`); the best
ACI_TESTS_FILES files. Runner: the repository's public SWE-bench command (Django `tests/runtests.py`,
SymPy `bin/test`, otherwise pytest). Completed or unavailable runs are compared with the same command
on an untouched copy of the base commit. Timeouts leave that comparison explicitly unchecked.

Subcommands: `schedule FILE...`, `run JOB` (background), `deliver`, `select FILE...`.
Job state lives in the repository's git directory (aci-tests/), never in the work tree or the patch.
"""
import hashlib
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import tempfile
import time
from itertools import zip_longest
from pathlib import Path

TEST_FILE = re.compile(r"(^|/)(test_[^/]*|[^/]*_tests?|tests)\.py$")
GENERIC = {"test", "tests", "testing", "py", "init", "src", "lib"}
STATUS = {"ok": "passed", "PASSED": "passed", "FAIL": "failed", "FAILED": "failed", "F": "failed",
          "ERROR": "error", "E": "error"}
BASE = Path("/tmp/aci-tests-base")


def git(*args, cwd=None):
    return subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd).stdout


def state_dir():
    path = Path(git("rev-parse", "--absolute-git-dir").strip()) / "aci-tests"
    path.mkdir(exist_ok=True)
    return path


def revision():
    """Identity of HEAD and tracked working-tree contents; None when unavailable.

    This is a boundary check, not an immutable test sandbox. Untracked files and
    changes reverted between checks are outside its coverage.
    """
    digest = hashlib.sha256()
    for args in (("rev-parse", "HEAD"), ("diff", "--no-ext-diff", "--no-textconv", "--binary", "HEAD", "--")):
        result = subprocess.run(["git", *args], capture_output=True)
        if result.returncode:
            return None
        digest.update(result.stdout)
        digest.update(b"\0")
    if os.environ.get('ACI_TESTS_CONTEXT') in ('impact', 'testmon'):
        # New files can affect discovery/imports too; include them in freshness.
        for path in git('ls-files', '--others', '--exclude-standard', '-z').split('\0'):
            if path:
                try:
                    digest.update(path.encode() + b'\0' + Path(path).read_bytes() + b'\0')
                except OSError:
                    return None
    return digest.hexdigest()


def module_of(path):
    """(import root, dotted module) of a source file: climb while the directory is a package."""
    parts = Path(path).with_suffix("").parts
    top = len(parts) - 1
    while top > 0 and Path(*parts[:top], "__init__.py").is_file():
        top -= 1
    return str(Path(*parts[:top])) if top else ".", ".".join(p for p in parts[top:] if p != "__init__")


def words(text):
    return [w for w in re.findall(r"[a-z0-9]+", text.lower()) if w not in GENERIC]


def shared(a, b):
    return sum(any(min(len(x), len(y)) >= 2 and (x.startswith(y) or y.startswith(x)) for y in b) for x in a)


def module_select(sources, limit):
    """Tracked test files most related to the edited source files, best first."""
    tests = [f for f in git("ls-files", "*.py").split("\n") if TEST_FILE.search(f)]
    scored = {}
    for source in sources:
        module = module_of(source)[1]
        parent, _, leaf = module.rpartition(".")
        imports = re.compile(rf"^\s*(from\s+{re.escape(module)}\s+import\b|import\s+{re.escape(module)}\b"
                             + (rf"|from\s+{re.escape(parent)}\s+import\s[^\n]*\b{re.escape(leaf)}\b" if parent else "")
                             + ")", re.M)
        mine = words(module.partition(".")[2] or module) or words(module)
        if not mine:
            continue
        for test in tests:
            try:
                text = Path(test).read_text(errors="ignore")
            except OSError:
                continue
            score = shared(mine, words(test)) + 2 * bool(imports.search(text))
            if score >= min(2, len(mine)):
                scored[test] = max(scored.get(test, 0), score)
    return sorted(scored, key=lambda t: (-scored[t], len(t), t))[:limit]


def select(sources, limit, evidence=None):
    """Optional declared-scope query; otherwise preserve the original ranking."""
    context = os.environ.get('ACI_TESTS_CONTEXT', 'scope' if os.environ.get('ACI_TESTS_SCOPE') == '1' else '')
    if context == 'testmon':
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import testmon_tests
        result = testmon_tests.selection(sources)
        if evidence is not None:
            evidence.update(result)
        return result['files']
    if context == 'impact':
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import impact_tests
        result = impact_tests.selection(sources)
        if evidence is not None:
            evidence.update(result)
        return result['files']
    if context in ('scope', 'issue'):
        # -I entrypoints omit the script directory from sys.path.
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import scope_tests
        tests = [f for f in git('ls-files', '*.py').splitlines() if TEST_FILE.search(f)]
        result = scope_tests.select(sources, tests, limit, context=context)
        if evidence is not None:
            evidence.update(result)
        if result.get('files'):
            return result['files']
    elif evidence is not None:
        evidence['method'] = 'module'
    return module_select(sources, limit)


def command(files, runner=None):
    """The repository's public test command for these files, as an argv list (run in the repo root)."""
    if runner is None:
        runner = ('django' if Path('tests/runtests.py').is_file() else
                  'sympy' if Path('bin/test').is_file() and Path('sympy').is_dir() else 'pytest')
    if runner == 'django':
        labels = [str(Path(f).relative_to("tests").with_suffix("")).replace("/", ".") for f in files]
        return ["python", "tests/runtests.py", "--verbosity", "2", "--settings=test_sqlite", "--parallel", "1", *labels]
    if runner == 'sympy':
        cache = [] if os.environ.get("SYMPY_USE_CACHE") == "yes" else ["-C"]
        if os.environ.get("ACI_TESTS_PAIRED_CONTEXT") == "1":
            return ["python", "bin/test", *cache, "--verbose", "--seed",
                    str(int(os.environ.get("ACI_TESTS_SEED", "0"))), *files]
        return ["python", "bin/test", *cache, "--verbose", *files]
    if runner != 'pytest':
        raise ValueError('unsupported native test runner')
    return ["python", "-m", "pytest", "-rA", "-p", "no:cacheprovider", *files]


def execution_module():
    # The isolated tool entrypoint omits its own directory from sys.path.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import execution_report
    return execution_report


def units_module():
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import aci_test_units
    return aci_test_units


def django_id(name, where):
    return where if where.endswith("." + name) else f"{where}.{name}"


def pytest_line(line):
    """(status, node id, message) of a `pytest -rA` summary line; ids of parametrized tests contain spaces,
    so the message starts at the first ' - ' outside brackets."""
    m = re.match(r"^(PASSED|FAILED|ERROR) ([^\s(][^\s]*(?:::|\.py).*)$", line)
    if not m:
        return None
    rest, depth = m[2], 0
    for i, ch in enumerate(rest):
        depth += (ch == "[") - (ch == "]")
        if depth == 0 and rest.startswith(" - ", i):
            return m[1], rest[:i], rest[i + 3:]
    return m[1], rest, None


def pytest_summary(log):
    """Final -rA section. Earlier output can contain complete captured child sessions."""
    headers = list(re.finditer(r"^={3,} short test summary info ={3,}[ \t]*$", log, re.M))
    return log[headers[-1].end():] if headers else None


def unittest_failures(log):
    """Completed unittest error blocks, aggregated by parent test identity.

    Older runners omit verbose subTest status lines. Use the final report, with
    its raw failure/error counts as a completeness check. Parameters stay in the
    raw log; parent IDs permit comparison with a passing baseline. A preceding
    child runner's completed report is outside this report's boundary.
    """
    endings = list(re.finditer(r'^Ran \d+ tests? in [^\n]+\n\s*\n(OK[^\n]*|FAILED \([^\n]+\))', log, re.M))
    if not endings or not endings[-1][1].startswith('FAILED'):
        return {}
    ending = endings[-1]
    report = log[endings[-2].end() if len(endings) > 1 else 0:ending.start()]
    blocks = re.findall(r'^={20,}\n(FAIL|ERROR): (\w+) \(([\w.]+)\)[^\n]*\n', report, re.M)
    counts = dict((name, int(n)) for name, n in re.findall(r'(failures|errors)=(\d+)', ending[1]))
    if any(sum(b[0] == kind for b in blocks) != counts.get(name, 0)
           for kind, name in [('FAIL', 'failures'), ('ERROR', 'errors')]):
        return {}  # Partial/nested reports must not invent a complete test result.
    result = {}
    for kind, name, where in blocks:
        test = django_id(name, where)
        if kind == 'ERROR' or result.get(test) != 'error':
            result[test] = STATUS[kind]
    return result


def parse(log):
    """Recognized test/collection outcomes and their final error lines."""
    log = re.sub(r'\x1b\[[0-9;]*m', '', log)
    summary = pytest_summary(log)
    if summary is not None:
        log = summary
    status, reason, pending, sympy_file = {}, {}, None, None
    for line in log.split("\n"):
        if p := pytest_line(line):                                                             # pytest -rA
            # A test can pass its body and error during teardown. Keep the error
            # regardless of the report categories' display order.
            if p[0] != "PASSED" or status.get(p[1]) not in ("failed", "error"):
                status[p[1]] = STATUS[p[0]]
            if p[0] == "ERROR" and p[1].endswith(".py") and "::" not in p[1]:
                status[p[1]] = "collection_error"
            if p[2]:
                reason[p[1]] = p[2]
        elif m := re.match(r"^(\w+) \(([\w.]+)\)(?:\s.*)? \.\.\. (ok|FAIL|ERROR)$", line):     # django -v 2
            status[django_id(m[1], m[2])] = STATUS[m[3]]
            pending = None
        elif m := re.match(r"^(\w+) \(([\w.]+)\)(?: \.\.\..*)?$", line):                       # docstring/interleaved stdout follows
            pending = django_id(m[1], m[2])
        elif pending and (m := re.search(r"(?: \.\.\. |^)(ok|FAIL|ERROR)$", line)):
            status[pending], pending = STATUS[m[1]], None
        # SymPy's native reporter writes a bare E for import exceptions, with
        # no newline before the next sympy/ file header. Keep those progress
        # tokens out of the node ID; do not strip letters from arbitrary paths.
        elif m := re.match(r"^(?:E+(?=sympy/))?(\S+\.py)\[\d+\]", line):
            sympy_file = m[1]
        elif m := re.match(r"^(test_\w+) (ok|F|E)(?:\s+\[(?:OK|FAIL)\])?$", line.strip()):    # sympy --verbose
            test = f"{sympy_file}::{m[1]}" if sympy_file else m[1]
            status[test] = STATUS[m[2]]
    if summary is None:
        status.update(unittest_failures(log))
    for m in re.finditer(r"^(?:FAIL|ERROR): (\w+) \(([\w.]+)\)[^\n]*\n(?:[^\n]*\n)*?-{20,}\n(.*?)\n\n", log, re.M | re.S):
        reason[django_id(m[1], m[2])] = m[3].strip().split("\n")[-1]                           # django tracebacks
    for m in re.finditer(r"^_+ (\S+?):(test_\w+) _+\n(.*?)(?=^_{3,}|^={3,}|\Z)", log, re.M | re.S):
        reason[f"{m[1]}::{m[2]}"] = m[3].strip().split("\n")[-1]                               # sympy tracebacks
    return status, reason


def first_error(log):
    """First exception in a traceback, not a warning or secondary chained exception.

    This is observed evidence, not an inferred root cause.
    """
    log = re.sub(r'\x1b\[[0-9;]*m', '', log)
    summary = pytest_summary(log)
    if summary is not None:
        # The traceback above may belong to a passing test's captured subprocess.
        for line in summary.splitlines():
            p = pytest_line(line)
            if not p or p[0] not in ("FAILED", "ERROR"):
                continue
            # -rA may omit/truncate reasons. Match a reported failing node's
            # section and stop before captured stdout or the next test section.
            name = re.escape(p[1].split("::", 1)[-1].replace("::", "."))
            title = (rf"ERROR collecting {name}" if "::" not in p[1]
                     else rf"(?:ERROR at (?:setup|teardown) of )?{name}")
            sections = re.findall(rf"^_{{3,}} {title} _{{3,}}[^\n]*\n"
                                  r"(.*?)(?=^[-_=]{3,}[^\n]*[-_=]{3,}[ \t]*$|\Z)", log, re.M | re.S)
            if sections and (error := first_error(sections[-1])):
                return error
            if p[2]:
                return p[2]
        return None
    in_traceback = False
    for line in log.splitlines():
        if "Traceback (most recent call last):" in line or re.match(r'^\s+File ".*", line \d+', line):
            in_traceback = True
        if m := re.match(r"^E\s+([\w.]+:.*|[\w.]+(?:Error|Exception)|assert\b.*)$", line):
            return m[1]
        if in_traceback and re.match(r"^[\w.]+(?::.*)?$", line):
            return line
    for line in log.splitlines():
        if line.startswith("ERROR: "):
            return line
        if (p := pytest_line(line)) and p[0] in ("FAILED", "ERROR") and p[2]:
            return p[2]
    return None


def outcome(log, returncode, timed_out=False, seconds=0):
    """Keep execution health separate from recognized test outcomes. Unknown is never pass."""
    raw_log = log
    log = re.sub(r'\x1b\[[0-9;]*m', '', log)
    status, reason = parse(log)
    summary = pytest_summary(log)
    evidence = summary if summary is not None else log
    # Public runner completion markers. Partial passes are not a completed run.
    complete = bool(re.search(r"tests finished:|^Ran \d+ tests? in |^.*\b\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed).* in [\d.]+\s*s", evidence, re.M))
    collection_error = (bool(re.search(r"ERROR collecting|Interrupted:.*during collection|\[\?\]\s+Failed to import", evidence))
                        or "collection_error" in status.values())
    consistent = True
    if summary is not None:
        # A final count alone cannot establish results for IDs missing from a partial summary.
        totals = re.findall(r"^=+ (\d+ (?:passed|failed|errors?|skipped|xfailed|xpassed|deselected|warnings?)\b[^\n]*?) in [\d.]+\s*s[^\n]*=+$",
                            summary, re.M)
        complete = bool(totals)
        if totals:
            counts = {name.rstrip("s") if name.startswith("error") else name: int(n)
                      for n, name in re.findall(r"(\d+) (passed|failed|errors?)\b", totals[-1])}
            reported = [STATUS[p[0]] for line in summary.splitlines() if (p := pytest_line(line))]
            consistent = all(reported.count(name) == counts.get(name, 0)
                             for name in ("passed", "failed", "error"))
    bad = any(s in ("failed", "error") for s in status.values())
    detail = None
    if timed_out:
        state, detail = "timeout", "partial results only; run did not finish"
    elif collection_error:
        state, detail = "unavailable", "test collection/import failed"
    elif returncode not in (0, 1) or not complete:
        state, detail = "unavailable", "runner did not complete normally"
    elif not consistent:
        state, detail = "unavailable", "summary counts and recognized test outcomes disagree"
    elif not status:
        state, detail = "unavailable", "no passing/failing test outcomes recognized"
    elif returncode == 1 and bad:
        state = "failed"
    elif returncode == 0 and not bad:
        state = "passed"
    else:
        state, detail = "unavailable", "exit code and recognized outcomes disagree"
    return dict(status=status, reason=reason, outcome=state, returncode=returncode, timed_out=timed_out,
                seconds=round(seconds, 1), detail=detail, first_error=first_error(log), log=raw_log)


def run_tests(argv, cwd, env, timeout, pass_fds=()):
    """Run in this process group (schedule kills the group to replace a stale run)."""
    start = time.time()
    try:
        out = subprocess.run(["nice", "-n", "10", *argv], cwd=cwd, env=env, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, text=True, errors="replace", timeout=timeout,
                             **({'pass_fds': pass_fds} if pass_fds else {}))
        log, timed_out, returncode = out.stdout, False, out.returncode
    except subprocess.TimeoutExpired as e:
        log = (e.stdout or b"").decode(errors="replace")
        timed_out, returncode = True, None
    except OSError as e:
        log, timed_out, returncode = f"{type(e).__name__}: {e}", False, None
    return outcome(log, returncode, timed_out, time.time() - start)


def base_copy(index_identity=None):
    """An untouched copy of the base commit, with the image's untracked build artifacts, made once."""
    base = BASE
    if index_identity:
        # An index can be used outside a one-repository container. Bind its
        # baseline copy to this worktree, HEAD and measured environment rather
        # than sharing a process-global /tmp directory with other projects.
        identity = '\0'.join([str(Path.cwd().resolve()), git('rev-parse', 'HEAD').strip(), index_identity])
        base = Path(tempfile.gettempdir()) / ('aci-tests-base-' + hashlib.sha256(identity.encode()).hexdigest())
    if not (base / ".aci-ready").is_file():
        subprocess.run(["rm", "-rf", str(base)], check=True)
        base.mkdir(parents=True)
        # No bytecode: a same-size edit within the same second would keep a stale .pyc valid.
        subprocess.run(f"tar --exclude=./.git --exclude=__pycache__ --exclude='*.pyc' -cf - . | "
                       f"tar -xf - -C {shlex.quote(str(base))}", shell=True, check=True)
        for path in git("diff", "--name-only", "-z", "HEAD").split("\0"):
            if path:
                shown = subprocess.run(["git", "show", f"HEAD:{path}"], capture_output=True)
                if os.environ.get('ACI_TESTS_CONTEXT') in ('impact', 'testmon') and shown.returncode:
                    (base / path).unlink(missing_ok=True)
                    continue
                original = shown.stdout
                (base / path).parent.mkdir(parents=True, exist_ok=True)
                (base / path).write_bytes(original)
        if os.environ.get('ACI_TESTS_CONTEXT') in ('impact', 'testmon'):
            for path in git('ls-files', '--others', '--exclude-standard', '-z').split('\0'):
                if path:
                    (base / path).unlink(missing_ok=True)
        (base / ".aci-ready").write_text("")
    return base


def schedule(sources):
    """Start a background run for the current edits, replacing a run that is still going."""
    state = state_dir()
    pid_file = state / "pid"
    if pid_file.is_file():
        try:
            os.killpg(int(pid_file.read_text()), signal.SIGKILL)
        except (ProcessLookupError, ValueError, PermissionError):
            pass
        pid_file.unlink()
    (state / "result.json").unlink(missing_ok=True)
    selection = {}
    files = select(sources, int(os.environ["ACI_TESTS_FILES"]), selection)
    if selection.get('method') == 'pytest_testmon':
        (state / 'testmon-last-selection.json').write_text(json.dumps(selection))
    if not files and not selection.get('command'):
        if os.environ.get('ACI_TESTS_ISOLATED') == '1':
            (state / 'job.json').unlink(missing_ok=True)
        if selection.get('method') == 'pytest_testmon':
            return ['[tests] unchecked: ' + selection['detail']]
        if selection.get('method') == 'base_execution_index':
            return ['[tests] unchecked: ' + selection['detail']]
        return [f"[tests] no existing test file found for {', '.join(sources)}"]
    job = {"id": str(time.time_ns()), "sources": sources, "files": files,
           "command": selection.get('command') or command(files),
           "selection": selection, "revision": revision()}
    if selection.get('execution_environment'):
        job['execution_environment'] = selection['execution_environment']
    if os.environ.get("ACI_TESTS_PAIRED_CONTEXT") == "1":
        # The historical PairedV treatment freezes native runner/hash randomness
        # for both snapshots; it does not change the model's foreground commands.
        job["execution_environment"] = {
            "PYTHONHASHSEED": str(int(os.environ.get("ACI_TESTS_HASH_SEED", "0")))
        }
    if os.environ.get("ACI_TESTS_EXECUTION") == "1":
        job["execution_plan"] = execution_module().capture(sources)
    (state / "job.json").write_text(json.dumps(job))
    if os.environ.get('ACI_TESTS_ISOLATED') == '1':
        # The host owns isolated execution. This is the latest pending request,
        # not a claim that this version has started or will necessarily run.
        return []
    proc = subprocess.Popen([sys.executable, "-I", __file__, "run", job["id"]], start_new_session=True,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    pid_file.write_text(str(proc.pid))
    if selection.get('method') == 'pytest_testmon':
        unit = f"; executing {len(selection['files'])} native test files" if selection['execution_unit'] == 'native_file' else ''
        return [f"[tests] started in the background: testmon selected {len(selection['tests'])} tests{unit} "
                '(the result comes with a later command)']
    if selection.get('method') == 'base_execution_index':
        scope = 'broader native run' if selection['full_suite_fallback'] else f"{len(selection['tests'])} linked tests"
        if selection.get('units'):
            scope += f"; executing {len(selection['units'])} native units"
        indexed = 'full' if selection.get('indexed_full_native_suite') else 'partial/unavailable'
        return [f"[tests] started in the background: {scope}; index={indexed}; "
                f"unit={selection['execution_unit']}; selection/command: {state / 'job.json'} "
                '(the result comes with a later command)'] + (
                    ['[selection] additional dependencies unverified; see selection/command record']
                    if selection.get('unchecked_reasons') else [])
    return [f"[tests] started in the background: {shlex.join(job['command'])} (the result comes with a later command)"]


def captured_request():
    path = state_dir() / 'job.json'
    return dict(job=json.loads(path.read_text()) if path.is_file() else None, revision=revision())


def run_captured_side(job_id, side):
    """One native command in an already isolated, host-owned container."""
    if side not in ('current', 'baseline'):
        raise ValueError('unknown captured side')
    state = state_dir()
    job = json.loads((state / 'job.json').read_text())
    if job['id'] != job_id or not job['revision'] or revision() != job['revision']:
        raise ValueError('captured workspace does not match the requested version')
    if job.get('execution_plan'):
        raise ValueError('captured execution does not support the separate execution-profile option')
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import impact_tests
    impact_tests.clear_bytecode(impact_tests.changed_paths())
    if side == 'baseline':
        # Native startup already removed nonignored image artifacts. Retain
        # ignored build products and the captured runtime, just as base_copy.
        subprocess.run(['git', 'reset', '--hard', 'HEAD'], check=True, capture_output=True)
        subprocess.run(['git', 'clean', '-fd'], check=True, capture_output=True)
    argv = job['command']
    env = dict(os.environ, **job.get('execution_environment', {}))
    env.pop('ACI_TESTS_PROGRESS', None)
    env.pop('ACI_TESTS_UNIT_STREAM', None)
    report = state / (job_id + '.' + side + '.units.json')
    unit_mode = job.get('selection', {}).get('execution_unit') == 'native_pytest_unit'
    stream = None
    if unit_mode:
        argv = units_module().command(argv, report)
        stream = os.dup(sys.stdout.fileno())
        env['ACI_TESTS_UNIT_STREAM'] = json.dumps(dict(fd=stream, id=job_id, side=side))
    # Both containers execute their own version at the original native path.
    # No live-tree import relocation or shared baseline directory is needed.
    root = str(Path.cwd().resolve())
    argv = [argv[0], str(Path(__file__).with_name('baseline_python.py')),
            '--current', root, root, *argv[1:]]
    try:
        result = run_tests(argv, '.', env, int(os.environ['ACI_TESTS_TIMEOUT']),
                           pass_fds=(stream,) if stream is not None else ())
    finally:
        if stream is not None:
            os.close(stream)
    if unit_mode:
        try:
            result['test_units'] = json.loads(report.read_text())
        except (OSError, ValueError):
            result['test_units'] = {'units': {}, 'detail': 'native unit report unavailable'}
    print(json.dumps(dict(kind='side_result', id=job_id, side=side, result=result)), flush=True)


def capture_line(capture, current_revision, requested_revision):
    relation = ('unverified' if current_revision is None else
                'unchanged' if current_revision == requested_revision else 'changed')
    return (f"[version] capture {capture['label']} after command {capture['action']}; "
            f"current worktree {relation}; evidence is for the captured version")


def captured_feedback(payload, limit):
    """Render observations without treating a completed invocation as finality.

    The host acknowledges only successful render responses. Raw evidence stays
    beside the existing callback logs; this function never schedules work.
    """
    state = state_dir()
    job, capture = payload['job'], payload['capture']
    (state / (job['id'] + '.paired.json')).write_text(json.dumps(payload))
    ack = dict(payload.get('ack', {}))
    if ack.get('final'):
        return dict(text='', ack=ack, pending=False)
    finals = payload.get('finals', {})
    version = capture_line(capture, revision(), job['revision'])
    if all(side in finals for side in ('current', 'baseline')):
        observed = {}
        for side in ('current', 'baseline'):
            value = dict(finals[side])
            log = state / (job['id'] + '.' + side + '.log')
            log.write_text(value.pop('log', ''))
            value['log_path'] = str(log)
            observed[side] = value
        result = dict(job, **observed['current'], baseline=observed['baseline'],
                      before=observed['baseline']['status'], freshness='captured',
                      capture_version_line=version)
        text = '\n'.join(render(result, limit)) + '\n'
        # Never acknowledge a final result if the configured envelope cannot
        # carry its version identity. The raw evidence remains available.
        if len(text) > limit or version not in text:
            return dict(text='', ack=ack, pending=True)
        ack['final'] = True
        return dict(text=text, ack=ack, pending=False)
    states = payload.get('states', {})
    shown = dict(ack.get('shown', {}))
    candidates, updates = [], []
    for unit in job.get('selection', {}).get('units', []):
        current = states.get('current', {}).get(unit, {})
        baseline = states.get('baseline', {}).get(unit, {})
        pair = [baseline.get('outcome', 'unobserved'), current.get('outcome', 'unobserved')]
        if pair == ['passed', 'failed']:
            failure = current.get('failure') or {}
            signature = [*pair, failure.get('message', '')]
            if shown.get(unit) != signature:
                candidates.append((False, unit, signature, current, baseline))
        elif unit in shown:
            updates.append((True, unit, pair, current, baseline))
    if not candidates and not updates:
        return dict(text='', ack=ack, pending=False)
    end = '[tests] end; the output of this command follows'
    lines = ['[tests] background run: status=running; captured pair still pending', version,
             '[comparison] provisional boundary observations; later invocations may change them']
    omitted_line = lambda n: f'[observations] {n} updates omitted; full evidence in the log'
    reserve = len(end) + len(omitted_line(len(updates) + len(candidates))) + 2
    log = f"[log] {state / (job['id'] + '.paired.json')}"
    log = log if len(log) <= 300 else log[:297] + '...'
    if len('\n'.join([*lines, log])) + reserve + 1 <= limit:
        lines.append(log)
    sent = 0
    for withdrawn, unit, signature, current, baseline in [*updates, *candidates]:
        if withdrawn:
            row = f"  updated: prior observation withdrawn for {unit}; base={signature[0]}, current={signature[1]}"
        else:
            counts = lambda v: f"{v.get('finished', 0)}/{v.get('collected', 0)} observed invocations"
            row = (f"  observed: {unit}; base=passed ({counts(baseline)}), "
                   f"current=failed ({counts(current)})")
        row = row if len(row) <= 400 else row[:397] + '...'
        if len('\n'.join([*lines, row])) + reserve + 1 > limit:
            break
        lines.append(row)
        sent += 1
        if withdrawn:
            shown.pop(unit)
        else:
            shown[unit] = signature
            detail = '    ' + ' '.join(signature[2].splitlines())
            detail = detail if len(detail) <= 300 else detail[:297] + '...'
            if len('\n'.join([*lines, detail])) + reserve + 1 <= limit:
                lines.append(detail)
    if not sent:
        return dict(text='', ack=ack, pending=True)
    omitted = len(updates) + len(candidates) - sent
    if omitted:
        lines.append(omitted_line(omitted))
    ack['shown'] = shown
    return dict(text='\n'.join([*lines, end]) + '\n', ack=ack, pending=bool(omitted))


def run(job_id):
    state = state_dir()
    job = json.loads((state / "job.json").read_text())
    if job["id"] != job_id:
        return
    timeout = int(os.environ["ACI_TESTS_TIMEOUT"])
    start_revision = revision()
    argv = job["command"]
    execution_env = dict(os.environ, **job.get("execution_environment", {}))
    if os.environ.get('ACI_TESTS_CONTEXT') in ('impact', 'testmon'):
        sys.path.insert(0, str(Path(__file__).resolve().parent))
        import impact_tests
        impact_tests.clear_bytecode(impact_tests.changed_paths())
    profile_path = state / f"{job_id}.execution-profile.json"
    unit_mode = job.get('selection', {}).get('execution_unit') == 'native_pytest_unit'
    unit_path = state / f"{job_id}.current.units.json"
    if "execution_plan" in job:
        config = execution_module().configuration(job["execution_plan"], Path.cwd())
        if config["files"]:
            if unit_mode:config['unit_report'] = str(unit_path)
            config_path = state / f"{job_id}.execution-config.json"
            config_path.write_text(json.dumps(config))
            argv = [argv[0], str(Path(__file__).with_name("trace_test_execution.py")),
                    str(config_path), str(profile_path), *argv[1:]]
    def execute(command, cwd, env, label, already_instrumented=False):
        report = state / f"{job_id}.{label}.units.json"
        env = dict(env)
        env.pop('ACI_TESTS_PROGRESS', None)
        if unit_mode and not already_instrumented:
            command = units_module().command(command, report)
            if label == 'current' and os.environ.get('ACI_TESTS_EARLY_CURRENT') == '1':
                env['ACI_TESTS_PROGRESS'] = json.dumps(dict(
                    state=str(state), id=job_id, start_revision=start_revision))
        if job.get('selection', {}).get('method') == 'base_execution_index':
            mode = ['--current'] if label == 'current' else []
            command = [command[0], str(Path(__file__).with_name('baseline_python.py')),
                       *mode, str(Path.cwd()), str(Path(cwd).resolve()), *command[1:]]
        observed = run_tests(command, cwd, env, timeout)
        if unit_mode:
            try:
                observed['test_units'] = json.loads(report.read_text())
            except (OSError, ValueError):
                observed['test_units'] = {'units': {}, 'detail': 'native unit report unavailable'}
            observed['unit_report_path'] = str(report)
        return observed
    current = execute(argv, ".", execution_env, 'current', argv != job['command'])
    end_revision = revision()
    if "execution_plan" in job:
        try:
            profile = json.loads(profile_path.read_text())
        except (OSError, ValueError):
            profile = {}
        evidence = execution_module().summarize(job["execution_plan"], profile, current)
        evidence_path = state / f"{job_id}.execution.json"
        evidence.update(path=str(evidence_path),profile_path=str(profile_path),executed_command=argv)
        evidence_path.write_text(json.dumps(evidence))
        current["code_execution"] = evidence
    log_path = state / f"{job_id}.current.log"
    log_path.write_text(current.pop("log"))
    progress_path = state / f"{job_id}.progress.json"
    if progress_path.is_file():
        current['progress_path'] = str(progress_path)

    def publish(baseline, reference=None):
        result = {**job, **current, "before": baseline["status"], "baseline": baseline,
                  "log_path": str(log_path), "start_revision": start_revision, "end_revision": end_revision}
        if reference:
            result['preparation_reference'] = reference
        if json.loads((state / "job.json").read_text())["id"] == job["id"]:
            (state / "result.tmp").write_text(json.dumps(result))
            (state / "result.tmp").replace(state / "result.json")

    baseline = {"outcome": "not_run", "detail": "current run timed out; reproduction unverified", "status": {}}
    reference = job.get('selection', {}).get('preparation_reference')
    current_status = ({u: value['outcome'] for u, value in current.get('test_units', {}).get('units', {}).items()}
                      if unit_mode else current['status'])
    # Only a completed passing selection may use historical preparation facts.
    # Failure/error classification still requires the existing fresh base run.
    reference = (reference if current['outcome'] == 'passed' and reference and reference['status']
                 and all(current_status.get(t) == 'passed' for t in reference['status']) else None)
    if reference:
        baseline = dict(outcome='not_run', status={},
                        detail='current tests passed; historical preparation evidence shown separately')
    elif not current["timed_out"]:
        if (os.environ.get('ACI_TESTS_EARLY_CURRENT') == '1' and current['outcome'] != 'passed'
                and not progress_path.is_file()):
            publish(dict(outcome='pending', status={},
                         detail='current tests finished; fresh baseline comparison is pending'))
        try:
            index_identity = job.get('selection', {}).get('index_sha256')
            base = base_copy(index_identity) if index_identity else base_copy()
            roots = sorted({str(base / module_of(s)[0]) for s in job["sources"]})
            env = dict(execution_env, PYTHONPATH=os.pathsep.join(filter(None, [*roots, execution_env.get("PYTHONPATH")])))
            baseline = execute(job["command"], str(base), env, 'baseline')
            baseline['workspace'] = str(base)
            baseline_log = state / f"{job_id}.baseline.log"
            baseline_log.write_text(baseline.pop("log"))
            baseline["log_path"] = str(baseline_log)
        except (OSError, subprocess.SubprocessError) as e:
            baseline = {"outcome": "unavailable", "status": {}, "returncode": None,
                        "detail": "base copy or test launch failed", "first_error": f"{type(e).__name__}: {e}"}
    publish(baseline, reference)


def render(result, limit):
    if result.get("freshness") in ("stale", "unverified"):
        lines = [f"[tests] background run: status={result['freshness']}; not evidence about the current workspace",
                 "[version] tracked code changed since scheduling/during testing" if result["freshness"] == "stale"
                 else "[version] tracked code identity unavailable",
                 f"[observed run] status={result['outcome']}; exit={result['returncode']}",
                 f"[log] {result.get('log_path', 'unavailable')}",
                 f"[raw] {shlex.join(result['command'])}"]
        end = "[tests] end; the output of this command follows"
        out, used = [], len(end) + 1
        for line in lines:
            line = line if len(line) <= 300 else line[:297] + "..."
            if used + len(line) + 1 <= limit:
                out.append(line)
                used += len(line) + 1
        return out + [end]
    if result.get('kind') == 'test_progress':
        # No unit-level verdict: other parameters/fixtures may still be running.
        end = '[tests] end; the output of this command follows'
        events = result['events']
        omitted = lambda n: f'[failures] {n} observations omitted; inspect the full progress log'
        lines = [f"[tests] background run: status=running; {result['completed_cases']}/{result['collected_cases']} cases finished",
                 '[comparison] pending; observed failures unclassified until fresh baseline completes; verification incomplete',
                 '[execution] selected tests continue; this is partial background evidence',
                 f"[log] {result['log_path']}"]
        out, used = [], len(end) + len(omitted(len(events))) + 2
        def append(line):
            nonlocal used
            line = line if len(line) <= 300 else line[:280] + '... [truncated]'
            if used + len(line) + 1 > limit:
                return False
            out.append(line)
            used += len(line) + 1
            return True
        for line in lines:
            append(line)
        historical = result.get('selection', {}).get('preparation_reference', {}).get('status', {})
        shown = 0
        for event in events:
            reference = historical.get(event['unit'], 'unobserved')
            line = f"  {event['outcome']} [preparation unit={reference}; historical only]: {event['nodeid']}"
            if not append(line):
                break
            shown += 1
            detail = '; '.join(r['when'] + ': ' + ' '.join(r['message'].splitlines())
                               for r in event['reports'])
            append('    ' + detail)
        if shown < len(events):
            out.append(omitted(len(events) - shown))
        return out + [end]
    status, before, reason = result["status"], result["before"], result["reason"]
    reference = result.get('preparation_reference')
    selection = result.get('selection', {})
    unit_mode = selection.get('execution_unit') == 'native_pytest_unit'
    diagnostic = None
    if unit_mode:
        status = {u: d['outcome'] for u, d in result.get('test_units', {}).get('units', {}).items()}
        before = {u: d['outcome'] for u, d in result['baseline'].get('test_units', {}).get('units', {}).items()}
        reason = {}
        diagnostic = units_module().failure_detail(
            result.get('test_units', {}), result['baseline'].get('test_units', {}), selection['units'])
    passed = sum(s == "passed" for s in status.values())
    bad = sorted(t for t, s in status.items() if s in ("failed", "error"))
    new = [t for t in bad if before.get(t) == "passed"]
    old = [t for t in bad if before.get(t) in ("failed", "error")]
    unknown = [t for t in bad if t not in new and t not in old]
    fixed = [t for t, s in status.items() if s == "passed" and before.get(t) in ("failed", "error")]
    head = f"[tests] background run: status={result['outcome']}; exit={result['returncode']}; "
    count_unit = 'native execution units' if unit_mode else 'recognized outcomes'
    head += (f"{passed} passed, {len(bad)} failed ({count_unit})" if status
             else "no test outcomes recognized")
    if unit_mode:
        head += f"; {sum(v not in ('passed', 'failed', 'error') for v in status.values())} partial/skipped/incomplete units"
    if result["timed_out"]:
        head += f"; stopped after {result['seconds']:.0f}s"
    lines = [head]
    if result.get('capture_version_line'):
        lines.append(result['capture_version_line'])
    if unit_mode and not reference:
        compared = units_module().comparison(result.get('test_units', {}),
                                             result['baseline'].get('test_units', {}), selection['units'])
        lines.append(f"[unit comparison] {len(compared['unverified'])} units incomplete/skipped/unobserved; "
                     'parameter cases are not matched across processes')
    if selection.get('method') == 'pytest_testmon':
        scope = 'full' if selection.get('indexed_full_native_suite') else 'partial'
        unit = f"; executed by file ({len(selection['files'])} files)" if selection['execution_unit'] == 'native_file' else ''
        lines.append(f"[selection] testmon: {len(selection['tests'])} selected{unit}; {scope} base preparation")
    if selection.get('method') == 'base_execution_index':
        scope = 'broader run; impact unknown' if selection['full_suite_fallback'] else 'linked tests only'
        coverage = 'full native preparation' if selection.get('indexed_full_native_suite') else 'partial/unavailable index'
        lines.append(f"[selection] {scope}; {coverage}; {selection.get('execution_unit')}")
        if selection.get('unchecked_reasons'):
            lines.append('[selection limits] additional dependencies unverified: ' + '; '.join(selection['unchecked_reasons']))
    if result.get("detail"):
        lines.append(f"[execution] {result['detail']}")
    if diagnostic:
        def brief(reports):
            # Condense only the display; raw messages and every case remain in
            # the native report. No message equality implies case identity.
            counts = {}
            for phase, message in reports:
                text = phase + ': ' + (message.splitlines() or [''])[0]
                counts[text] = counts.get(text, 0) + 1
            return '; '.join(f'{n}x {text}' for text, n in counts.items()) or 'none'
        if diagnostic['kind'] == 'new_unit':
            phase, message = diagnostic['current'][0]
            reason[diagnostic['unit']] = phase + ': ' + ' '.join(message.splitlines())
        else:
            reason[diagnostic['unit']] = (
                f"unpaired failures: base=[{brief(diagnostic['baseline'])}]; "
                f"current=[{brief(diagnostic['current'])}]")
        # Put the detailed unit first within its existing comparison category;
        # retain category rotation and the native test execution order.
        group = new if diagnostic['unit'] in new else old
        group.remove(diagnostic['unit'])
        group.insert(0, diagnostic['unit'])
    elif result.get("first_error"):
        lines.append(f"[first error] {result['first_error']}")
    elif result["outcome"] != "passed":
        lines.append("[first error] not identified; inspect the full log")
    baseline = result["baseline"]
    lines.append(f"[baseline] status={baseline['outcome']}; exit={baseline.get('returncode')}")
    if baseline.get("detail") and not reference:
        lines.append(f"[baseline detail] {baseline['detail']}")
    if baseline.get("first_error") and not diagnostic:
        if baseline["first_error"] == result.get("first_error"):
            lines.append("[baseline error] same first error reproduced before edits")
        else:
            lines.append(f"[baseline first error] {baseline['first_error']}")
    if result["outcome"] not in ("passed", "failed"):
        if not result["timed_out"] and result["returncode"] not in (None, 0) and baseline["outcome"] == "passed":
            lines.append("[comparison] command failed on edited code; same command passed on base")
        lines.append("[comparison] test-level comparison incomplete; missing outcomes are not passes")
    if reference:
        historical = reference['status']
        previously_failed = sum(s == 'passed' and historical.get(t) in ('failed', 'error')
                                for t, s in status.items())
        unverified = sum(historical.get(t) not in ('passed', 'failed', 'error') for t in status)
        lines.append(f"[reference] {previously_failed} previously failing "
                     + ('units' if unit_mode else 'tests')
                     + f" passed now; {unverified} without comparable preparation outcomes; "
                     "historical preparation, not a fresh paired run")
    elif baseline['outcome'] == 'pending':
        lines.append('[comparison] pending; current failures are unclassified until fresh baseline completes')
    elif status:
        lines.append(f"[comparison] {len(new)} new, {len(old)} also failing before your edits, "
                     f"{len(unknown)} failures unverified; {len(fixed)} fail-to-pass "
                     + ('units' if unit_mode else 'tests'))
    if result["outcome"] == "passed" and not fixed and not reference:
        lines.append("[comparison] no failing-before/passing-after test demonstrated")
    # Keep the full log reachable even when many test IDs exceed the observation budget.
    if result.get("log_path"):
        lines.append(f"[log] {result['log_path']}")
    if result.get('progress_path') and result['outcome'] not in ('passed', 'failed'):
        lines.append(f"[partial failure evidence] {result['progress_path']}")
    # Rotate categories so an existing failure is not systematically hidden by new ones.
    ordered = [t for row in zip_longest(new, unknown, old) for t in row if t is not None]
    end = "[tests] end; the output of this command follows"
    omitted = lambda n: f"[failures] {n} identities omitted; inspect the full log"
    out, used = [], len(end) + 1 + (len(omitted(len(bad))) + 1 if bad else 0)

    def append(line):
        nonlocal used
        line = line if len(line) <= 300 else line[:297] + "..."
        if used + len(line) + 1 > limit:
            return False
        out.append(line)
        used += len(line) + 1
        return True

    for line in lines:
        append(line)
    shown = 0
    for t in ordered[:8]:
        label = "new" if t in new else "also failing before edits" if t in old else "baseline unverified"
        # Put both states before potentially long IDs/reasons.
        line = f"  {status[t]} ({label}) [base={before.get(t, 'unobserved')}, current={status[t]}]: {t}"
        line += f": {reason[t]}" if reason.get(t) else ""
        if not append(line):
            break
        shown += 1
    if len(bad) > shown:
        out.append(omitted(len(bad) - shown))
    else:
        used -= len(omitted(len(bad))) + 1 if bad else 0
    append(f"[source] {', '.join(result['sources'])}; background result, not output of this command")
    append(f"[raw] {shlex.join(result['command'])}")
    if result.get("code_execution"):
        # Existing failures and reproduction information retain priority. Facts
        # use the remaining budget; their complete record stays on disk.
        evidence = result["code_execution"]
        facts = execution_module().lines(evidence)
        append(facts[0])
        append(f"[changed code evidence] {evidence['path']}")
        for line in facts[1:]:
            if not append(line):
                break
    return out + [end]


def deliver():
    state = state_dir()
    # Claim this phase atomically. A later phase can be published while revision
    # checking/rendering runs and must remain available for the next command.
    claimed = state / "delivery.tmp"
    try:
        (state / "result.json").replace(claimed)
    except FileNotFoundError:
        return
    result = json.loads(claimed.read_text())
    claimed.unlink()
    keys = ('revision', 'start_revision', 'end_revision')
    if result.get('kind') == 'test_progress':
        job = json.loads((state / 'job.json').read_text())
        if job['id'] != result['id']:
            return
        try:
            previous = json.loads((state / 'delivered.json').read_text())
        except (OSError, ValueError):
            previous = {}
        if previous.get('id') == result['id'] and previous.get('kind') != 'test_progress':
            return  # A delivered final comparison supersedes late progress.
        acknowledged = previous.get('sequence', 0) if previous.get('id') == result['id'] else 0
        result['events'] = [e for e in result['events'] if e['sequence'] > acknowledged]
        if not result['events']:
            return
        result = dict(job, **result, outcome='running', returncode=None)
        keys = ('revision', 'start_revision')  # No end revision exists while tests continue.
    versions = [result.get(key) for key in keys]
    result["delivery_revision"] = revision()
    versions.append(result["delivery_revision"])
    result["freshness"] = ("unverified" if any(v is None for v in versions)
                           else "current" if len(set(versions)) == 1 else "stale")
    (state / "delivered.json").write_text(json.dumps(result))
    sys.stdout.write("\n".join(render(result, int(os.environ["ACI_TESTS_CHARS"]))) + "\n")


if __name__ == "__main__":
    action, args = sys.argv[1], sys.argv[2:]
    if action == "run":
        try:
            run(args[0])
        finally:
            # schedule() gives this helper its own session. Publish the native
            # result first, then terminate the owned group, including children
            # left by subprocess.run's direct-child-only timeout cleanup. The
            # helper's SIGKILL exit is not the recorded native test exit status.
            if os.getsid(0) == os.getpgrp() == os.getpid():
                os.killpg(os.getpid(), signal.SIGKILL)
    elif action == "deliver":
        deliver()
    elif action == "schedule":
        print("\n".join(schedule(args)))
    elif action == "select":
        print("\n".join(select(args, int(os.environ["ACI_TESTS_FILES"]))))
    elif action == "revision":
        print(revision())
    elif action == 'request':
        print(json.dumps(captured_request()))
    elif action == 'captured-feedback':
        print(json.dumps(captured_feedback(json.load(sys.stdin), int(os.environ['ACI_TESTS_CHARS']))))
    elif action == 'run-captured-side':
        if os.getpgrp() != os.getpid():
            os.setsid()
        try:
            run_captured_side(*args)
        finally:
            if os.getsid(0) == os.getpgrp() == os.getpid():
                os.killpg(os.getpid(), signal.SIGKILL)
