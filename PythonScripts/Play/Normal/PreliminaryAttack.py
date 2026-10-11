"""Opt-in preliminary practice: blue 1/2 versus yellow 0.

Set SRC_PRELIM=1 before starting main.py. The yellow strategy is a practice
keeper and is NOT claimed to be the official preliminary opponent.
"""
import json
import math
import time
import CppPackage as C
import Global
from Geometry import CGeoPoint, CVector
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player, Enemy
from WorldModel import Params, Flags, kickStatus
from WorldModel.PowerCalculator import evalPower, P
from Play.Normal.PreliminaryPolicy import Frame, Robot, PreliminaryPolicy, angle_error, direction, distance


def snapshot():
    def robot(n, enemy=False):
        p = Enemy.pos(n) if enemy else Player.pos(n)
        return Robot(p.x(), p.y(), Enemy.dir(n) if enemy else Player.direction(n),
                     False if enemy else Player.isInfraredOn(n))
    p, v = Ball.pos(), Ball.vel()
    return Frame(time.monotonic(), (p.x(), p.y()), (v.x(), v.y()),
                 {n: robot(n) for n in PreliminaryPolicy.IDS if Player.valid(n)},
                 {n: robot(n, True) for n in range(Params.maxPlayer) if Enemy.valid(n)}, Ball.valid())


class AttackState(State):
    def __init__(self):
        super().__init__()
        self.policy = PreliminaryPolicy(Params.pitchLength/2, Params.pitchWidth/2, Params.penaltyDepth)
        self.last_log = 0
        self.last_phase = None

    def getTasks(self):
        f = snapshot()
        actions = self.policy.tick(f)
        for n in self.policy.IDS:
            C.setDribbleCommand(n, 0)
        if f.time-self.last_log > .25 or self.last_phase != self.policy.phase:
            print("PRELIM " + json.dumps({"t": round(f.time, 3), "phase": self.policy.phase,
                  "reason": self.policy.reason, "a": self.policy.attacker, "b": self.policy.receiver,
                  "carry": round(self.policy.carry), "ball": f.ball, "speed": math.hypot(*f.velocity),
                  "ours": {n: (r.x, r.y) for n, r in f.ours.items()},
                  "angles": {n: r.angle for n, r in f.ours.items()},
                  "enemies": {n: r.pos for n, r in f.enemies.items()} }), flush=True)
            self.last_log, self.last_phase = f.time, self.policy.phase
        Global.debugEngine.gui_debug_msg(CGeoPoint(-2000, 2500),
            f"PRELIM {self.policy.phase} A={self.policy.attacker} B={self.policy.receiver} carry={self.policy.carry:.0f}mm", debug_color=1)
        result = {}
        for n, action in actions.items():
            if action.kind == "stop":
                skill = Skill.Stop()
            else:
                target = CGeoPoint(*action.target)
                def execute(executor, action=action, target=target):
                    if action.dribble:
                        C.setDribbleCommand(executor, 3)
                    pos = Player.pos(executor)
                    if action.kind == "kick":
                        # Explicit direction gate; unlike Skill.Shoot, infrared does not bypass it.
                        ball = Ball.pos()
                        angle = direction((ball.x(), ball.y()), action.target)
                        near = pos.dist(Ball.pos()) < 155
                        aligned = angle_error(Player.direction(executor), angle) < .10
                        ball_in_front = angle_error(Player.direction(executor), direction((pos.x(), pos.y()), (ball.x(), ball.y()))) < .25
                        if near and aligned and ball_in_front:
                            # Use the project's calibrated mapping, with a conservative command cap.
                            # This cap is NOT a conversion to the 6.5 m/s rule; telemetry measures speed.
                            power = min(6000, evalPower(Ball.pos(), target, P.NORMAL))
                            kickStatus.setKick(executor, power)
                        destination = CGeoPoint(*self.policy.clamp((ball.x()-85*math.cos(angle), ball.y()-85*math.sin(angle))))
                    else:
                        destination, angle = target, action.angle
                    return C.makeItRushTo(executor, destination, angle,
                        Flags.dodge_our_defense_box, 0, 800, action.dribble, CVector(0, 0))
                skill = execute, lambda executor, target=target: target
            result["A" if n == 1 else "B"] = Task(skill, fixedNumber=n)
        return result

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(AttackState)
class PreliminaryAttack(StateMachine):
    pass


class PracticeKeeperState(State):
    def getTasks(self):
        C.setDribbleCommand(0, 0)
        # Yellow coordinates are normalized too: its own goal is at negative x.
        bx, by = Ball.posX(), Ball.posY()
        y = max(-350, min(350, by*.35))
        x = -Params.pitchLength/2 + 180
        if bx < -2200:
            x += min(450, (-bx-2200)*.3)
        return {"G": Task(Skill.RushTo(CGeoPoint(x, y), angle=0, maxAcc=800), fixedNumber=0)}

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(PracticeKeeperState)
class PreliminaryPracticeKeeper(StateMachine):
    pass
