"""用真实调度代码、伪视觉和伪技能验证完整流程；不模拟原生球物理。"""
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

import test_corner_pass_shot as corner_tests
from test_two_attack_vision import Point


class GiveAndGoTests(unittest.TestCase):
    def setUp(self):
        corner_tests.CornerPassTests.setUp(self)
        base_module = self.module
        self.positions = {1: Point(-160, 0), 2: Point(-1200, 500)}
        self.angles = {1: 0, 2: 0}
        self.infrared = {1: False, 2: False}
        self.player.Pos = lambda n: self.positions[n]
        self.player.direction = lambda n: self.angles[n]
        self.player.isInfraredOn = lambda n: self.infrared[n]
        self.ball.pos = lambda: Point(0, 0)
        self.kicks.setKick = Mock()

        def skill(kind, *args, **kwargs):
            run = Mock(name=kind)
            run.kind, run.args, run.kwargs = kind, args, kwargs
            return run, lambda n: None

        self.skills.SimpleGoTo.side_effect = lambda *a, **k: skill("move", *a, **k)
        self.skills.Stop.side_effect = lambda: skill("stop")
        self.skills.StaticGetBall.side_effect = lambda *a: skill("shot", *a)
        modules = {
            "CppPackage": self.cpp, "Global": NS(isPlaySwitched=False),
            "Geometry": NS(CGeoPoint=Point),
            "RoleMatch_LuaStyle": NS(StateMachine=object,
                                     Task=lambda skill, fixedNumber: NS(skill=skill, num=fixedNumber),
                                     declare_state_machine=lambda *a: lambda cls: cls),
            "RoleMatch_LuaStyle.Skills": NS(Skill=self.skills),
            "Vision": NS(Ball=self.ball, Player=self.player),
            "WorldModel": NS(Params=self.params, kickStatus=self.kicks),
            "WorldModel.PowerCalculator": NS(evalPower=self.power, P=NS(NORMAL=1, HIGH=2)),
            "Play.Test.Test_CornerPassShot": base_module,
        }
        path = Path(__file__).resolve().parents[1] / "Play/Test/Test_GiveAndGo.py"
        spec = importlib.util.spec_from_file_location("give_and_go_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", modules):
            spec.loader.exec_module(self.module)
        self.state = self.module.GiveAndGo()

    frame = corner_tests.CornerPassTests.frame

    @staticmethod
    def execute(tasks):
        for task in tasks.values():
            task.skill[0](task.num)

    def assert_stopped(self, tasks):
        self.assertEqual([t.skill[0].kind for t in tasks.values()], ["stop", "stop"])

    def prepare_first_pass(self):
        self.frame(100)
        corner = Point(self.params.pitchLength / 2 - 600, -self.params.pitchWidth / 2 + 600)
        angle = self.module.direction(Point(0, 0), corner)
        near, far = self.state.near, self.state.far
        self.positions[near] = Point(-98 * math.cos(angle), -98 * math.sin(angle))
        self.angles[near] = angle
        self.infrared[near] = True
        self.positions[far] = corner
        self.angles[far] = self.module.direction(corner, Point(0, 0))
        self.frame(101)
        self.frame(101.3)
        self.assertEqual(self.state.phase, "PASS_OUT")

    def advance_pass(self, now):
        origin, target = self.state.pass_origin, self.state.pass_target
        angle = self.module.direction(origin, target)
        self.ball.pos = lambda: Point(origin.x() + 200 * math.cos(angle),
                                      origin.y() + 200 * math.sin(angle))
        self.ball.velX = lambda: 1500 * math.cos(angle)
        self.ball.velY = lambda: 1500 * math.sin(angle)
        return self.frame(now)

    def test_assigns_closest_once_even_when_distances_swap(self):
        self.positions[2] = Point(-100, 0)
        tasks = self.frame()
        self.assertEqual((tasks["A"].num, tasks["B"].num), (2, 1))
        self.positions[1], self.positions[2] = Point(-50, 0), Point(-1000, 0)
        self.frame(101)
        self.assertEqual((self.state.near, self.state.far), (2, 1))

    def test_center_ball_starts_approach_without_corner_ball_requirement(self):
        self.execute(self.frame())
        self.assertTrue(self.state.assigned)
        self.assertEqual(self.state.phase, "SETUP")
        self.skills.StaticGetBall.assert_not_called()
        self.kicks.setKick.assert_not_called()

    def test_holder_waits_in_place_until_receiver_ready(self):
        self.infrared[1] = True
        self.positions[1] = Point(-98, 0)
        self.execute(self.frame())
        self.assertAlmostEqual(self.state.holds[1].x(), -98)
        self.positions[1] = Point(-100, 0)
        tasks = self.frame(102)
        self.execute(tasks)
        self.assertEqual(self.state.phase, "SETUP")
        self.assertEqual(self.state.holds[1].x(), -98)
        self.kicks.setKick.assert_not_called()

    def test_no_infrared_does_not_falsely_claim_possession(self):
        self.positions[1] = Point(-98, 0)
        self.execute(self.frame())
        self.assertNotIn(1, self.state.holds)
        self.kicks.setKick.assert_not_called()

    def test_does_not_kick_if_receiver_moves_away_after_ready(self):
        self.prepare_first_pass()
        self.positions[self.state.far] = Point(-1000, 1000)
        self.execute(self.frame(102))
        self.kicks.setKick.assert_not_called()
        self.assertFalse(self.state.pass_sent)

    def test_external_ball_motion_before_kick_does_not_advance(self):
        self.prepare_first_pass()
        self.advance_pass(102)
        self.assertEqual(self.state.phase, "PASS_OUT")

    def test_complete_two_pass_sequence_and_immediate_shot_activation(self):
        for swapped in (False, True):
            with self.subTest(swapped=swapped):
                self.setUp()
                if swapped:
                    self.positions[2] = Point(-100, 0)
                self.prepare_first_pass()
                self.execute(self.frame(102))
                self.kicks.setKick.assert_called_once()
                self.assertTrue(self.state.pass_sent)
                tasks = self.advance_pass(102.2)
                self.assertEqual(self.state.phase, "RETURN_SETUP")
                self.skills.StaticGetBall.assert_not_called()
                near, far = self.state.near, self.state.far
                self.assertEqual(tasks["A"].num, near)
                self.assertEqual(tasks["B"].num, far)
                shot = Point(3150, 0)
                self.positions[near], self.angles[near] = shot, 0
                self.infrared[near], self.infrared[far] = False, True
                self.angles[far] = self.module.direction(self.positions[far], self.module.mouth(shot, 0))
                held_ball = self.module.mouth(self.positions[far], self.angles[far])
                self.ball.pos = lambda: held_ball
                self.ball.velX, self.ball.velY = lambda: 0, lambda: 0
                self.frame(104)
                self.frame(104.3)
                self.assertEqual(self.state.phase, "RETURN_PASS")
                self.execute(self.frame(104.4))
                self.assertEqual(self.kicks.setKick.call_count, 2)
                tasks = self.advance_pass(104.6)
                self.assertEqual(self.state.phase, "FINISH")
                self.assertEqual(tasks["A"].skill[0].kind, "shot")
                self.assertEqual(tasks["A"].num, near)
                self.assertEqual(tasks["B"].skill[0].kind, "stop")
                self.assertFalse(self.infrared[near])

    def test_missing_vision_waits_before_assignment_but_stops_active_trial(self):
        self.ball.valid = lambda: False
        self.assert_stopped(self.frame())
        self.assertFalse(self.state.assigned)
        self.ball.valid = lambda: True
        self.frame()
        self.ball.valid = lambda: False
        self.assert_stopped(self.frame(101))
        self.assertEqual(self.state.phase, "DONE")

    def test_timeout_latches_stop_and_reset_clears_roles(self):
        self.frame()
        self.assert_stopped(self.frame(136))
        self.assert_stopped(self.frame(137))
        self.state.reset()
        self.assertFalse(self.state.assigned)
        self.assertEqual(self.state.phase, "SETUP")

    def test_invalid_power_stops_both_without_kick(self):
        self.prepare_first_pass()
        self.power.return_value = float("nan")
        self.assert_stopped(self.frame(102))
        self.kicks.setKick.assert_not_called()

    def test_large_field_targets_derive_from_params(self):
        self.params.pitchLength, self.params.pitchWidth = 12000, 8550
        self.params.penaltyDepth, self.params.penaltyWidth = 1800, 3600
        self.frame()
        self.assertAlmostEqual(self.state.corner_angle, math.atan2(3675, -5400))
        self.prepare_first_pass()

    def test_penalty_area_and_outside_ball_abort(self):
        self.positions[2] = Point(3490, 0)
        self.assert_stopped(self.frame())
        self.state.reset()
        self.positions[2] = Point(-1200, 500)
        self.ball.pos = lambda: Point(5000, 0)
        self.assert_stopped(self.frame())


if __name__ == "__main__":
    unittest.main()
