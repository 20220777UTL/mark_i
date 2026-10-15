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
        self.positions[near] = Point(-260 * math.cos(angle), -260 * math.sin(angle))
        self.angles[near] = angle
        self.infrared[near] = False
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

    def test_opening_waits_without_dribbling_or_claiming_possession(self):
        self.infrared[1] = True
        self.positions[1] = Point(-98, 0)
        self.execute(self.frame())
        self.assertEqual(self.state.holds, {})
        self.assertEqual(self.state.phase, "SETUP")
        self.assertTrue(all(c.args[1] == 0 for c in self.cpp.setDribbleCommand.call_args_list))
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
                angle = self.module.direction(self.state.pass_origin, self.state.pass_target)
                self.positions[self.state.near] = Point(-110 * math.cos(angle), -110 * math.sin(angle))
                with patch.object(self.module.time, "monotonic", return_value=102):
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
                self.execute(tasks)
                self.skills.StaticGetBall.assert_not_called()
                self.assertEqual(self.kicks.setKick.call_count, 2)
                self.assertEqual(tasks["A"].num, near)
                self.assertEqual(tasks["B"].skill[0].kind, "stop")
                self.assertFalse(self.infrared[near])

    def prepare_finish(self, ball=Point(3300, -150), velocity=(-500, 1500)):
        self.frame(100)
        self.positions[self.state.near] = Point(3150, 0)
        self.angles[self.state.near] = 0
        self.state.phase, self.state.started = "FINISH", 100
        self.ball.pos = lambda: ball
        self.ball.velX, self.ball.velY = lambda: velocity[0], lambda: velocity[1]
        # FINISH 不允许回到红外确认/持球流程。
        self.player.isInfraredOn = Mock(side_effect=AssertionError("finish queried possession"))

    def test_finish_meets_ball_in_bounded_area_without_dribble_or_composite_skill(self):
        self.prepare_finish()
        self.skills.SimpleGoTo.reset_mock()
        self.cpp.setDribbleCommand.reset_mock()
        tasks = self.frame(101)
        self.execute(tasks)
        destination = self.skills.SimpleGoTo.call_args.args[0]
        self.assertLessEqual(self.module.distance(destination, Point(3150, 0)), self.module.MEET_RADIUS)
        self.assertLess(destination.y(), 0)  # 在球到达前向底角来球方向迎球。
        self.assertTrue(all(call.args[1] == 0 for call in self.cpp.setDribbleCommand.call_args_list))
        self.skills.StaticGetBall.assert_not_called()
        self.kicks.setKick.assert_not_called()

    def test_finish_kicks_in_mouth_window_without_possession(self):
        self.prepare_finish(Point(3270, 0), (-1000, 0))
        with patch.object(self.module.time, "monotonic", return_value=101):
            self.execute(self.frame(101))
        self.kicks.setKick.assert_called_once_with(self.state.near, 4000)
        self.assertEqual(self.state.shot_requested_at, 101)
        self.assertEqual(self.state.frozen_finish[0].x(), 3150)
        self.player.isInfraredOn.assert_not_called()
        self.assert_stopped(self.frame(101.2))
        self.assertEqual(self.state.phase, "DONE")
        self.assert_stopped(self.frame(102))

    def test_finish_rejects_stopped_wrong_way_and_missed_balls(self):
        cases = [(Point(3300, 0), (0, 0)),
                 (Point(3300, 0), (1000, 0)),
                 (Point(3200, 0), (-1000, 0)),
                 (Point(3400, 800), (-1000, 0))]
        for ball, velocity in cases:
            with self.subTest(ball=(ball.x(), ball.y()), velocity=velocity):
                self.setUp()
                self.prepare_finish(ball, velocity)
                self.assert_stopped(self.frame(101))
                self.assertEqual(self.state.phase, "DONE")
                self.kicks.setKick.assert_not_called()
                self.skills.StaticGetBall.assert_not_called()

    def test_finish_does_not_kick_sideways_or_when_heading_is_wrong(self):
        for ball, heading in [(Point(3270, 80), 0), (Point(3270, 0), .5)]:
            with self.subTest(heading=heading):
                self.setUp()
                self.prepare_finish(ball, (-1000, 0))
                self.angles[self.state.near] = heading
                self.execute(self.frame(101))
                self.kicks.setKick.assert_not_called()

    def test_finish_stops_after_outgoing_ball_and_reset_clears_kick_latch(self):
        self.prepare_finish(Point(3270, 0), (-1000, 0))
        with patch.object(self.module.time, "monotonic", return_value=101):
            self.execute(self.frame(101))
        self.ball.pos, self.ball.velX = lambda: Point(3500, 0), lambda: 2500
        self.assert_stopped(self.frame(101.1))
        self.state.reset()
        self.assertIsNone(self.state.shot_requested_at)
        self.assertIsNone(self.state.frozen_finish)

    def test_missing_vision_waits_before_assignment_but_stops_active_trial(self):
        self.ball.valid = lambda: False
        self.assert_stopped(self.frame())
        self.assertFalse(self.state.assigned)
        self.ball.valid = lambda: True
        self.frame()
        self.ball.valid = lambda: False
        self.assert_stopped(self.frame(101))
        self.assertNotEqual(self.state.phase, "DONE")
        self.assert_stopped(self.frame(101.6))
        self.assertEqual(self.state.phase, "DONE")

    def test_short_vision_loss_pauses_and_resumes_without_reading_invalid_ball(self):
        self.frame(100)
        self.ball.valid = lambda: False
        original_pos = self.ball.pos
        self.ball.pos = Mock(side_effect=AssertionError("invalid ball read"))
        self.assert_stopped(self.frame(101))
        self.ball.valid, self.ball.pos = lambda: True, original_pos
        self.frame(101.2)
        self.assertEqual(self.state.phase, "SETUP")
        self.assertAlmostEqual(self.state.started, 100.2)

    def test_possession_requires_geometry_and_bounds_infrared_dropout(self):
        self.positions[1] = Point(-98, 0)
        self.infrared[1] = True
        with patch.object(self.module.time, "monotonic", return_value=100):
            self.assertTrue(self.state.has_ball(1))
        self.infrared[1] = False
        with patch.object(self.module.time, "monotonic", return_value=100.05):
            self.assertTrue(self.state.has_ball(1))
        with patch.object(self.module.time, "monotonic", return_value=100.2):
            self.assertFalse(self.state.has_ball(1))
        self.infrared[1], self.angles[1] = True, math.pi
        self.assertFalse(self.state.has_ball(1))

    def test_opening_stops_after_ball_moves_without_second_kick(self):
        self.prepare_first_pass()
        angle = self.module.direction(self.state.pass_origin, self.state.pass_target)
        self.positions[self.state.near] = Point(-110 * math.cos(angle), -110 * math.sin(angle))
        with patch.object(self.module.time, "monotonic", return_value=102):
            self.execute(self.frame(102))
        self.ball.pos = lambda: Point(40 * math.cos(angle), 40 * math.sin(angle))
        tasks = self.frame(102.05)
        self.assertEqual(tasks["A"].skill[0].kind, "stop")
        self.execute(tasks)
        self.kicks.setKick.assert_called_once()

    def test_travel_inserts_waypoint_when_ball_blocks_route(self):
        self.positions[1], self.positions[2] = Point(-500, 0), Point(-1000, 1000)
        self.state.travel(1, Point(500, 0), 0)
        target = self.skills.SimpleGoTo.call_args.args[0]
        self.assertGreater(abs(target.y()), 160)

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
