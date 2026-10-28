# Sourced by mini's native startup command or the README host checks.
(
    set -eu
    bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    uv venv --python 3.12 "$bundle_dir/.venv"
    uv pip install --python "$bundle_dir/.venv/bin/python" -r "$bundle_dir/requirements.txt"
)
