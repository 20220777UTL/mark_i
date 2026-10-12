"""初赛双车决策。坐标毫米，朝 +x 进攻。1/2 是角色，不是车号。

球权固定为：1 拿球 → 传给上角的 2 → 2 回传给下角的 1 → 1 再传给上角的 2 → 2 射门。
换阶段只认到位、持球、出球、接球。计时只用于视觉去抖和超时失败，不能单独推进阶段。
"""
from dataclasses import dataclass
from math import atan2, cos, hypot, sin, pi

# Command ceilings, not ball speeds. PowerCalculator chooses the actual command;
# a real grSim/robot speed check is still required before competition.
PASS_POWER = 7000
SHOT_POWER = 12000
STAGE_TIMEOUT = 30.0
HOLD_STABLE = 0.15
RELEASE_STABLE = 0.10
BEHIND = 85.0
# 禁区线外再留的停位点余量。小场地对方禁区前缘在 x=3500。
CORNER_MARGIN = 300.0
SHIFT_LIMIT = 300.0
DRIBBLE_LIMIT = 450.0


@dataclass(frozen=True)
class Robot:
    x: float
    y: float
    angle: float = 0.0
    infrared: bool = False
    speed: float = 0.0

    @property
    def pos(self):
        return self.x, self.y


@dataclass(frozen=True)
class Frame:
    time: float
    ball: tuple
    velocity: tuple
    ours: dict
    enemies: dict
    valid: bool = True


@dataclass(frozen=True)
class Action:
    kind: str
    pos: tuple = (0.0, 0.0)
    angle: float = 0.0
    dodge: bool = False
    dribble: bool = False
    power: float | None = None
    kick_target: tuple | None = None


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def direction(a, b):
    return atan2(b[1] - a[1], b[0] - a[0])


def angle_error(a, b):
    return abs((a - b + pi) % (2 * pi) - pi)


class TwoPlayerPolicy:
    IDS = (1, 2)

    def __init__(self, half_length=4500, half_width=3000, penalty_depth=1000,
                 penalty_width=2000, goal_width=1000, ids=(1, 2)):
        if len(ids) != 2 or ids[0] == ids[1]:
            raise ValueError('exactly two distinct attacker IDs are required')
        self.IDS = tuple(ids)
        self.half_length = half_length
        self.goal_width = goal_width
        self.penalty_front = half_length - penalty_depth
        self.own_penalty_front = -self.penalty_front
        self.penalty_half_width = penalty_width / 2
        self.limit_x = self.penalty_front - 150
        self.limit_y = half_width - 200
        self.upper = (self.penalty_front - CORNER_MARGIN, self.penalty_half_width + CORNER_MARGIN)
        self.lower = (self.penalty_front - CORNER_MARGIN, -(self.penalty_half_width + CORNER_MARGIN))
        self.phase = 'assign'
        self.role1 = self.role2 = None
        self.entered = None
        self.stable_since = None
        self.reason = 'waiting for vision'
        self.hold = {}
        self.possession_shift = 0.0
        self.pass_shifts = []
        self.shot_shift = 0.0
        self.passes = 0
        self.kick_armed = False
        self.kick_origin = None
        self.kick_aim = None
        self.flight_peak = 0.0
        self.kick_peaks = []
        self.peak_m_s = 0.0
        self.previous_ball = None
        self.shooter_id = None
        self.shot_logged = False
        self.pass_anchor = None
        self.kick_pose = None
        self.anchor_fixes = 0
        self.setup_mm = []
        self.vision_bad_since = None
        self.carried_mm = {n: 0.0 for n in self.IDS}
        self.peak_carried_mm = {n: 0.0 for n in self.IDS}
        self.carrier_last_pos = {n: None for n in self.IDS}

    def tick(self, frame):
        self._note_speed(frame)
        if self.phase in ('done', 'fault'):
            return self._stops()
        if not frame.valid or any(n not in frame.ours for n in self.IDS):
            self.stable_since = None
            self.vision_bad_since = frame.time if self.vision_bad_since is None else self.vision_bad_since
            if self.phase != 'assign' and frame.time - self.vision_bad_since > STAGE_TIMEOUT:
                self.fail('vision unavailable')
            return self._stops()
        self.vision_bad_since = None
        self._track_carry(frame)
        if any(self.carried_mm[n] > 800 for n in self.IDS):
            self.fail('continuous dribble exceeded 800 mm safety budget')
            return self._stops()
        if self._robot_inside(frame) or self._robot_inside_own(frame):
            self.fail('attacker entered a penalty area')
            return self._stops()
        if ((self._ball_in_penalty(frame.ball) or self._ball_in_own_penalty(frame.ball))
                and any(distance(robot.pos, frame.ball) < 150
                        for robot in frame.ours.values())):
            self.fail('attacker too close to ball in a penalty area')
            return self._stops()
        if self.entered is None:
            self.entered = frame.time
        if (self.phase not in ('assign', 'shot_flight')
                and frame.time - self.entered > STAGE_TIMEOUT):
            self.fail('stage timed out')
            return self._stops()
        actions = self._dispatch(frame)
        if frame.valid:
            self.previous_ball = frame.ball
        if self.phase in ('done', 'fault'):
            return self._stops()
        return actions

    def fail(self, reason):
        self.phase = 'fault'
        self.reason = reason

    def _dispatch(self, frame):
        return {
            'assign': self._assign,
            'get_ball': self._get_ball,
            'wait_upper': self._wait_upper,
            'pass_1': lambda f: self._play_pass(f, self.role1, self.role2, 'receive_1'),
            'receive_1': lambda f: self._play_receive(f, self.role2, self.upper, 'run_lower'),
            'run_lower': self._run_lower,
            'pass_2': lambda f: self._play_pass(f, self.role2, self.role1, 'receive_2'),
            'receive_2': lambda f: self._play_receive(f, self.role1, self.lower, 'attract'),
            'attract': self._attract,
            'pass_3': lambda f: self._play_pass(f, self.role1, self.role2, 'receive_3'),
            'receive_3': lambda f: self._play_receive(f, self.role2, self.upper, 'shoot'),
            'shoot': self._shoot,
            'shot_flight': self._shot_flight,
        }[self.phase](frame)

    def _assign(self, frame):
        if self._ball_in_penalty(frame.ball) or self._ball_in_own_penalty(frame.ball):
            self.fail('placed ball is in a penalty area')
            return self._stops()
        # Roles are chosen only after the manually placed ball has settled.
        if self._stable(frame, hypot(*frame.velocity) < 120, HOLD_STABLE):
            self.role1, self.role2 = sorted(
                self.IDS, key=lambda n: (distance(frame.ours[n].pos, frame.ball), n))
            self._change('get_ball', frame.time, 'roles assigned by distance')
        return self._stops()

    def _get_ball(self, frame):
        one, two = self.role1, self.role2
        actions = {
            one: self._collect(frame, one, self.upper),
            two: self._go(frame, two, self.upper, dodge=True, dribble=False),
        }
        # Once the ball is secured, stop travelling with it. Alignment for the
        # pass belongs to pass_1, after the support player reaches the station.
        if self._stable(frame, self._secured(frame, one), HOLD_STABLE):
            self._freeze(frame, one)
            self._change('wait_upper', frame.time, 'role 1 has the ball')
        return actions

    def _wait_upper(self, frame):
        one, two = self.role1, self.role2
        actions = {
            one: self._stay(frame, one, self.upper),
            two: self._go(frame, two, self.upper, dodge=True, dribble=False),
        }
        self._watch_holder(frame, one, self.upper)
        if self.phase == 'fault':
            return actions
        if self._stable(frame, self._arrived(frame, two, self.upper) and self._secured(frame, one), HOLD_STABLE):
            self._change('pass_1', frame.time, 'role 2 arrived at the upper corner')
        return actions

    def _run_lower(self, frame):
        one, two = self.role1, self.role2
        actions = {
            one: self._go(frame, one, self.lower, dodge=True, dribble=False),
            two: self._stay(frame, two, self.lower),
        }
        self._watch_holder(frame, two, self.lower)
        if self.phase == 'fault':
            return actions
        if self._stable(frame, self._arrived(frame, one, self.lower) and self._secured(frame, two), HOLD_STABLE):
            self._change('pass_2', frame.time, 'role 1 arrived at the lower corner')
        return actions

    def _attract(self, frame):
        one, two = self.role1, self.role2
        actions = {
            one: self._stay(frame, one, self.upper),
            two: self._go(frame, two, self.upper, dodge=True, dribble=False),
        }
        self._watch_holder(frame, one, self.upper)
        if self.phase == 'fault':
            return actions
        if self._stable(frame, self._arrived(frame, two, self.upper) and self._secured(frame, one), HOLD_STABLE):
            self._change('pass_3', frame.time, 'role 2 ready at the upper corner')
        return actions

    def _play_pass(self, frame, passer, receiver, nxt):
        station = self.upper if receiver == self.role2 else self.lower
        released = self._released(frame, passer)
        ball_in_flight = self.kick_armed and hypot(*frame.velocity) > 280
        actions = {
            passer: self._kick_or_hold(frame, passer, frame.ours[receiver].pos, PASS_POWER, released),
            # Hold the corner until the pass is actually kicked. Otherwise the
            # receiver heads toward the stationary ball while the passer aims.
            receiver: (self._receive_action(frame, receiver, station)
                       if ball_in_flight else self._go(frame, receiver, station,
                                                       dodge=True, dribble=False)),
        }
        self._watch_holder(frame, passer, frame.ours[receiver].pos)
        if self.phase == 'fault':
            return actions
        if self._stable(frame, released, RELEASE_STABLE):
            self._clear_carry(passer)
            self.pass_shifts.append(round(self.possession_shift, 1))
            self.passes += 1
            self.possession_shift = 0.0
            self._change(nxt, frame.time, f'pass {self.passes} left role {1 if passer == self.role1 else 2}')
        return actions

    def _play_receive(self, frame, receiver, station, nxt):
        other = self.role1 if receiver == self.role2 else self.role2
        actions = {
            receiver: self._receive_action(frame, receiver, station),
            other: self._idle(frame, other),
        }
        if self._stable(frame, self._secured(frame, receiver), HOLD_STABLE):
            self.kick_peaks.append(round(self.flight_peak, 3))
            self.flight_peak = 0.0
            self._freeze(frame, receiver, overwrite=True)
            role = 1 if receiver == self.role1 else 2
            self._change(nxt, frame.time, f'role {role} received the pass')
        return actions

    def _shoot(self, frame):
        shooter = self.role2
        target = self.open_goal(frame)
        released = self._released(frame, shooter)
        actions = {
            shooter: self._kick_or_hold(frame, shooter, target, SHOT_POWER, released),
            self.role1: self._go(frame, self.role1, self.lower, dodge=True, dribble=False),
        }
        self._watch_holder(frame, shooter, target)
        if self.phase == 'fault':
            return actions
        if self._stable(frame, released, RELEASE_STABLE):
            self._clear_carry(shooter)
            self.shot_shift = round(self.possession_shift, 1)
            self.shooter_id = shooter
            self._change('shot_flight', frame.time, 'role 2 shot')
        return actions

    def _shot_flight(self, frame):
        goal_x = self.half_length
        old = self.previous_ball
        if old is not None and old[0] < goal_x <= frame.ball[0] and frame.ball[0] != old[0]:
            y = old[1] + (frame.ball[1] - old[1]) * (goal_x - old[0]) / (frame.ball[0] - old[0])
            self._conclude_shot(abs(y) <= self.goal_width / 2 - 30,
                                'ball crossed goal line' if abs(y) <= self.goal_width / 2 - 30 else 'shot missed goal mouth')
        elif frame.ball[0] >= goal_x and abs(frame.ball[1]) <= self.goal_width / 2 - 30:
            self._conclude_shot(True, 'ball crossed goal line')
        elif hypot(*frame.velocity) < 200 and frame.time - self.entered > 1.0 and frame.ball[0] < goal_x - 150:
            self._conclude_shot(False, 'shot stopped before the goal line')
        elif frame.time - self.entered > STAGE_TIMEOUT:
            self._conclude_shot(False, 'goal not confirmed')
        return self._stops()

    def _kick_or_hold(self, frame, passer, target, power, released):
        robot = frame.ours[passer]
        aim_now = direction(frame.ball, target)
        # Rotation can push the ball out of the dribbler. Do not keep driving
        # toward an old hold point after that happens: reacquire from behind
        # the ball on the current passing line.
        if (self.kick_pose is not None and not self.kick_armed
                and not self.holding(frame, passer) and hypot(*frame.velocity) < 280):
            self.kick_pose = None
            self.hold.pop(passer, None)
            self.pass_anchor = self._anchor_point(frame.ball, target)
        face_ball = self._face_point(robot.pos, frame.ball, robot.angle)
        can_turn_here = (self.phase != 'shoot' or angle_error(face_ball, aim_now) < 0.55)
        if self.kick_pose is None and self.holding(frame, passer) and can_turn_here:
            # Passing is a stationary turn-and-kick. In particular, role 1 must
            # not carry the ball toward role 2 after role 2 reaches the corner.
            self.kick_pose = robot.pos
            self.hold[passer] = robot.pos
            self.possession_shift = 0.0
        if self.pass_anchor is None and not self.kick_armed:
            # 只算一次：站到球与目标连线的后方。之后目标点不再跟着球走。
            self.pass_anchor = self._anchor_point(frame.ball, target)
        anchor = self.hold.get(passer, self.pass_anchor or robot.pos)
        aim = self.kick_aim if self.kick_armed and self.kick_aim is not None else aim_now
        ball_left = self.kick_armed and hypot(*frame.velocity) > 400 and distance(frame.ball, robot.pos) > 130
        if released or ball_left:
            return self._rush(anchor, aim, dodge=False, dribble=False)
        if self.kick_pose is None:
            facing_ball = self._face_point(robot.pos, frame.ball, robot.angle)
            ball_front = distance(robot.pos, frame.ball) < 130 and angle_error(robot.angle, facing_ball) < 0.40
            # 球已经被碰到瞄准线外并停住时，按新的球位重算一次后方点。
            if (distance(robot.pos, self.pass_anchor) < 80 and robot.speed < 200
                    and hypot(*frame.velocity) < 120 and not ball_front and self.anchor_fixes < 2):
                self.anchor_fixes += 1
                self.pass_anchor = self._anchor_point(frame.ball, target)
            lined_up = distance(robot.pos, self.pass_anchor) < 70 and angle_error(robot.angle, aim_now) < 0.20
            if not (lined_up and ball_front and robot.speed < 300
                    and self.holding(frame, passer)):
                # 射门接球点常在球的侧面，直线贴上去会用车身把球碰离射门线。
                # 传球时接球人已经在目标线上，仍直接走到球后方。
                if self.phase == 'shoot':
                    point = self._safe_approach(robot.pos, self.pass_anchor, frame.ball)
                    return self._rush(point, aim_now, dodge=False, dribble=distance(point, self.pass_anchor) < 1)
                return self._rush(self.pass_anchor, aim_now, dodge=False, dribble=True)
            previous = self.hold.get(passer, robot.pos)
            self.setup_mm.append(round(distance(previous, robot.pos), 1))
            self.kick_pose = robot.pos
            self.hold[passer] = robot.pos
            self.possession_shift = 0.0
            anchor = robot.pos
        if not self.holding(frame, passer):
            return self._collect(frame, passer, target)
        aligned = angle_error(robot.angle, aim_now) < 0.12
        facing = angle_error(robot.angle, self._face_point(robot.pos, frame.ball, robot.angle)) < 0.35
        settled = robot.speed < 400 and self._toward(robot.pos, anchor, target) <= SHIFT_LIMIT
        ready = self._secured(frame, passer) and aligned and facing and settled
        if self.phase == 'shoot':
            # A stationary ball alongside the dribbler can make RushTo hunt
            # around its hold point indefinitely. A controlled, nearly aligned
            # shot is preferable to dragging it through another setup loop.
            ready = (self.holding(frame, passer) and robot.speed < 500
                     and angle_error(robot.angle, aim_now) < 0.10)
        if ready:
            if not self.kick_armed:
                self.kick_armed = True
                self.kick_origin = frame.ball
                self.kick_aim = aim_now
            return self._rush(anchor, self.kick_aim, dodge=False, dribble=True,
                              power=power, kick_target=target)
        return self._rush(anchor, aim_now, dodge=False, dribble=True)

    def _stay(self, frame, holder, teammate_or_point):
        if not self.holding(frame, holder):
            self.hold.pop(holder, None)
            return self._collect(frame, holder, teammate_or_point)
        self._freeze(frame, holder)
        if holder not in self.hold:
            return self._collect(frame, holder)
        return self._rush(self.hold[holder], frame.ours[holder].angle, dodge=False, dribble=True)

    def _idle(self, frame, n):
        stay = self.hold.get(n, frame.ours[n].pos)
        return self._rush(stay, self._face_point(frame.ours[n].pos, frame.ball, frame.ours[n].angle),
                          dodge=True, dribble=False)

    def _collect(self, frame, n, target=None):
        robot = frame.ours[n]
        face = self._face_point(robot.pos, frame.ball, robot.angle)
        if target is None:
            point = self._behind(frame.ball, face, BEHIND)
        else:
            point = self._anchor_point(frame.ball, target)
        return self._rush(point, face, dodge=False, dribble=True)

    def _anchor_point(self, ball, target):
        return self.clamp(self._behind(ball, direction(ball, target), BEHIND))

    def _safe_approach(self, robot, anchor, ball):
        if not self._path_hits(robot, anchor, ball, 130):
            return anchor
        ux, uy = self._unit(anchor, ball)
        px, py = -uy, ux
        lateral = (robot[0] - ball[0]) * px + (robot[1] - ball[1]) * py
        side = 1.0 if lateral >= 0 else -1.0
        for back in (120, 240, 360):
            for extra in (0, 220, 360):
                waypoint = self.clamp((anchor[0] - ux * back + side * px * extra,
                                       anchor[1] - uy * back + side * py * extra))
                # 绕行点本身要能再沿射门线贴上球，不能停在一个仍然会横穿的位置。
                if self._path_hits(robot, waypoint, ball, 130):
                    continue
                if self._path_hits(waypoint, anchor, ball, 130):
                    continue
                return waypoint
        return self.clamp((anchor[0] - ux * 360 + side * px * 360,
                           anchor[1] - uy * 360 + side * py * 360))

    def _path_hits(self, start, end, ball, gap):
        # 沿射门线从后方靠近是正常贴球。横穿时车身会先碰到球。
        abx, aby = end[0] - start[0], end[1] - start[1]
        length = hypot(abx, aby)
        if length < 30:
            return False
        if angle_error(atan2(aby, abx), direction(end, ball)) < 0.45:
            return False
        start_gap = hypot(start[0] - ball[0], start[1] - ball[1])
        steps = max(int(length / 20), 4)
        for i in range(1, steps):
            px = start[0] + abx * i / steps
            py = start[1] + aby * i / steps
            if hypot(px - end[0], py - end[1]) < 40:
                continue
            here = hypot(px - ball[0], py - ball[1])
            # 出发时已经贴着球。只有中途比现在更靠近，才算车身横穿。
            if here < gap and here < start_gap - 8:
                return True
        return False

    def _unit(self, origin, point):
        dx, dy = point[0] - origin[0], point[1] - origin[1]
        norm = hypot(dx, dy) or 1.0
        return dx / norm, dy / norm

    def _go(self, frame, n, point, dodge, dribble):
        return self._rush(point, self._face_point(frame.ours[n].pos, frame.ball, frame.ours[n].angle),
                          dodge=dodge, dribble=dribble)

    def _receive_action(self, frame, n, station):
        return self._rush(self._receive_point(frame, n, station),
                          self._face_point(frame.ours[n].pos, frame.ball, frame.ours[n].angle),
                          dodge=False, dribble=True)

    def _receive_point(self, frame, n, station):
        robot = frame.ours[n].pos
        speed = hypot(*frame.velocity)
        # 球已经进禁区就停在接应点，避免为了捡球冲进去。
        if self._ball_in_penalty(frame.ball) and speed < 400:
            return station
        if speed < 280:
            if self.kick_armed and self.kick_aim is not None:
                return self._along_aim(frame.ball, self.kick_aim, station)
            aim = self._face_point(robot, frame.ball, frame.ours[n].angle)
            return self.clamp(self._behind(frame.ball, aim, BEHIND))
        return self.clamp(self._along_velocity(frame.ball, frame.velocity, station))

    def _ball_in_penalty(self, ball):
        return ball[0] > self.penalty_front - 40 and abs(ball[1]) < self.penalty_half_width + 40

    def _ball_in_own_penalty(self, ball):
        return ball[0] < self.own_penalty_front + 40 and abs(ball[1]) < self.penalty_half_width + 40

    def _along_aim(self, ball, aim, station):
        return self.clamp(self._along_velocity(ball, (cos(aim) * 1000, sin(aim) * 1000), station))

    def _along_velocity(self, ball, vel, station):
        speed = hypot(*vel) or 1.0
        ux, uy = vel[0] / speed, vel[1] / speed
        dx, dy = station[0] - ball[0], station[1] - ball[1]
        travel = max(0.0, min(dx * ux + dy * uy, speed * 0.9))
        return ball[0] + ux * travel, ball[1] + uy * travel

    def open_goal(self, frame):
        # 门柱在 ±500。瞄准开角靠中的位置，避免贴着门柱被角度误差打出底线。
        # 守门员在中路或被下角的 1 吸引到负半区时，打上角露出的空当。
        opening = (self.goal_width / 2 - 40) * 0.65
        keeper = min(frame.enemies.values(),
                     key=lambda robot: distance(robot.pos, (self.half_length, 0)),
                     default=None)
        side = -1 if keeper is not None and keeper.y > 80 else 1
        return self.half_length, side * opening

    def _watch_holder(self, frame, holder, target):
        if self.pass_anchor is not None and self.kick_pose is None:
            return
        if holder not in self.hold or not self.holding(frame, holder):
            return
        if self.kick_armed and hypot(*frame.velocity) > 400:
            return
        pos = frame.ours[holder].pos
        self.possession_shift = max(self.possession_shift, distance(pos, self.hold[holder]))
        if self.possession_shift > DRIBBLE_LIMIT or self._toward(pos, self.hold[holder], target) > SHIFT_LIMIT:
            self.fail('passer moved toward the receiver before the kick')

    def _released(self, frame, passer):
        if not self.kick_armed or self.kick_origin is None or self.kick_aim is None:
            return False
        speed = hypot(*frame.velocity)
        if speed < 500:
            return False
        if angle_error(atan2(frame.velocity[1], frame.velocity[0]), self.kick_aim) > 0.35:
            return False
        if distance(frame.ball, self.kick_origin) < 150:
            return False
        if distance(frame.ball, frame.ours[passer].pos) < 180:
            return False
        return True

    def holding(self, frame, n):
        robot = frame.ours[n]
        if distance(robot.pos, frame.ball) >= 130:
            return False
        facing = angle_error(robot.angle, self._face_point(robot.pos, frame.ball, robot.angle)) < 0.35
        return (robot.infrared or facing) and hypot(*frame.velocity) < 800

    def _secured(self, frame, n):
        return self.holding(frame, n) and frame.ours[n].speed < 300

    def _arrived(self, frame, n, point):
        robot = frame.ours[n]
        return distance(robot.pos, point) < 160 and robot.speed < 250

    def _freeze(self, frame, n, overwrite=False):
        if n in self.hold and not overwrite:
            return
        pos = frame.ours[n].pos
        if self.inside(pos):
            self.fail('hold position is inside the opponent penalty area')
            return
        self.hold[n] = pos
        self.possession_shift = 0.0

    def _conclude_shot(self, scored, reason):
        if not self.shot_logged:
            self.kick_peaks.append(round(self.flight_peak, 3))
            self.flight_peak = 0.0
            self.shot_logged = True
        if scored:
            self.phase = 'done'
            self.reason = reason
        else:
            self.fail(reason)

    def _track_carry(self, frame):
        for n in self.IDS:
            if self.holding(frame, n):
                pos = frame.ours[n].pos
                old = self.carrier_last_pos[n]
                if old is not None:
                    self.carried_mm[n] += distance(old, pos)
                    self.peak_carried_mm[n] = max(self.peak_carried_mm[n],
                                                  self.carried_mm[n])
                self.carrier_last_pos[n] = pos
            elif distance(frame.ours[n].pos, frame.ball) > 250:
                self._clear_carry(n)

    def _clear_carry(self, n):
        self.carried_mm[n] = 0.0
        self.carrier_last_pos[n] = None

    def _robot_inside(self, frame):
        return any(self.inside(robot.pos) for robot in frame.ours.values())

    def _robot_inside_own(self, frame):
        return any(self.inside_own(robot.pos) for robot in frame.ours.values())

    def inside(self, point, margin=80):
        return point[0] > self.penalty_front - margin and abs(point[1]) < self.penalty_half_width + margin

    def inside_own(self, point, margin=80):
        return point[0] < self.own_penalty_front + margin and abs(point[1]) < self.penalty_half_width + margin

    def clamp(self, point):
        return (min(max(point[0], -self.limit_x), self.limit_x),
                min(max(point[1], -self.limit_y), self.limit_y))

    def _rush(self, pos, angle, dodge, dribble, power=None, kick_target=None):
        return Action('rush', self.clamp(pos), angle, dodge, dribble, power, kick_target)

    def _stops(self):
        return {n: Action('stop') for n in self.IDS}

    def _change(self, phase, now, reason):
        self.phase = phase
        self.entered = now
        self.reason = reason
        self.stable_since = None
        self.kick_armed = False
        self.kick_origin = None
        self.kick_aim = None
        self.pass_anchor = None
        self.kick_pose = None
        self.anchor_fixes = 0

    def _stable(self, frame, condition, seconds):
        if not condition:
            self.stable_since = None
            return False
        if self.stable_since is None:
            self.stable_since = frame.time
        return frame.time - self.stable_since >= seconds

    def _note_speed(self, frame):
        if not frame.valid:
            return
        speed = hypot(*frame.velocity) / 1000
        if self.kick_armed or self.passes or self.phase in ('shot_flight', 'receive_1', 'receive_2', 'receive_3'):
            self.flight_peak = max(self.flight_peak, speed)
            self.peak_m_s = max(self.peak_m_s, speed)

    def _behind(self, ball, angle, dist):
        return ball[0] - dist * cos(angle), ball[1] - dist * sin(angle)

    def _face_point(self, origin, point, fallback):
        if distance(origin, point) < 1:
            return fallback
        return direction(origin, point)

    def _toward(self, pos, origin, target):
        dx, dy = target[0] - origin[0], target[1] - origin[1]
        norm = hypot(dx, dy) or 1.0
        return (pos[0] - origin[0]) * dx / norm + (pos[1] - origin[1]) * dy / norm
