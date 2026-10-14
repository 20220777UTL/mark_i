import math
import runpy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from Play.Normal.AttackGeometry import (
    ball_at, intercept, clearance, choose_shot, ellipse_keeper,
    choose_static_shot, choose_corner_shot, redirect_heading, touch_intercept,
)


class Point:
    def __init__(self, x, y): self.a, self.b = x, y
    def x(self): return self.a
    def y(self): return self.b
    def dist(self, p): return math.hypot(self.a-p.a, self.b-p.b)


class GeometryTests(unittest.TestCase):
    def test_ball_prediction_stops_without_reversing(self):
        self.assertEqual(ball_at((0, 0), (800, 0), 1), (400, 0))
        self.assertEqual(ball_at((0, 0), (800, 0), 10), (400, 0))

    def test_intercept_leads_moving_ball_and_stays_legal(self):
        legal = lambda p: abs(p[0]) <= 3300 and abs(p[1]) <= 2800
        p = intercept((1000, 0), (0, 1000), (0, 0), (0, 0), legal)
        self.assertGreater(p[1], 0)
        self.assertTrue(legal(p))
        p = intercept((3400, 0), (2000, 0), (3000, 0), (0, 0), legal)
        self.assertTrue(legal(p))

    def test_keeper_movement_changes_shot_side(self):
        up = choose_shot((3000, 0), 0, 4500, 1000, (4200, 0), (0, 1000))
        down = choose_shot((3000, 0), 0, 4500, 1000, (4200, 0), (0, -1000))
        self.assertLess(up[1], 0)
        self.assertGreater(down[1], 0)
        self.assertLess(abs(up[1]), 500)

    def test_keeper_crossing_ball_path_is_blocked(self):
        # At t=.2 both ball and keeper reach (4000, 0).
        self.assertLess(clearance((3000, 0), (4500, 0), (4000, 200), (0, -1000), 0, 5000), 0)
        self.assertGreater(clearance((3000, 0), (4500, 0), (4000, 200), (0, 1000), 0, 5000), 0)

    def test_redirect_cancels_incoming_lateral_velocity(self):
        h = redirect_heading((0, 0), (4500, 0), (0, -1200), 1800, .25)
        self.assertGreater(h, 0)
        self.assertAlmostEqual(1800 * math.sin(h) - .25 * 1200, 0)

    def test_touch_intercept_never_returns_penalty_area_point(self):
        legal = lambda p: abs(p[0]) <= 3340 and abs(p[1]) <= 2840
        plan = touch_intercept((3480, 0), (1500, 0), (3200, 0), (0, 0), 0,
                               (4500, 0), legal, 82, 1800, .25)
        self.assertIsNone(plan)

    def test_static_goalie_model_intersects_goal_centered_ellipse(self):
        self.assertEqual(ellipse_keeper((3000, 0), 4500), (4200, 0))
        self.assertEqual(ellipse_keeper((4500, 1000), 4500), (4500, 500))

    def test_static_shot_targets_the_wider_side_of_the_goalie(self):
        left_open = choose_static_shot((3000, 0), 4500, 1000, (4200, 200))
        right_open = choose_static_shot((3000, 0), 4500, 1000, (4200, -200))
        self.assertLess(left_open[1], 0)
        self.assertGreater(right_open[1], 0)

    def test_live_keeper_selects_opposite_goal_corner_with_post_margin(self):
        self.assertEqual(choose_corner_shot((3000, 0), 4500, 1000, (4200, 200)), (4500, -410))
        self.assertEqual(choose_corner_shot((3000, 0), 4500, 1000, (4200, -200)), (4500, 410))

    def test_corner_selection_uses_ball_view_angle_for_off_centre_shots(self):
        # 门将位于球门中央时，偏侧的球位仍有大小不同的两个开放夹角。
        self.assertEqual(choose_corner_shot((3000, -800), 4500, 1000, (4200, 0)), (4500, -410))
        self.assertEqual(choose_corner_shot((3000, 800), 4500, 1000, (4200, 0)), (4500, 410))

    def test_corner_target_fallback_and_equal_angles_keep_previous_corner(self):
        previous = (4500, 410)
        for keeper in (None, (3000, 0), (4200, 0)):
            with self.subTest(keeper=keeper):
                self.assertEqual(choose_corner_shot((3000, 0), 4500, 1000, keeper, previous), previous)
        self.assertEqual(choose_corner_shot((3000, -800), 4500, 1000), (4500, -410))


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.pos = {0: Point(0, 0), 1: Point(3200, 800)}
        self.heading = {0: 0, 1: 0}
        self.ball = Point(82, 0)
        self.speed = 0
        self.velocity = Point(0, 0)
        self.keeper_pos = None
        self.omega = 0
        self.cpp = Mock()
        self.cpp.InTheirPenaltyArea.return_value = False
        self.cpp.InOurPenaltyArea.return_value = False
        self.v5_execute = Mock()
        self.get_ball_v5 = Mock(return_value=(self.v5_execute, lambda n: self.ball))
        self.kick = Mock()
        self.player = NS(Pos=lambda n: self.pos[n], direction=lambda n: self.heading[n],
            vel=lambda n: Point(0, 0), velMod=lambda n: 0, rotVel=lambda n: self.omega,
            toBallDir=lambda n: math.atan2(self.ball.b-self.pos[n].b, self.ball.a-self.pos[n].a))
        def declare(*states):
            def wrap(cls):
                cls.declared = states
                return cls
            return wrap
        modules = {
            'CppPackage': self.cpp,
            'RoleMatch_LuaStyle': NS(Task=lambda skill, fixedNumber: NS(skill=skill, skill_cpp=skill[0], number=fixedNumber),
                State=object, StateMachine=object, declare_state_machine=declare),
            'RoleMatch_LuaStyle.Skills': NS(Skill=NS(GetBallV5=self.get_ball_v5)),
            'Geometry': NS(CGeoPoint=Point),
            'Vision': NS(Ball=NS(pos=lambda: self.ball, vel=lambda: self.velocity,
                velMod=lambda: self.speed, posX=lambda: self.ball.a, posY=lambda: self.ball.b),
                Player=self.player, Enemy=NS(valid=lambda n: self.keeper_pos is not None,
                    pos=lambda n: self.keeper_pos, vel=lambda n: Point(0, 0))),
            'WorldModel': NS(Flags=NS(allow_dss=1, dribbling=256), kickStatus=self.kick,
                Params=NS(pitchLength=9000, pitchWidth=6000, penaltyDepth=1000,
                          playerRadius=90, goalWidth=1000, playerFrontToCenter=76)),
            'WorldModel.PowerCalculator': NS(evalPower=Mock(return_value=7000), P=NS(NORMAL=1,HIGH=2)),
        }
        with patch.dict(sys.modules, modules):
            self.m = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'Play/Normal/two_attack.py'))
        self.control = self.m['Control']()
        for _ in range(3): self.control.update()

    def state(self, name):
        s = self.m[name]()
        s.control = self.control
        return s

    def test_state_order_and_fixed_numbers(self):
        self.assertEqual([s.__name__ for s in self.m['two_attack'].declared],
            ['GetFirstBall','PassToAssistant','ReceiveAndReturn','PassBack',
             'InterceptAndShoot','Done'])
        for cls in self.m['two_attack'].declared:
            tasks = self.state(cls.__name__).getTasks()
            self.assertEqual([tasks['A'].number, tasks['B'].number], [0, 1])

    def test_first_pass_waits_for_ball_and_receiver(self):
        s = self.state('GetFirstBall')
        self.assertEqual(s.transFunction(), 'PassToAssistant')
        self.pos[1] = Point(1000, 0)
        self.assertEqual(s.transFunction(), '')
        self.pos[1] = Point(3200, 800)
        self.ball = Point(-96, 0)
        self.control.update()
        self.assertEqual(s.transFunction(), '')

    def test_receive_before_turning_and_reacquire_if_lost(self):
        s = self.state('PassToAssistant')
        self.ball = Point(0, 1000)
        self.control.update()
        s.getTasks()['A'].skill[0](0)
        self.cpp.makeItRushTo.assert_called_once()
        self.cpp.makeItSimpleGoTo.assert_not_called()
        self.kick.setKick.assert_not_called()
        self.assertAlmostEqual(self.cpp.makeItRushTo.call_args.args[2], math.pi/2)

    def test_pass_release_requires_kick_then_ball_departure(self):
        s = self.state('PassToAssistant')
        self.ball = Point(1500, 0)
        self.assertEqual(s.transFunction(), '')
        s.fired = (82, 0)
        self.assertEqual(s.transFunction(), 'ReceiveAndReturn')
        self.ball = Point(150, 0)
        self.assertEqual(s.transFunction(), '')

    def test_return_pass_and_final_shot_transitions(self):
        self.pos[0] = Point(3200, -800)
        self.ball = Point(3282, 800)
        for _ in range(3): self.control.update()
        self.heading[0] = self.m['prepare_return'](self.control)[1]
        self.assertEqual(self.state('ReceiveAndReturn').transFunction(), 'PassBack')
        back = self.state('PassBack')
        back.fired = (3282, 800)
        self.ball = Point(3282, -400)
        self.control.update()
        self.assertEqual(back.transFunction(), 'InterceptAndShoot')
        shot = self.state('InterceptAndShoot')
        shot.fired = (3282, -800)
        self.ball = Point(4000, -200)
        self.velocity = Point(1500, 0)
        self.assertEqual(shot.transFunction(), 'Done')

    def test_kick_while_rotating_if_predicted_heading_is_aligned(self):
        s = self.state('PassToAssistant')
        self.omega = 2
        angle = self.omega * .03
        target = Point(4500, math.tan(angle)*(4500-82))
        self.m['kick_to'](0, target, s, shooting=True).skill[0](0)
        self.kick.setKick.assert_called_once_with(0, 7000)
        self.assertEqual(s.fired, (82, 0))

    def test_no_kick_with_wrong_heading_or_outside_posts(self):
        s = self.state('PassToAssistant')
        self.m['kick_to'](0, Point(4500, 400), s, shooting=True).skill[0](0)
        self.kick.setKick.assert_not_called()
        self.omega = math.atan2(600, 4500-96)/.03
        self.m['kick_to'](0, Point(4500, 600), s, shooting=True).skill[0](0)
        self.kick.setKick.assert_not_called()

    def test_illegal_target_is_clamped_and_illegal_robot_stops(self):
        self.m['move_to'](0, Point(4400, 0), self.control).skill[0](0)
        self.assertLessEqual(self.cpp.makeItRushTo.call_args.args[1].x(), 3340)
        self.pos[0] = Point(3500, 0)
        self.m['receive'](0, self.control).skill[0](0)
        self.cpp.makeItStop.assert_called_once_with(0)

    def test_carry_limit_but_overspeed_does_not_reduce_power_in_test_mode(self):
        self.control.carry[0] = 851
        self.assertFalse(self.control.allowed(0))
        self.control.last_power = 6000
        self.speed = 7000
        self.control.update()
        self.assertEqual(self.control.cap, self.m['POWER_CAP'])
        self.ball = Point(2000, 0)
        self.control.update()
        self.assertEqual(self.control.carry[0], 0)

    def test_touch_shot_faces_goal_before_ball_arrives(self):
        self.ball = Point(82, 600)
        self.velocity = Point(0, -1200)
        self.speed = 1200
        self.control.held[0] = False
        s = self.state('InterceptAndShoot')
        s.getTasks()['A'].skill[0](0)
        self.assertIsNotNone(self.control.shot_target)
        self.get_ball_v5.assert_called_once()
        self.assertTrue(self.get_ball_v5.call_args.kwargs['ifIntercept'])
        self.v5_execute.assert_called_once_with(0)
        self.cpp.setDribbleCommand.assert_called_once_with(0, 3)
        angle = self.get_ball_v5.call_args.args[0]
        self.assertLess(abs(angle), 1.3)
        self.kick.setKick.assert_not_called()

    def test_touch_shot_fires_without_held_or_clear_keeper_lane(self):
        self.control.held[0] = False
        self.control.shot_target = (4500, 0)
        self.control.shot_locked = True
        s = self.state('InterceptAndShoot')
        with patch.dict(self.m['touch_shot'].__globals__, {'lane_clear': lambda target: False}):
            s.getTasks()['A'].skill[0](0)
        self.kick.setKick.assert_called_once_with(0, 7000)
        self.assertEqual(s.fired, (82, 0))

    def test_touch_shot_does_not_fire_at_off_axis_ball(self):
        self.ball = Point(82, 35)
        s = self.state('InterceptAndShoot')
        s.getTasks()['A'].skill[0](0)
        self.kick.setKick.assert_not_called()

    def test_touch_shot_rechecks_keeper_at_execution_and_only_locks_after_kick(self):
        self.control.held[0] = False
        self.keeper_pos = Point(4200, 200)
        self.heading[0] = math.atan2(-410, 4500 - 82)
        s = self.state('InterceptAndShoot')
        task = s.getTasks()['A']
        self.assertEqual(self.control.shot_target, (4500, -410))
        self.assertFalse(self.control.shot_locked)

        # 即使取任务后门将才换边，准备出脚时也必须重新选角、转向，不能朝旧角踢球。
        self.keeper_pos = Point(4200, -200)
        task.skill[0](0)
        self.assertEqual(self.control.shot_target, (4500, 410))
        self.assertFalse(self.control.shot_locked)
        self.kick.setKick.assert_not_called()
        self.get_ball_v5.assert_called_once()
        desired = math.atan2(410, 4500 - 82)
        self.assertAlmostEqual(self.get_ball_v5.call_args.args[0], desired)

        self.heading[0] = desired
        s.getTasks()['A'].skill[0](0)
        self.kick.setKick.assert_called_once_with(0, 7000)
        self.assertTrue(self.control.shot_locked)
        self.assertEqual(s.fired, (82, 0))

    def test_locked_target_does_not_change(self):
        self.control.shot_target = (4500, 410)
        self.control.shot_locked = True
        self.keeper_pos = Point(4200, 200)
        self.m['select_touch_target'](self.control, (3200, -800))
        self.assertEqual(self.control.shot_target, (4500, 410))

    def test_return_contact_is_independent_of_current_heading(self):
        self.m['prepare_return'](self.control)
        contact = self.control.return_contact
        self.heading[0] = math.pi
        self.m['prepare_return'](self.control)
        self.assertEqual(self.control.return_contact, contact)
        self.assertNotEqual(contact, self.m['mouth'](0))

    def test_done_stops_both_robots(self):
        for task in self.state('Done').getTasks().values():
            task.skill[0](task.number)
        self.assertEqual(self.cpp.makeItStop.call_count, 2)
        self.kick.setKick.assert_not_called()

    def test_capture_requires_close_ball_for_three_consecutive_frames(self):
        self.control = self.m['Control']()
        self.ball = Point(97, 0)
        for _ in range(5): self.control.update()
        self.assertFalse(self.control.held[0])
        self.ball = Point(82, 0)
        for _ in range(2): self.control.update()
        self.assertFalse(self.control.held[0])
        self.ball = Point(97, 0)
        self.control.update()
        self.ball = Point(82, 0)
        for _ in range(2): self.control.update()
        self.assertFalse(self.control.held[0])
        self.control.update()
        self.assertTrue(self.control.held[0])

    def test_turning_lag_keeps_possession_but_cannot_kick(self):
        self.ball = Point(100, -45)
        self.control.update()
        self.assertTrue(self.control.held[0])
        s = self.state('PassToAssistant')
        self.m['kick_to'](0, Point(4500, -45), s).skill[0](0)
        self.cpp.makeItSimpleGoTo.assert_called_once()
        self.cpp.makeItRushTo.assert_not_called()
        self.kick.setKick.assert_not_called()
        self.ball = Point(180, 0)
        self.control.update()
        self.assertFalse(self.control.held[0])
        self.m['kick_to'](0, Point(4500, 0), s).skill[0](0)
        self.cpp.makeItRushTo.assert_called_once()


    def test_near_ball_presses_inside_mouth_offset(self):
        self.ball = Point(120, 0)
        self.control.update()
        self.control.held[0] = False
        self.m['receive'](0, self.control).skill_cpp(0)
        cmd = self.cpp.makeItRushTo.call_args
        self.assertAlmostEqual(cmd.args[1].x(), 68)
        self.assertEqual(cmd.kwargs['maxAcc'], 0)

    def test_near_ball_wrong_heading_rotates_without_pressing(self):
        self.ball = Point(0, 120)
        self.control.update()
        self.m['receive'](0, self.control).skill_cpp(0)
        cmd = self.cpp.makeItRushTo.call_args
        self.assertEqual((cmd.args[1].x(), cmd.args[1].y()), (0, 0))
        self.assertAlmostEqual(cmd.args[2], math.pi / 2)

    def test_three_degree_pass_window_and_no_wait_for_rotation_stop(self):
        s = self.state('PassToAssistant')
        for degrees, expected in ((2.9, True), (3.1, False)):
            self.kick.reset_mock()
            target = Point(3000, math.tan(math.radians(degrees)) * (3000-82))
            self.m['kick_to'](0, target, s).skill_cpp(0)
            self.assertEqual(self.kick.setKick.called, expected)

    def test_chasing_nearby_ball_does_not_consume_carry_budget(self):
        self.control = self.m['Control']()
        for x in range(0, 1000, 50):
            self.pos[0] = Point(x, 0)
            self.ball = Point(x+150, 0)
            self.control.update()
        self.assertFalse(self.control.held[0])
        self.assertEqual(self.control.carry[0], 0)

    def test_prediction_returns_heading_consistent_with_contact(self):
        centre, facing = intercept((1000, 0), (0, 1000), (0, 0), (0, 0),
                                   lambda p: True, with_heading=True)
        self.assertAlmostEqual(facing, -math.pi / 2)
        self.assertGreater(centre[1], 0)

    def test_fetch_role_is_only_registered_for_receiver(self):
        self.ball = Point(120, 0)
        self.control.held[0] = False
        self.m['receive'](0, self.control).skill_cpp(0)
        self.cpp.TaskMediator.Instance().registerRole.assert_called_once_with(0, 'fetchBall')
        self.cpp.reset_mock()
        self.m['move_to'](1, Point(3200, 800), self.control).skill_cpp(1)
        self.cpp.TaskMediator.Instance().registerRole.assert_not_called()

    def test_fast_near_ball_keeps_intercept_heading(self):
        self.ball = Point(130, 0)
        self.velocity = Point(-1000, 0)
        self.speed = 1000
        self.control.held[0] = False
        self.m['receive'](0, self.control).skill_cpp(0)
        self.assertFalse(self.control.receive_near[0])
        self.assertAlmostEqual(self.cpp.makeItRushTo.call_args.args[2], 0)

    def test_held_ball_has_no_more_receive_pressure(self):
        self.m['receive'](0, self.control).skill_cpp(0)
        target = self.cpp.makeItRushTo.call_args.args[1]
        self.assertEqual((target.x(), target.y()), (0, 0))

if __name__ == '__main__': unittest.main()

