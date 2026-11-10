"""CLI bridge to the AutoCodeRover search APIs.

The upstream SearchBackend is reused unchanged. This dispatcher adds two
agent-computer-interface (ACI) improvements observed to matter in the
Verified Mini dev runs, applied only in this wrapper layer:

1. Lenient argument routing. A 1-argument search (search_method/search_class/
   search_code) called with an extra file-path argument is routed to the
   matching *_in_file API instead of failing argparse. Wrong tool/arg choices
   were ~17% of search calls in the baseline-S run.

2. Exact-then-fuzzy matching. When the backend reports "could not find", the
   dispatcher proposes near-miss symbol names from the live index (substring
   and difflib close matches) so the agent can retry instead of falling back
   to blind line reads (~32% of calls in baseline-S).

Neither path changes upstream search results; they only recover from unusable
calls and annotate not-found output with concrete suggestions.
"""

import argparse
import difflib
import inspect
from pathlib import Path
import subprocess
import sys

from joblib import Memory

upstream = Path(__file__).resolve().parent / "upstream" / "auto-code-rover"
sys.path.insert(0, str(upstream))
from app.search.search_backend import SearchBackend
from app.search.search_utils import find_python_files

# 1-arg name searches and the 2-arg API they route to when given a file path.
FILE_ROUTES = {
    "search_method": "search_method_in_file",
    "search_class": "search_class_in_file",
    "search_code": "search_code_in_file",
}
MAX_SUGGESTIONS = 8


@Memory(Path(__file__).resolve().parent / ".cache", verbose=0).cache
def indexed_backend(project_path, source_state):
    """Persist the original backend; file metadata invalidates it after edits."""
    return SearchBackend(project_path)


def get_backend(project_path):
    files = sorted(Path(path) for path in find_python_files(project_path))
    source_state = []
    for path in files:
        try:
            stat = path.stat()
        except OSError:
            source_state.append((str(path), None))
        else:
            source_state.append((str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
    return indexed_backend(project_path, source_state)


def looks_like_path(value):
    """Heuristic: an extra arg is a file path, not a symbol name."""
    return value.endswith(".py") or "/" in value


def index_names(backend, tool):
    """Candidate symbol names from the live index for fuzzy suggestions."""
    if "class" in tool:
        return list(getattr(backend, "class_index", {}).keys())
    names = list(getattr(backend, "function_index", {}).keys())
    class_func = getattr(backend, "class_func_index", {}) or {}
    for methods in class_func.values():
        names.extend(methods.keys())
    return names


def fuzzy_suggestions(query, names):
    """Substring matches first, then difflib close matches."""
    uniq = sorted(set(names))
    sub = [n for n in uniq if query.lower() in n.lower() or n.lower() in query.lower()]
    close = difflib.get_close_matches(query, uniq, n=MAX_SUGGESTIONS, cutoff=0.6)
    ordered = []
    for n in sub + close:
        if n not in ordered and n != query:
            ordered.append(n)
    return ordered[:MAX_SUGGESTIONS]


def run_tool(backend, tool, args):
    method = getattr(SearchBackend, tool)
    params = [n for n in inspect.signature(method).parameters if n != "self"]
    output, _results, ok = method(backend, *args[: len(params)])
    return output, ok, params


def main():
    # The native startup command installs tools before the agent budget starts.
    if sys.argv[1] == "--prepare":
        get_backend(sys.argv[2])
        return

    tool = sys.argv[1]
    raw_args = sys.argv[2:]

    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    project_path = root.stdout.strip()
    backend = get_backend(project_path)

    expected = [n for n in inspect.signature(getattr(SearchBackend, tool)).parameters if n != "self"]

    # (1) Lenient routing: 1-arg name search given an extra path -> *_in_file.
    if tool in FILE_ROUTES and len(raw_args) == 2 and looks_like_path(raw_args[1]):
        routed = FILE_ROUTES[tool]
        output, ok, _ = run_tool(backend, routed, [raw_args[0], raw_args[1]])
        print(f"[note] '{tool} NAME FILE' routed to '{routed}'.\n")
        print(output)
        return

    # Otherwise parse strictly against the real signature, but on arity mismatch
    # give a helpful message instead of a bare argparse error.
    if len(raw_args) != len(expected):
        print(
            f"[usage] {tool} expects {len(expected)} argument(s): {', '.join(expected)}.\n"
            f"Received {len(raw_args)}: {raw_args}.\n"
            f"For a file-scoped search use one of: "
            f"search_method_in_file, search_class_in_file, search_code_in_file, "
            f"search_method_in_class."
        )
        return

    output, ok, _ = run_tool(backend, tool, raw_args)

    # (2) Fuzzy fallback on not-found for name searches.
    if not ok and tool in ("search_method", "search_class", "search_method_in_class", "search_method_in_file"):
        query = raw_args[0]
        suggestions = fuzzy_suggestions(query, index_names(backend, tool))
        print(output)
        if suggestions:
            print(
                f"\n[suggest] No exact match for '{query}'. "
                f"Closest indexed symbols: {', '.join(suggestions)}.\n"
                f"Retry with one of these names if it matches your target."
            )
        return

    print(output)


if __name__ == "__main__":
    main()
