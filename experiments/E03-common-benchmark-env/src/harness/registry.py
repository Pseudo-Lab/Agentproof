"""알고리즘 목록: algorithms/*/algorithm.toml 을 읽는다. 알고리즘 추가 = 폴더 하나 추가."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]          # <실험>/src/
ALGORITHMS = ROOT / "algorithms"


@dataclass
class AlgorithmSpec:
    name: str
    description: str
    adapter: str                  # "algorithms.mem0.adapter:Mem0Adapter"
    folder: Path
    python_version: str
    venv: Path
    requirements: Path
    capabilities: list[str] = field(default_factory=list)
    config: dict = field(default_factory=dict)

    @property
    def python(self) -> Path:
        return self.venv / "bin" / "python"


def load_algorithm(folder: Path) -> AlgorithmSpec:
    raw = tomllib.loads((folder / "algorithm.toml").read_text())
    venv = (folder / raw["venv"]).resolve() if raw.get("venv") else folder / ".venv"
    config = dict(raw.get("config", {}))
    if raw.get("source"):          # 원본 코드 위치 → 어댑터 setup(config) 에 절대경로로 전달
        config["source"] = str((folder / raw["source"]).resolve())
    return AlgorithmSpec(name=raw["name"], description=raw.get("description", ""), adapter=raw["adapter"],
                         folder=folder, python_version=raw.get("python", "3.12"), venv=venv,
                         requirements=folder / raw.get("requirements", "requirements.txt"),
                         capabilities=raw.get("capabilities", []), config=config)


def algorithms() -> dict[str, AlgorithmSpec]:
    specs = [load_algorithm(p.parent) for p in sorted(ALGORITHMS.glob("*/algorithm.toml"))]
    return {s.name: s for s in specs}
