"""Pure decision logic, in millimetres/radians/seconds. No network or native calls.

Contact is estimated from vision/infrared, NOT an authoritative referee decision.
Every kick is conservatively treated as subject to a no-second-touch restriction.
"""
from dataclasses import dataclass, field
from math import atan2, cos, sin, hypot, pi

def distance(a, b):
    return hypot(a[0]-b[0], a[1]-b[1])

def direction(a, b):
    return atan2(b[1]-a[1], b[0]-a[0])

def angle_error(a, b):
    return abs((a-b+pi) % (2*pi)-pi)

def segment_clearance(p, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = max(0, min(1, ((p[0]-a[0])*dx+(p[1]-a[1])*dy)/max(1, dx*dx+dy*dy)))
    return distance(p, (a[0]+t*dx, a[1]+t*dy))

@dataclass
class Settings:
    attackers: tuple = (0, 1)
    half_length: float = 4500
    half_width: float = 3000
    penalty_depth: float = 1000
    penalty_half_width: float = 1000
    goal_half_width: float = 500
    robot_radius: float = 90
    support_width: float = 1500
    carry_limit: float = 800
    # Power is an uncalibrated actuator parameter, NOT ball speed.
    shot_power: float = 3800
    speed_trip: float = 6200
    kick_window: float = .12
    confirm_timeout: float = .65
    native_shoot_timeout: float = 2.0
    max_retries: int = 2

@dataclass
class Robot:
    pos: tuple
    heading: float = 0
    infrared: bool = False
    kicked: bool = False

@dataclass
class Frame:
    time: float
    ball: tuple
    velocity: tuple
    own: dict
    opponents: dict = field(default_factory=dict)
    valid: bool = True
    cycle: int | None = None

@dataclass
class Command:
    kind: str = 'stop'
    target: tuple | None = None
    heading: float = 0
    dribble: bool = False
    power: float = 0

@dataclass
class Plan:
    phase: str
    reason: str
    commands: dict
    striker: int | None = None
    supporter: int | None = None
    support_target: tuple | None = None
    aim: tuple | None = None
    carry_mm: float = 0
    speed_mm_s: float = 0
    locked: int | None = None

class Controller:
    def __init__(self, settings=None):
        self.cfg = settings or Settings()
        self.reset()

    def reset(self):
        """Start a new referee-authorized attack after a play change/restart."""
        self.striker = None
        self.aim = None
        self.side = None
        self.locked = None
        self.last_kick = -1e9
        self.contact_since = {}
        self.separated_since = {}
        self.carry = {}
        self.previous_pos = {}
        self.carry_blocked = set()
        self.aligned_since = None
        self.max_speed = 0
        self.speed_fault = False
        self.pending_shot = None
        self.shot_fault = False
        self.confirmed_shots = 0
        self.turn_owner = None
        self.cached_cycle = None
        self.cached_plan = None
        self.cached_time = 0
        self.retry_count = 0
        self.reposition = None
        self.fault_reason = ''

    def danger(self, p, extra=0):
        c = self.cfg
        return (abs(p[0]) >= c.half_length-c.penalty_depth-extra
                and abs(p[1]) <= c.penalty_half_width+extra)

    def legal_target(self, p):
        c = self.cfg
        margin = c.robot_radius+100
        x = max(-c.half_length+margin, min(c.half_length-margin, p[0]))
        y = max(-c.half_width+margin, min(c.half_width-margin, p[1]))
        if self.danger((x,y), margin):
            x = (1 if x >= 0 else -1)*(c.half_length-c.penalty_depth-margin-1)
        return (x,y)

    def touching(self, robot, ball):
        gap = distance(robot.pos, ball)
        return gap < 155 and (robot.infrared or angle_error(robot.heading, direction(robot.pos, ball)) < .55)

    def observe_contact(self, frame):
        for n, robot in frame.own.items():
            touching = frame.valid and self.touching(robot, frame.ball)
            if touching:
                self.separated_since.pop(n, None)
                if n in self.previous_pos:
                    self.carry[n] = self.carry.get(n, 0)+distance(robot.pos, self.previous_pos[n])
                if self.carry.get(n, 0) >= self.cfg.carry_limit:
                    self.carry_blocked.add(n)
                # Prefer a sustained near-mouth contact over proximity alone.
                confirmed = robot.infrared or distance(robot.pos, frame.ball) <= 105
                if confirmed:
                    self.contact_since.setdefault(n, frame.time)
                else:
                    self.contact_since.pop(n, None)
                if confirmed and self.locked is not None and n != self.locked and frame.time-self.contact_since[n] >= .08:
                    self.locked = None
            else:
                self.contact_since.pop(n, None)
                # A momentary lost detection must not reset the carry distance.
                if frame.valid and distance(robot.pos, frame.ball) > 280:
                    self.separated_since.setdefault(n, frame.time)
                    if frame.time-self.separated_since[n] >= .25:
                        self.carry[n] = 0
                        self.carry_blocked.discard(n)
                else:
                    self.separated_since.pop(n, None)
            self.previous_pos[n] = robot.pos

    def choose_aim(self, frame):
        c = self.cfg
        span = max(0, c.goal_half_width-150)
        candidates = [(c.half_length, -span), (c.half_length, span), (c.half_length, 0)]
        obstacles = [r.pos for r in frame.opponents.values()]
        def score(target):
            clearance = min((segment_clearance(p, frame.ball, target)-c.robot_radius-50
                             for p in obstacles), default=1000)
            return clearance
        best = max(candidates, key=score)
        # Keep the selected corner unless a clearly better lane appears before possession.
        if self.aim is None or score(best) > score(self.aim)+80:
            self.aim = best
        return self.aim

    def support_command(self, f, number, commands):
        """A no-touch restriction does not prevent retreating away from the ball."""
        if number is None or number not in f.own:
            return None
        c = self.cfg
        robot = f.own[number]
        if self.danger(robot.pos, c.robot_radius+30):
            return None
        if number in self.carry_blocked and number != self.locked:
            return None
        desired = self.legal_target((f.ball[0]-700, (self.side or -1)*c.support_width))
        if number == self.locked:
            gap = distance(robot.pos, f.ball)
            if gap < 1:
                return None
            ux, uy = (robot.pos[0]-f.ball[0])/gap, (robot.pos[1]-f.ball[1])/gap
            if gap < 450:
                # Retreat diagonally to clear the next shooter's approach corridor.
                px, py = -uy, ux
                if px*(desired[0]-robot.pos[0])+py*(desired[1]-robot.pos[1]) < 0:
                    px, py = -px, -py
                desired = self.legal_target((robot.pos[0]+300*ux+350*px,
                                             robot.pos[1]+300*uy+350*py))
            elif segment_clearance(f.ball, robot.pos, desired) < 300:
                # Take a lateral waypoint instead of cutting across the ball to the flank.
                sign = self.side or -1
                desired = self.legal_target((robot.pos[0]-sign*uy*450, robot.pos[1]+sign*ux*450))
            if distance(desired, f.ball) < min(gap,300):
                return None
            if segment_clearance(f.ball, robot.pos, desired) < min(gap,300)-1:
                return None
        commands[number] = Command('move', desired, direction(robot.pos, f.ball), False)
        return desired

    def step(self, f):
        # The native scheduler can call Python twice for one vision cycle.
        # Replay the same decision, including its kick, instead of advancing the FSM twice.
        if f.cycle is not None and f.cycle == self.cached_cycle:
            if f.time-self.cached_time > self.cfg.kick_window:
                return Plan('WAIT', 'stale vision cycle', {n: Command() for n in self.cfg.attackers},
                            striker=self.striker, locked=self.locked)
            return self.cached_plan
        plan = self._step(f)
        self.cached_cycle, self.cached_plan, self.cached_time = f.cycle, plan, f.time
        return plan

    def _step(self, f):
        c = self.cfg
        speed = hypot(*f.velocity) if f.valid else 0
        self.max_speed = max(self.max_speed, speed)
        self.speed_fault |= speed > c.speed_trip
        self.observe_contact(f)
        commands = {n: Command() for n in c.attackers}
        def result(phase, reason, support=None, target=None):
            return Plan(phase, reason, commands, self.striker, support, target, self.aim,
                        self.carry.get(self.striker, 0), speed, self.locked)
        if not f.valid:
            if self.pending_shot or self.reposition:
                self.shot_fault = True
                self.fault_reason = 'vision lost during attempt: reset round'
            return result('WAIT', 'ball not visible')
        if self.speed_fault:
            return result('WAIT', 'speed warning: reset round / check power')
        if self.shot_fault:
            return result('WAIT', self.fault_reason)
        if self.pending_shot is not None:
            attempt = self.pending_shot
            number = attempt['number']
            robot = f.own.get(number)
            moved = distance(f.ball, attempt['ball'])
            gap = distance(robot.pos, f.ball) if robot else 0
            age = f.time-attempt['time']
            attempt['max_moved'] = max(attempt['max_moved'], moved)
            attempt['peak'] = max(attempt['peak'], speed)
            attempt['feedback'] |= bool(robot and robot.kicked)
            if robot and gap < 155:
                attempt['contact_seen'] = True
            # Confirmation means observed ball departure, not an official valid goal.
            departed = robot is not None and attempt['contact_seen'] and moved >= 70 and gap >= 180
            if departed:
                self.locked = number
                self.last_kick = f.time
                self.confirmed_shots += 1
                self.turn_owner = next((n for n in c.attackers if n != number), None)
                self.striker = self.turn_owner
                self.aim = None
                self.aligned_since = None
                self.contact_since.clear()
                self.pending_shot = None
                self.retry_count = 0
            else:
                if (robot is None or abs(f.ball[0]) > c.half_length or abs(f.ball[1]) > c.half_width
                    or self.danger(f.ball, c.robot_radius+70)
                    or self.danger(robot.pos, c.robot_radius+30)
                    or number in self.carry_blocked):
                    self.shot_fault = True
                    self.fault_reason = 'attempt interrupted by visibility / field / carry guard'
                    return result('WAIT', self.fault_reason)
                # Native skill handles contact and direction. Once departure is plausible,
                # stop calling it while awaiting confirmation; never blindly re-touch.
                uncertain = attempt['feedback'] or (attempt['max_moved'] >= 25 and gap > 155)
                if uncertain and attempt['verify_since'] is None:
                    attempt['verify_since'] = f.time
                expired = (f.time-attempt['verify_since'] >= c.confirm_timeout
                           if attempt['verify_since'] is not None else age >= c.native_shoot_timeout)
                if expired:
                    stationary = attempt['max_moved'] < 25 and attempt['peak'] < 250 and not attempt['feedback']
                    self.pending_shot = None
                    if stationary and self.retry_count < c.max_retries:
                        self.retry_count += 1
                        self.turn_owner = number
                        theta = direction(f.ball, (c.half_length, 0))
                        target = self.legal_target((f.ball[0]-240*cos(theta), f.ball[1]-240*sin(theta)))
                        self.reposition = dict(number=number, time=f.time, ball=f.ball, target=target)
                        commands[number] = Command('move', target, theta, False)
                        return result('REPOSITION', 'stationary failed attempt: back off before retry')
                    self.shot_fault = True
                    self.fault_reason = 'retry limit reached' if stationary else 'ambiguous departure: inspect / reset round'
                    return result('WAIT', self.fault_reason)
                support = next((n for n in c.attackers if n != number and n in f.own), None)
                target = self.support_command(f, support, commands)
                if attempt['verify_since'] is None:
                    commands[number] = Command('normal_shoot', power=c.shot_power)
                return result('NATIVE_SHOOT' if attempt['verify_since'] is None else 'VERIFY_SHOT',
                              'NormalShoot handles contact and shot' if attempt['verify_since'] is None
                              else 'wait for observed ball departure', support, target)
        if self.shot_fault:
            return result('WAIT', self.fault_reason)
        if abs(f.ball[0]) > c.half_length or abs(f.ball[1]) > c.half_width:
            return result('WAIT', 'ball out: wait for referee')
        if self.danger(f.ball, c.robot_radius+70):
            return result('WAIT', 'ball near penalty area')
        if self.reposition is not None:
            retry = self.reposition
            number = retry['number']
            robot = f.own.get(number)
            if (robot is None or robot.kicked or distance(f.ball,retry['ball']) >= 25 or speed >= 250
                or number in self.carry_blocked or self.danger(robot.pos,c.robot_radius+30)):
                self.shot_fault = True
                self.fault_reason = 'retry interrupted: inspect / reset round'
                return result('WAIT', self.fault_reason)
            age = f.time-retry['time']
            if age >= .4 and distance(robot.pos,retry['target']) < 60:
                self.reposition = None
            elif age > 2:
                self.shot_fault = True
                self.fault_reason = 'reposition timed out'
                return result('WAIT', self.fault_reason)
            else:
                commands[number] = Command('move', retry['target'], direction(robot.pos,f.ball))
                supporter = next((n for n in c.attackers if n != number),None)
                target = self.support_command(f,supporter,commands)
                return result('REPOSITION', 'back off before retry',supporter,target)
        eligible = [n for n in c.attackers if n in f.own and n != self.locked
                    and n not in self.carry_blocked and not self.danger(f.own[n].pos, c.robot_radius+30)]
        if not eligible:
            support = self.locked if self.locked in f.own else None
            target = self.support_command(f, support, commands)
            return result('WAIT', 'no eligible attacker / carry guard', support, target)
        nearest = min(eligible, key=lambda n: distance(f.own[n].pos, f.ball))
        if self.turn_owner is not None:
            # Once a shot has departed, the next shooter keeps the turn even if its
            # teammate is nearer or the no-second-touch lock has subsequently cleared.
            if self.turn_owner not in eligible:
                support = next((n for n in c.attackers if n != self.turn_owner and n in f.own), None)
                target = self.support_command(f, support, commands)
                return result('WAIT', 'next shooter unavailable', support, target)
            nearest = self.turn_owner
        if (self.striker not in eligible or (self.turn_owner is None and
                distance(f.own[nearest].pos,f.ball)+500 < distance(f.own[self.striker].pos,f.ball))):
            self.striker = nearest
            self.aim = None
            self.aligned_since = None
        if self.side is None:
            self.side = -1 if f.ball[1] >= 0 else 1
        robot = f.own[self.striker]
        contact = self.touching(robot, f.ball)
        # The native skill owns shot selection; centre is only an approach reference.
        self.aim = None
        aim = (c.half_length, 0)
        theta = direction(f.ball, aim)
        others = [n for n in c.attackers if n != self.striker and n in f.own]
        supporter = others[0] if others else None
        support_target = self.support_command(f, supporter, commands)
        # Do not chase a departing shot. A returning/slow ball becomes a rebound opportunity.
        if f.time-self.last_kick < .35 or (f.time-self.last_kick < 3 and speed > 900 and f.velocity[0] > 200):
            return result('REBOUND', 'watch shot; first kicker locked', supporter, support_target)
        # Stage behind the ball, then approach its rear face with controlled dribble.
        behind = (f.ball[0]-180*cos(theta), f.ball[1]-180*sin(theta))
        near_axis = abs((robot.pos[0]-f.ball[0])*sin(theta)-(robot.pos[1]-f.ball[1])*cos(theta)) < 65
        is_behind = (robot.pos[0]-f.ball[0])*cos(theta)+(robot.pos[1]-f.ball[1])*sin(theta) < -30
        staged = (near_axis and is_behind and distance(robot.pos,f.ball) < 260)
        if self.danger(behind, c.robot_radius+50):
            return result('WAIT', 'approach would enter penalty area')
        if (staged or contact) and speed < 800:
            commands[self.striker] = Command('normal_shoot', power=c.shot_power)
            self.pending_shot = dict(number=self.striker, time=f.time, ball=f.ball,
                max_moved=0, peak=speed, feedback=False, contact_seen=contact, verify_since=None)
            return result('NATIVE_SHOOT', 'NormalShoot handles contact and shot', supporter, support_target)
        commands[self.striker] = Command('move', self.legal_target(behind), theta, False)
        phase, reason = 'PREPARE', 'approach behind ball'
        if self.locked is not None:
            phase, reason = 'RECOVER', 'other attacker collects rebound'
        return result(phase, reason, supporter, support_target)
