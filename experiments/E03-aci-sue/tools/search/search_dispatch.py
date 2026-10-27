"""CLI bridge to unchanged AutoCodeRover search APIs."""

import argparse
import inspect
from pathlib import Path
import subprocess
import sys

from joblib import Memory

upstream = Path(__file__).resolve().parent / "upstream" / "auto-code-rover"
sys.path.insert(0, str(upstream))
from app.search.search_backend import SearchBackend
from app.search.search_utils import find_python_files


@Memory(Path(__file__).resolve().parent / ".cache", verbose=0).cache
def indexed_backend(project_path, source_state):
    """Persist the original backend; file metadata invalidates it after edits."""
    return SearchBackend(project_path)


def get_backend(project_path):
    files = sorted(Path(path) for path in find_python_files(project_path))
    source_state = []
    for path in files:
        stat = path.stat()
        source_state.append((str(path), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
    return indexed_backend(project_path, source_state)


def main():
    # The native startup command installs tools before the agent budget starts.
    if sys.argv[1] == "--prepare":
        get_backend(sys.argv[2])
        return

    method = getattr(SearchBackend, sys.argv[1])
    parser = argparse.ArgumentParser(prog=sys.argv[1], description=inspect.getdoc(method))
    parameters = [name for name in inspect.signature(method).parameters if name != "self"]
    for name in parameters:
        parser.add_argument(name)
    args = parser.parse_args(sys.argv[2:])

    # Do not trust cwd after an agent changes directory inside the repository.
    root = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True, check=True
    )
    project_path = root.stdout.strip()
    backend = get_backend(project_path)
    print(method(backend, *(getattr(args, name) for name in parameters))[0])


if __name__ == "__main__":
    main()
