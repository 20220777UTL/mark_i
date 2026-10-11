"""初版双车：1拿球、2上角 -> 1传2 -> 1下角 -> 2传1 -> 1射门。

从仓库根目录运行 main.py 前设置 SRC_SIMPLE_PASS=1。仅用于蓝队仿真。
1/2 是每轮按球距分配的角色，不是固定机器人号码。
"""
import json
import math
import time

import CppPackage as C
import Global
from Geometry import CGeoPoint, CVector
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player
from WorldModel import Flags, Params, kickStatus

# 可调参数（坐标 mm、角度 rad；力度不是 m/s）。
ROBOT_IDS = (1, 2)
PASS_POWER = 6000
SHOT_POWER = 10000
MAX_ACC = 1000
ARRIVE_DISTANCE = 160
STABLE_SECONDS = .15
STAGE_TIMEOUT = 25
# 仿真多相机帧会偶发单帧 ball.Valid()==False；保留最近一次有效观测，
# 避免起步条件因 0/1 闪烁永远无法稳定。
BALL_GRACE_SECONDS = .30
PLAYER_GRACE_SECONDS = .30


def copy_point(p):
    return CGeoPoint(p.x(), p.y())


def face(a, b):
    return (b - a).dir()


class PassSequence(State):
    def __init__(self):
        super().__init__()
        self.phase = 'wait_ball'
        self.entered = time.monotonic()
        self.stable_since = None
        self.last_log = 0
        self.one, self.two = ROBOT_IDS
        x = Params.pitchLength / 2 - Params.penaltyDepth - 300
        y = Params.penaltyWidth / 2 + 300
        self.upper, self.lower = CGeoPoint(x, y), CGeoPoint(x, -y)
        self.goal = CGeoPoint(Params.pitchLength / 2, -Params.goalWidth * .35)
        self.hold = {}
        self.reason = ''
        self.previous_ball = None
        self.kick_origin = None
        self.last_held_pos = {}
        self.carry = {n: 0.0 for n in ROBOT_IDS}
        self.last_ball_seen = None
        self.last_player_seen = {n: None for n in ROBOT_IDS}

    def transition(self, phase, reason):
        self.phase, self.reason = phase, reason
        self.entered = time.monotonic()
        self.stable_since = None
        self.last_log = 0
        if phase in ('pass_out', 'pass_back', 'shoot'):
            self.kick_origin = None

    def stable(self, condition):
        now = time.monotonic()
        if not condition:
            self.stable_since = None
            return False
        if self.stable_since is None:
            self.stable_since = now
        return now - self.stable_since >= STABLE_SECONDS

    def has_ball(self, n):
        now = time.monotonic()
        if (self.last_ball_seen is None or now - self.last_ball_seen > BALL_GRACE_SECONDS
                or self.last_player_seen[n] is None or now - self.last_player_seen[n] > PLAYER_GRACE_SECONDS):
            return False
        p = Player.pos(n)
        error = math.atan2(math.sin(face(p, Ball.pos()) - Player.direction(n)),
                           math.cos(face(p, Ball.pos()) - Player.direction(n)))
        return p.dist(Ball.pos()) < 115 and (Player.isInfraredOn(n) or abs(error) < .30)

    def arrived(self, n, target):
        return Player.pos(n).dist(target) < ARRIVE_DISTANCE and Player.vel(n).mod() < 250

    def move(self, n, target, look_at, dribble=False):
        angle = face(Player.pos(n), look_at)
        return self.rush(target, angle, dribble, 0 if dribble else Flags.dodge_ball)

    def rush(self, target, angle, dribble, flag=0):
        # 直接调用底层 RushTo，显式控制吸球，减少本轮动作的隐式注册。
        def execute(n):
            C.setDribbleCommand(n, 3 if dribble else 0)
            return C.makeItRushTo(n, target, angle, flag, 0, MAX_ACC, dribble, CVector(0, 0))
        return execute, lambda n: target

    def hold_ball(self, n, look_at):
        if not self.has_ball(n):
            # 等待队友时若球滑开，先重新贴近球，再更新停球位置。
            self.hold[n] = copy_point(Player.pos(n))
            return self.collect(n, face(Ball.pos(), look_at))
        return self.move(n, self.hold[n], look_at, True)

    def receive(self, n, point):
        if Player.pos(n).dist(Ball.pos()) < 650:
            return self.collect(n, face(Player.pos(n), Ball.pos()))
        # 保守传球可能在接球点前方提前停下。球已慢下来时，接球队员
        # 直接追球，而不是一直守在原定接球点。
        if Ball.velMod() < 180:
            return self.collect(n, face(Player.pos(n), Ball.pos()))
        return self.move(n, point, Ball.pos(), True)

    def collect(self, n, angle):
        # 初测高层组合出现过原生堆错误；本版使用已实测的基础移动接球。
        b = Ball.pos()
        point = CGeoPoint(b.x()-85*math.cos(angle), b.y()-85*math.sin(angle))
        return self.rush(point, angle, True)

    def kick(self, target, power):
        def execute(n):
            b, p = Ball.pos(), Player.pos(n)
            angle = face(b, target)
            angle_error = abs(math.atan2(math.sin(angle-Player.direction(n)), math.cos(angle-Player.direction(n))))
            front_error = abs(math.atan2(math.sin(face(p,b)-Player.direction(n)), math.cos(face(p,b)-Player.direction(n))))
            C.setDribbleCommand(n, 3)
            if p.dist(b) < 110 and angle_error < .12 and front_error < .30:
                if self.kick_origin is None:
                    self.kick_origin = copy_point(b)
                kickStatus.setKick(n, power)
            behind = CGeoPoint(b.x()-85*math.cos(angle), b.y()-85*math.sin(angle))
            return C.makeItRushTo(n, behind, angle, 0, 0, MAX_ACC, True, CVector(0,0))
        return execute, lambda n: target

    def getTasks(self):
        now = time.monotonic()
        if Ball.valid():
            self.last_ball_seen = now
        for n in ROBOT_IDS:
            if Player.valid(n):
                self.last_player_seen[n] = now
        for n in ROBOT_IDS:
            C.setDribbleCommand(n, 0)
        actions = {n: Skill.Stop() for n in ROBOT_IDS}
        ball_recent = self.last_ball_seen is not None and now - self.last_ball_seen <= BALL_GRACE_SECONDS
        players_recent = all(self.last_player_seen[n] is not None and now - self.last_player_seen[n] <= PLAYER_GRACE_SECONDS
                             for n in ROBOT_IDS)
        valid = ball_recent and players_recent

        if self.phase == 'wait_ball':
            # 替换场景后滤波速度可在静止球上短暂抖动。球和两车
            # 连续可见一小段时间后开始；后续阶段仍确认到位与持球。
            if self.stable(valid):
                self.one, self.two = sorted(ROBOT_IDS, key=lambda n: (Player.pos(n).dist(Ball.pos()), n))
                self.transition('get_ball', 'roles assigned by distance')
        elif self.phase not in ('done', 'fault'):
            if not valid:
                self.stable_since = None
                if now - self.entered > STAGE_TIMEOUT:
                    self.transition('fault', 'vision unavailable')
            elif now - self.entered > STAGE_TIMEOUT:
                self.transition('fault', 'stage timed out')
            else:
                a, b = self.one, self.two
                if self.phase == 'get_ball':
                    actions[a] = self.collect(a, face(Ball.pos(), self.upper))
                    actions[b] = self.move(b, self.upper, Ball.pos())
                    if self.stable(self.has_ball(a)):
                        self.hold[a] = copy_point(Player.pos(a))
                        self.transition('wait_upper', 'role 1 has ball')
                elif self.phase == 'wait_upper':
                    actions[a] = self.hold_ball(a, self.upper)
                    actions[b] = self.move(b, self.upper, Ball.pos())
                    if self.stable(self.arrived(b, self.upper) and self.has_ball(a)):
                        self.transition('pass_out', 'role 2 ready at upper corner')
                elif self.phase == 'pass_out':
                    actions[a] = self.kick(self.upper, PASS_POWER)
                    actions[b] = self.move(b, self.upper, Ball.pos(), True)
                    if self.kick_origin is not None and Ball.pos().dist(self.kick_origin) > 160 and Ball.velMod() > 150:
                        self.transition('receive_upper', 'first pass left role 1')
                elif self.phase == 'receive_upper':
                    actions[b] = self.receive(b, self.upper)
                    if self.stable(self.has_ball(b)):
                        self.hold[b] = copy_point(Player.pos(b))
                        self.carry[b] = 0
                        self.transition('run_lower', 'role 2 received first pass')
                elif self.phase == 'run_lower':
                    actions[a] = self.move(a, self.lower, Ball.pos())
                    actions[b] = self.hold_ball(b, self.lower)
                    if self.stable(self.arrived(a, self.lower) and self.has_ball(b)):
                        self.transition('pass_back', 'role 1 ready at lower corner')
                elif self.phase == 'pass_back':
                    actions[b] = self.kick(self.lower, PASS_POWER)
                    actions[a] = self.move(a, self.lower, Ball.pos(), True)
                    if self.kick_origin is not None and Ball.pos().dist(self.kick_origin) > 160 and Ball.velMod() > 150:
                        self.transition('receive_lower', 'return pass left role 2')
                elif self.phase == 'receive_lower':
                    actions[a] = self.receive(a, self.lower)
                    if self.stable(self.has_ball(a)):
                        self.carry[a] = 0
                        self.transition('aim_shot', 'role 1 received return pass')
                elif self.phase == 'aim_shot':
                    angle = face(Ball.pos(), self.goal)
                    behind = CGeoPoint(Ball.posX()-250*math.cos(angle), Ball.posY()-250*math.sin(angle))
                    actions[a] = self.rush(behind, angle, False, Flags.dodge_ball)
                    error = abs(math.atan2(math.sin(angle-Player.direction(a)), math.cos(angle-Player.direction(a))))
                    if self.stable(Player.pos(a).dist(behind) < 80 and error < .18):
                        self.transition('shoot', 'role 1 aligned behind ball')
                elif self.phase == 'shoot':
                    actions[a] = self.kick(self.goal, SHOT_POWER)
                    if self.kick_origin is not None and Ball.pos().dist(self.kick_origin) > 160 and Ball.velMod() > 150:
                        self.transition('shot_flight', 'role 1 shot')
                elif self.phase == 'shot_flight':
                    old = self.previous_ball
                    p = Ball.pos()
                    goal_x = Params.pitchLength / 2
                    if old and old.x() < goal_x <= p.x():
                        y = old.y() + (p.y()-old.y())*(goal_x-old.x())/(p.x()-old.x())
                        crossed = abs(y) < Params.goalWidth/2 - 22
                        self.transition('done', 'ball crossed goal mouth' if crossed else 'shot missed goal mouth')
                    elif now-self.entered > 5:
                        self.transition('done', 'shot ended; goal not confirmed')

        if valid and self.phase not in ('done', 'fault', 'wait_ball', 'shot_flight'):
            for n in ROBOT_IDS:
                p = Player.pos(n)
                if p.x() > Params.pitchLength/2-Params.penaltyDepth-100 and abs(p.y()) < Params.penaltyWidth/2+100:
                    self.transition('fault', 'robot approached opponent penalty area')
                if self.has_ball(n):
                    previous = self.last_held_pos.get(n)
                    if previous:
                        self.carry[n] += previous.dist(p)
                    self.last_held_pos[n] = copy_point(p)
                else:
                    self.last_held_pos.pop(n, None)
                if self.carry[n] > 800:
                    self.transition('fault', 'carrying distance reached 800 mm')
        if self.phase in ('done', 'fault'):
            actions = {n: Skill.Stop() for n in ROBOT_IDS}
        if now-self.last_log > .5:
            status = dict(t=round(now,3),phase=self.phase,reason=self.reason,
                  role1=self.one,role2=self.two,ball=[Ball.posX(),Ball.posY()],
                  robots={n:[Player.pos(n).x(),Player.pos(n).y(),Player.direction(n)] for n in ROBOT_IDS},
                  carry=self.carry,ball_raw=Ball.valid(),ball_recent=ball_recent,
                  players_raw={n: Player.valid(n) for n in ROBOT_IDS},players_recent=players_recent)
            print('SIMPLE_PASS '+json.dumps(status),flush=True)
            self.last_log = now
        Global.debugEngine.gui_debug_msg(CGeoPoint(-2000,2600),f'{self.phase} role1={self.one} role2={self.two}',debug_color=1)
        if Ball.valid():
            self.previous_ball = copy_point(Ball.pos())
        return {'A' if n == 1 else 'B': Task(actions[n],fixedNumber=n) for n in ROBOT_IDS}

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''


@declare_state_machine(PassSequence)
class SimplePassPlay(StateMachine):
    pass
