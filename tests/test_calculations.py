import unittest

from signal_lens.calculations import cagr, delta, evidence_strength, pct_change, persistence, z_score


class CalculationTests(unittest.TestCase):
    def test_percentage_change(self):
        self.assertAlmostEqual(pct_change(125, 100), 25.0)

    def test_delta(self):
        self.assertAlmostEqual(delta(0.7, 1.1), -0.4)

    def test_cagr(self):
        self.assertAlmostEqual(cagr(100, 121, 2), 10.0, places=5)

    def test_z_score_is_zero_for_flat_peers(self):
        self.assertEqual(z_score(3, [3, 3, 3]), 0.0)

    def test_persistence_counts_from_newest_period(self):
        self.assertEqual(persistence([0, 1, 2, 3], threshold=1), 3)

    def test_strength_reasoning_is_transparent(self):
        label, reasoning = evidence_strength(4, 3, 3)
        self.assertEqual(label, "Strong")
        self.assertIn("4 surviving", reasoning)


if __name__ == "__main__":
    unittest.main()
