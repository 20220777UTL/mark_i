"""Pure, testable two-attacker decisions. Coordinates: mm, attack towards +x.

This is a practice policy, not a referee or a proof of rule compliance.
"""
from dataclasses import dataclass
from math import atan2, hypot, pi


@dataclass(frozen=True)
class Robot:
    x: float
    y: float
    angle: float = 0.0
    infrared: bool = False

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
    target: tuple = (0.0, 0.0)
    angle: float = 0.0
    dribble: bool = False


def distance(a, b):
    return hypot(a[0] - b[0], a[1] - b[1])


def direction(a, b):
    return atan2(b[1] - a[1], b[0] - a[0])


def angle_error(a, b):
    return abs((a - b + pi) % (2 * pi) - pi)


def segment_distance(p, a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = max(0, min(1, ((p[0]-a[0])*dx + (p[1]-a[1])*dy) / max(1, dx*dx+dy*dy)))
    return distance(p, (a[0]+t*dx, a[1]+t*dy))


class PreliminaryPolicy:
    IDS = (1, 2)

    def __init__(self, half_length=4500, half_width=3000, penalty_depth=1000):
        self.goal_x = half_length
        # Keep the entire robot outside either penalty area, with extra braking room.
        self.front = half_length - penalty_depth - 300
        self.width = half_width - 250
        self.phase = "acquire"
        self.attacker = self.receiver = None
        self.entered = None
        self.last_pos = None
        self.carry = 0.0
        self.held_since = None
        self.pass_origin = None
        self.pass_target = None
        self.side = 1
        self.reason = "initial"

    def change(self, phase, now, reason):
        self.phase, self.entered, self.reason = phase, now, reason

    def reset(self, now, reason):
        self.attacker = self.receiver = None
        self.held_since = self.last_pos = None
        self.carry = 0
        self.change("acquire", now, reason)

    def clamp(self, p):
        return max(-self.front, min(self.front, p[0])), max(-self.width, min(self.width, p[1]))

    def holding(self, frame, number):
        robot = frame.ours[number]
        d = distance(robot.pos, frame.ball)
        return d < 155 and (robot.infrared or angle_error(robot.angle, direction(robot.pos, frame.ball)) < .45)

    def clear(self, frame, a, b):
        return all(segment_distance(r.pos, a, b) > 260 for r in frame.enemies.values())

    def get_ball(self, frame, number, aim):
        robot = frame.ours[number]
        heading = direction(frame.ball, aim)
        from math import cos, sin
        behind = (frame.ball[0]-180*cos(heading), frame.ball[1]-180*sin(heading))
        if distance(robot.pos, behind) > 230 and not self.holding(frame, number):
            return Action("move", self.clamp(behind), heading, True)
        return Action("move", self.clamp(frame.ball), heading, True)

    def tick(self, f):
        stops = {n: Action("stop") for n in self.IDS}
        if self.entered is None:
            self.entered = f.time
        if not f.valid or any(n not in f.ours for n in self.IDS):
            self.reset(f.time, "missing vision")
            return stops
        # Conservative: no attacker chases a ball beyond either penalty front.
        if abs(f.ball[0]) > self.front or abs(f.ball[1]) > self.width:
            self.reset(f.time, "ball outside safe attack area; reset required")
            return stops
        if self.attacker is None:
            self.attacker = min(self.IDS, key=lambda n: distance(f.ours[n].pos, f.ball))
            self.receiver = next(n for n in self.IDS if n != self.attacker)
            self.side = 1 if f.ball[1] >= 0 else -1
            self.entered = f.time
        a, b = self.attacker, self.receiver
        ra, rb = f.ours[a], f.ours[b]
        held = self.holding(f, a)
        if held:
            if self.last_pos is not None:
                self.carry += distance(ra.pos, self.last_pos)
            self.last_pos = ra.pos
            if self.held_since is None:
                self.held_since = f.time
        else:
            self.last_pos = None
            self.held_since = None
        # Do not reset carry merely because infrared flickers.
        if self.carry >= 820:
            self.change("limit_stop", f.time, "carry budget exhausted; manual reset")
        if self.phase == "limit_stop":
            return stops
        support = self.clamp((min(self.front-150, f.ball[0]+650), -self.side*850))
        tasks = {b: Action("move", support, direction(rb.pos, f.ball))}
        elapsed = f.time - self.entered
        if self.phase == "acquire":
            tasks[a] = self.get_ball(f, a, (self.front, self.side*650))
            if held and f.time-self.held_since > .15:
                self.change("advance", f.time, "ball secured")
            elif elapsed > 6:
                self.reset(f.time, "acquire timeout; rematch nearest")
        elif self.phase == "advance":
            lure = self.clamp((min(self.front-100, ra.x+350), self.side*650))
            tasks[a] = Action("move", lure, direction(ra.pos, lure), True)
            keeper = min(f.enemies.values(), key=lambda r: distance(r.pos, (self.goal_x, 0)), default=None)
            drawn = keeper is not None and (keeper.x < self.goal_x-650 or keeper.y*self.side > 300)
            ready = distance(rb.pos, support) < 220
            if not held:
                self.change("acquire", f.time, "lost possession")
            elif self.carry > 450 or elapsed > 1.5 or (ready and drawn):
                if ready and self.clear(f, f.ball, rb.pos):
                    self.pass_target = rb.pos
                    self.pass_origin = f.ball
                    self.change("pass", f.time, "keeper drawn" if drawn else "carry/time limit: pass")
                elif self.carry > 650 or elapsed > 3:
                    self.change("shoot", f.time, "no safe pass; direct shot attempt")
                else:
                    tasks[a] = Action("move", ra.pos, direction(ra.pos, rb.pos), True)
        elif self.phase == "pass":
            tasks[b] = Action("move", self.pass_target, direction(rb.pos, f.ball), True)
            tasks[a] = Action("kick", self.pass_target, direction(ra.pos, self.pass_target), True)
            if not self.clear(f, f.ball, self.pass_target):
                tasks[a] = Action("move", ra.pos, direction(ra.pos, self.pass_target), True)
            if distance(f.ball, self.pass_origin) > 220 and distance(ra.pos, f.ball) > 200:
                self.change("receive", f.time, "pass released")
            elif elapsed > 5:
                self.change("shoot", f.time, "pass blocked/timeout")
        elif self.phase == "receive":
            tasks[a] = Action("move", self.clamp((ra.x-200, self.side*850)), direction(ra.pos, f.ball))
            predicted = self.clamp((f.ball[0]+.12*f.velocity[0], f.ball[1]+.12*f.velocity[1]))
            tasks[b] = Action("move", predicted, direction(rb.pos, f.ball), True)
            if self.holding(f, b):
                self.attacker, self.receiver = b, a
                self.carry = 0
                self.last_pos = rb.pos
                self.held_since = f.time
                self.side = 1 if rb.y >= 0 else -1
                self.change("shoot" if rb.x > 1800 else "advance", f.time, "receiver secured ball")
            elif elapsed > 4:
                self.reset(f.time, "receive timeout")
        elif self.phase == "shoot":
            targets = [(self.goal_x, y) for y in (-330, 330)]
            goal = max(targets, key=lambda p: min((segment_distance(r.pos, f.ball, p) for r in f.enemies.values()), default=10000))
            tasks[a] = Action("kick", goal, direction(ra.pos, goal), True)
            if not held and distance(ra.pos, f.ball) > 300:
                self.change("recover", f.time, "shot released")
            elif elapsed > 5:
                self.reset(f.time, "shoot timeout")
        elif self.phase == "recover":
            tasks = stops
            if elapsed > .7:
                self.reset(f.time, "new attack")
        return tasks
