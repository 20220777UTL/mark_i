import unittest
from math import atan2, cos, hypot, sin

from Play.Normal.TwoPlayerPolicy import (
    DRIBBLE_LIMIT, PASS_POWER, SHOT_POWER, SHIFT_LIMIT, STAGE_TIMEOUT,
    Frame, Robot, TwoPlayerPolicy, angle_error, direction,
)


def robot(x, y, angle=0.0, infrared=False, speed=0.0):
    return Robot(x, y, angle, infrared, speed)


def frame(t=0.0, ball=(1800, 550), velocity=(0, 0), ours=None, enemies=None, valid=True):
    if ours is None:
        ours = {1: robot(1500, 550, infrared=True), 2: robot(2200, -850)}
    return Frame(t, ball, velocity, ours, enemies or {0: robot(4250, 0)}, valid)


def distance_from_support(phase, pos):
    if phase == 'pass_2':
        target = (3200, -1300)
    elif phase == 'shoot':
        target = (4500, 0)
    else:
        target = (3200, 1300)
    return hypot(pos[0] - target[0], pos[1] - target[1])


def face(origin, point):
    return atan2(point[1] - origin[1], point[0] - origin[0])


class GateTests(unittest.TestCase):
    def test_vision_loss_stops_without_assigning_roles(self):
        policy = TwoPlayerPolicy()
        actions = policy.tick(frame(valid=False))
        self.assertEqual(policy.phase, 'assign')
        self.assertIsNone(policy.role1)
        self.assertTrue(all(action.kind == 'stop' for action in actions.values()))

    def test_closer_robot_is_role_one_after_roles_swap(self):
        policy = TwoPlayerPolicy()
        policy.tick(frame(0.0, ours={1: robot(2200, -850), 2: robot(1500, 550, infrared=True)}))
        policy.tick(frame(0.2, ours={1: robot(2200, -850), 2: robot(1500, 550, infrared=True)}))
        self.assertEqual((policy.role1, policy.role2), (2, 1))

    def test_waiting_does_not_advance_on_time_alone(self):
        policy = TwoPlayerPolicy()
        policy.phase = 'wait_upper'
        policy.role1, policy.role2 = 1, 2
        policy.hold[1] = (1500, 550)
        policy.entered = 0.0
        ball = (1585, 550)
        ours = {
            1: robot(1500, 550, face((1500, 550), ball), infrared=True),
            2: robot(1800, -400),
        }
        policy.tick(frame(10.0, ball=ball, ours=ours))
        self.assertEqual(policy.phase, 'wait_upper')
        policy.tick(frame(STAGE_TIMEOUT + 0.1, ball=ball, ours=ours))
        self.assertEqual(policy.phase, 'fault')
        self.assertIn('timed out', policy.reason)

    def test_ball_leaving_without_a_kick_command_does_not_advance(self):
        policy = self._armed_pass(False)
        aim = direction((1500, 550), (3200, 1300))
        velocity = (2000 * cos(aim), 2000 * sin(aim))
        ball = (1900, 700)
        ours = {1: robot(1500, 550, aim), 2: robot(3200, 1300)}
        policy.tick(frame(0.0, ball=ball, velocity=velocity, ours=ours))
        policy.tick(frame(1.0, ball=ball, velocity=velocity, ours=ours))
        self.assertEqual(policy.phase, 'pass_1')
        self.assertEqual(policy.passes, 0)

    def test_wrong_direction_does_not_count_as_a_pass(self):
        policy = self._armed_pass(True)
        ours = {1: robot(1500, 550, policy.kick_aim), 2: robot(3200, 1300)}
        policy.tick(frame(0.0, ball=(1585, 950), velocity=(0, 2500), ours=ours))
        policy.tick(frame(1.0, ball=(1585, 1400), velocity=(0, 2500), ours=ours))
        self.assertEqual(policy.phase, 'pass_1')

    def test_fast_ball_beside_receiver_is_not_a_catch(self):
        policy = TwoPlayerPolicy()
        policy.phase = 'receive_1'
        policy.role1, policy.role2 = 1, 2
        policy.entered = 0.0
        policy.kick_peaks = [1.0]
        ball = (3150, 1250)
        ours = {1: robot(1500, 550), 2: robot(3200, 1300, face((3200, 1300), ball))}
        policy.tick(frame(0.2, ball=ball, velocity=(0, -2500), ours=ours))
        policy.tick(frame(1.0, ball=ball, velocity=(0, -2500), ours=ours))
        self.assertEqual(policy.phase, 'receive_1')

    def test_penalty_entry_stops_both(self):
        policy = TwoPlayerPolicy()
        policy.phase = 'get_ball'
        policy.role1, policy.role2 = 1, 2
        policy.entered = 0.0
        actions = policy.tick(frame(0.2, ours={1: robot(4000, 0), 2: robot(2200, -850)}))
        self.assertEqual(policy.phase, 'fault')
        self.assertTrue(all(action.kind == 'stop' for action in actions.values()))

    def test_receive_target_stays_outside_penalty(self):
        policy = TwoPlayerPolicy()
        policy.phase = 'receive_1'
        policy.role1, policy.role2 = 1, 2
        policy.entered = 0.0
        actions = policy.tick(frame(
            0.2, ball=(3300, 200), velocity=(3000, 0),
            ours={1: robot(1500, 550), 2: robot(3200, 1300)}))
        self.assertLessEqual(actions[2].pos[0], policy.limit_x)
        self.assertFalse(policy.inside(actions[2].pos))

    def test_shot_setup_goes_around_the_ball(self):
        policy = TwoPlayerPolicy()
        policy.phase = 'shoot'
        policy.role1, policy.role2 = 1, 2
        policy.entered = 0.0
        policy.hold[2] = (2959, 1232)
        ball = (2938, 1120)
        ours = {
            1: robot(3190, -1290),
            2: robot(2957, 1228, face((2957, 1228), ball), infrared=True),
        }
        actions = policy.tick(frame(0.2, ball=ball, ours=ours))
        point = actions[2].pos
        self.assertFalse(policy._path_hits((2957, 1228), point, ball, 130))
        self.assertFalse(actions[2].dribble)
        self.assertGreater(hypot(point[0] - policy.pass_anchor[0], point[1] - policy.pass_anchor[1]), 100)

    def test_open_side_is_away_from_the_keeper(self):
        policy = TwoPlayerPolicy()
        self.assertGreater(policy.open_goal(frame(enemies={0: robot(4250, -400)}))[1], 0)
        self.assertLess(policy.open_goal(frame(enemies={0: robot(4250, 400)}))[1], 0)

    def _armed_pass(self, armed):
        policy = TwoPlayerPolicy()
        policy.phase = 'pass_1'
        policy.role1, policy.role2 = 1, 2
        policy.hold[1] = (1500, 550)
        policy.entered = 0.0
        if armed:
            policy.kick_armed = True
            policy.kick_origin = (1585, 550)
            policy.kick_aim = direction(policy.kick_origin, (3200, 1300))
        return policy


class SimulationTests(unittest.TestCase):
    def test_three_passes_then_role_two_scores_from_several_starts(self):
        cases = [
            ((1800, 550), {1: (1500, 550), 2: (2200, -850)}, 1),
            ((1800, 550), {1: (2200, -850), 2: (1500, 550)}, 2),
            ((1200, -400), {1: (900, -200), 2: (2100, 700)}, 1),
            ((2300, -200), {1: (1800, 900), 2: (2000, -350)}, 2),
        ]
        for ball, robots, expected_role1 in cases:
            with self.subTest(ball=ball, robots=robots):
                policy = simulate(ball, robots)
                self.assertEqual(policy.phase, 'done', policy.reason)
                self.assertEqual(policy.passes, 3)
                self.assertEqual(policy.role1, expected_role1)
                self.assertEqual(policy.shooter_id, policy.role2)
                self.assertEqual(policy.shooter_id, 3 - expected_role1)
                self.assertEqual(len(policy.pass_shifts), 3)
                self.assertTrue(all(shift < DRIBBLE_LIMIT for shift in policy.pass_shifts))
                self.assertLess(policy.shot_shift, DRIBBLE_LIMIT)
                self.assertLessEqual(policy.peak_m_s, 6.0)

    def test_pass_command_stays_on_the_hold_point(self):
        seen = []

        def watch(policy, actions):
            if policy.phase not in ('pass_1', 'pass_2', 'pass_3', 'shoot'):
                return
            passer = policy.role2 if policy.phase in ('pass_2', 'shoot') else policy.role1
            action = actions[passer]
            if action.power is None:
                return
            seen.append((policy.phase, action.pos, policy.hold[passer], action.power, action.dribble))

        simulate((1800, 550), {1: (1500, 550), 2: (2200, -850)}, watch)
        self.assertGreaterEqual(len({phase for phase, *_ in seen}), 4)
        for phase, pos, hold, power, dribble in seen:
            self.assertLess(hypot(pos[0] - hold[0], pos[1] - hold[1]), 1.0)
            expected = SHOT_POWER if phase == 'shoot' else PASS_POWER
            self.assertEqual(power, expected)
            self.assertTrue(dribble)
            self.assertGreater(distance_from_support(phase, pos), 800)


def simulate(ball, robots, watch=None):
    policy = TwoPlayerPolicy()
    state = {
        'ball': ball,
        'velocity': (0.0, 0.0),
        'robots': {n: robot(*pos) for n, pos in robots.items()},
        'cooldown': {},
        'infrared': {1: False, 2: False},
    }
    dt = 0.05
    phases = []
    for step in range(900):
        now = step * dt
        ours = {}
        for n, item in state['robots'].items():
            ours[n] = robot(item.x, item.y, item.angle, state['infrared'][n], item.speed)
        current = frame(now, state['ball'], state['velocity'], ours)
        actions = policy.tick(current)
        phases.append(policy.phase)
        if watch:
            watch(policy, actions)
        if policy.phase in ('done', 'fault'):
            break
        _apply(state, actions, policy, now, dt)
    else:
        policy.fail('simulation did not finish: ' + '>'.join(_compact(phases)))
    if policy.phase == 'fault' and 'simulation did not finish' not in policy.reason:
        policy.reason += ' path=' + '>'.join(_compact(phases))
    return policy


def _compact(phases):
    result = []
    for phase in phases:
        if not result or result[-1] != phase:
            result.append(phase)
    return result


def _apply(state, actions, policy, now, dt):
    launched = set()
    for n, action in actions.items():
        if action.kind == 'stop' or action.power is None:
            continue
        if hypot(state['robots'][n].x - state['ball'][0], state['robots'][n].y - state['ball'][1]) > 130:
            continue
        aim = action.angle
        speed = 3500.0
        state['velocity'] = (cos(aim) * speed, sin(aim) * speed)
        state['ball'] = (state['robots'][n].x + cos(aim) * 110, state['robots'][n].y + sin(aim) * 110)
        state['infrared'][n] = False
        state['cooldown'][n] = now + 0.45
        launched.add(n)
    for n, action in actions.items():
        item = state['robots'][n]
        if action.kind == 'stop':
            state['robots'][n] = robot(item.x, item.y, item.angle, speed=0)
            continue
        turn = _step_angle(item.angle, action.angle, 4.5 * dt)
        x, y, speed = _step_pos(item.x, item.y, action.pos, 2200 * dt)
        state['robots'][n] = robot(x, y, turn, speed=speed / dt)
    state['ball'] = (state['ball'][0] + state['velocity'][0] * dt, state['ball'][1] + state['velocity'][1] * dt)
    for n, action in actions.items():
        if n in launched or action.kind != 'rush' or not action.dribble or state['cooldown'].get(n, 0) > now:
            continue
        item = state['robots'][n]
        gap = hypot(item.x - state['ball'][0], item.y - state['ball'][1])
        if gap > 230:
            state['infrared'][n] = False
            continue
        state['velocity'] = (0.0, 0.0)
        state['ball'] = (item.x + cos(item.angle) * 95, item.y + sin(item.angle) * 95)
        state['infrared'][n] = True


def _step_angle(current, target, limit):
    error = (target - current + 3.1415926535) % (2 * 3.1415926535) - 3.1415926535
    if abs(error) <= limit:
        return target
    return current + limit * (1 if error > 0 else -1)


def _step_pos(x, y, target, limit):
    dx, dy = target[0] - x, target[1] - y
    gap = hypot(dx, dy)
    if gap <= limit:
        return target[0], target[1], 0.0
    return x + dx / gap * limit, y + dy / gap * limit, limit


class CommandShapeTests(unittest.TestCase):
    def test_support_runs_dodge_without_dribble_and_holder_turns_in_place(self):
        policy = TwoPlayerPolicy()
        policy.phase = 'wait_upper'
        policy.role1, policy.role2 = 1, 2
        policy.entered = 0.0
        ball = (1590, 540)
        ours = {
            1: robot(1500, 540, face((1500, 540), ball), infrared=True),
            2: robot(2000, 0),
        }
        actions = policy.tick(frame(0.0, ball=ball, ours=ours))
        self.assertEqual(actions[1].kind, 'rush')
        self.assertTrue(actions[1].dribble)
        self.assertFalse(actions[1].dodge)
        self.assertLess(hypot(actions[1].pos[0] - 1500, actions[1].pos[1] - 540), 1)
        self.assertFalse(actions[2].dribble)
        self.assertTrue(actions[2].dodge)
        self.assertEqual(actions[2].pos, policy.upper)
        self.assertLess(angle_error(actions[1].angle, ours[1].angle), 1e-6)


if __name__ == '__main__':
    unittest.main()
