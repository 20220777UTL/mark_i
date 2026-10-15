"""Pass/return/shot behavior, with actual outgoing native commands asserted."""
import math
import random
import unittest
from contextlib import redirect_stdout
from two_attack_fixture import Harness, Point
from Play.Normal import AttackParams as A
from Play.Normal.AttackGeometry import behind, crossed_goal, return_plan, intercept_contact
from Play.Normal.AttackFeedback import curve_fingerprint


class GeometryTests(unittest.TestCase):
    def test_return_distinguishes_landing_contact_and_robot_centre(self):
        p = return_plan((1000, 1000), (3000, 0), (4500, -410), 98, 200)
        self.assertAlmostEqual(math.dist(p.contact, p.landing), 200)
        self.assertAlmostEqual(math.dist(p.contact, p.centre), 98)
        self.assertAlmostEqual(math.dist((1000, 1000), p.landing) + 200, math.dist((1000, 1000), p.contact))
        self.assertEqual(p.centre, behind(p.contact, p.heading, 98))
        for source, lead in (((3000, 0), 0), ((2900, 0), 200)):
            with self.assertRaises(ValueError):
                return_plan(source, (3000, 0), (4500, 0), 98, lead)

    def test_short_prediction_is_bounded_without_friction_model(self):
        for velocity in ((0, 0), (1000, 0), (0, -2000)):
            contact = intercept_contact((0, 0), velocity, (500, -500))
            self.assertLessEqual(math.hypot(*contact), math.hypot(*velocity) * A.PREDICT_HORIZON)

    def test_goal_uses_entire_ball_and_crossing_position(self):
        self.assertFalse(crossed_goal((4490, 0), (4510, 0), 4500, 1000))
        self.assertTrue(crossed_goal((4400, 0), (4600, 600), 4500, 1000))
        self.assertFalse(crossed_goal((4400, 1300), (4600, 0), 4500, 1000))


class SequenceTests(unittest.TestCase):
    def test_five_states_and_fixed_numbers(self):
        h = Harness()
        machine = h.m['two_attack']()
        self.assertEqual(list(machine.states), ['FirstPass', 'PassBack', 'Shoot', 'FollowShot', 'Done'])
        h.settle()
        tasks = h.state('FirstPass').getTasks()
        self.assertEqual([t.number for t in tasks.values()], [0, 1])

    def test_first_pass_waits_for_receiver_and_alignment(self):
        h = Harness()
        h.positions[1] = Point(1000, 1000)
        h.settle()
        h.run(h.state('FirstPass'))
        h.kicks.setKick.assert_not_called()
        h.positions[1] = Point(*h.m['ASSISTANT_POS'])
        h.headings[1] = math.atan2(-h.positions[1].b, h.ball.a - h.positions[1].a)
        aim = math.atan2(h.positions[1].b, h.positions[1].a - h.ball.a)
        h.headings[0] = aim
        h.positions[0] = Point(h.ball.a - 100 * math.cos(aim), h.ball.b - 100 * math.sin(aim))
        h.settle()
        s = h.state('FirstPass')
        self.assertEqual(h.run(s), '')
        h.kicks.setKick.assert_called_once()
        self.assertIsNotNone(s.fired)
        h.ball = Point(h.ball.a + 300 * math.cos(aim), h.ball.b + 300 * math.sin(aim))
        h.update()
        self.assertEqual(h.run(s), 'PassBack')

    def test_chip_uses_landing_power_profile_and_correct_native_command(self):
        h = Harness()
        s, p = h.ready_return()
        h.run(s)
        h.kicks.setChipKick.assert_called_once_with(1, 2500)
        h.kicks.setKick.assert_not_called()
        args, kwargs = h.power.call_args
        self.assertEqual((args[1].x(), args[1].y()), p.landing)
        self.assertTrue(kwargs['is_chip'])
        self.assertTrue(h.c.chip_pending)
        self.assertTrue(h.c.plan_locked)

    def test_real_chip_requires_ir_not_visual_proximity(self):
        h = Harness(False)
        s, _ = h.ready_return()
        h.ir[1] = False
        h.update()
        h.run(s)
        h.kicks.setChipKick.assert_not_called()

    def test_flat_fallback_reasons_and_no_cross_environment_calibration(self):
        mutations = (
            ('chip_uncalibrated', lambda h: h.profile['chip'].update(calibrated=False)),
            ('chip_wrong_reference_or_sender', lambda h: h.profile['chip'].update(distance_reference='final_stop')),
            ('chip_wrong_reference_or_sender', lambda h: h.profile['chip'].update(sender=0)),
            ('chip_curve_changed', lambda h: h.curves['profiles']['chip']['limits'].update(max_power=3500)),
            ('chip_curve_changed', lambda h: setattr(h.global_, 'powerMax', 12000)),
            ('chip_outside_calibrated_range', lambda h: h.profile['chip'].update(max_distance_mm=500)),
            ('chip_landing_feedback_unavailable', lambda h: setattr(h, 'height', None)),
            ('chip_invalid_measurements', lambda h: h.profile['chip'].update(landing_lead_mm=float('nan'))),
        )
        for reason, mutate in mutations:
            with self.subTest(reason=reason):
                h = Harness()
                s, _ = h.ready_return()
                mutate(h)
                h.update()
                with redirect_stdout(h.log):
                    p = h.m['prepare_return'](h.c)
                self.assertFalse(p.is_chip)
                self.assertEqual(p.landing, p.contact)
                self.assertEqual(h.c.fallback_reason, reason)

    def test_landing_and_goal_lock_at_command(self):
        h = Harness()
        s, p = h.ready_return()
        h.run(s)
        h.ball = Point(h.ball.a - 150, h.ball.b - 150)
        h.keeper = Point(4200, -300)
        h.height, h.airborne = 300, True
        h.update()
        self.assertEqual(h.m['prepare_return'](h.c), p)

    def test_airborne_xy_contact_never_fires_and_waits_at_planned_centre(self):
        h = Harness()
        s, p = h.ready_return()
        h.run(s)
        h.ball = Point(*p.contact)
        h.height, h.airborne = 300, True
        h.update()
        h.clear_commands()
        h.run(h.state('Shoot'))
        h.kicks.setKick.assert_not_called()
        self.assertFalse(h.c.held[0])
        args = h.cpp.makeItRushTo.call_args.args
        self.assertEqual((args[1].x(), args[1].y()), p.centre)
        h.height, h.airborne = None, False
        h.settle()
        h.clear_commands()
        h.run(h.state('Shoot'))
        h.kicks.setKick.assert_not_called()
        self.assertFalse(h.c.grounded)

    def test_observed_landing_enables_contact_without_continuous_possession(self):
        h = Harness()
        s, p = h.ready_return()
        h.run(s)
        h.height, h.airborne = 300, True
        h.ball = Point(*p.landing)
        h.update()
        h.height, h.airborne = 22, False
        h.settle()
        self.assertTrue(h.c.grounded)
        self.assertIn('chip_landing_observed', h.log.getvalue())
        h.ball = Point(*p.contact)
        h.velocity = Point(-600 * math.cos(p.heading), -600 * math.sin(p.heading))
        h.update()
        self.assertFalse(h.c.held[0])
        h.clear_commands()
        shot = h.state('Shoot')
        h.run(shot)
        h.kicks.setKick.assert_called_once_with(0, 2500)
        h.kicks.setChipKick.assert_not_called()
        self.assertIn('chip_contact', h.log.getvalue())

    def test_real_ir_contact_recovers_missing_chip_height_feed(self):
        h = Harness(False)
        s, p = h.ready_return()
        h.run(s)
        h.ball = Point(*p.contact)
        h.height = None
        h.ir[0], h.ir[1] = True, False
        h.update()
        self.assertTrue(h.c.grounded)
        self.assertFalse(h.c.chip_pending)

    def test_lateral_fast_or_badly_aligned_arrival_falls_back_to_receive(self):
        for velocity, heading in (((0, 1500), 0), ((-5000, 0), 0), ((-500, 0), math.pi/2)):
            h = Harness()
            h.headings[0] = heading
            h.ball, h.velocity = Point(100, 0), Point(*velocity)
            h.update()
            s = h.state('Shoot')
            h.c.shot_target = (4500, 0)
            h.run(s)
            h.kicks.setKick.assert_not_called()

    def test_bad_power_and_unsafe_motion_cannot_emit_kick(self):
        for power in (0, -1, float('nan'), float('inf')):
            h = Harness()
            h.settle()
            h.power.return_value = power
            s = h.state('Shoot')
            h.c.shot_target = (4500, 0)
            h.run(s)
            h.kicks.setKick.assert_not_called()

    def test_carry_limit_and_field_guards_remain(self):
        h = Harness()
        h.settle()
        h.c.carry[0] = A.CARRY_LIMIT
        h.task(h.m['move_to'](0, (100, 0), h.c))
        h.cpp.makeItRushTo.assert_not_called()
        h.c.carry[0] = 0
        h.task(h.m['move_to'](0, (99999, 99999), h.c))
        dest = h.cpp.makeItRushTo.call_args.args[1]
        self.assertTrue(h.m['legal']((dest.x(), dest.y())))
        h.positions[0], h.ball = Point(3300, 0), Point(3400, 0)
        h.velocities[0] = Point(2500, 0)
        h.velocity = Point(2500, 0)
        h.update()
        h.clear_commands()
        h.task(h.m['receive'](0, h.c))
        h.kicks.setKick.assert_not_called()

    def test_all_outs_finish_and_goal_has_priority(self):
        for position, expected in (((4600, 0), 'goal'), ((4600, 1200), 'out'),
                                   ((0, 3040), 'out'), ((-4600, 0), 'out'), ((0, -3040), 'out')):
            h = Harness()
            h.ball = Point(4400, 0) if position[0] == 4600 else Point(0, 0)
            h.update()
            h.ball = Point(*position)
            h.update()
            self.assertEqual(h.c.outcome, expected)
            h.clear_commands()
            self.assertEqual(h.run(h.state('FirstPass')), 'Done')
            h.cpp.makeItRushTo.assert_not_called()
            h.kicks.setKick.assert_not_called()

    def test_airborne_or_unknown_chip_cannot_score_from_xy_crossing(self):
        for height, airborne in ((300, True), (None, False)):
            h = Harness()
            h.c.chip_pending = True
            h.height, h.airborne = height, airborne
            h.ball = Point(4400, 0)
            h.update()
            h.ball = Point(4600, 0)
            h.update()
            self.assertEqual(h.c.outcome, 'out')

    def test_departure_does_not_mean_goal_and_rebounds_repeat(self):
        h = Harness()
        h.settle()
        s = h.state('Shoot')
        h.c.shot_target = (4500, 0)
        h.run(s)
        h.ball, h.velocity = Point(300, 0), Point(-1000, 0)
        h.update()
        self.assertEqual(h.run(s), 'FollowShot')
        self.assertIsNone(h.c.outcome)
        f = h.state('FollowShot')
        self.assertEqual(h.run(f), 'PassBack')
        for _ in range(3):
            h.ball, h.velocity = Point(3000, 0), Point(-500, 0)
            h.update()
            self.assertEqual(h.run(f), 'Shoot')
            h.velocity = Point(1000, 0)
            h.update()
            self.assertEqual(h.run(f), '')

    def test_no_repeat_kick_until_departure_or_bounded_retry(self):
        h = Harness()
        h.settle()
        s = h.state('Shoot')
        h.c.shot_target = (4500, 0)
        h.run(s)
        h.run(s)
        self.assertEqual(h.kicks.setKick.call_count, 1)
        for _ in range(9): h.update(.1)
        h.run(s)
        self.assertEqual(h.kicks.setKick.call_count, 2)

    def test_failed_chip_recovers_only_with_fresh_possession_at_sender(self):
        for simulation in (False, True):
            with self.subTest(simulation=simulation):
                h = Harness(simulation)
                s, _ = h.ready_return()
                h.run(s)
                self.assertTrue(h.c.chip_pending)
                for _ in range(9): h.update(.1)
                self.assertFalse(h.c.chip_pending)
                self.assertIn('chip_aborted', h.log.getvalue())
                h.run(s)
                h.settle()
                h.run(s)
                self.assertEqual(h.kicks.setChipKick.call_count, 2)

    def test_missing_flight_feedback_does_not_timeout_into_false_landing(self):
        h = Harness()
        s, p = h.ready_return()
        h.run(s)
        h.height = None
        h.ball = Point(*p.contact)
        for _ in range(20): h.update(.1)
        self.assertTrue(h.c.chip_pending)
        self.assertFalse(h.c.grounded)
        h.clear_commands()
        h.run(h.state('Shoot'))
        h.kicks.setKick.assert_not_called()

    def test_restart_resets_outcome_attempt_and_plan(self):
        h = Harness()
        machine = h.m['two_attack']()
        machine.control = h.c
        h.c.outcome = 'out'
        machine.states['Shoot'].fired = (1, 2)
        machine.current_state = machine.states['Done']
        h.global_.isPlaySwitched = True
        h.cycle += 1
        with redirect_stdout(h.log):
            machine.hookBeforePlanTasks()
        self.assertIsNone(machine.control.outcome)
        self.assertIsNone(machine.states['Shoot'].fired)
        self.assertEqual(machine.current_state.state_name, 'FirstPass')

    def test_actual_state_machine_completes_pass_return_shot_and_out(self):
        for chip in (False, True):
            with self.subTest(chip=chip):
                h = Harness()
                machine = h.m['two_attack']()
                machine.control = h.c
                def frame():
                    h.time += .025
                    h.cycle += 1
                    with redirect_stdout(h.log):
                        machine.planTasks()
                # Fresh possession at the receiver is also evidence of a completed first pass.
                s, plan = h.ready_return(chip=chip)
                frame()
                self.assertEqual(machine.current_state.state_name, 'PassBack')
                frame()
                self.assertIsNotNone(machine.states['PassBack'].fired)
                h.ball = Point(*plan.landing)
                h.height, h.airborne = (300, True) if chip else (None, False)
                frame()
                self.assertEqual(machine.current_state.state_name, 'Shoot')
                if chip:
                    h.height, h.airborne = 22, False
                    for _ in range(4): frame()
                h.ball = Point(*plan.contact)
                h.velocity = Point(-400 * math.cos(plan.heading), -400 * math.sin(plan.heading))
                frame()
                self.assertIsNotNone(machine.states['Shoot'].fired)
                h.ball, h.velocity = Point(3500, -350), Point(1500, 0)
                frame()
                self.assertEqual(machine.current_state.state_name, 'FollowShot')
                h.ball = Point(4600, -350)
                frame()
                self.assertEqual(machine.current_state.state_name, 'Done')
                self.assertEqual(h.c.outcome, 'goal')

    def test_fingerprint_cli_float_and_runtime_integer_are_equivalent(self):
        h = Harness()
        self.assertEqual(curve_fingerprint(h.curves, 12700), curve_fingerprint(h.curves, 12700.0))

    def test_curve_change_between_planning_and_execution_cancels_chip(self):
        h = Harness()
        s, _ = h.ready_return()
        with redirect_stdout(h.log):
            task = s.getTasks()['B']
        h.curves['profiles']['chip']['limits']['max_power'] = 3200
        h.task(task)
        h.kicks.setChipKick.assert_not_called()

    def test_diagnostics_report_marks_gaps_and_does_not_invent_landing(self):
        from tools.two_attack_diagnostics import report
        start = dict(type='chip_start', environment='real', source=[0, 0],
                     plan=dict(landing=[1000, 0], contact=[1200, 0]), curve_fingerprint='test')
        data = report([start, dict(type='frame', valid=False),
            dict(type='chip_contact', speed=100, after_landing_mm=None)])
        self.assertTrue(data['attempts'][0]['observation_gap'])
        self.assertIsNone(data['attempts'][0]['first_landing'])

    def test_perturbed_observations_never_bypass_touch_or_legal_guards(self):
        # Offline sensor/trajectory replay, not a claim of grSim or hardware validation.
        rng = random.Random(42)
        for friction in (200, 800, 1600):
            for dt in (.008, .025, .08):
                h = Harness()
                speed = 2000.
                y = 800.
                for _ in range(24):
                    speed = max(0, speed - friction * dt)
                    y -= speed * dt
                    h.ball = Point(100 + rng.uniform(-20, 20), y + rng.uniform(-15, 15))
                    h.velocity = Point(0, -speed)
                    h.update(dt)
                    h.clear_commands()
                    h.run(h.state('Shoot'))
                    if h.kicks.setKick.called:
                        self.assertTrue(h.m['touch_ready'](h.c, 0, h.c.shot_target) or h.c.held[0])
                    for call in h.cpp.makeItRushTo.call_args_list:
                        p = call.args[1]
                        self.assertTrue(h.m['legal']((p.x(), p.y())))


if __name__ == '__main__':
    unittest.main()
