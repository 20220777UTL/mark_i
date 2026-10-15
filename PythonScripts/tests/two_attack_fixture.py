"""Strategy harness: fresh vision cycles in, captured native commands out."""
import io
import math
import runpy
import sys
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch
from Play.Normal.AttackFeedback import curve_fingerprint


class Point:
    def __init__(self, x, y, z=0):
        self.a, self.b, self.c = x, y, z
    def x(self): return self.a
    def y(self): return self.b
    def z(self): return self.c


class FrameState:
    def __init__(self):
        self.state_name = type(self).__name__
    def run(self, switched):
        for task in reversed(list(self.getTasks().values())):
            task.skill_cpp(task.number)
        return self.transFunction()


class Harness:
    def __init__(self, simulation=True):
        self.time, self.cycle = 10., 0
        self.positions = {0: Point(0, 0), 1: Point(3250, 1100)}
        self.headings = {0: 0., 1: 0.}
        self.velocities = {0: Point(0, 0), 1: Point(0, 0)}
        self.omegas = {0: 0., 1: 0.}
        self.robot_valid = {0: True, 1: True}
        self.ir = {0: False, 1: False}
        self.ball, self.velocity = Point(100, 0), Point(0, 0)
        self.ball_valid, self.height, self.airborne, self.remaining = True, None, False, 0.
        self.keeper = None
        self.cpp, self.kicks = Mock(), Mock()
        self.cpp.CVector.side_effect = Point
        self.cpp.InTheirPenaltyArea.return_value = False
        self.cpp.InOurPenaltyArea.return_value = False
        self.global_ = NS(isSimulation=simulation, isPlaySwitched=False, powerMax=12700,
                          debugEngine=Mock(), needDetailedRuntimeDebugInfo=True)
        self.player = NS(
            isValid=Mock(side_effect=lambda n: self.robot_valid[n]),
            Pos=Mock(side_effect=lambda n: self.positions[n]),
            vel=lambda n: self.velocities[n], direction=lambda n: self.headings[n],
            rotVel=lambda n: self.omegas[n],
            isInfraredOn=Mock(side_effect=lambda n: self.ir[n]),
            infraredCount=Mock(return_value=0), infraredOffCount=Mock(return_value=0),
            kickBallVision=Mock(return_value=False))
        self.native = NS(
            RealPos=lambda: Point(self.ball.a, self.ball.b, self.height) if self.height is not None else Point(0, 0, 0),
            ChipBallState=lambda: self.airborne, ChipRestFlyTime=lambda: self.remaining,
            BestChipPredictPos=lambda: Point(0, 0))
        self.ball_api = NS(valid=lambda: self.ball_valid, pos=Mock(side_effect=lambda: self.ball),
                           vel=lambda: self.velocity, ball=lambda: self.native)
        self.curves = {'profiles': {'chip': {'curves': {'Normal': [[0, 1000], [3000, 3000]]}, 'limits': {'max_power': 4000}}}}
        self.power = Mock(return_value=2500)
        modules = {
            'CppPackage': self.cpp, 'Global': self.global_,
            'Utils': NS(DebugColor=NS(Yellow=1)),
            'Geometry': NS(CGeoPoint=Point),
            'RoleMatch_LuaStyle': NS(State=FrameState,
                Task=lambda skill, fixedNumber: NS(skill_cpp=skill[0], matchPos=skill[1], number=fixedNumber)),
            'Vision': NS(Ball=self.ball_api, Player=self.player,
                Enemy=NS(valid=lambda n: self.keeper is not None, pos=lambda n: self.keeper),
                vision=NS(getCycle=lambda: self.cycle)),
            'WorldModel': NS(Params=NS(pitchLength=9000, pitchWidth=6000, penaltyDepth=1000,
                            goalWidth=1000, playerRadius=90, playerFrontToCenter=76),
                Flags=NS(allow_dss=1, dodge_ball=16), kickStatus=self.kicks,
                worldModel=Mock(), ballStatus=NS(getBallPossession=lambda *args: .5)),
            'WorldModel.PowerCalculator': NS(evalPower=self.power, P=NS(NORMAL=1, HIGH=2)),
            'PowerCurveBackend': NS(curve_snapshot=lambda: self.curves),
        }
        path = Path(__file__).resolve().parents[1] / 'Play/Normal/two_attack.py'
        with patch.dict(sys.modules, modules):
            # Exercise the real framework's hook/reset/transition ordering.
            runtime = runpy.run_path(str(path.parents[2] / 'RoleMatch_LuaStyle/StateMachine.py'))
            modules['RoleMatch_LuaStyle'].StateMachine = runtime['StateMachine']
            modules['RoleMatch_LuaStyle'].declare_state_machine = runtime['declare_state_machine']
            self.m = runpy.run_path(str(path))
        self.profile = {'mouth_offsets_mm': {'0': 100, '1': 100}, 'chip': {'calibrated': False}}
        self.c = self.m['Control'](clock=lambda: self.time, calibration=self.profile)
        self.log = io.StringIO()

    def update(self, dt=.025, fresh=True):
        self.time += dt
        if fresh: self.cycle += 1
        with redirect_stdout(self.log):
            self.c.update()

    def settle(self):
        for _ in range(4): self.update()

    def state(self, name):
        state = self.m[name]()
        state.control = self.c
        return state

    def run(self, state):
        with redirect_stdout(self.log):
            return state.run(False)

    def task(self, task):
        with redirect_stdout(self.log):
            task.skill_cpp(task.number)

    def clear_commands(self):
        self.cpp.reset_mock()
        self.kicks.reset_mock()
        self.power.reset_mock()

    def enable_chip(self):
        self.height = 22
        self.profile['chip'] = dict(calibrated=True, sender=1, distance_reference='first_landing',
            observation_verified=True, curve_fingerprint=curve_fingerprint(self.curves, 12700),
            min_distance_mm=100, max_distance_mm=3000, landing_lead_mm=200)

    def ready_return(self, chip=True):
        if chip: self.enable_chip()
        self.ball = Point(3150, 1100)
        self.update()
        with redirect_stdout(self.log):
            plan = self.m['prepare_return'](self.c)
        aim = math.atan2(plan.landing[1] - self.ball.b, plan.landing[0] - self.ball.a)
        self.positions[1] = Point(self.ball.a - 100 * math.cos(aim), self.ball.b - 100 * math.sin(aim))
        self.headings[1] = aim
        self.positions[0] = Point(*plan.centre)
        self.headings[0] = plan.heading
        self.ir[1] = True
        self.settle()
        self.clear_commands()
        return self.state('PassBack'), plan
