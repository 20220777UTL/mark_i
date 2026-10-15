"""Invalid frames and hardware/simulation possession must gate every state."""
import math
import unittest
from pathlib import Path
from unittest.mock import mock_open, patch
from two_attack_fixture import Harness, Point
from Play.Normal import AttackParams as A
from Play.Normal.AttackFeedback import chip_feedback, load_calibration


class VisionTests(unittest.TestCase):
    def test_simulation_never_calls_infrared_even_with_telemetry(self):
        h = Harness()
        h.player.isInfraredOn.side_effect = AssertionError('not available in simulation')
        with patch.object(Path, 'open', mock_open()):
            h.c.telemetry = 'trace.jsonl'
            h.settle()
        self.assertTrue(h.c.held[0])
        for method in (h.player.isInfraredOn, h.player.infraredCount, h.player.infraredOffCount):
            method.assert_not_called()

    def test_real_requires_ir_and_uses_elapsed_time(self):
        for dt in (.01, .025):
            h = Harness(False)
            for _ in range(20): h.update(dt)
            self.assertFalse(h.c.held[0])
            h.ir[0] = True
            h.update(dt)
            self.assertFalse(h.c.held[0])
            for _ in range(math.ceil(A.POSSESSION_SECONDS / dt) + 1): h.update(dt)
            self.assertTrue(h.c.held[0])
            h.ir[0] = False
            h.update(dt)
            self.assertFalse(h.c.held[0])

    def test_real_ir_does_not_require_the_old_narrow_window(self):
        h = Harness(False)
        h.ball = Point(125, 20)
        h.ir[0] = True
        h.settle()
        self.assertTrue(h.c.held[0])

    def test_ir_chatter_and_sensor_failure_do_not_fall_back_to_vision(self):
        h = Harness(False)
        for _ in range(4):
            h.ir[0] = True
            h.update(.02)
            h.ir[0] = False
            h.update(.02)
        self.assertFalse(h.c.held[0])
        h.player.isInfraredOn.side_effect = RuntimeError('no radio')
        h.update()
        self.assertFalse(h.c.valid)
        h.run(h.state('FirstPass'))
        h.cpp.makeItRushTo.assert_not_called()
        h.kicks.setKick.assert_not_called()

    def test_fast_glancing_ball_is_not_possession(self):
        h = Harness()
        h.velocity = Point(0, 1800)
        h.settle()
        self.assertFalse(h.c.held[0])
        h.velocity = Point(0, 0)
        h.omegas[0] = 5
        h.settle()
        self.assertFalse(h.c.held[0])

    def test_invalid_input_in_every_state_stops_without_transition(self):
        faults = (
            lambda h: setattr(h, 'ball_valid', False),
            lambda h: h.robot_valid.update({1: False}),
            lambda h: setattr(h, 'ball', Point(float('nan'), 0)),
            lambda h: setattr(h, 'velocity', Point(float('inf'), 0)),
            lambda h: h.headings.update({0: float('nan')}),
            lambda h: h.positions.update({1: Point(99999, 0)}),
            lambda h: h.headings.update({0: 9999}),
        )
        for state in ('FirstPass', 'PassBack', 'Shoot', 'FollowShot', 'Done'):
            for fault in faults:
                with self.subTest(state=state, fault=fault):
                    h = Harness()
                    h.settle()
                    fault(h)
                    h.update()
                    h.clear_commands()
                    self.assertEqual(h.run(h.state(state)), '')
                    self.assertEqual(h.cpp.makeItStop.call_count, 2)
                    h.cpp.makeItRushTo.assert_not_called()
                    h.kicks.setKick.assert_not_called()
                    h.kicks.setChipKick.assert_not_called()
                    self.assertFalse(any(h.c.held.values()))

    def test_invalid_ball_is_not_read(self):
        h = Harness()
        h.ball_valid = False
        h.ball_api.pos.side_effect = AssertionError('invalid ball read')
        h.update()
        h.run(h.state('FirstPass'))
        h.ball_api.pos.assert_not_called()

    def test_repeated_frame_and_long_gap_cannot_confirm_possession(self):
        h = Harness()
        h.update()
        for _ in range(5): h.update(fresh=False)
        self.assertFalse(h.c.valid)
        h.update(.5)
        self.assertFalse(h.c.held[0])
        h.settle()
        self.assertTrue(h.c.held[0])

    def test_pause_keeps_real_ir_dribbler_but_not_kick(self):
        h = Harness(False)
        h.ir[0] = True
        h.settle()
        h.ball_valid = False
        h.update()
        h.run(h.state('Shoot'))
        h.cpp.setDribbleCommand.assert_any_call(0, A.DRIBBLE_COMMAND)
        h.cpp.setDribbleCommand.assert_any_call(1, 0)
        h.kicks.setBothKick.assert_any_call(0, 0, 0)

    def test_recovery_does_not_bridge_carry_or_goal(self):
        h = Harness(False)
        h.ir[0] = True
        h.settle()
        h.c.carry[0] = 100
        h.ball_valid = False
        h.update()
        h.positions[0] = Point(500, 0)
        h.ball = Point(600, 0)
        h.ball_valid = True
        h.update()
        self.assertEqual(h.c.carry[0], 100)
        self.assertFalse(h.c.held[0])
        h.ball = Point(4400, 0)
        h.ir[0] = False
        h.update()
        h.ball_valid = False
        h.update()
        h.ball = Point(4600, 0)
        h.ball_valid = True
        h.update()
        self.assertEqual(h.c.outcome, 'out')

    def test_zero_chip_defaults_are_unknown_not_ground(self):
        h = Harness()
        feedback = chip_feedback(h.ball_api, (100, 0))
        self.assertIsNone(feedback.height)
        self.assertFalse(feedback.ground)
        self.assertIsNone(feedback.predicted)

    def test_stale_height_for_another_position_is_rejected(self):
        h = Harness()
        h.native.RealPos = lambda: Point(2000, 2000, 22)
        self.assertFalse(chip_feedback(h.ball_api, (100, 0)).ground)

    def test_zero_height_needs_real_xy_and_all_zero_origin_is_unknown(self):
        h = Harness()
        h.height = 0
        self.assertTrue(chip_feedback(h.ball_api, (100, 0)).ground)
        h.ball = Point(0, 0)
        self.assertFalse(chip_feedback(h.ball_api, (0, 0)).ground)

    def test_optional_feedback_failure_and_nan_diagnostics_do_not_crash(self):
        h = Harness(False)
        h.native.RealPos = lambda: (_ for _ in ()).throw(RuntimeError('unsupported'))
        h.player.infraredCount.return_value = float('nan')
        output = mock_open()
        with patch.object(Path, 'open', output):
            h.c.telemetry = 'trace.jsonl'
            h.update()
            self.assertNotIn('NaN', output().write.call_args.args[0])

    def test_default_profiles_are_separate_and_uncalibrated(self):
        self.assertFalse(load_calibration('real')['chip']['calibrated'])
        self.assertFalse(load_calibration('simulation')['chip']['calibrated'])
        self.assertIsNone(load_calibration('real')['mouth_offsets_mm']['0'])


if __name__ == '__main__':
    unittest.main()
