"""Isolated no-ball calibration. Only supplied SmartGoTo and Stop actuate robots.

Units: mm, mm/s, seconds, radians. Records filtered vision, not wheel commands.
Normal match plays and their tuning remain unchanged. Each NormalPlay entry starts
a new, separately logged suite; Halt/StopGame remain controlled by the referee.
"""
import json
import math
import time
import uuid
from pathlib import Path

import CppPackage
import Global
from Geometry import CGeoPoint
from Vision import Player, vision
from Utils import DebugColor
from WorldModel import Flags, kickStatus
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import SmartGoTo, Stop

START = (-1800, -1500)
TARGET = (1800, -1500)
TEST_ROBOT = 1
# Repeats expose variability; requested speeds are triggers, NOT speed limits.
CASES = [('slow', 0)] * 3 + [('stop', v) for v in (600, 1000, 1400) for _ in range(2)]
MOVE_FLAGS = Flags.allow_dss | Flags.dodge_our_defense_box | Flags.dodge_ball


class CalibrationProtocol:
    """Experiment sequencing only; no custom motion controller."""
    def __init__(self, now):
        self.index = 0
        self.phase = 'PREPARE'
        self.entered = now
        self.since = None
        self.reason = 'move to start using supplied SmartGoTo slowly'
        self.run_origin = None
        self.brake_origin = None

    @property
    def case(self):
        return CASES[min(self.index, len(CASES)-1)]

    def change(self, phase, now, reason):
        self.phase, self.entered, self.reason = phase, now, reason
        self.since = None

    def stable(self, condition, now, duration):
        if not condition:
            self.since = None
            return False
        if self.since is None:
            self.since = now
        return now - self.since >= duration

    def fault(self, now, reason):
        if self.phase not in ('DONE', 'FAULT'):
            self.change('FAULT', now, reason)

    def step(self, now, sample):
        pos, speed = sample['pos'], sample['speed']
        kind, trigger = self.case
        if self.phase in ('DONE', 'FAULT'):
            return 'Stop', None
        # Interior envelope leaves substantial room to the physical walls.
        if abs(pos[0]) > 2800 or not -2300 < pos[1] < 600 or speed > 2300:
            self.fault(now, 'interior envelope / speed guard; inspect before restarting')
            return 'Stop', None
        if now-self.entered > 25:
            self.fault(now, 'phase timeout: ' + self.phase)
            return 'Stop', None

        if self.phase == 'PREPARE':
            if self.stable(math.dist(pos, START) < 80 and speed < 80, now, .6):
                self.change('READY', now, 'Stop before each trial; remove inherited velocity')
                return 'Stop', None
            return 'SmartGoTo slowly', START

        if self.phase == 'READY':
            if math.dist(pos, START) > 150:
                self.fault(now, 'drifted away from start during settling')
            elif self.stable(speed < 50, now, 1.0):
                self.run_origin = list(pos)
                self.brake_origin = None
                self.change('RUN', now, 'slow target approach' if kind == 'slow' else f'accelerate until measured speed >= {trigger}')
            else:
                return 'Stop', None

        if self.phase == 'RUN':
            if kind == 'stop':
                # Positive x is the test direction. Keep sideways motion out of braking trials.
                if speed >= trigger and sample['vel'][0] > 0:
                    self.brake_origin = list(pos)
                    self.change('BRAKE', now, 'supplied Stop requested; measure actual stopping response')
                    return 'Stop', None
                if pos[0] > 200:
                    self.fault(now, 'requested trigger speed not reached in acceleration lane')
                    return 'Stop', None
                return 'SmartGoTo normal', TARGET
            if self.stable(math.dist(pos, TARGET) < 80 and speed < 80, now, 1.0):
                self.change('RESULT', now, 'slow approach completed; remain stopped')
                return 'Stop', None
            return 'SmartGoTo slowly', TARGET

        if self.phase == 'BRAKE':
            if self.stable(speed < 50, now, .6):
                self.change('RESULT', now, 'Stop trial completed')
            return 'Stop', None

        if self.phase == 'RESULT':
            if now-self.entered >= 1.0:
                self.index += 1
                if self.index == len(CASES):
                    self.change('DONE', now, 'all 9 trials complete; press Halt and export curves')
                else:
                    self.run_origin = self.brake_origin = None
                    self.change('PREPARE', now, 'return to start using supplied SmartGoTo slowly')
            return 'Stop', None
        return 'Stop', None


class MotionCalibrationState(State):
    def __init__(self):
        super().__init__()
        self.last_reset_cycle = None
        self.protocol = None
        self.file = None
        self.cached_cycle = None
        self.cached_tasks = None
        self.cached_time = 0

    def reset(self, now):
        if self.file:
            self.file.close()
        self.protocol = CalibrationProtocol(now)
        self.started = now
        self.run_id = time.strftime('%Y%m%d_%H%M%S') + '_' + uuid.uuid4().hex[:8]
        directory = Path('LOG/motion_calibration')
        directory.mkdir(parents=True, exist_ok=True)
        self.log_path = directory / (self.run_id + '.jsonl')
        self.file = self.log_path.open('a', encoding='utf-8')
        self.last_log = self.last_flush = -1e9
        self.last_event = None
        self.cached_cycle = None
        print(f'[CALIBRATION] log={self.log_path} robot=1 trials=9', flush=True)

    @staticmethod
    def stop_tasks():
        return {f'Calib_{n}': Task(Stop(), fixedNumber=n) for n in (0, 1)}

    def getTasks(self):
        now, cycle = time.monotonic(), vision.getCycle()
        if self.protocol is None or (Global.isPlaySwitched and cycle != self.last_reset_cycle):
            self.reset(now)
            self.last_reset_cycle = cycle
        kickStatus.clearAll()
        for n in (0, 1):
            CppPackage.setDribbleCommand(n, 0)
        if cycle == self.cached_cycle:
            if now-self.cached_time <= .12:
                return self.cached_tasks
            self.protocol.fault(now, 'vision cycle stalled; repeat suite after reconnecting')
            self.record(now, cycle, None, 'Stop', None)
            return self.stop_tasks()
        tasks = self.stop_tasks()
        sample = None
        command, target = 'Stop', None
        if not Player.isValid(TEST_ROBOT):
            self.protocol.fault(now, 'blue 1 missing from vision')
        else:
            p, v = Player.Pos(TEST_ROBOT), Player.vel(TEST_ROBOT)
            sample = dict(pos=[p.x(), p.y()], vel=[v.x(), v.y()],
                          speed=Player.velMod(TEST_ROBOT), heading=Player.direction(TEST_ROBOT))
            command, target = self.protocol.step(now, sample)
            if target is not None:
                flags = MOVE_FLAGS | (Flags.slowly if command.endswith('slowly') else 0)
                # Preserve supplied defaults: sender=0, maxAcc=0, Velocity=(0,0).
                tasks['Calib_1'] = Task(SmartGoTo(CGeoPoint(*target), dir=0, flag=flags), fixedNumber=1)
        self.record(now, cycle, sample, command, target)
        self.draw(sample)
        self.cached_cycle, self.cached_time, self.cached_tasks = cycle, now, tasks
        return tasks

    def record(self, now, cycle, sample, command, target):
        p = self.protocol
        event = (p.index, p.phase, command)
        changed = event != self.last_event
        if now-self.last_log < .02 and not changed:
            return
        row = dict(schema=1, run_id=self.run_id, time=time.time(), elapsed=now-self.started,
                   cycle=cycle, trial=min(p.index+1, len(CASES)), kind=p.case[0],
                   trigger_speed=p.case[1], phase=p.phase, reason=p.reason,
                   robot=TEST_ROBOT, sample=sample, skill=command, target=target,
                   start=START, endpoint=TARGET, run_origin=p.run_origin,
                   brake_origin=p.brake_origin,
                   remaining=math.dist(sample['pos'], TARGET) if sample else None)
        self.file.write(json.dumps(row)+'\n')
        if changed or now-self.last_flush >= .5:
            self.file.flush()
            self.last_flush = now
        if changed:
            print(f'[CALIBRATION] trial={row["trial"]}/9 {p.case} {p.phase}: {p.reason}', flush=True)
        self.last_log, self.last_event = now, event

    def draw(self, sample):
        p, debug = self.protocol, Global.debugEngine
        speed = sample['speed']/1000 if sample else 0
        gap = math.dist(sample['pos'], TARGET) if sample else 0
        for point, name in ((START, 'START'), (TARGET, 'TARGET')):
            debug.gui_debug_x(CGeoPoint(*point), debug_color=DebugColor.Green)
            debug.gui_debug_msg(CGeoPoint(point[0]-200, point[1]+250), name, debug_color=DebugColor.Green, size=130)
        debug.gui_debug_msg(CGeoPoint(-4000,2500),
                            f'CALIBRATION {min(p.index+1,9)}/9 {p.case[0]} {p.case[1]} | {p.phase}',
                            debug_color=DebugColor.White, size=160)
        debug.gui_debug_msg(CGeoPoint(-4000,2250), f'Blue #1 speed {speed:.2f} m/s | remaining {gap:.0f} mm',
                            debug_color=DebugColor.Cyan, size=140)
        debug.gui_debug_msg(CGeoPoint(-4000,2000), p.reason, debug_color=DebugColor.Yellow, size=110)

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''


@declare_state_machine(MotionCalibrationState)
class MotionCalibration(StateMachine):
    pass
