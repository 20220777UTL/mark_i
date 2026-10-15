"""球后对准一脚开球 → 底角接应 → 回传接射。单轮实验，需实车标定。"""
import math
import time

import CppPackage
import Global
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player
from WorldModel import Params, kickStatus, Flags
from WorldModel.PowerCalculator import evalPower, P
from Play.Test.Test_CornerPassShot import (
    CornerPassShot, PASSER, RECEIVER, distance, direction, angle_error,
)

# 复用旧测试的两车视觉检查、停止清理和框架接口；角色在这两个车号间动态分配。
ROBOT_IDS = (PASSER, RECEIVER)
LIMITS = {"SETUP": 35, "PASS_OUT": 8, "RETURN_SETUP": 18,
          "RETURN_PASS": 8, "FINISH": 6}
# 最后一脚的实验参数，单位 mm、秒、弧度；只有底角接第一脚球允许吸球。
MEET_RADIUS = 300
MEET_LEAD_TIME = .06
MIN_INCOMING_SPEED = 150
KICK_SIDE_TOLERANCE = 40
KICK_FRONT_MARGIN = 55
KICK_ANGLE_TOLERANCE = math.radians(8)
KICK_WINDOW_SECONDS = .18
PASS_ANGLE_TOLERANCE = math.radians(5)
TRAVEL_ACCELERATION = 2000
# 规则上限1m；留100mm余量。按可见车身累计路程保守终止，不替代实车判罚。
CARRY_STOP_DISTANCE = 900
CLEAR_BALL_SEPARATION = 250


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
        self.shot_requested_at = None
        self.frozen_finish = None
        self.last_possession = {}
        self.vision_lost_since = None
        self.last_status_at = -math.inf
        self.opening_kick_at = None
        self.opening_closed = False
        self.return_kick_at = None
        self.return_closed = False
        self.carry_last = None
        self.carry_distance = 0

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
        geometry_ok = (distance(robot, ball) < 160
                       and angle_error(Player.direction(number), direction(robot, ball)) < .35)
        if not geometry_ok:
            self.last_possession.pop(number, None)
            return False
        now = time.monotonic()
        if Player.isInfraredOn(number):
            self.last_possession[number] = now
            return True
        # 仅在几何关系仍正确且球较慢时，容忍已确认持球后的短暂红外掉线。
        return (now - self.last_possession.get(number, -math.inf) < .12
                and math.hypot(Ball.velX(), Ball.velY()) < 300)

    def status(self, **values):
        if time.monotonic() - self.last_status_at >= 1:
            self.last_status_at = time.monotonic()
            print(f"[give-and-go] WAIT {self.phase} " + " ".join(
                f"{key}={value:.2f}" if isinstance(value, float) else f"{key}={value}"
                for key, value in values.items()), flush=True)

    def carry_limit_reached(self):
        robot = Player.Pos(self.far)
        if distance(robot, Ball.pos()) > CLEAR_BALL_SEPARATION:
            self.carry_last, self.carry_distance = None, 0
        elif self.carry_last is not None:
            self.carry_distance += distance(robot, self.carry_last)
            self.carry_last = copy_point(robot)
        elif self.has_ball(self.far):
            self.carry_last = copy_point(robot)
        # 红外掉线不清计数；只有观察到明显人球分离才重新计数。
        return self.carry_distance >= CARRY_STOP_DISTANCE

    def travel(self, number, target, angle):
        # 单个手写绕行点不能保证整段路径安全；使用已有原生规划与动态避障。
        if (abs(target.x()) > Params.pitchLength / 2 - 110
                or abs(target.y()) > Params.pitchWidth / 2 - 110
                or (target.x() > Params.pitchLength / 2 - Params.penaltyDepth - 110
                    and abs(target.y()) < Params.penaltyWidth / 2 + 110)):
            self.status(route=f"robot {number}: unsafe target; stopped")
            return Skill.Stop()
        return Skill.SmartGoTo(target, angle,
                               flag=Flags.dodge_ball | Flags.allow_dss | Flags.slowly,
                               maxAcc=TRAVEL_ACCELERATION)

    def opening_skill(self, corner):
        """固定球后接近并预触发一次开球；不吸球，不追着移动的球继续接触。"""
        angle = direction(self.pass_origin, self.pass_target)
        robot, ball = Player.Pos(self.near), Ball.pos()
        moved = distance(ball, self.pass_origin)
        if self.pass_sent and (moved > 30 or math.hypot(Ball.velX(), Ball.velY()) > 150):
            self.opening_closed = True
        if self.opening_kick_at is not None and time.monotonic() - self.opening_kick_at >= KICK_WINDOW_SECONDS:
            self.opening_closed = True
        if self.opening_closed:
            return Skill.Stop()  # 关闭后即使球弹回，也不重新触发。
        receiver_ready = self.at_position(self.far, corner, self.corner_angle)
        heading_ok = angle_error(Player.direction(self.near), angle) < PASS_ANGLE_TOLERANCE
        self.status(receiver_ready=receiver_ready, heading_ok=heading_ok,
                    ball_distance=distance(robot, ball), kick_requested=self.pass_sent)
        if moved > 30:
            self.opening_closed = True
            return Skill.Stop()
        if not heading_ok:
            if self.pass_sent or distance(robot, ball) < 170:
                self.change_phase("DONE", "opening heading lost near ball; no second contact")
                return Skill.Stop()
            return self.move(copy_point(robot), angle)  # 球外修正朝向，不靠近或吸球。
        if not receiver_ready:
            return Skill.Stop()
        destination = CGeoPoint(self.pass_origin.x() - 96 * math.cos(angle),
                                self.pass_origin.y() - 96 * math.sin(angle))
        move, match_position = self.move(destination, angle, dribble=False)
        power = evalPower(self.pass_origin, self.pass_target, P.NORMAL)
        if not math.isfinite(power) or power <= 0:
            self.change_phase("DONE", "invalid opening power")
            return Skill.Stop()
        at_mouth = (distance(robot, ball) < 150
                    and angle_error(Player.direction(self.near), direction(robot, ball)) < .2)

        def run(number):
            result = move(number)
            if at_mouth:
                kickStatus.setKick(number, power)
                self.pass_sent = True
                if self.opening_kick_at is None:
                    self.opening_kick_at = time.monotonic()
                    print(f"[give-and-go] OPENING_KICK robot={number} power={power:.0f}; dribble OFF", flush=True)
            return result

        return run, match_position

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
                 < PASS_ANGLE_TOLERANCE
                 and self.at_position(receiver, receiver_pos, receiver_angle))
        self.status(has_ball=self.has_ball(passer), infrared=Player.isInfraredOn(passer),
                    ball_distance=distance(Player.Pos(passer), Ball.pos()),
                    ball_angle_deg=math.degrees(angle_error(Player.direction(passer), direction(Player.Pos(passer), Ball.pos()))),
                    pass_angle_deg=math.degrees(angle_error(Player.direction(passer), direction(Player.Pos(passer), target))),
                    passer_speed=Player.velMod(passer),
                    receiver_distance=distance(Player.Pos(receiver), receiver_pos),
                    receiver_angle_deg=math.degrees(angle_error(Player.direction(receiver), receiver_angle)),
                    receiver_speed=Player.velMod(receiver))
        if not ready:
            self.ready_since = None
        elif self.ready_since is None:
            self.ready_since = time.monotonic()
        return ready and time.monotonic() - self.ready_since >= .25

    def begin_pass(self, phase, target):
        self.pass_origin = copy_point(Ball.pos())
        self.pass_target = copy_point(target)
        self.pass_sent = False
        if phase == "PASS_OUT":
            self.opening_kick_at, self.opening_closed = None, False
        else:
            self.return_kick_at, self.return_closed = None, False
        self.change_phase(phase, f"target=({target.x():.0f},{target.y():.0f})")

    def departed(self):
        vx, vy = Ball.velX(), Ball.velY()
        speed = math.hypot(vx, vy)
        angle = direction(self.pass_origin, self.pass_target)
        return (self.pass_sent and distance(Ball.pos(), self.pass_origin) > 100
                and speed > 350 and vx * math.cos(angle) + vy * math.sin(angle) > .65 * speed)

    def pass_skill(self, passer, receiver, receiver_pos, receiver_angle):
        if self.pass_sent and (distance(Ball.pos(), self.pass_origin) > 30
                               or math.hypot(Ball.velX(), Ball.velY()) > 150):
            self.return_closed = True
        if self.return_kick_at is not None and time.monotonic() - self.return_kick_at >= KICK_WINDOW_SECONDS:
            self.return_closed = True
        if self.return_closed:
            return Skill.Stop()
        power = evalPower(Ball.pos(), self.pass_target, P.NORMAL)
        if not math.isfinite(power) or power <= 0:
            self.change_phase("DONE", "invalid pass power")
            return Skill.Stop()
        held = self.has_ball(passer)
        if self.pass_sent and not held:
            self.return_closed = True
            return Skill.Stop()
        move, match_position = self.collect(passer, self.pass_target)
        can_kick = (held and Player.velMod(passer) < 120
                    and self.at_position(receiver, receiver_pos, receiver_angle)
                    and angle_error(Player.direction(passer),
                                    direction(Player.Pos(passer), self.pass_target)) < PASS_ANGLE_TOLERANCE)

        def run(number):
            result = move(number)
            if can_kick:
                kickStatus.setKick(number, power)
                self.pass_sent = True
                if self.return_kick_at is None:
                    self.return_kick_at = time.monotonic()
                    print(f"[give-and-go] kick requested robot={number} power={power:.0f}", flush=True)
            return result

        return run, match_position

    def finish_tasks(self, shot, goal):
        """小范围迎球，球口窗口内预触发平射；没有吸球或失接后的取球分支。"""
        ball, robot = Ball.pos(), Player.Pos(self.near)
        vx, vy = Ball.velX(), Ball.velY()
        speed = math.hypot(vx, vy)
        now = time.monotonic()
        if distance(robot, shot) > MEET_RADIUS + 80:
            return self.done("shooter left reception area; no chase")
        if self.shot_requested_at is not None:
            if (distance(ball, robot) > 300 and vx > 500
                    and angle_error(math.atan2(vy, vx), direction(robot, goal)) < .4):
                return self.done("outgoing ball after kick request; not proof of a goal")
            if now - self.shot_requested_at >= KICK_WINDOW_SECONDS:
                return self.done("kick window closed; no recapture or second attempt")

        nominal_mouth = mouth(shot, 0)
        if ball.x() < nominal_mouth.x() - 140:
            return self.done("ball passed reception line; no chase")
        if speed < MIN_INCOMING_SPEED:
            return self.done("incoming ball too slow/stopped; no collection")

        # 踢球判定用实际车身朝向和球相对球口的位置，不用红外持球信号。
        heading = Player.direction(self.near)
        dx, dy = ball.x() - robot.x(), ball.y() - robot.y()
        forward = dx * math.cos(heading) + dy * math.sin(heading)
        lateral = -dx * math.sin(heading) + dy * math.cos(heading)
        actual_mouth = mouth(robot, heading)
        approaching = vx * (actual_mouth.x() - ball.x()) + vy * (actual_mouth.y() - ball.y()) > 0
        can_kick = (Params.playerFrontToCenter - 5 <= forward
                    <= Params.playerFrontToCenter + 22 + KICK_FRONT_MARGIN
                    and abs(lateral) <= KICK_SIDE_TOLERANCE and approaching
                    and angle_error(heading, direction(ball, goal)) <= KICK_ANGLE_TOLERANCE)

        if self.shot_requested_at is not None and not can_kick:
            return self.done("ball left shot contact window; no rebound or second attempt")

        if self.frozen_finish is not None:
            destination, aim = self.frozen_finish
        elif can_kick:
            destination, aim = copy_point(robot), heading
        else:
            if vx >= -50:
                return self.done("ball no longer approaching reception line")
            time_to_line = (nominal_mouth.x() - ball.x()) / vx
            if time_to_line < 0:
                return self.done("missed reception line; no retry")
            # shortcut: 短时直线速度预测，每帧重算；不声称已标定摩擦和碰撞补偿。
            meet_time = max(0, time_to_line - MEET_LEAD_TIME)
            contact = CGeoPoint(ball.x() + vx * meet_time, ball.y() + vy * meet_time)
            aim = direction(contact, goal)
            offset = Params.playerFrontToCenter + 22
            destination = CGeoPoint(contact.x() - offset * math.cos(aim),
                                    contact.y() - offset * math.sin(aim))
            if distance(destination, shot) > MEET_RADIUS:
                return self.done("predicted contact outside reception area; no chase")
            if (destination.x() > Params.pitchLength / 2 - Params.penaltyDepth - 110
                    and abs(destination.y()) < Params.penaltyWidth / 2 + 110):
                return self.done("predicted contact too close to penalty area")

        power = evalPower(ball, goal, P.HIGH)
        if not math.isfinite(power) or power <= 0:
            return self.done("invalid shot power")
        move, match_position = self.move(destination, aim, dribble=False)

        def run(number):
            result = move(number)
            if can_kick:
                kickStatus.setKick(number, power)
                if self.shot_requested_at is None:
                    self.shot_requested_at = time.monotonic()
                    # 开始出脚后锁住位置/朝向，短窗口补发同一脚请求，不转身补救。
                    self.frozen_finish = (copy_point(robot), heading)
                    print(f"[give-and-go] DIRECT_KICK robot={number} "
                          f"front={forward:.1f} side={lateral:.1f} power={power:.0f}", flush=True)
            return result

        return self.tasks_for((run, match_position), Skill.Stop())

    def getTasks(self):
        kickStatus.clearAll()
        for number in ROBOT_IDS:
            CppPackage.setDribbleCommand(number, 0)
        if self.phase == "DONE":
            return self.stop_tasks()
        if not self.vision_ok():
            self.ready_since = None
            self.last_possession.clear()
            if self.pass_sent:
                self.opening_closed = self.return_closed = True
            if self.assigned:
                if self.vision_lost_since is None:
                    self.vision_lost_since = time.monotonic()
                self.status(vision="invalid; stopped without using stale ball position")
                if self.phase == "FINISH" or time.monotonic() - self.vision_lost_since > .5:
                    return self.done("vision lost; restart trial after restoring vision")
                return self.stop_tasks()
            if self.vision_status != "waiting":
                print(f"[give-and-go] waiting for ball and robots {ROBOT_IDS}", flush=True)
                self.vision_status = "waiting"
            return self.stop_tasks()

        if self.vision_lost_since is not None:
            gap = time.monotonic() - self.vision_lost_since
            if gap > .5:
                return self.done("vision gap exceeded 0.5s before recovery")
            self.started += gap
            self.vision_lost_since = None

        ball = Ball.pos()
        if abs(ball.x()) > Params.pitchLength / 2 or abs(ball.y()) > Params.pitchWidth / 2:
            return self.done("ball outside field")
        for n in ROBOT_IDS:
            pos = Player.Pos(n)
            if abs(pos.x()) > Params.pitchLength / 2 or abs(pos.y()) > Params.pitchWidth / 2:
                return self.done(f"robot {n} outside field")
            if (pos.x() > Params.pitchLength / 2 - Params.penaltyDepth - 110
                    and abs(pos.y()) < Params.penaltyWidth / 2 + 110):
                return self.done(f"robot {n} at opponent penalty area boundary")
            if (pos.x() < -Params.pitchLength / 2 + Params.penaltyDepth + 110
                    and abs(pos.y()) < Params.penaltyWidth / 2 + 110
                    and distance(pos, ball) < 160):
                return self.done(f"non-goalkeeper {n} near ball at own penalty area boundary")

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
        if self.phase in ("RETURN_SETUP", "RETURN_PASS") and self.carry_limit_reached():
            return self.done("continuous carry reached 900mm guard; release/reset trial")

        if self.phase == "SETUP":
            self.corner_angle = direction(corner, ball)
            target = mouth(corner, self.corner_angle)
            angle = direction(ball, target)
            behind = CGeoPoint(ball.x() - 260 * math.cos(angle), ball.y() - 260 * math.sin(angle))
            near_skill = self.travel(self.near, behind, angle)
            far_skill = self.travel(self.far, corner, self.corner_angle)
            ready = (self.at_position(self.near, behind, angle)
                     and angle_error(Player.direction(self.near), angle) < PASS_ANGLE_TOLERANCE
                     and self.at_position(self.far, corner, self.corner_angle)
                     and math.hypot(Ball.velX(), Ball.velY()) < 100)
            self.status(behind_distance=distance(Player.Pos(self.near), behind),
                        near_angle_deg=math.degrees(angle_error(Player.direction(self.near), angle)),
                        far_distance=distance(Player.Pos(self.far), corner),
                        far_angle_deg=math.degrees(angle_error(Player.direction(self.far), self.corner_angle)),
                        near_speed=Player.velMod(self.near), far_speed=Player.velMod(self.far),
                        ball_speed=math.hypot(Ball.velX(), Ball.velY()))
            if not ready:
                self.ready_since = None
            elif self.ready_since is None:
                self.ready_since = time.monotonic()
            elif time.monotonic() - self.ready_since >= .25:
                self.begin_pass("PASS_OUT", target)
            return self.tasks_for(near_skill, far_skill)

        if self.phase == "PASS_OUT":
            if self.departed():
                self.change_phase("RETURN_SETUP", "first pass departed; near robot runs to shot point")
            else:
                near_skill = self.opening_skill(corner)
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
            near_skill = self.travel(self.near, shot, 0)
            if self.ready_to_pass(self.far, self.near, shot, 0, shot_mouth):
                self.begin_pass("RETURN_PASS", shot_mouth)
            return self.tasks_for(near_skill, far_skill)

        if self.phase == "RETURN_PASS":
            if self.departed():
                self.change_phase("FINISH", "return pass departed; bounded meet + direct kick, dribble OFF")
            else:
                far_skill = self.pass_skill(self.far, self.near, shot, 0)
                if self.phase == "DONE":
                    return self.stop_tasks()
                return self.tasks_for(self.move(shot, 0), far_skill)

        return self.finish_tasks(shot, goal)


@declare_state_machine(GiveAndGo)
class Test_GiveAndGo(StateMachine):
    def hookBeforePlanTasks(self):
        if Global.isPlaySwitched:
            self.start_state.reset()
