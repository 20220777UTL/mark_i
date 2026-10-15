"""按校赛规则及用户“最后不补射”约束添加反例；不模拟触球物理。"""
import unittest
from unittest.mock import patch
import test_give_and_go as flow

Point = flow.Point


class RuleRegressionTests(unittest.TestCase):
    setUp = flow.GiveAndGoTests.setUp
    frame = flow.GiveAndGoTests.frame
    execute = staticmethod(flow.GiveAndGoTests.execute)
    assert_stopped = flow.GiveAndGoTests.assert_stopped
    prepare_finish = flow.GiveAndGoTests.prepare_finish

    def test_finish_rebound_cannot_request_a_second_shot(self):
        self.prepare_finish(Point(3270, 0), (-1000, 0))
        with patch.object(self.module.time, 'monotonic', return_value=101):
            self.execute(self.frame(101))
        self.ball.pos, self.ball.velX = lambda: Point(3330, 0), lambda: 1000
        self.execute(self.frame(101.03))
        self.ball.pos, self.ball.velX = lambda: Point(3270, 0), lambda: -1000
        with patch.object(self.module.time, 'monotonic', return_value=101.06):
            self.execute(self.frame(101.06))
        self.kicks.setKick.assert_called_once()
        self.assertEqual(self.state.phase, 'DONE')

    def test_non_goalkeeper_near_ball_in_own_penalty_area_stops(self):
        self.positions[1] = Point(-3490, 0)
        self.ball.pos = lambda: Point(-3392, 0)
        self.infrared[1] = True
        self.frame(100)
        self.assertEqual(self.state.phase, 'DONE')
        self.kicks.setKick.assert_not_called()

    def test_long_continuous_carry_stops_even_when_infrared_drops(self):
        self.frame(100)
        self.state.phase, self.state.started = 'RETURN_SETUP', 100
        self.positions[1], self.angles[1] = Point(3150, 0), 0
        for step in range(11):
            self.positions[2] = Point(2900 + 100 * step, -2400)
            self.angles[2] = 0
            self.ball.pos = lambda: self.module.mouth(self.positions[2], 0)
            self.infrared[2] = step != 5
            self.frame(101 + .05 * step)
        self.assertEqual(self.state.phase, 'DONE')
        self.kicks.setKick.assert_not_called()

    def test_carry_budget_resets_only_after_clear_ball_separation(self):
        self.positions[2], self.angles[2], self.infrared[2] = Point(2900, -2400), 0, True
        self.ball.pos = lambda: self.module.mouth(self.positions[2], 0)
        self.assertFalse(self.state.carry_limit_reached())
        self.positions[2] = Point(3300, -2400)
        self.infrared[2] = False
        self.assertFalse(self.state.carry_limit_reached())
        self.assertEqual(self.state.carry_distance, 400)
        self.ball.pos = lambda: Point(0, 0)
        self.assertFalse(self.state.carry_limit_reached())
        self.assertEqual(self.state.carry_distance, 0)
        self.assertIsNone(self.state.carry_last)
        self.state.reset()
        self.assertEqual(self.state.carry_distance, 0)

    def test_robot_in_own_area_can_leave_when_ball_is_far_away(self):
        self.positions[1] = Point(-3490, 0)
        self.frame(100)
        self.assertEqual(self.state.phase, 'SETUP')

    def test_same_contact_window_can_keep_request_until_timeout(self):
        self.prepare_finish(Point(3270, 0), (-1000, 0))
        for now in (101, 101.05):
            with patch.object(self.module.time, 'monotonic', return_value=now):
                self.execute(self.frame(now))
        self.assertEqual(self.kicks.setKick.call_count, 2)
        self.assert_stopped(self.frame(101.2))
