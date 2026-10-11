"""初赛双车：1 拿球、2 上角 → 1 传 2 → 1 下角 → 2 传 1 → 1 再传 2 → 2 射门。

球权是 1 → 2 → 1 → 2 → 射门。1/2 是每轮按离球距离分配的角色，不是固定车号。
从仓库根目录运行 main.py 前设置 SRC_SIMPLE_PASS=1。仅用于蓝队仿真。
"""
import json
import time

import CppPackage as C
import Global
from Geometry import CGeoPoint, CVector
from Play.Normal.TwoPlayerPolicy import Frame, Robot, TwoPlayerPolicy
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Enemy, Player
from WorldModel import Flags, Params, kickStatus

ROBOT_IDS = (1, 2)
# 仿真多相机偶发单帧 Valid()==False。短时沿用上一帧，超时后两车 Stop()。
VISION_GRACE = 0.30
LOG_PERIOD = 0.50


def _robot(n):
    pos = Player.pos(n)
    return Robot(pos.x(), pos.y(), Player.direction(n), Player.isInfraredOn(n), Player.vel(n).mod())


class PassSequence(State):
    def __init__(self):
        super().__init__()
        self.policy = TwoPlayerPolicy(
            Params.pitchLength / 2, Params.pitchWidth / 2, Params.penaltyDepth,
            Params.penaltyWidth, Params.goalWidth)
        self.cache = None
        self.last_log = 0.0
        self.reported = False
        self.peak_m_s = 0.0

    def _frame(self, now):
        ball_ok = Ball.valid()
        players_ok = all(Player.valid(n) for n in ROBOT_IDS)
        if ball_ok and players_ok:
            enemies = {}
            if Enemy.valid(0):
                pos = Enemy.pos(0)
                enemies[0] = Robot(pos.x(), pos.y(), Enemy.dir(0), speed=Enemy.vel(0).mod())
            frame = Frame(now, (Ball.posX(), Ball.posY()), (Ball.velX(), Ball.velY()),
                          {n: _robot(n) for n in ROBOT_IDS}, enemies, True)
            self.cache = (now, frame)
            speed = Ball.velMod() / 1000
            if speed > 0.4:
                self.peak_m_s = max(self.peak_m_s, speed)
            return frame
        if self.cache is not None and now - self.cache[0] <= VISION_GRACE:
            cached = self.cache[1]
            return Frame(now, cached.ball, cached.velocity, cached.ours, cached.enemies, True)
        return Frame(now, (0.0, 0.0), (0.0, 0.0), {}, {}, False)

    def _skill(self, action):
        if action.kind == 'stop':
            return Skill.Stop()
        # 按 RushTo(pos, angle, maxAcc=1000, flag, needDribble, vel, registerRole="", sender=0) 下发。
        # Skill.RushTo 会丢掉 registerRole 并强制注册 fetchBall，两车同时注册会触发已经出现过的原生错误。
        pos = CGeoPoint(float(action.pos[0]), float(action.pos[1]))
        angle = float(action.angle)
        flag = Flags.dodge_ball if action.dodge else 0
        dribble = bool(action.dribble)
        power = None if action.power is None else float(action.power)
        vel = CVector(0, 0)

        def execute(n, pos=pos, angle=angle, flag=flag, dribble=dribble, power=power, vel=vel):
            C.setDribbleCommand(n, 3 if dribble else 0)
            if power is not None:
                kickStatus.setKick(n, power)
            return C.makeItRushTo(n, pos, angle, flag, 0, 1000, dribble, vel)

        return execute, (lambda n, pos=pos: pos)

    def _result(self):
        policy = self.policy
        return {
            'ok': policy.phase == 'done' and policy.reason == 'ball crossed goal line',
            'phase': policy.phase,
            'reason': policy.reason,
            'passes': policy.passes,
            'shooter_role': 2 if policy.shooter_id is not None else None,
            'shooter_id': policy.shooter_id,
            'role1': policy.role1,
            'role2': policy.role2,
            'pass_shift_mm': policy.pass_shifts,
            'setup_mm': policy.setup_mm,
            'shot_shift_mm': policy.shot_shift,
            'peak_m_s': round(max(self.peak_m_s, policy.peak_m_s), 3),
            'kick_peaks_m_s': policy.kick_peaks,
            'ball': [round(v, 1) for v in policy.previous_ball] if policy.previous_ball else None,
        }

    def getTasks(self):
        now = time.monotonic()
        for n in ROBOT_IDS:
            C.setDribbleCommand(n, 0)
        frame = self._frame(now)
        actions = self.policy.tick(frame)
        if self.policy.phase in ('done', 'fault') and not self.reported:
            self.reported = True
            print('SIMPLE_PASS_RESULT ' + json.dumps(self._result()), flush=True)
        if now - self.last_log > LOG_PERIOD:
            robots = {}
            if frame.valid:
                robots = {str(n): [round(r.x, 1), round(r.y, 1), round(r.angle, 3)] for n, r in frame.ours.items()}
            print('SIMPLE_PASS ' + json.dumps({
                't': round(now, 3), 'phase': self.policy.phase, 'reason': self.policy.reason,
                'role1': self.policy.role1, 'role2': self.policy.role2, 'passes': self.policy.passes,
                'shift_mm': round(self.policy.possession_shift, 1), 'pass_shift_mm': self.policy.pass_shifts,
                'peak_m_s': round(max(self.peak_m_s, self.policy.peak_m_s), 3),
                'ball': [round(v, 1) for v in frame.ball] if frame.valid else None,
                'keeper': [round(frame.enemies[0].x, 1), round(frame.enemies[0].y, 1)] if 0 in frame.enemies else None,
                'ball_speed': round(hypot_speed(frame), 3), 'robots': robots,
                'hold': {str(n): [round(p[0], 1), round(p[1], 1)] for n, p in self.policy.hold.items()},
            }), flush=True)
            self.last_log = now
        if frame.valid:
            Global.debugEngine.gui_debug_msg(
                CGeoPoint(-2000, 2600),
                f'{self.policy.phase} role1={self.policy.role1} role2={self.policy.role2}',
                debug_color=1)
        return {'A' if n == 1 else 'B': Task(self._skill(actions[n]), fixedNumber=n) for n in ROBOT_IDS}

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''


def hypot_speed(frame):
    return (frame.velocity[0] ** 2 + frame.velocity[1] ** 2) ** 0.5 / 1000


@declare_state_machine(PassSequence)
class SimplePassPlay(StateMachine):
    pass
