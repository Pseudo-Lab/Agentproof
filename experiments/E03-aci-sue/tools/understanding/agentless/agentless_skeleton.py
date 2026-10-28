"""CLI adapter for Agentless's unchanged get_skeleton."""

import argparse
from pathlib import Path
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("file_path", type=Path)
    args = parser.parse_args()
    upstream = Path(__file__).resolve().parent / "upstream" / "Agentless"
    sys.path.insert(0, str(upstream))
    from agentless.util.compress_file import get_skeleton

    source = args.file_path.read_text(encoding="utf-8")
    print(get_skeleton(source, compress_assign=True), end="")


if __name__ == "__main__":
    main()
