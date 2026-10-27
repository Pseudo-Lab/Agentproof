#!/usr/bin/env bash
# 가상환경 만들기.
#   scripts/setup_venv.sh harness   → src/.venv               (requirements.txt)
#   scripts/setup_venv.sh <algo>    → algorithms/<algo>/.venv  (algorithm.toml 의 python·requirements)
# algorithm.toml 에 venv 를 지정했으면(기존 환경 재사용) 그 경로에 설치한다.
# 알고리즘 폴더에 setup.sh 가 있으면 venv 생성 전에 먼저 실행한다(원본 코드 확인 등).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TARGET="${1:?사용: scripts/setup_venv.sh harness|<algorithm>}"

if [ "$TARGET" = "harness" ]; then
  uv venv --python 3.12 "$ROOT/.venv"
  uv pip install --python "$ROOT/.venv/bin/python" -r "$ROOT/requirements.txt"
  "$ROOT/.venv/bin/python" -m nltk.downloader -q punkt_tab
  exit 0
fi

DIR="$ROOT/algorithms/$TARGET"
[ -f "$DIR/algorithm.toml" ] || { echo "알고리즘 없음: $TARGET" >&2; exit 1; }
read -r PY VENV REQ < <(python3 - "$DIR" <<'EOF'
import sys, tomllib, pathlib
d = pathlib.Path(sys.argv[1]); t = tomllib.loads((d / "algorithm.toml").read_text())
venv = (d / t["venv"]).resolve() if t.get("venv") else d / ".venv"
print(t.get("python", "3.12"), venv, d / t.get("requirements", "requirements.txt"))
EOF
)
[ -x "$DIR/setup.sh" ] && "$DIR/setup.sh"
[ -x "$VENV/bin/python" ] || uv venv --python "$PY" "$VENV"
uv pip install --python "$VENV/bin/python" -r "$REQ"
echo "$TARGET: $VENV"
