import math
import runpy
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from Play.Normal.AttackGeometry import (
    ball_at, intercept, clearance, choose_shot, ellipse_keeper,
    choose_static_shot, choose_corner_shot, redirect_heading, redirect_possible,
    stopping_reach, touch_intercept, crossed_goal,
)


class Point:
    def __init__(self, x, y): self.a, self.b = x, y
    def x(self): return self.a
    def y(self): return self.b
    def dist(self, p): return math.hypot(self.a-p.a, self.b-p.b)


class FrameState:
    """保留真实框架的顺序：先执行任务，再判断状态切换。"""
    def __init__(self):
        self.state_name = type(self).__name__

    def run(self, switched):
        for task in self.getTasks().values():
            task.skill_cpp(task.number)
        return self.transFunction()


class GeometryTests(unittest.TestCase):
    def test_goal_requires_whole_ball_crossing_between_posts(self):
        self.assertFalse(crossed_goal((4490, 0), (4510, 0), 4500, 1000))
        self.assertTrue(crossed_goal((4490, 0), (4530, 0), 4500, 1000))
        self.assertFalse(crossed_goal((4490, 490), (4530, 490), 4500, 1000))
        self.assertFalse(crossed_goal((4530, 0), (4400, 0), 4500, 1000))
        self.assertFalse(crossed_goal(None, (4530, 0), 4500, 1000))

    def test_goal_uses_crossing_position_not_final_sample(self):
        self.assertTrue(crossed_goal((4400, 0), (4600, 600), 4500, 1000))
        self.assertFalse(crossed_goal((4400, 1300), (4600, 0), 4500, 1000))

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

    def test_stop_at_contact_requires_acceleration_and_braking_time(self):
        self.assertAlmostEqual(stopping_reach(1, 0), 450)
        self.assertIsNone(stopping_reach(.5, 1800))
        self.assertAlmostEqual(stopping_reach(1, 1800), 900)
        self.assertAlmostEqual(stopping_reach(1.5, -900), 225)

    def test_unreachable_touch_is_rejected_instead_of_returning_best_miss(self):
        self.assertIsNone(touch_intercept((2500, 0), (0, 0), (0, 0), (0, 0), 0,
                                         (4500, 0), lambda p: True, 82, 1800, 1))

    def test_safe_robot_centre_does_not_make_unsafe_ball_contact_legal(self):
        plan = touch_intercept((3400, 0), (0, 0), (3318, 0), (0, 0), 0,
                               (4500, 0), lambda p: p[0] < 3340, 82, 1800, 1,
                               contact_legal=lambda p: p[0] <= 3320)
        self.assertIsNone(plan)

    def test_lateral_robot_velocity_must_also_be_stoppable(self):
        self.assertIsNone(touch_intercept((82, 0), (0, 0), (0, 0), (0, 2500), 0,
                                         (4500, 0), lambda p: True, 82, 1800, 1))

    def test_impossible_incoming_velocity_is_not_a_valid_redirect(self):
        self.assertFalse(redirect_possible((0, 0), (4500, 0), (0, 5000), 1800, 1))
        self.assertFalse(redirect_possible((0, 0), (4500, 0), (-2500, 0), 1800, 1))
        self.assertTrue(redirect_possible((0, 0), (4500, 0), (0, 1000), 1800, 1))

    def test_receive_intercept_filters_ball_contact_as_well_as_robot_centre(self):
        centre = intercept((3400, 0), (0, 0), (3000, 0), (0, 0), lambda p: True,
                           contact_legal=lambda p: p[0] <= 3320)
        self.assertEqual(centre, (3000, 0))


class SequenceTests(unittest.TestCase):
    def setUp(self):
        self.pos = {0: Point(0, 0), 1: Point(3200, 800)}
        self.heading = {0: 0, 1: 0}
        self.robot_velocity = {0: Point(0, 0), 1: Point(0, 0)}
        self.ball = Point(82, 0)
        self.speed = 0
        self.velocity = Point(0, 0)
        self.ball_valid = True
        self.keeper_pos = None
        self.omega = 0
        self.cpp = Mock()
        self.cpp.CVector.side_effect = Point
        self.cpp.InTheirPenaltyArea.return_value = False
        self.cpp.InOurPenaltyArea.return_value = False
        self.v5_execute = Mock()
        self.get_ball_v5 = Mock(return_value=(self.v5_execute, lambda n: self.ball))
        self.kick = Mock()
        self.player = NS(Pos=lambda n: self.pos[n], direction=lambda n: self.heading[n],
            vel=lambda n: self.robot_velocity[n], velMod=lambda n: math.hypot(self.robot_velocity[n].a, self.robot_velocity[n].b), rotVel=lambda n: self.omega,
            toBallDir=lambda n: math.atan2(self.ball.b-self.pos[n].b, self.ball.a-self.pos[n].a))
        def declare(*states):
            def wrap(cls):
                cls.declared = states
                return cls
            return wrap
        modules = {
            'CppPackage': self.cpp,
            'RoleMatch_LuaStyle': NS(Task=lambda skill, fixedNumber: NS(skill=skill, skill_cpp=skill[0], number=fixedNumber),
                State=FrameState, StateMachine=object, declare_state_machine=declare),
            'RoleMatch_LuaStyle.Skills': NS(Skill=NS(GetBallV5=self.get_ball_v5)),
            'Geometry': NS(CGeoPoint=Point),
            'Vision': NS(Ball=NS(valid=lambda: self.ball_valid, pos=lambda: self.ball, vel=lambda: self.velocity,
                velMod=lambda: self.speed, posX=lambda: self.ball.a, posY=lambda: self.ball.b),
                Player=self.player, Enemy=NS(valid=lambda n: self.keeper_pos is not None,
                    pos=lambda n: self.keeper_pos, vel=lambda n: Point(0, 0))),
            'WorldModel': NS(Flags=NS(allow_dss=1, dodge_ball=16, dribbling=256), kickStatus=self.kick,
                Params=NS(pitchLength=9000, pitchWidth=6000, penaltyDepth=1000,
                          playerRadius=90, goalWidth=1000, playerFrontToCenter=76)),
            'WorldModel.PowerCalculator': NS(evalPower=Mock(return_value=7000), P=NS(NORMAL=1,HIGH=2)),
        }
        with patch.dict(sys.modules, modules):
            self.m = runpy.run_path(str(Path(__file__).resolve().parents[1] / 'Play/Normal/two_attack.py'))
        self.pos[1] = self.m['ASSISTANT_POS']
        self.control = self.m['Control']()
        for _ in range(3): self.control.update()

    def state(self, name):
        s = self.m[name]()
        s.control = self.control
        return s

    def observe(self, position, velocity=(0, 0)):
        self.ball, self.velocity = Point(*position), Point(*velocity)
        self.speed = math.hypot(*velocity)
        self.control.update()

    def machine(self, name):
        machine = self.m['two_attack']()
        machine.control = self.control
        machine.states = {cls.__name__: self.state(cls.__name__) for cls in machine.declared}
        machine.start_state = machine.states['GetFirstBall']
        machine.current_state = machine.states[name]
        return machine

    def frame(self, machine, switched=False):
        with patch.dict(sys.modules, {'Global': NS(isPlaySwitched=switched)}):
            machine.hookBeforePlanTasks()
        if switched:
            machine.current_state = machine.start_state
        result = machine.current_state.run(False)
        if result:
            machine.current_state = machine.states[result]
        return machine.current_state.state_name

    def test_state_order_and_fixed_numbers(self):
        self.assertEqual([s.__name__ for s in self.m['two_attack'].declared],
            ['GetFirstBall','PassToAssistant','ReceiveAndReturn','PassBack',
             'InterceptAndShoot','FollowShot','Done'])
        for cls in self.m['two_attack'].declared:
            tasks = self.state(cls.__name__).getTasks()
            self.assertEqual([tasks['A'].number, tasks['B'].number], [0, 1])

    def test_first_pass_waits_for_ball_and_receiver(self):
        s = self.state('GetFirstBall')
        self.assertEqual(s.transFunction(), 'PassToAssistant')
        self.pos[1] = Point(1000, 0)
        self.assertEqual(s.transFunction(), '')
        self.pos[1] = self.m['ASSISTANT_POS']
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
        self.ball = Point(self.pos[1].a + 82, self.pos[1].b)
        for _ in range(3): self.control.update()
        centre, self.heading[0] = self.m['prepare_return'](self.control)
        self.pos[0] = Point(*centre)
        self.assertEqual(self.state('ReceiveAndReturn').transFunction(), 'PassBack')
        back = self.state('PassBack')
        back.fired = (self.ball.a, self.ball.b)
        self.ball = Point(self.ball.a - 100, self.ball.b - 400)
        self.control.update()
        self.assertEqual(back.transFunction(), 'InterceptAndShoot')
        shot = self.state('InterceptAndShoot')
        shot.fired = self.control.return_contact
        self.ball = Point(4000, -200)
        self.velocity = Point(1500, 0)
        self.assertEqual(shot.transFunction(), 'FollowShot')

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
        self.get_ball_v5.assert_not_called()
        self.cpp.makeItRushTo.assert_called_once()
        self.cpp.setDribbleCommand.assert_called_once_with(0, 3)
        command = self.cpp.makeItRushTo.call_args
        angle = command.args[2]
        self.assertTrue(self.m['motion_legal'](0, (command.args[1].a, command.args[1].b)))
        self.assertEqual((command.kwargs['vel'].a, command.kwargs['vel'].b), (0, 0))
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
        self.get_ball_v5.assert_not_called()
        desired = math.atan2(410, 4500 - 82)
        self.assertAlmostEqual(self.cpp.makeItRushTo.call_args.args[2], desired)

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

    def test_fast_ball_capture_still_requires_three_consecutive_frames(self):
        self.control = self.m['Control']()
        self.velocity = Point(300, 0)
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

    def test_triangle_contact_is_close_to_goal_off_centre_and_behind_receiver(self):
        assistant = self.m['ASSISTANT_POS']
        self.assertEqual((assistant.a, assistant.b), (3250, 1100))
        self.assertEqual(self.m['SHOT_CONTACT'], (3050, -350))
        contact = self.m['SHOT_CONTACT']
        self.assertLess(contact[0], assistant.a - 82)
        self.assertLess(math.hypot(4500 - contact[0], contact[1]), 1600)
        self.assertTrue(self.m['ball_recoverable'](contact))
        self.ball = Point(assistant.a, assistant.b)
        for keeper_y in (-300, 0, 300):
            self.keeper_pos = Point(4200, keeper_y)
            centre, angle = self.m['prepare_return'](self.control)
            self.assertTrue(self.m['legal'](centre))
            self.assertLess(centre[1], -200)
            self.assertAlmostEqual(centre[0] + 82 * math.cos(angle), contact[0])
            self.assertAlmostEqual(centre[1] + 82 * math.sin(angle), contact[1])

    def test_first_holder_preaims_while_receiver_runs_without_kicking(self):
        self.pos[1] = Point(1000, 0)
        s = self.state('GetFirstBall')
        s.getTasks()['A'].skill_cpp(0)
        self.cpp.makeItSimpleGoTo.assert_called_once()
        self.assertGreater(self.cpp.makeItSimpleGoTo.call_args.args[2], 0)
        self.kick.setKick.assert_not_called()
        self.assertEqual(s.transFunction(), '')

    def test_return_holder_preaims_but_waits_for_shooter(self):
        self.ball = Point(self.pos[1].a + 82, self.pos[1].b)
        for _ in range(3): self.control.update()
        s = self.state('ReceiveAndReturn')
        s.getTasks()['B'].skill_cpp(1)
        self.cpp.makeItSimpleGoTo.assert_called_once()
        self.assertLess(self.cpp.makeItSimpleGoTo.call_args.args[2], 0)
        self.kick.setKick.assert_not_called()
        self.assertEqual(s.transFunction(), '')

    def test_return_pass_rechecks_shooter_readiness_after_state_entry(self):
        self.ball = Point(3230, 1050)
        centre, angle = self.m['prepare_return'](self.control)
        desired = self.m['direction']((self.ball.a, self.ball.b), self.control.return_contact)
        self.heading[1] = desired
        self.pos[1] = Point(self.ball.a - 82 * math.cos(desired), self.ball.b - 82 * math.sin(desired))
        self.control.held[1] = True
        self.pos[0], self.heading[0] = Point(*centre), angle
        self.assertTrue(self.m['return_ready'](self.control))
        self.pos[0] = Point(2000, 0)
        s = self.state('PassBack')
        s.getTasks()['B'].skill_cpp(1)
        self.kick.setKick.assert_not_called()

    def test_settled_ball_can_be_confirmed_after_two_frames(self):
        self.control = self.m['Control']()
        self.control.update()
        self.assertFalse(self.control.held[0])
        self.control.update()
        self.assertTrue(self.control.held[0])

    def test_fast_capture_includes_mouth_rotational_velocity(self):
        self.control = self.m['Control']()
        self.omega = 4
        self.control.update()
        self.control.update()
        self.assertFalse(self.control.held[0])

    def test_early_release_requires_kick_separation_speed_and_direction(self):
        s = self.state('PassToAssistant')
        s.target = Point(3000, 0)
        self.ball, self.velocity, self.speed = Point(160, 0), Point(1500, 0), 1500
        self.assertFalse(s.released(0))
        s.fired = (82, 0)
        self.assertTrue(s.released(0))
        self.velocity = Point(0, 1500)
        self.assertFalse(s.released(0))
        self.velocity, self.speed = Point(100, 0), 100
        self.assertFalse(s.released(0))
        self.ball, self.velocity, self.speed = Point(120, 0), Point(1500, 0), 1500
        self.assertFalse(s.released(0))

    def test_confirmed_first_pass_starts_run_without_extra_state_frame(self):
        s = self.state('PassToAssistant')
        s.target, s.fired = Point(3000, 0), (82, 0)
        self.ball, self.velocity, self.speed = Point(160, 0), Point(1500, 0), 1500
        s.getTasks()['A'].skill_cpp(0)
        self.assertGreater(self.cpp.makeItRushTo.call_args.args[1].a, 2800)
        self.kick.setKick.assert_not_called()
        self.assertEqual(s.transFunction(), 'ReceiveAndReturn')

    def test_shot_uses_checked_centre_as_actual_native_target(self):
        self.ball = Point(600, 100)
        self.control.held[0] = False
        plan = ((600, 100), (518, 100), .8, 0)
        with patch.dict(self.m['touch_shot'].__globals__, {'touch_intercept': lambda *a, **kw: plan}):
            self.state('InterceptAndShoot').getTasks()['A'].skill_cpp(0)
        target = self.cpp.makeItRushTo.call_args.args[1]
        self.assertEqual((target.a, target.b), (518, 100))
        self.get_ball_v5.assert_not_called()

    def test_near_ball_wrong_heading_brakes_before_contact(self):
        self.ball = Point(180, 0)
        self.heading[0] = math.pi / 2
        self.control.held[0] = False
        self.state('InterceptAndShoot').getTasks()['A'].skill_cpp(0)
        target = self.cpp.makeItRushTo.call_args.args[1]
        self.assertEqual((target.a, target.b), (0, 0))
        self.kick.setKick.assert_not_called()

    def test_unreachable_shot_fallback_also_brakes_instead_of_pushing(self):
        self.ball = Point(200, 0)
        self.robot_velocity[0] = Point(1000, 0)
        self.control.held[0] = False
        self.state('InterceptAndShoot').getTasks()['A'].skill_cpp(0)
        command = self.cpp.makeItRushTo.call_args
        self.assertEqual((command.args[1].a, command.args[1].b), (0, 0))
        self.assertEqual((command.kwargs['vel'].a, command.kwargs['vel'].b), (0, 0))
        self.assertEqual(command.kwargs['maxAcc'], 1800)
        self.kick.setKick.assert_not_called()

    def test_uncompensatable_ball_at_mouth_is_held_then_shot_when_settled(self):
        self.control.held[0] = False
        self.velocity, self.speed = Point(0, 5000), 5000
        s = self.state('InterceptAndShoot')
        s.getTasks()['A'].skill_cpp(0)
        command = self.cpp.makeItRushTo.call_args
        self.assertEqual((command.args[1].a, command.args[1].b), (0, 0))
        self.kick.setKick.assert_not_called()
        self.velocity, self.speed = Point(0, 0), 0
        self.heading[0] = self.m['direction']((82, 0), self.control.shot_target)
        s.getTasks()['A'].skill_cpp(0)
        self.kick.setKick.assert_called_once_with(0, 7000)

    def test_ball_inside_box_waits_outside_and_resumes_when_ball_returns(self):
        self.pos[0] = Point(3000, -350)
        self.ball = Point(3600, 0)
        self.control.held[0] = False
        s = self.state('InterceptAndShoot')
        s.getTasks()['A'].skill_cpp(0)
        target = self.cpp.makeItRushTo.call_args.args[1]
        self.assertTrue(self.m['legal']((target.a, target.b)))
        self.assertLess(target.a, 3200)
        self.kick.setKick.assert_not_called()
        self.ball = Point(3082, -350)
        s.getTasks()['A'].skill_cpp(0)
        self.kick.setKick.assert_called_once_with(0, 7000)

    def test_after_kick_robot_does_not_chase_ball_waiting_for_release(self):
        s = self.state('InterceptAndShoot')
        s.fired = (82, 0)
        self.ball = Point(130, 0)
        s.getTasks()['A'].skill_cpp(0)
        self.cpp.makeItRushTo.assert_not_called()
        self.cpp.makeItStop.assert_called_once_with(0)

    def test_inward_motion_near_boundary_is_allowed_but_outward_braking_is_checked(self):
        self.pos[0] = Point(3200, -350)
        self.robot_velocity[0] = Point(-1000, 0)
        self.assertTrue(self.control.allowed(0))
        self.robot_velocity[0] = Point(1000, 0)
        self.assertFalse(self.control.allowed(0))

    def test_invalid_touch_destination_never_reaches_motion_command(self):
        self.ball = Point(1000, 0)
        self.control.shot_target = (4500, -410)
        s = self.state('InterceptAndShoot')
        self.m['touch_motion'](s, (3500, 0), 0).skill_cpp(0)
        self.cpp.makeItRushTo.assert_not_called()
        self.cpp.makeItStop.assert_called_once_with(0)

    def test_shot_flight_does_not_finish_or_retry_while_still_on_target(self):
        self.control.start_shot((3050, -350))
        self.observe((4000, -350), (1500, 0))
        self.assertTrue(self.control.shot_departed)
        self.assertFalse(self.control.rebound_ready)
        self.assertIsNone(self.control.outcome)
        self.assertEqual(self.state('FollowShot').transFunction(), '')

    def test_immediate_blocked_shot_can_retry_without_forward_release(self):
        s = self.state('InterceptAndShoot')
        s.fired = (82, 0)
        self.control.start_shot(s.fired)
        self.observe((-100, 0), (-1000, 0))
        self.assertFalse(s.released(0))
        self.assertTrue(self.control.rebound_ready)
        self.assertEqual(s.transFunction(), 'FollowShot')

    def test_near_rebound_unlocks_goal_target_and_preserves_carry_and_clearance(self):
        self.observe((3050, -350))
        self.control.rebound_ready = True
        self.control.shot_locked = True
        self.control.shot_target = (4500, 410)
        self.control.keeper_cleared = True
        self.control.carry[0] = 400
        self.assertEqual(self.state('FollowShot').transFunction(), 'InterceptAndShoot')
        self.assertTrue(self.control.direct_rebound)
        self.assertFalse(self.control.shot_locked)
        self.assertIsNone(self.control.shot_target)
        self.assertEqual(self.control.carry[0], 400)
        self.assertTrue(self.control.keeper_cleared)

    def test_far_rebound_reuses_single_return_pass(self):
        self.observe((1500, -300))
        self.control.rebound_ready = True
        machine = self.machine('FollowShot')
        self.assertEqual(self.frame(machine), 'ReceiveAndReturn')
        self.assertFalse(self.control.direct_rebound)

        centre, self.heading[0] = self.m['prepare_return'](self.control)
        self.pos[0] = Point(*centre)
        self.heading[1] = self.m['direction']((1500, -300), self.control.return_contact)
        self.pos[1] = Point(1500 - 82 * math.cos(self.heading[1]), -300 - 82 * math.sin(self.heading[1]))
        self.assertEqual(self.frame(machine), 'ReceiveAndReturn')
        self.assertEqual(self.frame(machine), 'PassBack')
        self.assertEqual(self.frame(machine), 'PassBack')
        self.kick.setKick.assert_called_once_with(1, 7000)
        self.ball, self.velocity, self.speed = Point(2000, -316), Point(1500, -50), 1501
        self.assertEqual(self.frame(machine), 'InterceptAndShoot')
        # 回传途中球还远离门时，不得被“直接补射转远球”分支重新送回接球状态。
        self.assertEqual(self.frame(machine), 'InterceptAndShoot')

    def test_rebound_distance_boundary_and_outgoing_lookahead(self):
        self.observe((2300, 0))
        self.assertFalse(self.m['rebound_needs_pass']())
        self.observe((2299, 0))
        self.assertTrue(self.m['rebound_needs_pass']())
        self.observe((2700, 0), (-2000, 0))
        self.assertTrue(self.m['rebound_needs_pass']())
        self.observe((2700, 0), (2000, 0))
        self.assertFalse(self.m['rebound_needs_pass']())

    def test_direct_rebound_can_switch_to_pass_before_kick(self):
        self.observe((1800, 0), (-1500, 0))
        self.control.direct_rebound = True
        s = self.state('InterceptAndShoot')
        s.getTasks()['A'].skill_cpp(0)
        self.kick.setKick.assert_not_called()
        self.assertGreater(self.cpp.makeItRushTo.call_args.args[1].a, 2800)
        self.assertEqual(s.transFunction(), 'ReceiveAndReturn')
        self.assertFalse(self.control.direct_rebound)

    def test_repeated_near_rebounds_reset_reused_state_and_finish_only_on_goal(self):
        self.pos[0] = Point(3000, -350)
        self.heading[0] = self.m['direction']((3082, -350), (4500, -410))
        self.control.previous.clear()  # 测试场景初始化的瞬移不应计入真实带球里程。
        self.observe((3082, -350))
        machine = self.machine('InterceptAndShoot')
        for attempt in range(3):
            with self.subTest(attempt=attempt):
                self.ball, self.velocity, self.speed = Point(3082, -350), Point(0, 0), 0
                self.assertEqual(self.frame(machine), 'InterceptAndShoot')
                self.assertEqual(self.kick.setKick.call_count, attempt + 1)
                self.ball, self.velocity, self.speed = Point(4100, -350), Point(1500, 0), 1500
                self.assertEqual(self.frame(machine), 'FollowShot')
                self.velocity = Point(-1000, 0)
                self.speed = 1000
                self.assertEqual(self.frame(machine), 'InterceptAndShoot')
                self.assertIsNone(self.control.outcome)
        self.ball, self.velocity, self.speed = Point(4530, -350), Point(1500, 0), 1500
        self.assertEqual(self.frame(machine), 'Done')
        self.assertEqual(self.control.outcome, 'goal')
        self.assertEqual(self.kick.setKick.call_count, 3)

    def test_keeper_deflection_outside_sideline_finishes(self):
        self.keeper_pos = Point(4200, 200)
        self.control.previous_ball = None
        self.observe((4100, 200), (1500, 0))
        self.observe((4080, 350), (-300, 1800))
        self.assertTrue(self.control.keeper_cleared)
        self.assertIsNone(self.control.outcome)
        self.observe((3600, 3040), (-300, 1800))
        self.assertEqual(self.control.outcome, 'keeper_clearance_out')

    def test_goal_takes_priority_over_keeper_deflection_out(self):
        self.keeper_pos = Point(4400, 0)
        self.control.previous_ball = None
        self.observe((4400, 0), (1500, 0))
        self.observe((4530, 0), (800, 0))
        self.assertTrue(self.control.keeper_cleared)
        self.assertEqual(self.control.outcome, 'goal')

    def test_clearance_requires_whole_ball_out_across_each_boundary(self):
        pairs = (((4510, 700), (4530, 700)), ((-4510, 700), (-4530, 700)),
                 ((2000, 3010), (2000, 3030)), ((2000, -3010), (2000, -3030)))
        for partially_out, fully_out in pairs:
            with self.subTest(boundary=fully_out):
                self.control = self.m['Control']()
                self.control.keeper_cleared = True
                self.observe(partially_out)
                self.assertIsNone(self.control.outcome)
                self.observe(fully_out)
                self.assertEqual(self.control.outcome, 'keeper_clearance_out')

    def test_next_rebound_reselects_corner_from_live_keeper(self):
        self.pos[0] = Point(3000, -350)
        self.control.previous.clear()
        self.observe((3082, -350))
        self.control.shot_target = (4500, -410)
        self.control.shot_locked = True
        self.control.rebound_ready = True
        self.keeper_pos = Point(4200, -300)
        self.assertEqual(self.state('FollowShot').transFunction(), 'InterceptAndShoot')
        self.state('InterceptAndShoot').getTasks()['A'].skill_cpp(0)
        self.assertEqual(self.control.shot_target, (4500, 410))
        self.kick.setKick.assert_not_called()  # 仍须按原有射门窗口完成瞄准。

    def test_contact_detection_handles_fast_sample_crossing_and_stationary_ball(self):
        self.keeper_pos = Point(4200, 0)
        self.control.previous_ball = None
        self.observe((4000, 0), (3000, 0))
        self.observe((4400, 0), (1000, 1800))
        self.assertTrue(self.control.keeper_cleared)
        self.control.keeper_cleared = False
        self.control.previous_ball = None
        self.observe((2000, 0), (0, 0))
        self.observe((2000, 0), (1000, 0))
        self.assertFalse(self.control.keeper_cleared)

    def test_keeper_lane_proximity_without_velocity_change_is_not_clearance(self):
        self.keeper_pos = Point(4200, 0)
        self.control.previous_ball = None
        self.observe((4100, 0), (1500, 0))
        self.observe((4150, 0), (1480, 0))
        self.assertFalse(self.control.keeper_cleared)

    def test_reacquiring_ball_clears_previous_keeper_attribution(self):
        self.control.keeper_cleared = True
        self.observe((82, 0))
        self.assertFalse(self.control.keeper_cleared)

    def test_out_without_keeper_clearance_stops_but_does_not_finish(self):
        self.observe((2500, 3040), (0, 1000))
        self.assertIsNone(self.control.outcome)
        self.assertEqual(self.state('FollowShot').run(False), '')
        self.assertEqual(self.cpp.makeItStop.call_count, 2)
        self.cpp.makeItRushTo.assert_not_called()

    def test_finish_stops_before_tasks_in_every_state_and_remains_latched(self):
        self.control.outcome = 'keeper_clearance_out'
        for cls in self.m['two_attack'].declared:
            with self.subTest(state=cls.__name__):
                self.cpp.reset_mock()
                self.assertEqual(self.state(cls.__name__).run(False), 'Done')
                self.assertEqual(self.cpp.makeItStop.call_count, 2)
                self.cpp.makeItRushTo.assert_not_called()
                self.kick.setKick.assert_not_called()
        self.observe((3000, 0))
        self.assertEqual(self.control.outcome, 'keeper_clearance_out')

    def test_missing_or_nonfinite_ball_pauses_without_false_goal_or_exit(self):
        self.observe((4400, 0), (1500, 0))
        self.ball_valid = False
        self.control.update()
        self.assertEqual(self.state('FollowShot').run(False), '')
        self.assertIsNone(self.control.previous_ball)
        self.ball_valid = True
        self.observe((4600, 0), (1500, 0))
        self.assertIsNone(self.control.outcome)
        self.observe((float('nan'), 0))
        self.assertFalse(self.control.ball_available)
        self.assertIsNone(self.control.outcome)

    def test_manual_play_restart_resets_terminal_and_old_attempts(self):
        machine = self.machine('Done')
        machine.control.outcome = 'goal'
        for state in machine.states.values():
            state.fired = (100, 0)
        self.frame(machine, switched=True)
        self.assertIsNone(machine.control.outcome)
        self.assertIsNone(machine.control.shot_origin)
        self.assertTrue(all(state.fired is None for state in machine.states.values()))
        self.assertNotEqual(machine.current_state.state_name, 'Done')

if __name__ == '__main__': unittest.main()

