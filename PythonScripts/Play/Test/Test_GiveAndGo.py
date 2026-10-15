"""默认摆球 → 近车控球 → 底角接应 → 回传接射。仅仿真，单轮运行。"""
import math
import time

import CppPackage
import Global
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player
from WorldModel import Params, kickStatus
from WorldModel.PowerCalculator import evalPower, P
from Play.Test.Test_CornerPassShot import (
    CornerPassShot, PASSER, RECEIVER, distance, direction, angle_error,
)

# 复用旧测试的两车视觉检查、停止清理和框架接口；角色在这两个车号间动态分配。
ROBOT_IDS = (PASSER, RECEIVER)
LIMITS = {"SETUP": 35, "PASS_OUT": 8, "RETURN_SETUP": 18,
          "RETURN_PASS": 8, "FINISH": 6}


def copy_point(point):
    return CGeoPoint(point.x(), point.y())


def mouth(point, angle):
    offset = Params.playerFrontToCenter + 22
    return CGeoPoint(point.x() + offset * math.cos(angle),
                     point.y() + offset * math.sin(angle))


class GiveAndGo(CornerPassShot):
    def reset(self):
        super().reset()
        self.near, self.far = ROBOT_IDS
        self.assigned = False
        self.holds = {}
        self.pass_target = None
        self.pass_sent = False
        self.corner_angle = 0

    def tasks_for(self, near_skill, far_skill):
        return {"A": Task(near_skill, fixedNumber=self.near),
                "B": Task(far_skill, fixedNumber=self.far)}

    def change_phase(self, phase, reason):
        self.phase, self.started = phase, time.monotonic()
        self.ready_since = None
        print(f"[give-and-go] {phase}: {reason}", flush=True)

    def done(self, reason):
        self.change_phase("DONE", reason)
        return self.stop_tasks()

    def has_ball(self, number):
        robot, ball = Player.Pos(number), Ball.pos()
        return (distance(robot, ball) < 160 and Player.isInfraredOn(number)
                and angle_error(Player.direction(number), direction(robot, ball)) < .35)

    def move(self, target, angle, dribble=False):
        execute, match_position = Skill.SimpleGoTo(target, angle=angle)

        def run(number):
            CppPackage.setDribbleCommand(number, 3 if dribble else 0)
            return execute(number)

        return run, match_position

    def collect(self, number, target):
        """先接近并吸球；一旦控住，锁定车身位置，只原地朝向传球点。"""
        robot, ball = Player.Pos(number), Ball.pos()
        if self.has_ball(number):
            if number not in self.holds:
                self.holds[number] = copy_point(robot)
            return self.move(self.holds[number], direction(robot, target), dribble=True)
        self.holds.pop(number, None)
        angle = direction(robot, ball)
        offset = Params.playerFrontToCenter + 20
        destination = CGeoPoint(ball.x() - offset * math.cos(angle),
                               ball.y() - offset * math.sin(angle))
        if angle_error(Player.direction(number), angle) > math.radians(10):
            destination = robot
        return self.move(destination, angle, dribble=distance(robot, ball) < 400)

    @staticmethod
    def at_position(number, point, angle):
        return (distance(Player.Pos(number), point) < 75 and Player.velMod(number) < 120
                and angle_error(Player.direction(number), angle) < math.radians(7))

    def ready_to_pass(self, passer, receiver, receiver_pos, receiver_angle, target):
        ready = (self.has_ball(passer)
                 and Player.velMod(passer) < 120
                 and angle_error(Player.direction(passer), direction(Player.Pos(passer), target))
                 < math.radians(5)
                 and self.at_position(receiver, receiver_pos, receiver_angle))
        if not ready:
            self.ready_since = None
        elif self.ready_since is None:
            self.ready_since = time.monotonic()
        return ready and time.monotonic() - self.ready_since >= .25

    def begin_pass(self, phase, target):
        self.pass_origin = copy_point(Ball.pos())
        self.pass_target = copy_point(target)
        self.pass_sent = False
        self.change_phase(phase, f"target=({target.x():.0f},{target.y():.0f})")

    def departed(self):
        vx, vy = Ball.velX(), Ball.velY()
        speed = math.hypot(vx, vy)
        angle = direction(self.pass_origin, self.pass_target)
        return (self.pass_sent and distance(Ball.pos(), self.pass_origin) > 100
                and speed > 350 and vx * math.cos(angle) + vy * math.sin(angle) > .65 * speed)

    def pass_skill(self, passer, receiver, receiver_pos, receiver_angle):
        if self.pass_sent:
            return Skill.Stop()
        power = evalPower(Ball.pos(), self.pass_target, P.NORMAL)
        if not math.isfinite(power) or power <= 0:
            self.change_phase("DONE", "invalid pass power")
            return Skill.Stop()
        move, match_position = self.collect(passer, self.pass_target)
        can_kick = (self.has_ball(passer)
                    and self.at_position(receiver, receiver_pos, receiver_angle)
                    and angle_error(Player.direction(passer),
                                    direction(Player.Pos(passer), self.pass_target)) < math.radians(5))

        def run(number):
            result = move(number)
            if can_kick:
                kickStatus.setKick(number, power)
                self.pass_sent = True
                print(f"[give-and-go] kick requested robot={number} power={power:.0f}", flush=True)
            return result

        return run, match_position

    def getTasks(self):
        kickStatus.clearAll()
        for number in ROBOT_IDS:
            CppPackage.setDribbleCommand(number, 0)
        if self.phase == "DONE":
            return self.stop_tasks()
        if not self.vision_ok():
            if self.assigned:
                return self.done("vision lost; restart trial after restoring vision")
            if self.vision_status != "waiting":
                print(f"[give-and-go] waiting for ball and robots {ROBOT_IDS}", flush=True)
                self.vision_status = "waiting"
            return self.stop_tasks()

        ball = Ball.pos()
        if abs(ball.x()) > Params.pitchLength / 2 or abs(ball.y()) > Params.pitchWidth / 2:
            return self.done("ball outside field")
        for n in ROBOT_IDS:
            pos = Player.Pos(n)
            if (pos.x() > Params.pitchLength / 2 - Params.penaltyDepth - 110
                    and abs(pos.y()) < Params.penaltyWidth / 2 + 110):
                return self.done(f"robot {n} at opponent penalty area boundary")

        corner = CGeoPoint(Params.pitchLength / 2 - 600, -Params.pitchWidth / 2 + 600)
        shot = CGeoPoint(Params.pitchLength / 2 - Params.penaltyDepth - 350, 0)
        goal = CGeoPoint(Params.pitchLength / 2, 0)
        shot_mouth = mouth(shot, 0)
        if not self.assigned:
            self.near, self.far = sorted(ROBOT_IDS, key=lambda n: (distance(Player.Pos(n), ball), n))
            self.assigned = True
            self.corner_angle = direction(corner, ball)
            self.change_phase("SETUP", f"near/shooter={self.near}, far/corner={self.far}; "
                              f"field={Params.pitchLength}x{Params.pitchWidth}; "
                              f"corner=({corner.x():.0f},{corner.y():.0f}); "
                              f"shot=({shot.x():.0f},{shot.y():.0f})")
        if time.monotonic() - self.started > LIMITS[self.phase]:
            return self.done(f"{self.phase} timeout")

        if self.phase == "SETUP":
            self.corner_angle = direction(corner, ball)
            target = mouth(corner, self.corner_angle)
            near_skill = self.collect(self.near, target)
            far_skill = self.move(corner, self.corner_angle, dribble=True)
            if self.ready_to_pass(self.near, self.far, corner, self.corner_angle, target):
                self.begin_pass("PASS_OUT", target)
            return self.tasks_for(near_skill, far_skill)

        if self.phase == "PASS_OUT":
            if self.departed():
                self.change_phase("RETURN_SETUP", "first pass departed; near robot runs to shot point")
            else:
                near_skill = self.pass_skill(self.near, self.far, corner, self.corner_angle)
                if self.phase == "DONE":
                    return self.stop_tasks()
                return self.tasks_for(near_skill, self.move(corner, self.corner_angle, dribble=True))

        if self.phase == "RETURN_SETUP":
            # 远车留在底角迎接第一脚球；球进入附近后才接近取球，不追到中场。
            if distance(ball, corner) < 550 or self.has_ball(self.far) or self.far in self.holds:
                far_skill = self.collect(self.far, shot_mouth)
            else:
                far_skill = self.move(corner, direction(corner, ball), dribble=True)
                self.ready_since = None
            near_skill = self.move(shot, 0)
            if self.ready_to_pass(self.far, self.near, shot, 0, shot_mouth):
                self.begin_pass("RETURN_PASS", shot_mouth)
            return self.tasks_for(near_skill, far_skill)

        if self.phase == "RETURN_PASS":
            if self.departed():
                self.change_phase("FINISH", "return pass departed; StaticGetBall starts before contact")
            else:
                far_skill = self.pass_skill(self.far, self.near, shot, 0)
                if self.phase == "DONE":
                    return self.stop_tasks()
                return self.tasks_for(self.move(shot, 0), far_skill)

        # shortcut: 最后一脚的移动和踢球时机由现有原生技能决定，仍需仿真验证。
        if self.near_since is None and distance(ball, Player.Pos(self.near)) < 220:
            self.near_since = time.monotonic()
            print("[give-and-go] ball near shooter", flush=True)
        if (self.near_since is not None and distance(ball, Player.Pos(self.near)) > 300
                and Ball.velX() > 500
                and angle_error(math.atan2(Ball.velY(), Ball.velX()),
                                direction(Player.Pos(self.near), goal)) < .4):
            return self.done("possible shot; inspect recording, not a success assertion")
        power = evalPower(ball, goal, P.HIGH)
        if not math.isfinite(power) or power <= 0:
            return self.done("invalid shot power")
        return self.tasks_for(Skill.StaticGetBall(goal, power, 0), Skill.Stop())


@declare_state_machine(GiveAndGo)
class Test_GiveAndGo(StateMachine):
    def hookBeforePlanTasks(self):
        if Global.isPlaySwitched:
            self.start_state.reset()
