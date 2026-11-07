"""run.py 설정 폴더 선택(--config-dir) 단위 테스트. 모델 호출 없음.
run.py 를 import 하므로 mini-swe-agent 가 설치된 환경(.venv)에서 돈다."""
import copy
import json
import sys
import tempfile
import unittest
from pathlib import Path

EXPERIMENT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(EXPERIMENT / "src"))
try:
    import run  # noqa: E402
except ImportError as e:  # mini-swe-agent 없음
    run = None
    IMPORT_ERROR = e


@unittest.skipIf(run is None, "mini-swe-agent 가 없어 run.py 를 import 할 수 없다")
class ConfigDirTests(unittest.TestCase):
    def write_pair(self, d: Path, a: dict, b: dict):
        (d / "baseline.json").write_text(json.dumps(a))
        (d / "intervention.json").write_text(json.dumps(b))

    def test_default_dir_is_unchanged(self):
        cfgs = run.load_configs()
        self.assertEqual(cfgs["baseline"]["limits"]["max_turns"], 30)
        self.assertEqual(run.config_label(run.DEFAULT_CONFIG_DIR, "baseline"), "configs/baseline.json")

    def test_ctx16k_differs_only_in_context_and_turns(self):
        base = run.load_configs()
        new = run.load_configs(EXPERIMENT / "configs" / "ctx16k")
        for c in run.CONDITIONS:
            a, b = copy.deepcopy(base[c]), copy.deepcopy(new[c])
            self.assertEqual(b["model"]["options"]["num_ctx"], 16384)
            self.assertEqual(b["limits"]["context_tokens"], 16384)
            self.assertEqual(b["limits"]["max_turns"], 50)
            for x in (a, b):
                x["model"]["options"].pop("num_ctx")
                for k in ("context_tokens", "max_turns", "note"):
                    x["limits"].pop(k)
            self.assertEqual(a, b)
        self.assertEqual(run.config_label(EXPERIMENT / "configs" / "ctx16k", "intervention"),
                         "configs/ctx16k/intervention.json")

    def test_mismatch_outside_compression_is_rejected(self):
        a = json.loads((run.DEFAULT_CONFIG_DIR / "baseline.json").read_text())
        b = json.loads((run.DEFAULT_CONFIG_DIR / "intervention.json").read_text())
        b["limits"]["max_turns"] = 31
        with tempfile.TemporaryDirectory() as d:
            self.write_pair(Path(d), a, b)
            with self.assertRaises(SystemExit):
                run.load_configs(Path(d))

    def test_wrong_condition_field_is_rejected(self):
        a = json.loads((run.DEFAULT_CONFIG_DIR / "baseline.json").read_text())
        with tempfile.TemporaryDirectory() as d:
            self.write_pair(Path(d), a, a)
            with self.assertRaises(SystemExit):
                run.load_configs(Path(d))


if __name__ == "__main__":
    unittest.main()
