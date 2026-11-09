"""analyze_main 검정 함수 단위 테스트. 손으로 계산 가능한 값과 비교한다."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import analyze_main as am  # noqa: E402


class McNemarTests(unittest.TestCase):
    def test_known_values(self):
        self.assertAlmostEqual(am.mcnemar_exact(3, 1), 0.625)  # 2*(1+4)/16
        self.assertAlmostEqual(am.mcnemar_exact(0, 0), 1.0)
        self.assertAlmostEqual(am.mcnemar_exact(5, 0), 2 / 32)
        self.assertAlmostEqual(am.mcnemar_exact(2, 2), 1.0)


class WilcoxonTests(unittest.TestCase):
    def test_all_same_sign(self):
        self.assertAlmostEqual(am.wilcoxon_exact([1, 2, 3, 4, 5]), 2 / 32)
        self.assertAlmostEqual(am.wilcoxon_exact([-x for x in range(1, 31)]), 2 / 2 ** 30)

    def test_symmetric_is_one(self):
        self.assertAlmostEqual(am.wilcoxon_exact([1, -1, 2, -2]), 1.0)

    def test_zeros_dropped_and_ties(self):
        # 0 은 버리고 |1|,|1| 동순위(1.5,1.5), 3 은 순위 3. W+ = 1.5+3 = 4.5, 총합 6.
        # 8 조합의 W+: 0,1.5,1.5,3,3,4.5,4.5,6 → W+ ≤ 1.5 인 경우 3개 → p = 2*3/8
        self.assertAlmostEqual(am.wilcoxon_exact([0, 1, -1, 3]), 0.75)


if __name__ == "__main__":
    unittest.main()
