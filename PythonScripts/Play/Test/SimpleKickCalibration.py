"""Simulation-only flat-kick calibration using the normal shooting skill."""
import json
import os
import time
from pathlib import Path

import CppPackage as C
import Global
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball
from Geometry import CGeoPoint
from WorldModel import kickStatus
from Play.Test.KickCalibration import reset_scene


class MeasureKick(State):
    def __init__(self):
        super().__init__()
        powers = [int(p) for p in os.environ.get('SRC_KICK_POWERS', '12700').split(',')]
        if not Global.isSimulation:
            raise ValueError('Calibration is simulation only')
        if any(p < 0 or p > 40000 for p in powers):
            raise ValueError('Simulation calibration power must be within 0..40000')
        self.trials = [(p, r + 1) for p in powers for r in range(int(os.environ.get('SRC_KICK_REPEATS', '3')))]
        self.index = 0
        self.stage = 'reset'
        self.samples = []

    def getTasks(self):
        now = time.perf_counter()
        action = Skill.Stop()
        if self.index >= len(self.trials) or self.stage == 'fault':
            return {'A': Task(action, fixedNumber=1)}
        power, repeat = self.trials[self.index]
        if self.stage == 'reset':
            reset_scene()
            self.started = now
            self.stage = 'settle'
            self.samples = []
        elif self.stage == 'settle':
            if now - self.started > 2 and Ball.valid() and abs(Ball.posX() + 1800) < 50 and Ball.velMod() < 100:
                self.started = now
                self.stage = 'shoot'
            elif now - self.started > 12:
                self.stage = 'fault'
                print('SIMPLE_FAULT ball did not settle', flush=True)
        elif self.stage == 'shoot':
            if Ball.valid():
                raw = Ball.rawPos()
                self.samples.append([now - self.started, Ball.posX(), Ball.posY(),
                                     Ball.velMod() / 1000, Ball.ball().RawVel().mod() / 1000,
                                     raw.x(), raw.y()])
            # Capture from the first shooting frame, before the ball leaves the robot.
            if Ball.posX() < -1500:
                def execute(executor):
                    C.setDribbleCommand(executor, 3)
                    kickStatus.setKick(executor, power)
                    return C.makeItRushTo(executor, CGeoPoint(-1800, 0), 0, maxAcc=500, needDribble=True)
                action = execute, lambda executor: CGeoPoint(-2000, 0)
            if (Ball.valid() and Ball.posX() > 1000) or now - self.started > 8:
                data = [s for s in self.samples if -1850 < s[1] < 1000 and abs(s[2]) < 400]
                result = dict(power=power, repeat=repeat, released=Ball.posX() > -1500,
                              started=self.started, ended=now,
                              peak_m_s=max((s[3] for s in data), default=0),
                              raw_vel_peak_m_s=max((s[4] for s in data), default=0), samples=self.samples)
                sample_dir = Path(os.environ.get('SRC_KICK_SAMPLE_DIR', '../kick-samples'))
                sample_dir.mkdir(parents=True, exist_ok=True)
                (sample_dir / f'{power}-{repeat}.json').write_text(json.dumps(result), encoding='utf-8')
                del result['samples']
                print('SIMPLE_RESULT ' + json.dumps(result), flush=True)
                self.index += 1
                self.stage = 'reset'
                action = Skill.Stop()
                if self.index == len(self.trials):
                    print('SIMPLE_DONE', flush=True)
        return {'A': Task(action, fixedNumber=1)}

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''


@declare_state_machine(MeasureKick)
class SimpleKickCalibration(StateMachine):
    pass
