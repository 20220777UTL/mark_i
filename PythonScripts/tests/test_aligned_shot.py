"""Exercise the real skill with simulated vision and captured native commands."""
import math
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


def point(x, y):
    return SimpleNamespace(x=lambda: x, y=lambda: y)


class AlignedShotTests(unittest.TestCase):
    def setUp(self):
        self.cpp = Mock()
        self.kicks = Mock()
        self.player = Mock()
        self.player.isValid.return_value = True
        self.player.Pos.return_value = point(0, 0)
        self.player.direction.return_value = 0.0
        self.player.rotVel.return_value = 0.0
        self.player.isInfraredOn.side_effect = AssertionError("Infrared unavailable in simulation")
        self.ball = Mock()
        self.ball.valid.return_value = True
        self.ball.pos.return_value = point(95, 0)
        modules = {
            'CppPackage': self.cpp,
            'Vision': SimpleNamespace(Ball=self.ball, Player=self.player),
            'WorldModel': SimpleNamespace(
                Flags=SimpleNamespace(force_kick=0x80000000),
                Positions=SimpleNamespace(theirGoal=point(4500, 0)),
                kickStatus=self.kicks),
        }
        path = Path(__file__).resolve().parents[1] / 'RoleMatch_LuaStyle/Skills/AlignedShot.py'
        with patch.dict(sys.modules, modules):
            self.skill = runpy.run_path(str(path))['TurnAndShootAligned']

    def run_skill(self, **kwargs):
        execute, _ = self.skill(power=6000, **kwargs)
        execute(1)

    def assert_no_shot(self):
        self.kicks.setKick.assert_not_called()
        self.kicks.setChipKick.assert_not_called()

    def test_aligned_zero_angle_fires_and_clears_only_own_previous_command(self):
        self.run_skill(angle=0)
        self.kicks.setBothKick.assert_called_once_with(1, 0, 0)
        self.kicks.setKick.assert_called_once_with(1, 6000)
        self.cpp.makeItSimpleGoTo.assert_called_once()

    def test_wrong_heading_blocks(self):
        self.run_skill(angle=math.pi / 2)
        self.assert_no_shot()
        self.assertAlmostEqual(self.cpp.makeItSimpleGoTo.call_args.args[2], math.pi / 2)

    def test_fast_rotation_blocks_even_when_current_heading_is_correct(self):
        self.player.rotVel.return_value = -2.0
        self.run_skill(angle=0)
        self.assert_no_shot()

    def test_wraparound_at_pi(self):
        heading = math.radians(179)
        self.player.direction.return_value = heading
        self.ball.pos.return_value = point(95 * math.cos(heading), 95 * math.sin(heading))
        self.run_skill(angle=math.radians(-179))
        self.kicks.setKick.assert_called_once()

    def test_ball_behind_or_far_blocks(self):
        for position in (point(-95, 0), point(500, 0)):
            with self.subTest(position=position):
                self.ball.pos.return_value = position
                self.run_skill(angle=0)
                self.assert_no_shot()

    def test_fires_without_reading_infrared(self):
        self.run_skill(angle=0)
        self.kicks.setKick.assert_called_once_with(1, 6000)
        self.player.isInfraredOn.assert_not_called()

    def test_missing_vision_stops_without_movement(self):
        self.ball.valid.return_value = False
        self.run_skill(angle=0)
        self.assert_no_shot()
        self.cpp.makeItStop.assert_called_once_with(1)
        self.cpp.makeItSimpleGoTo.assert_not_called()

    def test_nonfinite_vision_stops(self):
        self.player.direction.return_value = float('nan')
        self.run_skill(angle=0)
        self.assert_no_shot()
        self.cpp.makeItStop.assert_called_once_with(1)

    def test_target_direction_is_measured_from_ball(self):
        self.run_skill(target=point(95, 1000))
        self.assertAlmostEqual(self.cpp.makeItSimpleGoTo.call_args.args[2], math.pi / 2)
        self.assert_no_shot()

    def test_chip_and_default_goal(self):
        self.run_skill(isChip=True)
        self.kicks.setChipKick.assert_called_once_with(1, 6000)
        self.kicks.setKick.assert_not_called()

    def test_force_kick_cannot_bypass_gate(self):
        self.run_skill(angle=math.pi / 2, flag=0x80000001)
        self.assert_no_shot()
        self.assertEqual(self.cpp.makeItSimpleGoTo.call_args.args[3], 1)

    def test_reused_closure_rechecks_vision_each_frame(self):
        execute, _ = self.skill(angle=0, power=6000)
        self.player.direction.return_value = 1.0
        execute(1)
        self.assert_no_shot()
        self.player.direction.return_value = 0.0
        execute(1)
        self.kicks.setKick.assert_called_once()
        self.player.direction.return_value = 1.0
        execute(1)
        self.kicks.setKick.assert_called_once()
        self.assertEqual(self.kicks.setBothKick.call_count, 3)

    def test_invalid_parameters_rejected(self):
        for kwargs in ({'angle': 0, 'target': point(1, 1)},
                       {'angle': float('nan')}, {'tolerance': 0},
                       {'maxRotVel': -1}, {'power': -1}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                self.skill(**({'power': 6000} | kwargs))


if __name__ == '__main__':
    unittest.main()
