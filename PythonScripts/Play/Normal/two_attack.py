"""Two robots, five states: flat pass, chip return, touch shot, rebound, done.

Distances mm; times seconds. Hardware possession comes from infrared.
Uncalibrated/unobservable chip returns explicitly fall back to a flat pass.
"""
import json
import math
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import CppPackage as C
import Global
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import Task, State, StateMachine, declare_state_machine
from Vision import Ball, Player, Enemy, vision
from WorldModel import Params, Flags, kickStatus, ballStatus
from WorldModel.PowerCalculator import evalPower, P
from PowerCurveBackend import curve_snapshot
from Play.Normal import AttackParams as A
from Play.Normal.AttackFeedback import (
    ChipFeedback, chip_feedback, chip_reason, curve_fingerprint,
    finite, load_calibration, optional,
)
from Play.Normal.AttackGeometry import (
    angle_error, behind, choose_corner_shot, crossed_goal, direction,
    distance, goal_ray, intercept_contact, return_plan, static_clearance,
)

mainshoot, assistant = 0, 1
NUMBERS = (mainshoot, assistant)
PENALTY_FRONT_X = Params.pitchLength / 2 - Params.penaltyDepth
ASSISTANT_POS = (PENALTY_FRONT_X - A.ASSISTANT_FRONT_CLEARANCE, A.ASSISTANT_SIDE_OFFSET)
SHOT_CONTACT = (PENALTY_FRONT_X - A.SHOT_CONTACT_CLEARANCE, A.SHOT_SIDE_OFFSET)


def xy(p):
    return p.x(), p.y()


def point(p):
    return CGeoPoint(*p)


def legal(p):
    margin = Params.playerRadius + A.BOUNDARY_EXTRA
    return (finite(*p) and abs(p[0]) <= PENALTY_FRONT_X - margin
            and abs(p[1]) <= Params.pitchWidth / 2 - margin
            and not C.InTheirPenaltyArea(point(p), margin)
            and not C.InOurPenaltyArea(point(p), margin))


def ball_recoverable(p):
    return (abs(p[0]) <= PENALTY_FRONT_X - A.TOUCH_BALL_CLEARANCE
            and abs(p[1]) <= Params.pitchWidth / 2 - A.BALL_RADIUS - A.BOUNDARY_EXTRA)


def halt(number, keep_ball=False):
    kickStatus.setBothKick(number, 0, 0)
    C.setDribbleCommand(number, A.DRIBBLE_COMMAND if keep_ball else 0)
    C.makeItStop(number)


def stop(number):
    # A fixed safe match point avoids reading invalid vision even during matching.
    return Task((halt, lambda n: point((0, 0))), fixedNumber=number)


@dataclass(frozen=True)
class Robot:
    pos: tuple
    velocity: tuple
    heading: float
    omega: float


class Control:
    def __init__(self, clock=time.monotonic, calibration=None):
        self.clock = clock
        self.environment = 'simulation' if Global.isSimulation else 'real'
        self.calibration = load_calibration(self.environment) if calibration is None else calibration
        self.offsets = {}
        offsets = self.calibration.get('mouth_offsets_mm', {})
        for n in NUMBERS:
            value = offsets.get(str(n)) if isinstance(offsets, dict) else None
            self.offsets[n] = value if finite(value) and 0 < value < 2 * Params.playerRadius else Params.playerFrontToCenter + A.BALL_RADIUS
        self.valid = False
        self.now = 0.
        self.cycle = self.last_time = None
        self.epoch = 0
        self.robots = {}
        self.ball = self.velocity = None
        self.feedback = ChipFeedback()
        self.infrared = dict.fromkeys(NUMBERS)
        self.held = dict.fromkeys(NUMBERS, False)
        self.since = dict.fromkeys(NUMBERS)
        self.carry = dict.fromkeys(NUMBERS, 0.)
        self.previous_robots = {}
        self.previous_ball = None
        self.previous_grounded = False
        self.outcome = None
        self.plan = None
        self.plan_locked = False
        self.shot_target = None
        self.chip_pending = False
        self.airborne_seen = False
        self.ground_since = None
        self.grounded = False
        self.chip_started = None
        self.landing_sample = None
        self.contact_recorded = False
        self.fallback_reason = None
        self.telemetry = os.environ.get('SRC_TWO_ATTACK_TELEMETRY')

    def record(self, kind, **data):
        def clean(value):
            if isinstance(value, dict):
                return {key: clean(item) for key, item in value.items()}
            if isinstance(value, (list, tuple)):
                return [clean(item) for item in value]
            if value is None or isinstance(value, (str, bool)) or finite(value):
                return value
            return None
        row = clean(dict(type=kind, time=self.now, environment=self.environment, **data))
        if kind != 'frame':
            print('TWO_ATTACK: ' + json.dumps(row, allow_nan=False), flush=True)
        if self.telemetry:
            try:
                with Path(self.telemetry).open('a', encoding='utf-8') as stream:
                    stream.write(json.dumps(row, allow_nan=False) + '\n')
            except OSError as exc:
                print(f'TWO_ATTACK: telemetry disabled: {exc}', flush=True)
                self.telemetry = None

    def mouth(self, n):
        r = self.robots[n]
        return behind(r.pos, r.heading, -self.offsets[n])

    def contact(self, n):
        r = self.robots[n]
        dx, dy = self.ball[0] - r.pos[0], self.ball[1] - r.pos[1]
        forward = dx * math.cos(r.heading) + dy * math.sin(r.heading)
        lateral = -dx * math.sin(r.heading) + dy * math.cos(r.heading)
        return (abs(forward - self.offsets[n]) <= A.CONTACT_TOLERANCE
                and abs(lateral) <= A.CONTACT_TOLERANCE)

    def relative_speed(self, n):
        r, offset = self.robots[n], self.offsets[n]
        return math.hypot(self.velocity[0] - r.velocity[0] + r.omega * offset * math.sin(r.heading),
                          self.velocity[1] - r.velocity[1] - r.omega * offset * math.cos(r.heading))

    def invalidate(self):
        self.valid = False
        self.epoch += 1
        self.held = dict.fromkeys(NUMBERS, False)
        self.since = dict.fromkeys(NUMBERS)
        self.previous_robots = {}
        self.previous_ball = None
        self.previous_grounded = False
        self.ground_since = None
        if self.telemetry:
            self.record('frame', valid=False, cycle=self.cycle, epoch=self.epoch)

    def pause(self):
        for n in NUMBERS:
            halt(n, keep_ball=self.environment == 'real' and self.infrared[n] is True)

    def update(self):
        self.now = self.clock()
        cycle = vision.getCycle()
        # Repeated frames and long gaps never count as continuing observations.
        gap = self.last_time is not None and not 0 <= self.now - self.last_time <= A.MAX_FRAME_GAP
        duplicate = cycle == self.cycle
        self.last_time, self.cycle = self.now, cycle
        self.infrared = dict.fromkeys(NUMBERS)
        if self.environment == 'real':
            for n in NUMBERS:
                value = optional(lambda: Player.isInfraredOn(n)) if Player.isValid(n) else None
                self.infrared[n] = value if isinstance(value, bool) else None
        if gap:
            self.invalidate()
        if (duplicate or not Ball.valid() or not all(Player.isValid(n) for n in NUMBERS)
                or (self.environment == 'real' and any(v is None for v in self.infrared.values()))):
            self.invalidate()
            return
        robots = {n: Robot(xy(Player.Pos(n)), xy(Player.vel(n)), Player.direction(n), Player.rotVel(n)) for n in NUMBERS}
        ball, velocity = xy(Ball.pos()), xy(Ball.vel())
        values = (*ball, *velocity, *(v for r in robots.values() for v in (*r.pos, *r.velocity, r.heading, r.omega)))
        if (not finite(*values) or abs(ball[0]) > Params.pitchLength or abs(ball[1]) > Params.pitchWidth
                or any(abs(r.pos[0]) > Params.pitchLength or abs(r.pos[1]) > Params.pitchWidth
                       or abs(r.heading) > math.tau for r in robots.values())):
            self.invalidate()
            return
        self.valid, self.robots, self.ball, self.velocity = True, robots, ball, velocity
        self.feedback = chip_feedback(Ball, ball)
        self.update_ground()
        if self.outcome is None:
            if (self.grounded and self.previous_grounded
                    and crossed_goal(self.previous_ball, ball, Params.pitchLength / 2, Params.goalWidth)):
                self.outcome = 'goal'
            elif abs(ball[0]) > Params.pitchLength / 2 + A.BALL_RADIUS or abs(ball[1]) > Params.pitchWidth / 2 + A.BALL_RADIUS:
                self.outcome = 'out'
            if self.outcome:
                self.record('outcome', outcome=self.outcome)
        for n, r in robots.items():
            was_held = self.held[n]
            near = distance(r.pos, ball) <= 2 * Params.playerRadius + A.BALL_RADIUS
            in_front = ((ball[0] - r.pos[0]) * math.cos(r.heading)
                        + (ball[1] - r.pos[1]) * math.sin(r.heading)) > 0
            signal = (self.infrared[n] is True and near and in_front if self.environment == 'real'
                      else self.contact(n) and self.relative_speed(n) <= A.CAPTURE_STABLE_SPEED)
            signal = signal and self.grounded
            self.since[n] = (self.now if self.since[n] is None else self.since[n]) if signal else None
            self.held[n] = self.since[n] is not None and self.now - self.since[n] >= A.POSSESSION_SECONDS
            if distance(r.pos, ball) > A.CARRY_RESET_DISTANCE and self.infrared[n] is not True:
                self.carry[n] = 0.
            elif was_held and self.held[n] and n in self.previous_robots:
                self.carry[n] += distance(r.pos, self.previous_robots[n])
        self.previous_robots = {n: r.pos for n, r in robots.items()}
        self.previous_ball, self.previous_grounded = ball, self.grounded
        if self.telemetry:
            sensors = {}
            if self.environment == 'real':
                for n in NUMBERS:
                    sensors[n] = dict(on=self.infrared[n],
                        on_count=optional(lambda: Player.infraredCount(n)),
                        off_count=optional(lambda: Player.infraredOffCount(n)),
                        kicked_vision=optional(lambda: Player.kickBallVision(n)),
                        kicked_out=optional(lambda: ballStatus.IsBallKickedOut(n)),
                        possession=optional(lambda: ballStatus.getBallPossession(True, n)))
            self.record('frame', valid=True, cycle=cycle, ball=ball, velocity=velocity,
                        feedback=asdict(self.feedback), held=self.held, sensors=sensors)

    def update_ground(self):
        if self.feedback.flying:
            self.airborne_seen = True
        # A lost kick packet must not leave us waiting forever for a flight that
        # never happened. Retry only with fresh evidence the ball is still held.
        sender_has_ball = (self.contact(assistant) and not self.feedback.flying
            and (self.infrared[assistant] is True if self.environment == 'real'
                 else self.feedback.ground and self.relative_speed(assistant) <= A.CAPTURE_STABLE_SPEED))
        if (self.chip_pending and not self.airborne_seen and self.chip_started is not None
                and self.now - self.chip_started > A.KICK_RETRY_SECONDS and sender_has_ball):
            self.record('chip_aborted', reason='ball_still_at_sender')
            self.chip_pending = self.plan_locked = False
            self.chip_started = None
        awaiting = self.chip_pending or self.airborne_seen
        self.grounded = not awaiting and not self.feedback.flying
        # A real mouth sensor may confirm contact when the optional height feed fails.
        infrared_contact = (self.environment == 'real' and self.infrared[mainshoot] is True
                            and self.contact(mainshoot) and not self.feedback.flying)
        if awaiting:
            low = self.feedback.ground and self.airborne_seen
            self.ground_since = (self.now if self.ground_since is None else self.ground_since) if low else None
            self.grounded = infrared_contact or (self.ground_since is not None
                and self.now - self.ground_since >= A.POSSESSION_SECONDS)
            if low and self.chip_started is not None and self.landing_sample is None:
                self.landing_sample = self.ball
                self.record('chip_landing_observed', ball=self.ball,
                    landing_error_mm=distance(self.ball, self.plan.landing),
                    flight_seconds=self.now - self.chip_started, velocity=self.velocity)
            if self.grounded:
                self.chip_pending = self.airborne_seen = False
                self.ground_since = None

    def allowed(self, n):
        return self.valid and self.outcome is None and self.carry[n] < A.CARRY_LIMIT

    def begin_chip(self):
        self.chip_pending = True
        self.airborne_seen = False
        self.grounded = False
        self.chip_started = self.now
        self.landing_sample = None
        self.contact_recorded = False
        self.record('chip_start', source=self.ball, plan=asdict(self.plan),
                    curve_fingerprint=self.calibration.get('chip', {}).get('curve_fingerprint'))

    def record_contact(self):
        if self.chip_started is not None and not self.contact_recorded:
            self.record('chip_contact', ball=self.ball, velocity=self.velocity,
                speed=math.hypot(*self.velocity),
                after_landing_mm=distance(self.landing_sample, self.ball) if self.landing_sample else None)
            self.contact_recorded = True


def keeper():
    if Enemy.valid(0):
        p = xy(Enemy.pos(0))
        if finite(*p):
            return p
    return None


def lane_clear(control, target):
    p = keeper()
    return p is None or static_clearance(control.ball, target, p, Params.playerRadius) > A.BALL_RADIUS


def movement_bounds(control, n):
    vx, vy = control.robots[n].velocity
    margin = Params.playerRadius + A.BOUNDARY_EXTRA
    x, y = PENALTY_FRONT_X - margin, Params.pitchWidth / 2 - margin
    def reserve(v):
        return max(0, v) * A.COMMAND_DELAY + max(0, v) ** 2 / (2 * A.BRAKE_ACCEL)
    return -x + reserve(-vx), x - reserve(vx), -y + reserve(-vy), y - reserve(vy)


def move_to(number, target, control, angle=None, fetching=False):
    if not control.allowed(number):
        return stop(number)
    r = control.robots[number]
    left, right, bottom, top = movement_bounds(control, number)
    if left > right or bottom > top or not finite(*target):
        return stop(number)
    destination = (max(left, min(right, target[0])), max(bottom, min(top, target[1])))
    if not legal(destination):
        return stop(number)
    angle = direction(r.pos, control.ball) if angle is None else angle
    if not finite(angle):
        return stop(number)
    if fetching:
        toward = direction(r.pos, control.ball)
        approach = max(0, r.velocity[0] * math.cos(toward) + r.velocity[1] * math.sin(toward))
        braking = approach * A.COMMAND_DELAY + approach ** 2 / (2 * A.BRAKE_ACCEL)
        if (distance(r.pos, control.ball) <= A.APPROACH_DISTANCE + braking
                and (angle_error(r.heading, angle) > A.ALIGN_ANGLE or approach > A.APPROACH_SPEED)):
            destination = r.pos
    if not legal(destination):
        return stop(number)
    def execute(n):
        if not control.allowed(n):
            halt(n)
            return
        kickStatus.setBothKick(n, 0, 0)
        C.setDribbleCommand(n, A.DRIBBLE_COMMAND)
        if fetching:
            C.TaskMediator.Instance().registerRole(n, 'fetchBall')
        flags = Flags.allow_dss
        if not fetching:
            flags |= Flags.dodge_ball
        C.makeItRushTo(n, point(destination), angle, flag=flags,
                       maxAcc=A.MAX_ACCEL, needDribble=True, vel=C.CVector(0, 0))
    task = Task((execute, lambda n: point(destination)), fixedNumber=number)
    task.safe_motion = True
    return task


def receive(number, control, heading=None):
    if not control.allowed(number) or not control.grounded:
        return stop(number)
    r = control.robots[number]
    if control.held[number]:
        return move_to(number, r.pos, control, r.heading, fetching=True)
    contact = intercept_contact(control.ball, control.velocity, control.mouth(number))
    if not ball_recoverable(contact):
        return stop(number)
    if heading is None:
        heading = direction((0, 0), tuple(-v for v in control.velocity)) if math.hypot(*control.velocity) > A.MOVING_SPEED else direction(r.pos, contact)
    return move_to(number, behind(contact, heading, control.offsets[number]), control, heading, fetching=True)


def choose_target(control, contact):
    return choose_corner_shot(contact, Params.pitchLength / 2, Params.goalWidth, keeper())


def prepare_return(control):
    if control.plan_locked:
        return control.plan
    goal = control.plan.goal if control.plan else choose_target(control, SHOT_CONTACT)
    flat = return_plan(control.ball, SHOT_CONTACT, goal, control.offsets[mainshoot])
    chip = control.calibration.get('chip', {})
    lead = chip.get('landing_lead_mm') if isinstance(chip, dict) else None
    candidate = None
    if finite(lead) and 0 < lead < distance(control.ball, SHOT_CONTACT):
        candidate = return_plan(control.ball, SHOT_CONTACT, goal, control.offsets[mainshoot], lead)
    fingerprint = optional(lambda: curve_fingerprint(curve_snapshot(), Global.powerMax))
    reason = chip_reason(control.calibration, fingerprint,
                         distance(control.ball, candidate.landing) if candidate else 0,
                         control.feedback.ground)
    if reason is None and (candidate is None or not ball_recoverable(candidate.landing)
                           or not ball_recoverable(candidate.contact) or not legal(candidate.centre)):
        reason = 'chip_illegal_landing'
    if reason != control.fallback_reason:
        control.record('return_mode', reason=reason, is_chip=reason is None)
        control.fallback_reason = reason
    control.plan = flat if reason else candidate
    return control.plan


def ready_at(control, n, target, heading):
    r = control.robots[n]
    return (control.allowed(n) and legal(r.pos) and legal(target) and distance(r.pos, target) <= A.READY_DISTANCE
            and angle_error(r.heading, heading) <= A.ALIGN_ANGLE
            and math.hypot(*r.velocity) <= A.APPROACH_SPEED
            and abs(r.omega) * A.COMMAND_DELAY <= A.KICK_ANGLE)


def touch_ready(control, n, target):
    r = control.robots[n]
    aim = direction(control.ball, target)
    lateral = abs(-control.velocity[0] * math.sin(aim) + control.velocity[1] * math.cos(aim))
    longitudinal = control.velocity[0] * math.cos(aim) + control.velocity[1] * math.sin(aim)
    # Without a calibrated redirect model only accept almost head-on/slow arrivals.
    return (control.grounded and control.contact(n)
            and lateral <= A.CAPTURE_STABLE_SPEED and longitudinal <= A.MOVING_SPEED
            and abs(longitudinal) * A.COMMAND_DELAY <= 2 * A.CONTACT_TOLERANCE
            and math.hypot(*r.velocity) <= A.APPROACH_SPEED
            and angle_error(r.heading, aim) + abs(r.omega) * A.COMMAND_DELAY <= A.KICK_ANGLE
            and goal_ray(control.ball, r.heading, Params.pitchLength / 2, Params.goalWidth))


def kick_to(number, target, state, level=P.HIGH, shooting=False, allow_kick=True, is_chip=False, touch=False):
    c = state.control
    if not c.allowed(number) or not c.grounded or not legal(c.robots[number].pos):
        return stop(number)
    if state.fired is not None:
        return stop(number)
    if not c.held[number] and not touch:
        return receive(number, c)
    r = c.robots[number]
    aim = direction(c.ball, target)
    centre = r.pos if touch or angle_error(r.heading, aim) > A.ALIGN_ANGLE else behind(c.ball, aim, c.offsets[number])
    movement = move_to(number, centre, c, aim, fetching=True)
    def execute(n):
        if not c.allowed(n) or not c.grounded:
            halt(n)
            return
        movement.skill_cpp(n)
        aligned = angle_error(r.heading, aim) + abs(r.omega) * A.COMMAND_DELAY <= A.KICK_ANGLE
        contact = c.contact(n) if c.environment == 'simulation' or touch else c.infrared[n] is True
        ready = (getattr(movement, 'safe_motion', False) and allow_kick and aligned and contact
                 and math.hypot(*r.velocity) <= A.APPROACH_SPEED
                 and (touch_ready(c, n, target) if touch else c.held[n]))
        if shooting:
            ready = ready and goal_ray(c.ball, r.heading, Params.pitchLength / 2, Params.goalWidth)
        if not ready or not c.allowed(n) or not lane_clear(c, target):
            return
        if is_chip:
            fingerprint = optional(lambda: curve_fingerprint(curve_snapshot(), Global.powerMax))
            if chip_reason(c.calibration, fingerprint, distance(c.ball, target), c.feedback.ground):
                return
        power = evalPower(point(c.ball), point(target), level, is_chip=is_chip)
        if finite(power) and power > 0:
            (kickStatus.setChipKick if is_chip else kickStatus.setKick)(n, power)
            state.fired, state.fired_at, state.fired_epoch = c.ball, c.now, c.epoch
            if isinstance(state, PassBack):
                c.plan_locked = True
            if is_chip:
                c.begin_chip()
            if shooting:
                c.record_contact()
            c.record('kick', robot=n, target=target, is_chip=is_chip, power=power)
    return Task((execute, lambda n: point(target)), fixedNumber=number)


class AttackState(State):
    def __init__(self):
        super().__init__()
        self.reset_attempt()

    def reset_attempt(self):
        self.fired = None
        self.fired_at = 0.
        self.fired_epoch = 0

    def run(self, isStateSwitched):
        c = self.control
        if c.outcome:
            for n in NUMBERS:
                halt(n)
            return 'Done'
        if not c.valid:
            c.pause()
            return ''
        if self.fired is not None and self.fired_epoch != c.epoch:
            # Re-establish the departure anchor after a gap; never infer a missed kick.
            self.fired, self.fired_at, self.fired_epoch = c.ball, c.now, c.epoch
        return super().run(isStateSwitched)

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''

    def released(self, number):
        c = self.control
        return (c.valid and self.fired is not None and self.fired_epoch == c.epoch
                and not c.contact(number)
                and distance(self.fired, c.ball) > 2 * A.BALL_RADIUS
                and distance(c.robots[number].pos, c.ball) > c.offsets[number] + 2 * A.CONTACT_TOLERANCE)

    def retry(self, number):
        if (self.fired is not None and self.control.now - self.fired_at > A.KICK_RETRY_SECONDS
                and not self.released(number) and not self.control.chip_pending):
            self.reset_attempt()
            self.control.plan_locked = False


class FirstPass(AttackState):
    def getTasks(self):
        c = self.control
        self.retry(mainshoot)
        receiver_heading = direction(c.robots[assistant].pos, c.ball)
        ready = ready_at(c, assistant, ASSISTANT_POS, receiver_heading)
        return {'A': kick_to(mainshoot, c.mouth(assistant), self, allow_kick=ready),
                'B': move_to(assistant, ASSISTANT_POS, c, receiver_heading)}

    def transFunction(self):
        return 'PassBack' if self.released(mainshoot) or self.control.held[assistant] else ''


class PassBack(AttackState):
    def getTasks(self):
        c = self.control
        self.retry(assistant)
        if c.chip_pending:
            return {'A': move_to(mainshoot, c.plan.centre, c, c.plan.heading), 'B': stop(assistant)}
        if distance(c.ball, SHOT_CONTACT) < 1 and not c.plan_locked:
            return {'A': receive(mainshoot, c), 'B': stop(assistant)}
        plan = prepare_return(c)
        ready = (ready_at(c, mainshoot, plan.centre, plan.heading)
                 and ball_recoverable(plan.landing) and ball_recoverable(plan.contact))
        return {'A': move_to(mainshoot, plan.centre, c, plan.heading),
                'B': kick_to(assistant, plan.landing, self, level=P.NORMAL,
                             allow_kick=ready, is_chip=plan.is_chip)}

    def transFunction(self):
        if self.released(assistant) or self.control.held[mainshoot]:
            self.control.shot_target = self.control.plan.goal if self.control.plan else None
            return 'Shoot'
        return ''


class Shoot(AttackState):
    def getTasks(self):
        c = self.control
        self.retry(mainshoot)
        if not c.grounded:
            waiting = move_to(mainshoot, c.plan.centre, c, c.plan.heading) if c.plan else stop(mainshoot)
            return {'A': waiting, 'B': stop(assistant)}
        if c.shot_target is None:
            c.shot_target = c.plan.goal if c.plan_locked and c.plan else choose_target(c, c.ball)
        if self.fired is not None:
            task = stop(mainshoot)
        elif c.held[mainshoot]:
            c.record_contact()
            task = kick_to(mainshoot, c.shot_target, self, shooting=True)
        elif touch_ready(c, mainshoot, c.shot_target):
            task = kick_to(mainshoot, c.shot_target, self, shooting=True, touch=True)
        else:
            # Align to the goal during gentle arrivals; catch fast lateral balls front-on.
            aim = direction(c.ball, c.shot_target)
            lateral = abs(-c.velocity[0] * math.sin(aim) + c.velocity[1] * math.cos(aim))
            task = receive(mainshoot, c, aim if lateral <= A.CAPTURE_STABLE_SPEED else None)
        return {'A': task, 'B': stop(assistant)}

    def transFunction(self):
        return 'FollowShot' if self.released(mainshoot) else ''


class FollowShot(AttackState):
    def getTasks(self):
        return {'A': stop(mainshoot), 'B': stop(assistant)}

    def transFunction(self):
        c = self.control
        if not c.grounded:
            return ''
        flying_to_goal = math.hypot(*c.velocity) > A.MOVING_SPEED and goal_ray(
            c.ball, direction((0, 0), c.velocity), Params.pitchLength / 2, Params.goalWidth)
        if flying_to_goal:
            return ''
        c.plan = c.shot_target = None
        c.plan_locked = False
        c.chip_started = None
        return 'PassBack' if distance(c.ball, (Params.pitchLength / 2, 0)) > A.REBOUND_SHOT_DISTANCE else 'Shoot'


class Done(AttackState):
    def getTasks(self):
        return {'A': stop(mainshoot), 'B': stop(assistant)}


@declare_state_machine(FirstPass, PassBack, Shoot, FollowShot, Done)
class two_attack(StateMachine):
    def __init__(self):
        super().__init__()
        self.control = Control()
        self.last_state = None

    def hookBeforePlanTasks(self):
        environment = 'simulation' if Global.isSimulation else 'real'
        if Global.isPlaySwitched or environment != self.control.environment:
            self.control = Control()
            self.current_state = self.start_state
            for state in self.states.values():
                state.reset_attempt()
            self.last_state = None
        self.control.update()
        for state in self.states.values():
            state.control = self.control
        active = self.start_state if Global.isPlaySwitched else self.current_state
        if active.state_name != self.last_state:
            active.reset_attempt()
            self.control.record('state', state=active.state_name)
            self.last_state = active.state_name
