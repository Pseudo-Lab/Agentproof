"""Definition-first compressed grep for condition G (spec: docs/search-grep.md).

GNU grep still decides every match, exit status and error message. This wrapper
only changes how matches are shown when its standard output goes straight to the
model (mini's pipe, or a `head -n K` that writes to it). Pipes into other
programs, redirections and command substitutions get the unchanged grep.

Python files are grouped by the enclosing class/function from AutoCodeRover's
parser (`search_utils.parse_python_file`, test-file rule `is_test_file`). When
the pattern names a symbol, its definitions are shown first, wherever they are.
"""
import ast
import difflib
import hashlib
import keyword
import os
import re
import shlex
import signal
import stat
import subprocess
import sys
from pathlib import Path

REAL_GREP = next((p for p in ("/usr/bin/grep", "/bin/grep") if os.access(p, os.X_OK)), "/usr/bin/grep")
# What the model sees of one command's output. mini's swebench.yaml: the whole output below
# 10,000 characters, else the first and last 5,000. aci-obs-competition.yaml sets
# ACI_OUTPUT_CHARS: only the first that many characters (Gemma competition harness).
# U' and L read these two names from here.
_HEAD_CHARS = os.environ.get("ACI_OUTPUT_CHARS")
WHOLE_OUTPUT_CHARS = int(_HEAD_CHARS) if _HEAD_CHARS else 10000
CUT_NOTE = f"only the first {_HEAD_CHARS} characters would be shown" if _HEAD_CHARS else "mini would drop the middle"
MODEL_CHARS = min(6000, WHOLE_OUTPUT_CHARS)   # shown-output budget
LINE_CHARS = 200
DEFS_PER_NAME, DEFS_TOTAL, BARE_NAME_MAX_DEFS = 3, 4, 3
SKELETON_LINES = 8          # child signatures shown under a definition (Agentless-style skeleton)
SUGGESTIONS = 5
CONTEXT_CHARS = min(9000, WHOLE_OUTPUT_CHARS)  # explicit -A/-B/-C reads, below the cut
UNLIMITED = 10**9

# GNU grep 3.7 options. Short options taking an argument, options that turn the output
# into something other than matching lines (those run the unchanged grep), and the rest.
SHORT_ARG = set("ABCDXdefm")
SHORT_RAW = set("lLcqoZzbTuVh")
SHORT_OK = set("EFGPiyrRvnHswxaIU")
LONG = {  # name -> 0 no argument, 1 required, 2 optional (only with '=')
    "after-context": 1, "before-context": 1, "context": 2, "binary-files": 1, "color": 2, "colour": 2,
    "devices": 1, "directories": 1, "exclude": 1, "exclude-from": 1, "exclude-dir": 1, "file": 1,
    "group-separator": 1, "include": 1, "label": 1, "max-count": 1, "regexp": 1,
    "basic-regexp": 0, "extended-regexp": 0, "fixed-strings": 0, "perl-regexp": 0, "ignore-case": 0,
    "no-ignore-case": 0, "word-regexp": 0, "line-regexp": 0, "null-data": 0, "no-messages": 0,
    "invert-match": 0, "version": 0, "help": 0, "byte-offset": 0, "line-number": 0, "line-buffered": 0,
    "with-filename": 0, "no-filename": 0, "only-matching": 0, "quiet": 0, "silent": 0, "binary": 0,
    "text": 0, "recursive": 0, "dereference-recursive": 0, "files-without-match": 0,
    "files-with-matches": 0, "count": 0, "initial-tab": 0, "null": 0, "no-group-separator": 0,
    "unix-byte-offsets": 0,
}
LONG_RAW = {"files-without-match", "files-with-matches", "count", "quiet", "silent", "only-matching",
            "null", "null-data", "byte-offset", "initial-tab", "version", "help", "no-filename",
            "label", "unix-byte-offsets"}


class Raw(Exception):
    """Run the unchanged grep."""


# --------------------------------------------------------------------------- arguments

def parse_args(argv):
    """GNU getopt-style parse (with permutation) of the facts the wrapper needs."""
    opts = {"patterns": [], "pattern_file": False, "syntax": "G", "recursive": False, "invert": False,
            "context": 0, "operands": [], "argv": list(argv)}
    i, only_operands = 0, False
    while i < len(argv):
        arg = argv[i]
        i += 1
        if only_operands or arg == "-" or not arg.startswith("-"):
            opts["operands"].append(arg)
            continue
        if arg == "--":
            only_operands = True
            continue
        if arg.startswith("--"):
            name, eq, value = arg[2:].partition("=")
            matches = [n for n in LONG if n == name] or [n for n in LONG if n.startswith(name)]
            if len(matches) != 1:
                raise Raw(f"option {arg}")
            name = matches[0]
            if LONG[name] == 1 and not eq:
                if i >= len(argv):
                    raise Raw("missing argument")
                value, i = argv[i], i + 1
            elif LONG[name] == 0 and eq:
                raise Raw(f"option {arg}")
            if name in LONG_RAW or (name in ("color", "colour") and value == "always"):
                raise Raw(f"option --{name}")
            _apply(opts, name, value if eq or LONG[name] == 1 else None)
            continue
        cluster, j = arg[1:], 0
        while j < len(cluster):
            ch = cluster[j]
            j += 1
            if ch.isdigit():
                digits = ch
                while j < len(cluster) and cluster[j].isdigit():
                    digits, j = digits + cluster[j], j + 1
                opts["context"] = max(opts["context"], int(digits))
            elif ch in SHORT_ARG:
                value = cluster[j:]
                if not value:
                    if i >= len(argv):
                        raise Raw("missing argument")
                    value, i = argv[i], i + 1
                _apply(opts, ch, value)
                break
            elif ch in SHORT_RAW:
                raise Raw(f"option -{ch}")
            elif ch in SHORT_OK:
                _apply(opts, ch, None)
            else:
                raise Raw(f"option -{ch}")
    if not opts["patterns"] and not opts["pattern_file"]:
        if not opts["operands"]:
            raise Raw("no pattern")
        opts["patterns"].append(opts["operands"].pop(0))
    if "-" in opts["operands"]:
        raise Raw("stdin operand")
    opts["filter"] = not opts["operands"] and not opts["recursive"]
    if opts["invert"] and not opts["filter"]:
        raise Raw("-v over files prints non-matching lines")
    return opts


def _apply(opts, name, value):
    if name in ("e", "regexp"):
        opts["patterns"].append(value)
    elif name in ("f", "file"):
        opts["pattern_file"] = True
    elif name in ("E", "extended-regexp"):
        opts["syntax"] = "E"
    elif name in ("F", "fixed-strings"):
        opts["syntax"] = "F"
    elif name in ("G", "basic-regexp"):
        opts["syntax"] = "G"
    elif name in ("P", "perl-regexp"):
        opts["syntax"] = "P"
    elif name in ("r", "R", "recursive", "dereference-recursive"):
        opts["recursive"] = True
    elif name in ("d", "directories") and value == "recurse":
        opts["recursive"] = True
    elif name in ("v", "invert-match"):
        opts["invert"] = True
    elif name in ("A", "B", "C", "after-context", "before-context", "context"):
        if value is not None and not value.isdigit():
            raise Raw("context value")
        opts["context"] = max(opts["context"], int(value) if value else 2)


# Pattern-level whitespace and anchors, removed before reading a symbol name.
_DECORATION = re.compile(r"\\s[*+]?|\[\[:space:\]\][*+]?|\[ \\t\][*+]?|\[\\t \][*+]?|\[ \][*+]?|\\t"
                         r"| [*+]|\\b|\\<|\\>")
_NAME = re.compile(r"^(?:(async)\s+)?(?:(def|class)\s+)?([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*(?:\(.*|:.*)?$")
NOT_NAMES = set(keyword.kwlist) | {"self", "cls", "print", "True", "False", "None"}


def pattern_names(patterns, syntax):
    """[(prefix, name, qualifier)] if every pattern alternative is a decorated symbol name, else []."""
    names = []
    for pattern in patterns:
        if syntax == "F":
            alternatives = pattern.split("\n")
        elif syntax == "G":
            alternatives = pattern.split("\\|")
        else:
            if re.search(r"\([^)]*\|", pattern):
                return []
            alternatives = pattern.split("|")
        for alt in alternatives:
            text = alt.strip()
            if syntax != "F":
                text = text.removeprefix("^").removesuffix("$").removeprefix(".*").removesuffix(".*")
                text = _DECORATION.sub(" ", text)
                text = text.replace("\\(", "(").replace("\\.", ".").replace("\\:", ":")
            match = _NAME.match(text.strip())
            if not match:
                return []
            prefix = "def" if match.group(1) else match.group(2)
            qualifier, _, name = match.group(3).rpartition(".")
            if qualifier in ("self", "cls") or (qualifier and not qualifier[:1].isupper()):
                qualifier = ""
            if name in NOT_NAMES or len(name) < 3:
                return []
            names.append((prefix, name, qualifier))
    return names


# --------------------------------------------------------------------------- where stdout goes

def _ppid(pid):
    with open(f"/proc/{pid}/stat") as handle:
        return int(handle.read().rsplit(")", 1)[1].split()[1])


def _same(a, b):
    return (a.st_dev, a.st_ino) == (b.st_dev, b.st_ino)


def shown_to_model():
    """True when our standard output is the pipe the model reads.

    mini runs the command with `docker exec`, so the top process of our process
    chain (parent pid 0) writes to the pipe mini reads. We show the compressed view
    only when our fd 1 is that same pipe. Anything else — a redirection, `$(…)`, or a
    pipe into another program (`| head`, `| wc`, `| grep`, `| xargs`) — gives a
    different fd, so the unchanged grep runs. `| head` therefore falls through to
    plain grep; that is an accepted loss in exchange for dropping the /proc race
    tracking it used to need."""
    mine = os.fstat(1)
    if not stat.S_ISFIFO(mine.st_mode):
        return False
    chain, pid = [os.getpid()], os.getpid()
    while (parent := _ppid(pid)) != 0:
        chain.append(parent)
        pid = parent
    root = int(os.environ.get("ACI_GREP_ROOT_PID") or chain[-1])
    if root not in chain:
        return False
    try:
        return _same(mine, os.stat(f"/proc/{root}/fd/1"))
    except OSError:
        return False


# --------------------------------------------------------------------------- Python structure

def acr_search_utils():
    roots = (os.environ.get("ACI_ACR_PATH"), "/opt/aci-acr",
             Path(__file__).resolve().parents[3] / "external/auto-code-rover")
    for root in roots:
        if root and (Path(root) / "app" / "search" / "search_utils.py").is_file():
            sys.path.insert(0, str(root))
            from app.search import search_utils
            return search_utils
    raise ImportError("AutoCodeRover search_utils not found")


class Repo:
    def __init__(self):
        self.cwd = os.getcwd()
        try:
            root = subprocess.run(["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True,
                                  check=True).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            root = ""
        self.root = root or self.cwd
        self.utils = acr_search_utils()
        self._nodes = {}

    def abspath(self, path):
        return os.path.normpath(os.path.join(self.cwd, path))

    def display(self, path):
        rel = os.path.relpath(self.abspath(path), self.cwd)
        return self.abspath(path) if rel.startswith("../") else rel

    def rel(self, path):
        return os.path.relpath(self.abspath(path), self.root)

    def version_note(self, path):
        """Optional edit precondition; does not certify complete body exposure."""
        if os.environ.get('ACI_EDIT_BOUND') != '1' or not path.endswith('.py'):
            return ''
        cache = self.__dict__.setdefault('_edit_versions', {})
        key = self.abspath(path)
        if key not in cache:
            try:
                cache[key] = hashlib.sha256(Path(key).read_bytes()).hexdigest()[:12]
            except OSError:
                cache[key] = None
        return f" [edit-version: {cache[key]}]" if cache[key] else ''

    def is_source(self, path):
        rel = self.rel(path)
        return path.endswith(".py") and not rel.startswith("..") and not self.utils.is_test_file(rel)

    def nodes(self, path):
        """[(start, end, kind, name)] from AutoCodeRover's parser, outer first; None if unparseable."""
        key = self.abspath(path)
        if key not in self._nodes:
            info = self.utils.parse_python_file(key) if key.endswith(".py") else None
            if info is None:
                self._nodes[key] = None
            else:
                classes, _, functions, _ = info
                nodes = [(s, e, "class", n) for n, s, e in classes] + [(s, e, "def", n) for n, s, e in functions]
                self._nodes[key] = sorted(nodes, key=lambda node: (node[0], -node[1]))
        return self._nodes[key]

    def symbol(self, path, line):
        """(kind, qualified name, start, end) of the class/function holding `line`; None if not Python."""
        nodes = self.nodes(path)
        if nodes is None:
            return None
        names, kind, span, seen_class = [], "module", None, False
        for start, end, node_kind, name in nodes:
            if start > line:
                break
            if end < line:
                continue
            names.append(name)
            span = (start, end)
            if node_kind == "def":
                kind = "method" if seen_class else "def"
                break
            kind, seen_class = "class", True
        if span is None:
            return ("module", "", 0, 0)
        return (kind, ".".join(names), span[0], span[1])

    def lines(self, path):
        key = self.abspath(path)
        cache = getattr(self, "_lines", None)
        if cache is None:
            cache = self._lines = {}
        if key not in cache:
            try:
                cache[key] = Path(key).read_text(errors="replace").split("\n")
            except OSError:
                cache[key] = None
        return cache[key]

    def scope_chain(self, path, line):
        """Complete statement ancestors, innermost first; no indentation guesses."""
        key = self.abspath(path)
        cache = self.__dict__.setdefault('_scopes', {})
        if key not in cache:
            source = self.lines(path)
            try:
                tree = ast.parse('\n'.join(source)) if source is not None else None
            except (SyntaxError, ValueError):
                tree = None
            spans = set()
            for node in ast.walk(tree) if tree is not None else []:
                if isinstance(node, ast.stmt) and getattr(node, 'end_lineno', None):
                    start = min([node.lineno] + [d.lineno for d in getattr(node, 'decorator_list', [])])
                    spans.add((start, node.end_lineno))
            cache[key] = sorted(spans, key=lambda span: (span[1] - span[0], span[0]))
        return [span for span in cache[key] if span[0] <= line <= span[1]]

    def _header(self, lines, start):
        """Signature header lines of the def/class beginning at 1-based `start` (until the `:`)."""
        out = []
        for i in range(start - 1, min(start + 9, len(lines))):
            out.append(lines[i])
            if re.search(r":\s*(#.*)?$", lines[i]):   # end of the signature line(s)
                break
        return out

    def skeleton(self, path, start, end):
        """Signature headers of the direct child defs/classes inside [start, end] (Agentless-style).

        Uses AutoCodeRover's node spans, so it shares that parser's limits (no `async def`,
        no dynamic definitions). Returns [] when the symbol has no nested defs/classes."""
        nodes = self.nodes(path)
        lines = self.lines(path)
        if not nodes or lines is None:
            return []
        inside = [n for n in nodes if n[0] > start and n[1] <= end]
        children = [n for n in inside if not any(o[0] < n[0] and o[1] >= n[1] for o in inside)]
        headers = []
        for s, _, _, _ in sorted(children):
            headers += self._header(lines, s)
        return headers

    def body(self, path, start, end, limit):
        """[(line_no, text)] of the symbol body after its signature, up to `limit` lines.

        Short symbols return their whole body so the model need not read it again with sed;
        long ones return [] so the caller falls back to the signature-only skeleton."""
        lines = self.lines(path)
        if lines is None or end <= start:
            return []
        header = self._header(lines, start)
        first = start + len(header)                     # line after the signature
        span = [(n, lines[n - 1]) for n in range(first, min(end, len(lines)) + 1)]
        return span if len(span) <= limit else []


def find_definitions(repo, wanted):
    """{name: [definition]} for source definitions of the wanted names (test files excluded)."""
    if not wanted:
        return {}
    pattern = r"^[[:space:]]*(async[[:space:]]+)?(def|class)[[:space:]]+(" + "|".join(sorted(wanted)) + r")\b"
    out = subprocess.run([REAL_GREP, "-rnIE", "--null", "--color=never", "--include=*.py", "--exclude-dir=.git",
                          "-e", pattern, repo.root], capture_output=True).stdout
    found = {name: [] for name in wanted}
    for raw in out.split(b"\n"):
        path, sep, rest = raw.partition(b"\0")
        match = re.match(rb"(\d+):(.*)", rest, re.S)
        if not sep or not match:
            continue
        path, line, text = path.decode(errors="replace"), int(match.group(1)), match.group(2).decode(errors="replace")
        name = re.search(r"(?:def|class)\s+(\w+)", text).group(1)
        if name not in found or not repo.is_source(path):
            continue
        sym = repo.symbol(path, line)
        if sym is None or sym[2] != line:
            continue
        found[name].append({"name": name, "path": repo.display(path), "abs": repo.abspath(path), "line": line,
                            "kind": sym[0], "qual": sym[1], "start": sym[2], "end": sym[3], "text": text})
    return found


def suggestions(repo, name):
    out = subprocess.run([REAL_GREP, "-rnoIE", "--null", "--color=never", "--include=*.py", "--exclude-dir=.git",
                          "-e", r"^[[:space:]]*(async[[:space:]]+)?(def|class)[[:space:]]+[A-Za-z_][A-Za-z0-9_]*",
                          repo.root], capture_output=True).stdout
    where = {}
    for raw in out.split(b"\n"):
        path, sep, rest = raw.partition(b"\0")
        match = re.match(rb"(\d+):.*?(\w+)$", rest)
        if sep and match:
            path = path.decode(errors="replace")
            symbol = match.group(2).decode()
            if symbol not in where and repo.is_source(path):
                where[symbol] = f"{repo.display(path)}:{int(match.group(1))}"
    names = sorted(where)
    lower = name.lower()
    picked = [n for n in names if n != name and len(n) > 2 and (lower in n.lower() or n.lower() in lower)]
    picked = sorted(picked, key=lambda n: (abs(len(n) - len(name)), n))[:SUGGESTIONS]
    for close in difflib.get_close_matches(name, names, n=SUGGESTIONS, cutoff=0.6):
        if close not in picked and close != name:
            picked.append(close)
    return [(n, where[n]) for n in picked[:SUGGESTIONS]]


# --------------------------------------------------------------------------- matches

def parse_null_output(data):
    """grep -H -n --null output -> ([(path, line, is_match, text)], other lines)."""
    records, other = [], []
    for raw in data.split(b"\n"):
        if not raw or raw == b"--":
            continue
        path, sep, rest = raw.partition(b"\0")
        match = re.match(rb"(\d+)([:-])(.*)", rest, re.S)
        if sep and match:
            records.append((path.decode(errors="replace"), int(match.group(1)), match.group(2) == b":",
                            match.group(3).decode(errors="replace")))
        else:
            other.append(raw.decode(errors="replace"))
    return records, other


def parse_filter_output(text):
    """Lines of an upstream `grep -r/-H` (path:N:text, path-N-text or path:text); None if any other line."""
    records, file_lines = [], {}
    for line in text.split("\n"):
        if not line or line == "--":
            continue
        record = None
        for match in re.finditer(r"([:-])(\d+)\1", line):
            path = line[:match.start()]
            if path and os.path.isfile(path):
                record = (path, int(match.group(2)), match.group(1) == ":", line[match.end():])
                break
        if record is None:
            path, sep, rest = line.partition(":")
            if not sep or not os.path.isfile(path):
                return None
            lines = file_lines.setdefault(path, Path(path).read_text(errors="replace").split("\n"))
            used = {r[1] for r in records if r[0] == path}
            numbers = [i + 1 for i, content in enumerate(lines) if content == rest and i + 1 not in used]
            if not numbers:
                return None
            record = (path, numbers[0], True, rest)
        records.append(record)
    return records or None


def clip(text):
    return text if len(text) <= LINE_CHARS else text[:LINE_CHARS] + "…"


def plural(n, word):
    return f"{n} {word}{'' if n == 1 else ('es' if word.endswith('ch') else 's')}"


class View:
    """Matches grouped by file and enclosing symbol, rendered under a character budget."""

    def __init__(self, repo, records, opts):
        self.repo, self.opts = repo, opts
        explicit = {repo.abspath(p) for p in opts["operands"] if os.path.isfile(p)}
        by_path = {}
        for path, line, is_match, text in records:
            by_path.setdefault(path, []).append((line, is_match, text))
        self.files = [{"path": path, "abs": repo.abspath(path), "display": repo.display(path), "rows": rows,
                       "matches": sum(1 for r in rows if r[1]), "source": repo.is_source(path),
                       "explicit": repo.abspath(path) in explicit, "def_lines": set(), "groups": None}
                      for path, rows in by_path.items()]
        self.total = sum(f["matches"] for f in self.files)

    def mark_definitions(self, definitions):
        """Flag definitions already among the matches; return the others."""
        located = {(f["abs"], r[0]): f for f in self.files for r in f["rows"] if r[1]}
        outside = []
        for d in definitions:
            owner = located.get((d["abs"], d["line"]))
            if owner is None:
                outside.append(d)
            else:
                owner["def_lines"].add(d["line"])
        return outside

    def split(self):
        has_source = any(f["source"] for f in self.files)
        shown = [f for f in self.files if f["source"] or f["explicit"] or not has_source]
        folded = [f for f in self.files if f not in shown]
        shown.sort(key=lambda f: 0 if f["def_lines"] else 1)
        return shown, folded

    def groups(self, f):
        """[{label, name, rows, matches, is_def}] in line order, definition groups first."""
        if f["groups"] is not None:
            return f["groups"]
        python = f["path"].endswith(".py")
        match_lines = sorted(r[0] for r in f["rows"] if r[1])
        keys = {}
        for line in match_lines:
            keys[line] = (self.repo.symbol(f["path"], line) if python else None) or ("", "", 0, 0)
        groups, order = {}, []
        for line, is_match, text in f["rows"]:
            if is_match:
                key = keys[line]
            else:  # a context row belongs with its nearest match
                key = keys[min(match_lines, key=lambda m: abs(m - line))] if match_lines else ("", "", 0, 0)
            if key not in groups:
                groups[key] = []
                order.append(key)
            groups[key].append((line, is_match, text))
        result = []
        for key in order:
            kind, qual, start, end = key
            is_def = start > 0 and start in f["def_lines"]
            if not kind:
                label, name = None, "lines"
            elif kind == "module":
                label, name = "  [module level]", "module level"
            else:
                label, name = f"  [{kind} {qual}, lines {start}-{end}{', definition' if is_def else ''}]", qual
            rows = sorted(groups[key])
            result.append({"label": label, "name": name, "rows": rows, "is_def": is_def,
                           "span": (start, end), "matches": [r for r in rows if r[1]]})
        result.sort(key=lambda g: 0 if g["is_def"] else 1)
        f["groups"] = result
        return result

    def render_scopes(self, f, char_budget):
        """Keep matches, then grow whole AST scopes within the formatted budget.

        Overlapping scopes share rows. Complete scopes never clip a source line.
        An oversized minimum or unparseable file is explicitly match-only.
        """
        heading = f"<file>{f['display']}</file> ({plural(f['matches'], 'match')})" + self.repo.version_note(f['path'])
        groups = self.groups(f)
        matches = sorted((r for g in groups for r in g['matches']),
                         key=lambda r: (r[0] not in f['def_lines'], r[0]))
        source = self.repo.lines(f['path'])
        selected, labels, spans, fallback = {}, [], {}, set()
        match_numbers = {r[0] for r in matches}

        def output():
            complete = sorted(set(spans.values()))
            complete = [s for s in complete if not any(o != s and o[0] <= s[0] and s[1] <= o[1] for o in complete)]
            notes = [f"  [scope lines {a}-{b}, complete]" for a, b in complete]
            if fallback:
                notes.append('  [scope incomplete: match-only fallback]')
            hidden = len(match_numbers - selected.keys())
            if hidden:
                notes.append(f'  +{hidden} more matches')
            return [heading, *notes, *labels,
                    *[f"{n}{':' if n in match_numbers else '-'}{text}" for n, text in sorted(selected.items())]]

        def fits():
            return sum(len(line) + 1 for line in output()) <= char_budget

        omitted = False
        for n, _, text in matches:
            label = next((g['label'] for g in groups if any(r[0] == n for r in g['matches'])), None)
            old_labels = list(labels)
            if label and label not in labels:
                labels.append(label)
            selected[n] = clip(text)
            fallback.add(n)
            if not fits():
                del selected[n]
                fallback.remove(n)
                labels = old_labels
                omitted = True
                break
        for n, _, _ in matches:
            if n not in selected or source is None:
                continue
            for start, end in self.repo.scope_chain(f['path'], n):
                old_rows, old_spans, old_fallback = dict(selected), dict(spans), set(fallback)
                selected.update((i, source[i - 1]) for i in range(start, end + 1))
                spans[n] = (start, end)
                fallback.difference_update(i for i in match_numbers if start <= i <= end)
                if not fits():
                    selected, spans, fallback = old_rows, old_spans, old_fallback
                    break
        if not selected:
            return [heading], True
        return output(), omitted or bool(fallback)

    def render_file(self, f, char_budget, context, want_body=False):
        """Render one file's matches, filling `char_budget` in priority order.

        Groups come definition-first (see groups()); within a group the definition line and,
        for a `def/class X` search, its body/skeleton come first, then the remaining matches.
        When the budget runs out we stop and note what was left with `+N more`, so there is no
        fixed per-file/per-symbol/per-match table — the single char budget decides how much shows."""
        if not context and f['path'].endswith('.py'):
            return self.render_scopes(f, char_budget)
        used = [0]

        def fits(line):
            if used[0] + len(line) + 1 > char_budget:
                return False
            used[0] += len(line) + 1
            return True

        lines = [f"<file>{f['display']}</file> ({plural(f['matches'], 'match')})" + self.repo.version_note(f['path'])]
        used[0] = len(lines[0]) + 1
        omitted = False
        groups = self.groups(f)
        shown_groups = 0
        for group in groups:
            header = [group["label"]] if group["label"] else []
            body_lines = []
            if want_body and group["is_def"] and not context:
                start, end = group["span"]
                # Whole body up to the budget, else the member skeleton; the budget is the cut,
                # so a long function shows a boundary window rather than nothing (vmini50 pattern).
                for n, text in self.repo.body(f["path"], start, end, UNLIMITED):
                    body_lines.append(f"{n}-{clip(text)}")
                if not body_lines:
                    body_lines = [clip(s) for s in self.repo.skeleton(f["path"], start, end)]
            match_rows = sorted(group["matches"], key=lambda r: (0 if r[0] in f["def_lines"] else 1, r[0]))
            ctx = {}
            if context:
                reach = self.opts["context"]
                ctx = {r[0]: r[2] for r in group["rows"]
                       if not r[1] and any(abs(r[0] - mr[0]) <= reach for mr in match_rows)}
            # Try to place this group's header, then its match lines (def line first) + body/context.
            trial = list(header)
            for r in match_rows:
                trial.append(f"{r[0]}:{clip(r[2])}")
            emitted_rows, cut_rows = [], []
            for line in trial:
                (emitted_rows if fits(line) else cut_rows).append(line)
            if len(emitted_rows) <= len(header) and group is not groups[0] and shown_groups:
                used[0] -= sum(len(l) + 1 for l in emitted_rows)   # no room for a real match: drop the header too
                omitted = True
                break
            lines += emitted_rows
            shown_groups += 1
            # Body/context lines fill whatever budget remains after the match lines.
            for n, text in sorted(ctx.items()):
                if fits(f"{n}-{clip(text)}"):
                    lines.append(f"{n}-{clip(text)}")
            for bl in body_lines:
                if fits(bl):
                    lines.append(bl)
            if cut_rows:
                omitted = True
                nums = [r[0] for r in match_rows][len(emitted_rows) - len(header):]
                listed = ", ".join(map(str, nums[:8])) + (", …" if len(nums) > 8 else "")
                if fits(f"  +{len(nums)} more at lines {listed}"):
                    lines.append(f"  +{len(nums)} more at lines {listed}")
                break
        hidden = groups[shown_groups:]
        if hidden:
            omitted = True
            count = sum(len(g["matches"]) for g in hidden)
            names = ", ".join(g["name"] for g in hidden)
            full = clip(f"  +{len(hidden)} more symbols ({plural(count, 'match')}): {names}")
            terse = f"  +{len(hidden)} more symbols ({plural(count, 'match')})"
            lines.append(full if used[0] + len(full) + 1 <= char_budget else terse)
        return lines, omitted

    def render(self, budget_chars, prefix, want_body=False):
        """Fill `budget_chars` in priority order: definitions, then source files, then folded.

        No per-file/per-symbol/per-match tables: each file gets the budget left after the ones
        before it, and render_file fills that adaptively. A file that cannot get a useful share
        (header + at least one match) is summarised with the rest as `+N more files`."""
        shown, folded = self.split()
        fold = []
        if folded:
            by_top = {}
            for f in folded:
                top = f["display"].split("/", 1)[0] + ("/" if "/" in f["display"] else "")
                by_top[top] = by_top.get(top, 0) + f["matches"]
            parts = ", ".join(f"{k} {v}" for k, v in sorted(by_top.items(), key=lambda kv: -kv[1]))
            fold = [clip(f"[folded] {plural(sum(f['matches'] for f in folded), 'match')} in "
                         f"{plural(len(folded), 'test/doc/other file')}: {parts}")]
        if self.opts["filter"]:
            hint = f"[raw] replace grep with {REAL_GREP} for unchanged output"
        else:
            hint = f"[raw] {REAL_GREP} {shlex.join(self.opts['argv'])}"

        def chars(lst):
            return sum(len(l) + 1 for l in lst)

        context = bool(self.opts["context"])
        body, omitted, placed = [], bool(folded), 0
        for i, f in enumerate(shown):
            # Reserve room for the fold line, the raw hint and a possible "+N more files" note.
            reserve = chars(fold) + len(hint) + 1 + 60
            remaining = budget_chars - chars(prefix) - chars(body) - reserve
            part, cut = self.render_file(f, remaining, context, want_body=want_body)
            # Needs at least a header and one real line; otherwise stop and summarise the rest.
            if len(part) < 2 and i:
                break
            body += part
            omitted |= cut
            placed = i + 1
        rest = shown[placed:]
        if rest:
            omitted = True
            body.append(clip(f"+{plural(len(rest), 'more file')} ({plural(sum(f['matches'] for f in rest), 'match')}): "
                             + ", ".join(f["display"] for f in rest)))
        summary = []
        if omitted or len(self.files) > 1:
            summary = [f"[grep] {plural(self.total, 'match')} in {plural(len(self.files), 'file')}"
                       + ("; Python source shown first" if folded else "")]
        raw = [hint] if omitted else []
        return summary + prefix + body + fold + raw


def definition_block(repo, definitions, overflow, others, compact):
    lines = []
    for name in dict.fromkeys(d["name"] for d in definitions):
        group = [d for d in definitions if d["name"] == name]
        if compact:
            lines += [f"[definition] {d['kind']} {d['qual']} {d['path']}:{d['start']}-{d['end']}" + repo.version_note(d['path']) for d in group]
            continue
        lines.append(f"[definitions of {name}]")
        for d in group:
            lines += [f"<file>{d['path']}</file>" + repo.version_note(d['path']),
                      f"  [{d['kind']} {d['qual']}, lines {d['start']}-{d['end']}, definition]",
                      f"{d['line']}:{clip(d['text'])}"]
            skeleton = repo.skeleton(d["path"], d["start"], d["end"])
            lines += [clip(s) for s in skeleton[:SKELETON_LINES]]
            if len(skeleton) > SKELETON_LINES:
                lines.append(f"    … +{len(skeleton) - SKELETON_LINES} more members")
    for name, extra in overflow.items():
        listed = ", ".join(f"{d['path']}:{d['line']}" for d in extra[:4]) + (", …" if len(extra) > 4 else "")
        lines.append(clip(f"  +{len(extra)} more definitions of {name}: {listed}"))
    for name, extra in others.items():
        listed = ", ".join(f"{d['path']}:{d['line']}" for d in extra[:4]) + (f" (+{len(extra) - 4})" if len(extra) > 4 else "")
        lines.append(clip(f"[other definitions of {name}] {listed}"))
    return lines


def identifier_like(name):
    """snake_case, CamelCase or digits: a code symbol rather than an English word like `default`."""
    return "_" in name.strip("_") or name.startswith("_") or any(c.isupper() or c.isdigit() for c in name)


def choose_definitions(repo, names, found, opts, files):
    """Definitions of the searched names, nearest to the search scope first."""
    scopes = [repo.abspath(p) for p in opts["operands"]] or [repo.cwd]
    near = {os.path.dirname(s) if os.path.isfile(s) else s for s in scopes} | {os.path.dirname(f["abs"]) for f in files}
    tops = {repo.rel(p).split("/", 1)[0] for p in near if not repo.rel(p).startswith("..")}

    def rank(d):
        if any(s != repo.root and (d["abs"] == s or d["abs"].startswith(s.rstrip("/") + "/")) for s in scopes):
            return 0
        if os.path.dirname(d["abs"]) in near:
            return 1
        return 2 if repo.rel(d["abs"]).split("/", 1)[0] in tops else 3

    ordered = []
    for prefix, name, qualifier in names:
        defs = found.get(name, [])
        if qualifier:
            defs = [d for d in defs if d["qual"].endswith(f"{qualifier}.{name}")] or defs
        if prefix == "class":
            defs = [d for d in defs if d["kind"] == "class"]
        elif prefix == "def":
            defs = [d for d in defs if d["kind"] in ("def", "method")]
        # Every definition can label a match; only these may be shown outside the matches.
        showable = bool(prefix) or (identifier_like(name) and len(defs) <= BARE_NAME_MAX_DEFS)
        ordered += [dict(d, showable=showable) for d in sorted(defs, key=lambda d: (rank(d), d["path"], d["line"]))]
    return ordered


def cap_definitions(outside):
    """Definitions outside the matches: at most DEFS_PER_NAME per name, DEFS_TOTAL overall."""
    shown, overflow = [], {}
    for d in outside:
        if len(shown) < DEFS_TOTAL and sum(1 for s in shown if s["name"] == d["name"]) < DEFS_PER_NAME:
            shown.append(d)
        else:
            overflow.setdefault(d["name"], []).append(d)
    return shown, overflow


def complete_definitions(view, lines, budget):
    """Append the whole visible definition set, or keep the original output.

    These are definitions already identified by GNU matches and the existing
    parser, not inferred change obligations. Preserve every original line and
    never choose a subset based on body length or a benchmark target.
    """
    if view.opts["context"]:
        return lines
    visible, current = {}, None
    for line in lines:
        tag = re.match(r"<file>(.*?)</file>", line)
        if tag:
            current = tag[1]
        row = re.match(r"(\d+)[:-](.*)", line)
        if current and row:
            visible[(current, int(row[1]))] = row[2]
    extra = []
    for f in view.split()[0]:
        source = view.repo.lines(f["path"])
        if source is None:
            continue
        for group in view.groups(f):
            start, end = group["span"]
            # The query can match a definition without spelling its exact name
            # (e.g. a substring or regex). Its parsed start is the evidence.
            if (start <= 0 or not any(row[0] == start for row in group["matches"])
                    or group["label"] not in lines):
                continue
            rows = [(n, source[n - 1]) for n in range(start, end + 1)]
            if all(visible.get((f["display"], n)) == text for n, text in rows):
                continue
            label = group["label"] if group["is_def"] else group["label"][:-1] + ", definition]"
            extra += [f"<file>{f['display']}</file>", label,
                      *[f"{n}-{text}" for n, text in rows]]
    if not extra:
        return lines
    result = [*lines, "[definition context] Complete bodies of the matched definitions shown above; review their relevance.",
              *extra, "[definition context] end"]
    return result if sum(len(line) + 1 for line in result) <= budget else lines


# --------------------------------------------------------------------------- main

def transform(opts, budget):
    """(raw bytes or None, exit code, lines or None)."""
    argv = opts["argv"]
    if opts["filter"]:
        result = subprocess.run(["grep", "--color=never", *argv], stdout=subprocess.PIPE, executable=REAL_GREP)
        try:
            return render_records(opts, budget, result, parse_filter_output(result.stdout.decode(errors="replace")), [])
        except Exception:
            return result.stdout, result.returncode, None   # standard input is consumed; show grep's output
    result = subprocess.run(["grep", "--color=never", "-H", "-n", "--null", *argv], stdout=subprocess.PIPE, executable=REAL_GREP)
    records, other = parse_null_output(result.stdout)
    return render_records(opts, budget, result, records, other)


def render_records(opts, budget, result, records, other):
    if records is None:          # filter input that is not grep output with file names
        return result.stdout, result.returncode, None
    budget_chars = budget
    repo = Repo()
    names = [] if opts["invert"] or opts["pattern_file"] else pattern_names(opts["patterns"], opts["syntax"])
    view = View(repo, records, opts)
    if opts["context"]:          # the model asked for surrounding lines: allow mini's full cut
        budget_chars = CONTEXT_CHARS
    shown, overflow, others, candidates = [], {}, {}, []
    if names:
        found = find_definitions(repo, {n for _, n, _ in names})
        candidates = choose_definitions(repo, names, found, opts, view.files)
        outside = view.mark_definitions(candidates)
        in_matches = {d["name"] for d in candidates if d not in outside}
        prefixed = {n for p, n, _ in names if p}
        # A definition already among the matches answers the search; others become one pointer line.
        for d in outside:
            if d["name"] in in_matches and d["name"] in prefixed:
                others.setdefault(d["name"], []).append(d)
        shown, overflow = cap_definitions([d for d in outside if d["name"] not in in_matches and d["showable"]])
    prefix = definition_block(repo, shown, overflow, others, compact=False)
    if sum(len(l) + 1 for l in prefix) > budget_chars // 2:     # definitions must not crowd out matches
        prefix = definition_block(repo, shown, overflow, others, compact=True)

    if not records:
        lines = list(prefix)
        if not shown and not overflow and not others:
            for prefix_kind, name, _ in names:
                close = suggestions(repo, name) if prefix_kind else []
                if close:
                    lines.append(clip(f"[suggest] no definition named {name}; similar: "
                                      + ", ".join(f"{n} ({where})" for n, where in close)))
        if not lines:
            return b"", result.returncode, None
        lines += ["[grep] no matches"]
        record_edit_focus(repo, names, candidates, records, lines)
        return None, result.returncode, lines
    want_body = bool(names) and any(prefix_kind for prefix_kind, _, _ in names)
    lines = view.render(budget_chars, prefix, want_body=want_body)
    # The budget covers match and body lines; file headers and "+N more" notes can go past it.
    # The whole view must be shown, so shrink the budget by the overflow and render again.
    while (over := sum(len(l) + 1 for l in lines + other) - WHOLE_OUTPUT_CHARS) > 0 and budget_chars > over:
        budget_chars -= over
        lines = view.render(budget_chars, prefix, want_body=want_body)
    lines += other
    if os.environ.get("ACI_GREP_COMPLETE_DEFINITIONS") == "1":
        lines = complete_definitions(view, lines, min(budget, WHOLE_OUTPUT_CHARS))
    record_edit_focus(repo, names, candidates, records, lines)
    return None, result.returncode, lines


def record_edit_focus(repo, names, candidates, records, lines):
    if os.environ.get('ACI_EDIT_FILTER') != '1':
        return
    try:
        directory = Path(os.environ.get('ACI_EDIT_FILTER_PATH', Path(__file__).resolve().parents[1] / 'edit-diff'))
        sys.path.insert(0, str(directory))
        import edit_filter
        edit_filter.record_observation(repo, names, candidates, records,
                                       ('\n'.join(lines) + '\n')[:WHOLE_OUTPUT_CHARS])
    except Exception:
        pass  # Observation instrumentation never changes GNU/G output/status.


def main(argv):
    signal.signal(signal.SIGPIPE, signal.SIG_DFL)
    try:
        opts = parse_args(argv)
        if not shown_to_model():
            raise Raw("not shown directly to the model")
        budget = MODEL_CHARS
    except Exception:
        os.execv(REAL_GREP, ["grep", *argv])
    try:
        raw, code, lines = transform(opts, budget)
    except Exception:
        if opts["filter"]:
            return 2
        os.execv(REAL_GREP, ["grep", *argv])
    out = sys.stdout.buffer
    out.write(raw if lines is None else ("\n".join(lines) + "\n").encode("utf-8", errors="replace"))
    out.flush()
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
