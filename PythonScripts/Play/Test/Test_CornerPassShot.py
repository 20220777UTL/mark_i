"""单次底角传球接射实验；用 SRC_CORNER_PASS_TEST=1 启用，仅用于仿真。"""
import math
import time

import CppPackage
import Global
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player
from WorldModel import Params, kickStatus
from WorldModel.PowerCalculator import evalPower, P

PASSER, RECEIVER = 1, 2
PASS_LEVEL = P.NORMAL
SHOT_LEVEL = P.HIGH
TIMEOUTS = {"SETUP": 20, "PASS": 8, "RECEIVE_SHOOT": 6}


def distance(a, b):
    return math.hypot(a.x() - b.x(), a.y() - b.y())


def direction(a, b):
    return math.atan2(b.y() - a.y(), b.x() - a.x())


def angle_error(a, b):
    return abs(math.atan2(math.sin(a - b), math.cos(a - b)))


class CornerPassShot(State):
    def __init__(self):
        super().__init__()
        self.reset()

    def reset(self):
        self.phase = "SETUP"
        self.started = None
        self.ready_since = None
        self.pass_origin = None
        self.near_since = None
        self.vision_status = None

    def change_phase(self, phase, reason):
        self.phase, self.started = phase, time.monotonic()
        print(f"[corner-pass] {phase}: {reason}", flush=True)

    def stop_tasks(self):
        kickStatus.clearAll()
        return self.tasks_for(Skill.Stop(), Skill.Stop())

    @staticmethod
    def tasks_for(a, b):
        return {"A": Task(a, fixedNumber=PASSER),
                "B": Task(b, fixedNumber=RECEIVER)}

    def vision_ok(self):
        if not Ball.valid() or not all(Player.isValid(n) for n in (PASSER, RECEIVER)):
            return False
        for point in (Ball.pos(), Player.Pos(PASSER), Player.Pos(RECEIVER)):
            if (not all(math.isfinite(v) for v in (point.x(), point.y()))
                    or abs(point.x()) > Params.pitchLength / 2 + 1000
                    or abs(point.y()) > Params.pitchWidth / 2 + 1000):
                return False
        return (all(math.isfinite(Player.direction(n))
                    and abs(Player.direction(n)) <= math.tau
                    and math.isfinite(Player.velMod(n)) for n in (PASSER, RECEIVER))
                and all(math.isfinite(v) for v in (Ball.velX(), Ball.velY())))

    def getTasks(self):
        # Stop 和基本移动不一定清吸球指令；每帧先清，再由本帧技能决定。
        for number in (PASSER, RECEIVER):
            CppPackage.setDribbleCommand(number, 0)
        if self.phase == "DONE":
            return self.stop_tasks()
        valid = self.vision_ok()
        if valid != self.vision_status:
            print(f"[corner-pass] vision {'ready' if valid else 'missing/invalid; stopped'}",
                  flush=True)
            self.vision_status = valid
        if not valid:
            self.ready_since = None
            if self.phase != "SETUP":
                self.change_phase("DONE", "vision lost during trial")
            return self.stop_tasks()

        now = time.monotonic()
        if self.started is None:
            self.started = now
        if now - self.started > TIMEOUTS[self.phase]:
            self.change_phase("DONE", f"{self.phase} timeout; reset scene and restart strategy")
            return self.stop_tasks()

        ball = Ball.pos()
        goal = CGeoPoint(Params.pitchLength / 2, 0)
        corner = CGeoPoint(Params.pitchLength / 2 - 600, -Params.pitchWidth / 2 + 600)
        receive = CGeoPoint(Params.pitchLength / 2 - Params.penaltyDepth - 350, 0)
        # 接应点是车身中心；传球瞄准朝球门一侧的球口，而非车身中心。
        mouth = CGeoPoint(receive.x() + Params.playerFrontToCenter + 22, receive.y())
        pass_angle = direction(corner, mouth)
        behind = CGeoPoint(corner.x() - 180 * math.cos(pass_angle),
                           corner.y() - 180 * math.sin(pass_angle))
        b = Player.Pos(RECEIVER)
        if (b.x() > Params.pitchLength / 2 - Params.penaltyDepth - 110
                and abs(b.y()) < Params.penaltyWidth / 2 + 110):
            self.change_phase("DONE", "receiver approaching penalty area; stop trial")
            return self.stop_tasks()

        if self.phase == "SETUP":
            ready = (distance(ball, corner) < 120 and math.hypot(Ball.velX(), Ball.velY()) < 100
                     and distance(Player.Pos(PASSER), behind) < 80
                     and angle_error(Player.direction(PASSER), pass_angle) < math.radians(8)
                     and distance(b, receive) < 60
                     and angle_error(Player.direction(RECEIVER), 0) < math.radians(5)
                     and all(Player.velMod(n) < 100 for n in (PASSER, RECEIVER)))
            if not ready:
                self.ready_since = None
            elif self.ready_since is None:
                self.ready_since = now
            elif now - self.ready_since >= .3:
                self.pass_origin = CGeoPoint(ball.x(), ball.y())
                self.change_phase("PASS", "both ready; ground pass to receiver mouth")
            return self.tasks_for(Skill.SimpleGoTo(behind, angle=pass_angle),
                                  Skill.SimpleGoTo(receive, angle=0))

        if self.phase == "PASS":
            vx, vy = Ball.velX(), Ball.velY()
            speed = math.hypot(vx, vy)
            toward = direction(self.pass_origin, mouth)
            departed = (distance(ball, self.pass_origin) > 100 and speed > 400
                        and (vx * math.cos(toward) + vy * math.sin(toward)) > .7 * speed)
            if departed:
                # 不等红外持球；球在路上就让接射技能开始调整。
                self.change_phase("RECEIVE_SHOOT", "pass departed; enable StaticGetBall now")
            else:
                power = evalPower(ball, mouth, PASS_LEVEL)
                if not math.isfinite(power) or power <= 0:
                    self.change_phase("DONE", "invalid pass power")
                    return self.stop_tasks()
                return self.tasks_for(Skill.StaticGetBall(mouth, power, 0),
                                      Skill.SimpleGoTo(receive, angle=0))

        if abs(ball.x()) > Params.pitchLength / 2 or abs(ball.y()) > Params.pitchWidth / 2:
            self.change_phase("DONE", "ball crossed field boundary; inspect replay")
            return self.stop_tasks()
        if self.near_since is None and distance(ball, b) < 220:
            self.near_since = now
            print("[corner-pass] ball near receiver; inspect contact in replay", flush=True)
        if (self.near_since is not None and distance(ball, b) > 300 and Ball.velX() > 500
                and angle_error(math.atan2(Ball.velY(), Ball.velX()), direction(b, goal)) < .4):
            self.change_phase("DONE", f"possible shot, {now - self.near_since:.3f}s after near-ball; "
                              "not proof of one-touch or a goal")
            return self.stop_tasks()
        power = evalPower(ball, goal, SHOT_LEVEL)
        if not math.isfinite(power) or power <= 0:
            self.change_phase("DONE", "invalid shot power")
            return self.stop_tasks()
        # shortcut: 接球路径和触球时机交给原生技能；录像若显示停球再转身，再替换此处。
        return self.tasks_for(Skill.Stop(), Skill.StaticGetBall(goal, power, 0))

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(CornerPassShot)
class Test_CornerPassShot(StateMachine):
    def hookBeforePlanTasks(self):
        if Global.isPlaySwitched:
            self.start_state.reset()
