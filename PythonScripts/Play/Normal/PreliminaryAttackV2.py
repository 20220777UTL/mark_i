"""Native adapter for the preliminary V2 planner. Baseline remains separate."""
import json
import time
from pathlib import Path
import CppPackage
import Global
from Geometry import CGeoPoint
from Vision import Ball, Player, Enemy, vision
from Utils import DebugColor
from WorldModel import Params, Flags, kickStatus
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import RushTo, Stop, NormalShoot
from .prelim_v2_logic import Controller, Settings, Frame, Robot, direction, distance, angle_error

ATTACKERS = (0, 1)

def point(p):
    return CGeoPoint(*p)

def xy(p):
    return (p.x(), p.y())

def explicit_move(command):
    """Non-shooting movement only; the supplied NormalShoot owns all shooting."""
    target = point(command.target)
    flags = Flags.allow_dss | Flags.dodge_our_defense_box
    if not command.dribble:
        flags |= Flags.dodge_ball
    skill, match = RushTo(target, angle=command.heading, maxAcc=1200,
                         flag=flags,
                         needDribble=command.dribble)
    def run(number):
        CppPackage.setDribbleCommand(number, 3 if command.dribble else 0)
        return skill(number)
    return run, match

class AttackV2(State):
    def __init__(self):
        super().__init__()
        self.controller = Controller(Settings(
            attackers=ATTACKERS, half_length=Params.pitchLength/2,
            half_width=Params.pitchWidth/2, penalty_depth=Params.penaltyDepth,
            penalty_half_width=Params.penaltyWidth/2, goal_half_width=Params.goalWidth/2,
            robot_radius=Params.playerRadius))
        self.last_log = 0
        self.last_phase = None
        self.last_reset_cycle = None
        self.last_native_log = {}

    def getTasks(self):
        cycle = vision.getCycle()
        if Global.isPlaySwitched and cycle != self.last_reset_cycle:
            self.controller.reset()
            self.last_reset_cycle = cycle
        own = {n: Robot(xy(Player.Pos(n)), Player.direction(n), bool(Player.isInfraredOn(n)),
                        bool(Player.isBallKicked(n)))
               for n in ATTACKERS if Player.isValid(n)}
        opponents = {n: Robot(xy(Enemy.pos(n)), Enemy.dir(n))
                     for n in range(Params.maxPlayer) if Enemy.valid(n)}
        valid = bool(vision.ball().Valid())
        frame = Frame(time.monotonic(), xy(Ball.pos()), xy(Ball.vel()), own, opponents, valid, cycle)
        plan = self.controller.step(frame)
        tasks = {}
        # Explicitly clear dribble as well as kicks, including when a robot disappears.
        kickStatus.clearAll()
        for n in ATTACKERS:
            CppPackage.setDribbleCommand(n, 0)
            command = plan.commands[n]
            tasks[f'V2_{n}'] = Task(self.skill_for(command, frame), fixedNumber=n)
        self.draw(frame, plan)
        self.log(frame, plan)
        return tasks

    def skill_for(self, command, frame):
        if command.kind == 'stop':
            return Stop()
        if command.kind != 'normal_shoot':
            return explicit_move(command)
        skill, match = NormalShoot(command.power, flag=Flags.allow_dss | Flags.dodge_our_defense_box)
        def run(number):
            value = skill(number)
            if frame.time-self.last_native_log.get(number, -1e9) >= .1:
                self.last_native_log[number] = frame.time
                # Task construction is not proof of a sent UDP packet or a physical kick.
                record = dict(time=time.time(), cycle=frame.cycle, version='2.2', robot=number,
                    stage='after_NormalShoot_task_construction', requested_power=command.power,
                    need_kick=bool(kickStatus.needKick(number)), kick_power=kickStatus.getKickPower(number),
                    force_closed=bool(kickStatus.isForceClosed()),
                    infrared=frame.own[number].infrared, kick_feedback=frame.own[number].kicked)
                with Path('LOG/prelim_v2_native_blue.jsonl').open('a',encoding='utf-8') as output:
                    output.write(json.dumps(record)+'\n')
            return value
        return run, match

    def draw(self, frame, plan):
        debug = Global.debugEngine
        text = f'V2.2 {plan.phase}: {plan.reason}'
        debug.gui_debug_msg(CGeoPoint(-4200, -2500), text, debug_color=DebugColor.White, size=145)
        debug.gui_debug_msg(CGeoPoint(-4200, -2750),
            f'Carry {plan.carry_mm:.0f}/800 mm | ball {plan.speed_mm_s/1000:.2f} m/s | '
            f'peak {self.controller.max_speed/1000:.2f} | shots {self.controller.confirmed_shots} | retry {self.controller.retry_count}/2',
            debug_color=DebugColor.Yellow, size=140)
        for n, robot in frame.own.items():
            shooter = n == plan.striker
            role = 'Shooter' if shooter else 'Support'
            suffix = ' LOCKED' if n == plan.locked else ''
            if plan.commands[n].kind == 'stop':
                suffix += ' STOP'
            color = DebugColor.Orange if shooter else DebugColor.Cyan
            x = max(-4200, min(3000, robot.pos[0]-150))
            y = max(-2700, min(2700, robot.pos[1]+(260 if shooter else -350)))
            debug.gui_debug_msg(CGeoPoint(x,y), f'{role} #{n}{suffix}', debug_color=color, size=160, weight=75)
        if plan.support_target is not None and plan.supporter in frame.own:
            target = point(plan.support_target)
            debug.gui_debug_x(target, debug_color=DebugColor.Green)
            debug.gui_debug_line(point(frame.own[plan.supporter].pos), target, debug_color=DebugColor.Cyan)
            debug.gui_debug_msg(CGeoPoint(target.x()-300,target.y()-250),
                f'Target ({target.x():.0f}, {target.y():.0f}) mm', debug_color=DebugColor.Green,size=150)
        if plan.aim is not None and frame.valid and plan.phase != 'WAIT':
            debug.gui_debug_x(point(plan.aim), debug_color=DebugColor.Orange)
            debug.gui_debug_line(point(frame.ball), point(plan.aim), debug_color=DebugColor.Orange)
            debug.gui_debug_msg(CGeoPoint(plan.aim[0]-1000,plan.aim[1]+200),
                'Shot aim', debug_color=DebugColor.Orange,size=150)

    def log(self, frame, plan):
        interval = .05 if self.controller.pending_shot else .25
        if frame.time-self.last_log < interval and plan.phase == self.last_phase:
            return
        self.last_log, self.last_phase = frame.time, plan.phase
        record = dict(time=time.time(), cycle=frame.cycle, play='PreliminaryAttackV2', version='2.2',
            team='yellow' if Global.isYellow else 'blue', phase=plan.phase, reason=plan.reason,
            ball=frame.ball, velocity=frame.velocity, ball_valid=frame.valid,
            robots={str(n): r.pos for n,r in frame.own.items()}, striker=plan.striker,
            contact={str(n): dict(heading=r.heading,infrared=r.infrared,kick_feedback=r.kicked,
                gap_mm=distance(r.pos,frame.ball),ball_angle_error=angle_error(r.heading,direction(r.pos,frame.ball)))
                for n,r in frame.own.items()}, retry_count=self.controller.retry_count,
            support=plan.supporter, target=plan.support_target, aim=plan.aim,
            carry_mm=plan.carry_mm, speed_mm_s=plan.speed_mm_s,
            peak_speed_mm_s=self.controller.max_speed, locked=plan.locked,
            confirmed_shots=self.controller.confirmed_shots, pending_shot=self.controller.pending_shot,
            commands={str(n): dict(kind=c.kind, target=c.target, power=c.power)
                      for n,c in plan.commands.items()})
        with Path('LOG/prelim_v2_blue.jsonl').open('a',encoding='utf-8') as output:
            output.write(json.dumps(record)+'\n')

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''

@declare_state_machine(AttackV2)
class PreliminaryAttackV2(StateMachine):
    pass
