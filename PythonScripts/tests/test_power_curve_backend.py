from __future__ import annotations

import json
import math
import unittest
from pathlib import Path

import sys


PYTHON_SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(PYTHON_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(PYTHON_SCRIPTS_DIR))
from PowerCurveBackend import PowerCurveStore
from PowerCurveBackend import clamp_with_limits


def _payload() -> dict:
    return {
        "version": 1,
        "profiles": {
            "flat": {
                "limits": {
                    "min_power": 500,
                    "max_power": 3500,
                },
                "curves": {
                    "Low": {"points": [{"position_mm": 0, "power": 0}, {"position_mm": 1000, "power": 1000}, {"position_mm": 2000, "power": 2000}]},
                    "Normal": {"points": [{"position_mm": 0, "power": 0}, {"position_mm": 1000, "power": 1500}, {"position_mm": 2000, "power": 3000}]},
                    "High": {"points": [{"position_mm": 0, "power": 0}, {"position_mm": 1000, "power": 2000}, {"position_mm": 2000, "power": 4000}]},
                },
            },
            "chip": {
                "limits": {
                    "min_power": 800,
                    "max_power": 5000,
                },
                "curves": {
                    "Low": {"points": [{"position_mm": 0, "power": 800}, {"position_mm": 1000, "power": 1400}, {"position_mm": 2000, "power": 2200}]},
                    "Normal": {"points": [{"position_mm": 0, "power": 1000}, {"position_mm": 1000, "power": 2200}, {"position_mm": 2000, "power": 3600}]},
                    "High": {"points": [{"position_mm": 0, "power": 1200}, {"position_mm": 1000, "power": 3000}, {"position_mm": 2000, "power": 4800}]},
                },
            },
        },
    }


class PowerCurveBackendTest(unittest.TestCase):
    def setUp(self) -> None:
        self.curve_file = Path(__file__).resolve().parent / "_curve_test_runtime.json"
        self.curve_file.write_text(json.dumps(_payload()), encoding="utf-8")
        self.store = PowerCurveStore(curve_file=self.curve_file, reload_interval_sec=0.0)

    def tearDown(self) -> None:
        if self.curve_file.exists():
            self.curve_file.unlink()

    def test_hits_exact_nodes(self) -> None:
        self.assertEqual(self.store.evaluate(0, "Low"), 0)
        self.assertEqual(self.store.evaluate(1000, "Normal"), 1500)
        self.assertEqual(self.store.evaluate(2000, "High"), 4000)
        self.assertEqual(self.store.evaluate(1000, "High", profile="chip"), 3000)

    def test_monotone_curve_stays_monotone_and_finite(self) -> None:
        values = [self.store.evaluate(distance, "High") for distance in range(0, 2001, 50)]
        self.assertTrue(all(math.isfinite(value) for value in values))
        self.assertEqual(values, sorted(values))
        self.assertGreaterEqual(min(values), 0)
        self.assertLessEqual(max(values), 4000)

    def test_out_of_range_uses_endpoints(self) -> None:
        self.assertEqual(self.store.evaluate(-100, "Low"), 0)
        self.assertEqual(self.store.evaluate(99999, "Low"), 2000)

    def test_invalid_reload_keeps_previous_cache(self) -> None:
        before = self.store.evaluate(1500, "Normal")
        self.curve_file.write_text("{invalid json", encoding="utf-8")
        after = self.store.evaluate(1500, "Normal")
        self.assertEqual(before, after)

    def test_limits_snapshot_and_clamp(self) -> None:
        limits = self.store.limits_snapshot()
        self.assertEqual(limits["min_power"], 500)
        self.assertEqual(limits["max_power"], 3500)
        self.assertEqual(clamp_with_limits(200, limits), 500)
        self.assertEqual(clamp_with_limits(9999, limits), 3500)
        self.assertEqual(clamp_with_limits(3200, limits, hard_max=3000), 3000)

    def test_chip_profile_uses_independent_curves_and_limits(self) -> None:
        flat_value = self.store.evaluate(1000, "Normal", profile="flat")
        chip_value = self.store.evaluate(1000, "Normal", profile="chip")
        self.assertNotEqual(flat_value, chip_value)
        chip_limits = self.store.limits_snapshot(profile="chip")
        self.assertEqual(chip_limits["min_power"], 800)
        self.assertEqual(chip_limits["max_power"], 5000)

    def test_legacy_payload_is_migrated_to_chip_clone(self) -> None:
        legacy_payload = {
            "version": 1,
            "limits": {"min_power": 400, "max_power": 2800},
            "curves": {
                "Low": {"points": [{"position_mm": 0, "power": 0}, {"position_mm": 2000, "power": 2000}]},
                "Normal": {"points": [{"position_mm": 0, "power": 0}, {"position_mm": 2000, "power": 2600}]},
                "High": {"points": [{"position_mm": 0, "power": 0}, {"position_mm": 2000, "power": 2800}]},
            },
        }
        self.curve_file.write_text(json.dumps(legacy_payload), encoding="utf-8")
        migrated_store = PowerCurveStore(curve_file=self.curve_file, reload_interval_sec=0.0)
        self.assertEqual(
            migrated_store.evaluate(1500, "Normal", profile="flat"),
            migrated_store.evaluate(1500, "Normal", profile="chip"),
        )
        self.assertEqual(migrated_store.limits_snapshot(profile="chip")["max_power"], 2800)


if __name__ == "__main__":
    unittest.main()
