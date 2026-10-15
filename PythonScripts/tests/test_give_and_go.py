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
        self.skills.SmartGoTo = Mock(side_effect=lambda *a, **k: skill("planned_move", *a, **k))
        flags_spec = importlib.util.spec_from_file_location("real_flags_test", Path(__file__).resolve().parents[1] / "WorldModel/Flags.py")
        self.flags = importlib.util.module_from_spec(flags_spec)
        flags_spec.loader.exec_module(self.flags)
        modules = {
            "CppPackage": self.cpp, "Global": NS(isPlaySwitched=False),
            "Geometry": NS(CGeoPoint=Point),
            "RoleMatch_LuaStyle": NS(StateMachine=object,
                                     Task=lambda skill, fixedNumber: NS(skill=skill, num=fixedNumber),
                                     declare_state_machine=lambda *a: lambda cls: cls),
            "RoleMatch_LuaStyle.Skills": NS(Skill=self.skills),
            "Vision": NS(Ball=self.ball, Player=self.player),
            "WorldModel": NS(Params=self.params, kickStatus=self.kicks, Flags=self.flags),
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
                self.positions[self.state.near] = Point(-98 * math.cos(angle), -98 * math.sin(angle))
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
                with patch.object(self.module.time, "monotonic", return_value=104.4):
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
        self.positions[self.state.near] = Point(-98 * math.cos(angle), -98 * math.sin(angle))
        with patch.object(self.module.time, "monotonic", return_value=102):
            self.execute(self.frame(102))
        self.ball.pos = lambda: Point(40 * math.cos(angle), 40 * math.sin(angle))
        tasks = self.frame(102.05)
        self.assertEqual(tasks["A"].skill[0].kind, "stop")
        self.execute(tasks)
        self.kicks.setKick.assert_called_once()

    def test_travel_requests_native_avoidance_and_conservative_acceleration(self):
        self.positions[1], self.positions[2] = Point(-500, 0), Point(-1000, 1000)
        self.state.travel(1, Point(500, 0), 0)
        call = self.skills.SmartGoTo.call_args
        self.assertEqual(call.kwargs["maxAcc"], 2000)
        self.assertEqual(call.kwargs["flag"], self.flags.dodge_ball | self.flags.allow_dss | self.flags.slowly)
        self.skills.SimpleGoTo.assert_not_called()

    def test_six_degree_heading_keeps_setup_correcting_instead_of_deadlocking(self):
        self.frame(100)
        corner = Point(3900, -2400)
        angle = self.module.direction(Point(0, 0), corner)
        self.positions[1] = Point(-260 * math.cos(angle), -260 * math.sin(angle))
        self.positions[2], self.angles[2] = corner, angle + math.pi
        self.angles[1] = angle + math.radians(6)
        self.frame(101)
        self.frame(101.3)
        self.assertEqual(self.state.phase, "SETUP")

    def test_valid_frame_after_long_vision_gap_still_aborts(self):
        self.frame(100)
        self.ball.valid = lambda: False
        self.frame(101)
        self.ball.valid = lambda: True
        self.assert_stopped(self.frame(102))
        self.assertEqual(self.state.phase, "DONE")

    def test_opening_rebound_cannot_rearm_kick(self):
        self.prepare_first_pass()
        angle = self.module.direction(self.state.pass_origin, self.state.pass_target)
        self.positions[self.state.near] = Point(-98 * math.cos(angle), -98 * math.sin(angle))
        with patch.object(self.module.time, "monotonic", return_value=102):
            self.execute(self.frame(102))
        self.ball.pos = lambda: Point(40 * math.cos(angle), 40 * math.sin(angle))
        self.execute(self.frame(102.02))
        self.ball.pos = lambda: Point(0, 0)
        with patch.object(self.module.time, "monotonic", return_value=102.04):
            self.execute(self.frame(102.04))
        self.kicks.setKick.assert_called_once()

    def test_finish_checks_actual_mouth_before_nominal_line(self):
        self.prepare_finish(Point(3220, 0), (-1000, 0))
        self.positions[self.state.near] = Point(3080, 0)  # 合法等待误差内，实际球口仍在来球前方。
        with patch.object(self.module.time, "monotonic", return_value=101):
            self.execute(self.frame(101))
        self.kicks.setKick.assert_called_once_with(self.state.near, 4000)

    def test_return_pass_keeps_request_briefly_until_ball_moves(self):
        self.frame(100)
        self.positions[1], self.positions[2] = Point(3150, 0), Point(3900, -2400)
        target = self.module.mouth(self.positions[1], 0)
        self.angles[2] = self.module.direction(self.positions[2], target)
        origin = self.module.mouth(self.positions[2], self.angles[2])
        self.ball.pos, self.infrared[2] = lambda: origin, True
        with patch.object(self.module.time, "monotonic", return_value=101):
            self.state.begin_pass("RETURN_PASS", target)
            self.execute(self.frame(101))
        with patch.object(self.module.time, "monotonic", return_value=101.05):
            self.execute(self.frame(101.05))
        self.assertEqual(self.kicks.setKick.call_count, 2)
        self.ball.pos = lambda: Point(origin.x() - 40, origin.y())
        self.execute(self.frame(101.06))
        self.ball.pos = lambda: origin
        with patch.object(self.module.time, "monotonic", return_value=101.08):
            self.execute(self.frame(101.08))
        self.assertEqual(self.kicks.setKick.call_count, 2)

    def test_close_ball_route_does_not_use_unsafe_single_waypoint(self):
        # 旧路径 (200,0)->(0,-260) 距球最近仅158.52mm，小于自身声明的160mm。
        self.positions[1], self.positions[2] = Point(200, 0), Point(-1000, 1000)
        self.state.travel(1, Point(-260, 0), 0)
        self.skills.SimpleGoTo.assert_not_called()
        self.skills.SmartGoTo.assert_called_once()
        self.assertTrue(self.skills.SmartGoTo.call_args.kwargs["flag"] & self.flags.dodge_ball)

    def test_opening_corrects_heading_outside_ball_contact(self):
        self.prepare_first_pass()
        expected_angle = self.angles[self.state.near]
        self.angles[self.state.near] += math.radians(6)
        self.skills.SimpleGoTo.reset_mock()
        self.execute(self.frame(102))
        move = self.skills.SimpleGoTo.call_args_list[0]
        self.assertAlmostEqual(move.args[0].x(), self.positions[self.state.near].x())
        self.assertAlmostEqual(move.kwargs["angle"], expected_angle)
        self.kicks.setKick.assert_not_called()

    def test_opening_expiry_is_latched_and_reset_clears_it(self):
        self.prepare_first_pass()
        self.state.pass_sent = True
        self.state.opening_kick_at = 101
        self.execute(self.frame(101.2))
        self.assertTrue(self.state.opening_closed)
        self.kicks.setKick.assert_not_called()
        self.state.reset()
        self.assertFalse(self.state.opening_closed)
        self.assertIsNone(self.state.opening_kick_at)

    def test_native_replay_gap_does_not_expire_kick_before_contact(self):
        self.prepare_first_pass()
        # 本轮回放：球仍在(0,0)，车先后距球约149mm、133mm，尚未到球口。
        # 时间取一个超过旧0.18s窗口的慢接近情形，不冒充回放中的原始时间戳。
        samples = [(102, -129.95135498046875, 72.50067901611328, -0.5727083683013916),
                   (102.3, -115.26274108886717, 65.86621856689453, -0.48427820205688477)]
        for now, x, y, heading in samples:
            self.positions[1], self.angles[1] = Point(x, y), heading
            with patch.object(self.module.time, "monotonic", return_value=now):
                tasks = self.frame(now)
                self.execute(tasks)
            self.assertNotEqual(getattr(tasks["A"].skill[0], "kind", None), "stop")
            destination = self.skills.SimpleGoTo.call_args_list[-2].args[0]
            self.assertAlmostEqual(math.hypot(destination.x(), destination.y()), 96)
            self.assertFalse(self.state.opening_closed)
            self.assertIsNone(self.state.opening_kick_at)
            self.kicks.setKick.assert_not_called()
        angle = self.module.direction(self.state.pass_origin, self.state.pass_target)
        self.positions[1] = Point(-98 * math.cos(angle), -98 * math.sin(angle))
        self.angles[1] = angle
        with patch.object(self.module.time, "monotonic", return_value=102.6):
            self.execute(self.frame(102.6))
        self.assertEqual(self.state.opening_kick_at, 102.6)
        self.kicks.setKick.assert_called_once()
        self.assertTrue(all(call.args[1] == 0 for call in self.cpp.setDribbleCommand.call_args_list
                            if call.args[0] == 1))

    def test_opening_waits_for_front_contact_without_infrared(self):
        self.prepare_first_pass()
        angle = self.module.direction(self.state.pass_origin, self.state.pass_target)
        self.positions[1] = Point(-120 * math.cos(angle), -120 * math.sin(angle))
        self.infrared[1] = False
        with patch.object(self.module.time, "monotonic", return_value=102):
            self.execute(self.frame(102))
        self.kicks.setKick.assert_not_called()
        self.positions[1] = Point(-98 * math.cos(angle), -98 * math.sin(angle))
        with patch.object(self.module.time, "monotonic", return_value=102.4):
            self.execute(self.frame(102.4))
        self.kicks.setKick.assert_called_once()
        self.assertEqual(self.state.opening_kick_at, 102.4)

    def test_opening_does_not_trigger_for_ball_beside_or_behind_robot(self):
        self.prepare_first_pass()
        angle = self.module.direction(self.state.pass_origin, self.state.pass_target)
        for forward, side in ((98, 18), (-98, 0)):
            self.positions[1] = Point(-forward * math.cos(angle) + side * math.sin(angle),
                                      -forward * math.sin(angle) - side * math.cos(angle))
            with patch.object(self.module.time, "monotonic", return_value=102):
                self.execute(self.frame(102))
            self.kicks.setKick.assert_not_called()
            self.assertIsNone(self.state.opening_kick_at)

    def test_return_pass_expiry_never_retries_even_with_valid_possession(self):
        self.frame(100)
        self.positions[1], self.positions[2] = Point(3150, 0), Point(3900, -2400)
        target = self.module.mouth(self.positions[1], 0)
        self.angles[2] = self.module.direction(self.positions[2], target)
        ball = self.module.mouth(self.positions[2], self.angles[2])
        self.ball.pos, self.infrared[2] = lambda: ball, True
        with patch.object(self.module.time, "monotonic", return_value=101):
            self.state.begin_pass("RETURN_PASS", target)
            self.execute(self.frame(101))
        self.execute(self.frame(101.2))
        self.execute(self.frame(101.3))
        self.assertTrue(self.state.return_closed)
        self.kicks.setKick.assert_called_once()

    def test_return_pass_has_its_own_fresh_trigger_window(self):
        self.frame(100)
        self.state.return_closed = True  # 第一脚曾短暂丢失视觉，不能污染之后的第二脚。
        self.state.return_kick_at = 100
        with patch.object(self.module.time, "monotonic", return_value=101):
            self.state.begin_pass("RETURN_PASS", Point(3248, 0))
        self.assertFalse(self.state.return_closed)
        self.assertIsNone(self.state.return_kick_at)

    def test_vision_loss_during_opening_disarms_until_restart(self):
        self.prepare_first_pass()
        self.state.pass_sent, self.state.opening_kick_at = True, 101.31
        self.ball.valid = lambda: False
        self.assert_stopped(self.frame(101.32))
        self.ball.valid = lambda: True
        self.execute(self.frame(101.36))
        self.assertTrue(self.state.opening_closed)
        self.kicks.setKick.assert_not_called()

    def test_unsafe_destination_and_out_of_field_robot_stop(self):
        self.skills.SmartGoTo.reset_mock()
        for target in (Point(4490, 0), Point(3600, 0), Point(0, 2990)):
            self.assertEqual(self.state.travel(1, target, 0)[0].kind, "stop")
        self.skills.SmartGoTo.assert_not_called()
        self.positions[1] = Point(-4600, 0)
        self.assert_stopped(self.frame(100))
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
