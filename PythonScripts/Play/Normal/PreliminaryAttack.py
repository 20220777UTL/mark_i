"""Initial 2v1 baseline: one shooter plus one supporting robot.
Edit this file for competition tactics. This is a tested starting point,
not a guarantee of competition scoring or calibrated real-robot kick speed.
"""
import json
import time
from pathlib import Path
import Global
from Geometry import CGeoPoint
from Vision import Ball, Player, vision
from Utils import DebugColor
from WorldModel import Params
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import NormalShoot, RushTo, Stop
from Play.Normal.GoalieFool import GoalieFool

ATTACKERS = (0, 1)
SHOT_POWER = 5000  # Skill power, NOT metres/second. Calibrate on real hardware.

class Attack(State):
    def __init__(self):
        super().__init__()
        self.striker = ATTACKERS[0]

    def draw_roles(self, available, target=None, stopped_reason=None):
        """Draw current roles and the actual RushTo target; never send motion commands."""
        debug = Global.debugEngine
        for number in available:
            shooter = number == self.striker
            label = 'Shooter' if shooter else 'Support'
            color = DebugColor.Orange if shooter else DebugColor.Cyan
            pos = Player.Pos(number)
            offset_y = 260 if shooter else -360
            label_pos = CGeoPoint(max(-4200, min(3200, pos.x() - 180)),
                                 max(-2750, min(2750, pos.y() + offset_y)))
            suffix = ' [STOP]' if stopped_reason else ''
            debug.gui_debug_msg(label_pos, f'{label} #{number}{suffix}',
                                debug_color=color, size=160, weight=75)
            if not shooter and target is not None:
                debug.gui_debug_line(pos, target, debug_color=DebugColor.Cyan)
        if target is not None:
            # A cross marks the exact target; the line joins it to the support robot.
            debug.gui_debug_x(target, debug_color=DebugColor.Green)
            debug.gui_debug_line(CGeoPoint(target.x()-100, target.y()),
                                 CGeoPoint(target.x()+100, target.y()), debug_color=DebugColor.Green)
            debug.gui_debug_line(CGeoPoint(target.x(), target.y()-100),
                                 CGeoPoint(target.x(), target.y()+100), debug_color=DebugColor.Green)
            debug.gui_debug_msg(CGeoPoint(target.x()-350, target.y()-300),
                                f'Target ({target.x():.0f}, {target.y():.0f}) mm',
                                debug_color=DebugColor.Green, size=160, weight=75)
        if stopped_reason:
            debug.gui_debug_msg(CGeoPoint(-4200, -2600), f'Attack STOP: {stopped_reason}',
                                debug_color=DebugColor.Orange, size=160)

    def getTasks(self):
        available = [n for n in ATTACKERS if Player.isValid(n)]
        if not available:
            return {}
        if not vision.ball().Valid():
            self.draw_roles(available, stopped_reason='ball not visible')
            return {role: Task(Stop(), fixedNumber=n) for role, n in zip(('A','B'), available)}
        nearest = min(available, key=Player.toBallDist)
        if self.striker not in available or Player.toBallDist(nearest) + 600 < Player.toBallDist(self.striker):
            self.striker = nearest
        ball = Ball.pos()
        # Wait when the ball is out or in either penalty area; do not chase into it.
        out = abs(ball.x()) > Params.pitchLength/2 or abs(ball.y()) > Params.pitchWidth/2
        penalty = abs(ball.x()) > Params.pitchLength/2 - Params.penaltyDepth - 150 and abs(ball.y()) < Params.penaltyWidth/2 + 150
        if out or penalty:
            self.draw_roles(available, stopped_reason='ball out' if out else 'ball near penalty area')
            return {role: Task(Stop(), fixedNumber=n) for role, n in zip(('A','B'), available)}
        tasks = {'A': Task(NormalShoot(SHOT_POWER, False), fixedNumber=self.striker)}
        others = [n for n in available if n != self.striker]
        target = None
        if others:
            y = -1500 if ball.y() >= 0 else 1500
            x = max(-2800, min(2800, ball.x() - 800))
            target = CGeoPoint(x,y)
            tasks['B'] = Task(RushTo(target, angle=0, maxAcc=1500), fixedNumber=others[0])
        self.draw_roles(available, target=target)
        return tasks

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''

class Telemetry:
    def hookAfterPlanTasks(self):
        now = time.monotonic()
        if now - getattr(self, '_last_log', 0) < 1:
            return
        self._last_log = now
        b = Ball.pos()
        sample = {'time': time.time(), 'team': 'yellow' if Global.isYellow else 'blue',
                  'play': self.name, 'cycle': vision.getCycle(), 'ball': [b.x(), b.y()],
                  'robots': {str(n): [Player.Pos(n).x(), Player.Pos(n).y()] for n in ((0,) if Global.isYellow else ATTACKERS) if Player.isValid(n)}}
        logfile = 'LOG/prelim_yellow.jsonl' if Global.isYellow else 'LOG/prelim_blue.jsonl'
        with Path(logfile).open('a', encoding='utf-8') as f:
            f.write(json.dumps(sample) + '\n')

@declare_state_machine(Attack)
class PreliminaryAttack(Telemetry, StateMachine):
    pass

class Move(State):
    def getTasks(self):
        return {'A': Task(RushTo(CGeoPoint(0,600), angle=0, maxAcc=1000), fixedNumber=ATTACKERS[0]),
                'B': Task(RushTo(CGeoPoint(0,-600), angle=0, maxAcc=1000), fixedNumber=ATTACKERS[1])}

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''

@declare_state_machine(Move)
class MoveCheck(Telemetry, StateMachine):
    pass

class PracticeGoalie(Telemetry, GoalieFool):
    pass
