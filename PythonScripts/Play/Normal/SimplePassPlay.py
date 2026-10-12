"""SRC 初赛 NormalPlay：两车两次传球，由角色 1 射门。

每个比赛阶段都是 RoleMatch_LuaStyle.State；transFunction 返回下一状态名。
角色 1/2 在每回合球静止后按离球距离确定，本回合不重新匹配。
"""
import json
import subprocess
import time
from math import hypot
from pathlib import Path

import CppPackage as C
import Global
from Geometry import CGeoPoint, CVector
from Play.Normal.TwoPlayerPolicy import Action, Frame, Robot, TwoPlayerPolicy, distance
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Enemy, Player
from WorldModel import Flags, Params, kickStatus
from WorldModel.PowerCalculator import P, evalPower


VISION_GRACE_SECONDS = 0.30
LOG_PERIOD_SECONDS = 0.50
BALL_SETTLED_MM_S = 120


def _robot(number):
    point = Player.pos(number)
    return Robot(point.x(), point.y(), Player.direction(number),
                 Player.isInfraredOn(number), Player.vel(number).mod())


class AttackSession:
    """One attack's shared data. The framework State instances own the transitions."""

    def __init__(self):
        self.round_number = 0
        self.finished_rounds = 0
        self.goals = 0
        self.last_result = None
        self.last_log = 0.0
        self.scene_prepared = False
        self.reset()

    def reset(self):
        self.ids = None
        self.policy = None
        self.cached_frame = None
        self.frame = None
        self.actions = {}
        self.reported = False
        self.recovery_started = None
        self.recovery_ball = None
        self.peak_m_s = 0.0

    def _new_policy(self, ids):
        self.ids = tuple(ids)
        self.policy = TwoPlayerPolicy(
            Params.pitchLength / 2, Params.pitchWidth / 2,
            Params.penaltyDepth, Params.penaltyWidth, Params.goalWidth,
            ids=self.ids)
        self.round_number += 1
        print(f'PRELIM_ROUND {self.round_number} cars={self.ids}', flush=True)

    def observe(self, *, allow_new_policy=True):
        now = time.monotonic()
        available = tuple(sorted(int(n) for n in Player.getAllValidNumbers()))
        if allow_new_policy and self.policy is None and len(available) == 2 and Ball.valid():
            self._new_policy(available)
        ids = self.ids or available
        if Ball.valid() and all(Player.valid(n) for n in ids):
            enemies = {}
            for n in range(Params.maxPlayer):
                if Enemy.valid(n):
                    point = Enemy.pos(n)
                    enemies[n] = Robot(point.x(), point.y(), Enemy.dir(n),
                                       speed=Enemy.vel(n).mod())
            frame = Frame(now, (Ball.posX(), Ball.posY()), (Ball.velX(), Ball.velY()),
                          {n: _robot(n) for n in ids}, enemies, bool(ids))
            self.cached_frame = (now, frame)
            self.peak_m_s = max(self.peak_m_s, hypot(*frame.velocity) / 1000)
        elif self.cached_frame is not None and now - self.cached_frame[0] <= VISION_GRACE_SECONDS:
            old = self.cached_frame[1]
            frame = Frame(now, old.ball, old.velocity, old.ours, old.enemies, True)
        else:
            frame = Frame(now, (0.0, 0.0), (0.0, 0.0), {}, {}, False)
        self.frame = frame
        return frame, available

    def step(self):
        if Global.autoPreparePreliminaryScene and not self.scene_prepared:
            # Medusa's embedded Winsock state rejects Python socket.sendto
            # (WSAEFAULT). Run the existing scene sender in its venv instead.
            root = Path(__file__).resolve().parents[3]
            subprocess.run(
                [str(root / 'PythonScripts' / '.venv' / 'Scripts' / 'python.exe'),
                 str(root / 'PythonScripts' / 'tools' / 'preliminary_scene.py')],
                cwd=root, check=True, timeout=5)
            self.scene_prepared = True
            print('PRELIM_SCENE blue=1,2 yellow=0 ball=(1800,550)', flush=True)
        frame, available = self.observe()
        for n in self.ids or available:
            C.setDribbleCommand(n, 0)
        if self.policy is None:
            self.actions = {n: Action('stop') for n in available}
        else:
            self.actions = self.policy.tick(frame)
            self._report_if_finished()
            self._show_debug()
        return self.tasks()

    def tasks(self):
        return {
            chr(ord('A') + index): Task(self._skill(action), fixedNumber=number)
            for index, (number, action) in enumerate(sorted(self.actions.items()))
        }

    def _skill(self, action):
        if action.kind == 'stop':
            return Skill.Stop()
        point = CGeoPoint(float(action.pos[0]), float(action.pos[1]))
        angle = float(action.angle)
        flag = Flags.dodge_ball if action.dodge else 0
        dribble = bool(action.dribble)
        kick_target = (CGeoPoint(*action.kick_target)
                       if action.kick_target is not None else None)
        kick_ceiling = action.power
        # This pair is a normal Skill/Task interface. It avoids the current
        # Skill.RushTo wrapper, which registers both attackers as fetchBall.
        def execute(number):
            C.setDribbleCommand(number, 3 if dribble else 0)
            if kick_ceiling is not None and kick_target is not None:
                level = P.HIGH if self.policy.phase == 'shoot' else P.NORMAL
                origin = Ball.pos()
                power_target = kick_target
                if level is P.HIGH:
                    # Ask the shared power curve for a point past the goal
                    # line; the aiming point itself stays inside the goal.
                    dx = kick_target.x() - origin.x()
                    dy = kick_target.y() - origin.y()
                    scale = 1.0 + 2000.0 / max(hypot(dx, dy), 1.0)
                    power_target = CGeoPoint(origin.x() + dx * scale,
                                             origin.y() + dy * scale)
                calculated = evalPower(origin, power_target, level)
                command = min(float(kick_ceiling), float(calculated))
                if command > 0:
                    kickStatus.setKick(number, command)
            return C.makeItRushTo(number, point, angle, flag, 0, 1000,
                                  dribble, CVector(0, 0))

        return execute, (lambda number, point=point: point)

    def next_state(self, current):
        if self.policy is None:
            return ''
        if self.policy.phase in ('done', 'fault'):
            return 'recover'
        return self.policy.phase if self.policy.phase != current else ''

    def recover(self):
        frame, available = self.observe(allow_new_policy=False)
        self._show_result()
        for n in self.ids or available:
            C.setDribbleCommand(n, 0)
        self.actions = {n: Action('stop') for n in self.ids or available}
        if self.recovery_started is None:
            self.recovery_started = frame.time
            self.recovery_ball = self.policy.previous_ball if self.policy else None
        return self.tasks()

    def ready_for_new_round(self):
        frame = self.frame
        if frame is None or not frame.valid or self.policy is None:
            return False
        if len(Player.getAllValidNumbers()) != 2:
            return False
        if hypot(*frame.velocity) > BALL_SETTLED_MM_S:
            return False
        if (abs(frame.ball[0]) > self.policy.limit_x or
                abs(frame.ball[1]) > self.policy.limit_y or
                self.policy.inside(frame.ball) or
                self.policy.inside_own(frame.ball)):
            return False
        elapsed = frame.time - self.recovery_started
        moved = (self.recovery_ball is None or
                 distance(frame.ball, self.recovery_ball) > 250)
        if self.policy.phase == 'done':
            return moved and elapsed > 0.3
        return elapsed > 1.0 and (moved or self.policy.reason not in
                                  ('vision unavailable', 'attacker entered a penalty area'))

    def _report_if_finished(self):
        policy = self.policy
        if self.reported or policy.phase not in ('done', 'fault'):
            return
        self.reported = True
        self.finished_rounds += 1
        scored = policy.phase == 'done'
        if scored:
            self.goals += 1
        self.last_result = (f'GOAL!  Round {self.round_number}' if scored else
                            f'NO GOAL  Round {self.round_number}')
        print('PRELIM_RESULT ' + json.dumps({
            'round': self.round_number,
            'ok': policy.phase == 'done',
            'reason': policy.reason,
            'role1': policy.role1,
            'role2': policy.role2,
            'passes': policy.passes,
            'shooter': policy.shooter_id,
            'peak_m_s': round(max(self.peak_m_s, policy.peak_m_s), 3),
            'peak_carry_mm': {str(n): round(x, 1)
                              for n, x in policy.peak_carried_mm.items()},
        }), flush=True)

    def _show_debug(self):
        policy = self.policy
        self._show_result()
        if self.frame.time - self.last_log > LOG_PERIOD_SECONDS:
            print('PRELIM ' + json.dumps({
                'round': self.round_number,
                'phase': policy.phase,
                'role1': policy.role1,
                'role2': policy.role2,
                'passes': policy.passes,
                'ball': [round(x, 1) for x in self.frame.ball],
                'ball_m_s': round(hypot(*self.frame.velocity) / 1000, 3),
                'robots': {str(n): [round(r.x), round(r.y), round(r.angle, 2)]
                           for n, r in self.frame.ours.items()},
                'targets': {str(n): [round(x) for x in action.pos]
                            for n, action in self.actions.items() if action.kind != 'stop'},
                'hold': {str(n): [round(x) for x in p]
                         for n, p in policy.hold.items()},
                'carry_mm': {str(n): round(x) for n, x in policy.carried_mm.items()},
                'reason': policy.reason,
            }), flush=True)
            self.last_log = self.frame.time
        Global.debugEngine.gui_debug_msg(
            CGeoPoint(-2000, 2600),
            f'Round {self.round_number}: {policy.phase} '
            f'role1={policy.role1} role2={policy.role2} passes={policy.passes}',
            debug_color=1)

    def _show_result(self):
        # The Client's white background can use a different visual scale.
        # Draw the small field, goal, and penalty area used by this practice play.
        goal_x = Params.pitchLength / 2
        half_width = Params.pitchWidth / 2
        penalty_x = goal_x - Params.penaltyDepth
        penalty_half_width = Params.penaltyWidth / 2
        field_corners = (
            (-goal_x, -half_width),
            (goal_x, -half_width),
            (goal_x, half_width),
            (-goal_x, half_width),
        )
        for first, second in zip(field_corners, field_corners[1:] + field_corners[:1]):
            Global.debugEngine.gui_debug_line(CGeoPoint(*first), CGeoPoint(*second), debug_color=5)
        corners = (
            (penalty_x, -penalty_half_width),
            (goal_x, -penalty_half_width),
            (goal_x, penalty_half_width),
            (penalty_x, penalty_half_width),
        )
        for first, second in zip(corners, corners[1:] + corners[:1]):
            Global.debugEngine.gui_debug_line(CGeoPoint(*first), CGeoPoint(*second), debug_color=5)
        Global.debugEngine.gui_debug_line(
            CGeoPoint(goal_x, -Params.goalWidth / 2),
            CGeoPoint(goal_x, Params.goalWidth / 2), debug_color=4)
        Global.debugEngine.gui_debug_msg(
            CGeoPoint(penalty_x - 350, penalty_half_width + 300),
            '9x6 GOAL / PENALTY', debug_color=5, size=145, weight=75)
        Global.debugEngine.gui_debug_msg(
            CGeoPoint(1800, 2600),
            f'GOALS {self.goals}/{self.finished_rounds}',
            debug_color=4, size=220, weight=75)
        if self.last_result is not None:
            Global.debugEngine.gui_debug_msg(
                CGeoPoint(1800, 2250), self.last_result,
                debug_color=4 if self.last_result.startswith('GOAL!') else 1,
                size=180, weight=75)


class AttackState(State):
    phase_name = ''

    def __init__(self):
        super().__init__(self.phase_name)
        self.session = None

    def getTasks(self):
        return self.session.step()

    def getMatchString(self):
        # Each round chooses the nearer car once. Task.fixedNumber then locks it.
        return ''

    def transFunction(self):
        return self.session.next_state(self.phase_name)


class Assign(AttackState):
    phase_name = 'assign'


class GetBall(AttackState):
    phase_name = 'get_ball'


class WaitUpper(AttackState):
    phase_name = 'wait_upper'


class Pass1(AttackState):
    phase_name = 'pass_1'


class Receive1(AttackState):
    phase_name = 'receive_1'


class RunLower(AttackState):
    phase_name = 'run_lower'


class Pass2(AttackState):
    phase_name = 'pass_2'


class Receive2(AttackState):
    phase_name = 'receive_2'


class Shoot(AttackState):
    phase_name = 'shoot'


class ShotFlight(AttackState):
    phase_name = 'shot_flight'


class Recover(State):
    def __init__(self):
        super().__init__('recover')
        self.session = None

    def getTasks(self):
        return self.session.recover()

    def getMatchString(self):
        return ''

    def transFunction(self):
        if not self.session.ready_for_new_round():
            return ''
        self.session.reset()
        return 'assign'


@declare_state_machine(
    Assign, GetBall, WaitUpper, Pass1, Receive1, RunLower,
    Pass2, Receive2, Shoot, ShotFlight, Recover)
class SimplePassPlay(StateMachine):
    def __init__(self):
        super().__init__()
        self.session = AttackSession()
        self._session_attached = False

    def planTasks(self):
        if not self._session_attached:
            for state in self.state_instances:
                state.session = self.session
            self._session_attached = True
        if Global.isPlaySwitched:
            self.session.reset()
        super().planTasks()
