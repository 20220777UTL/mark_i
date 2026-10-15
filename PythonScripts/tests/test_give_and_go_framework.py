"""真实 StateMachine/State/Task 和技能包装器执行，替身只负责视觉及原生接口。"""
import ast
import importlib.util
import io
import math
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
import unittest
import typing
from unittest.mock import Mock, patch

import test_give_and_go as flow_tests


class Point(flow_tests.Point):
    def __add__(self, other):
        return Point(self.x() + other.x(), self.y() + other.y())

    def __sub__(self, other):
        return Point(self.x() - other.x(), self.y() - other.y())

    def mod(self):
        return math.hypot(self.x(), self.y())


class RoleNumber:
    MatchType = NS(Fixed=1, Auto=2)

    def __init__(self, match_type, number):
        self.matchType, self.currentRoleNumber = match_type, number


class FrameworkTests(unittest.TestCase):
    def setUp(self):
        flow_tests.GiveAndGoTests.setUp(self)
        root = Path(__file__).resolve().parents[1]
        debug = NS(gui_debug_msg=Mock())
        self.global_state = NS(isPlaySwitched=False, debugEngine=debug,
                               roleNumberStructTable={}, lastRoleNumberStructTable={},
                               RoleNumberStruct=RoleNumber, needDetailedRuntimeDebugInfo=False)
        g = self.global_state
        g.resetRoleNumbersTableBeforeRoleMatch = lambda: setattr(g, "roleNumberStructTable", {})
        g.getRoleNumber = lambda role: g.roleNumberStructTable[role].currentRoleNumber
        self.player.getAllValidNumbers = lambda: [1, 2]
        self.player.ourPlayer = lambda n: NS(Pos=lambda: Point(self.positions[n].x(), self.positions[n].y()))
        self.cpp.CGeoPoint, self.cpp.CVector = Point, Point
        self.cpp.makeItSimpleGoTo, self.cpp.makeItSmartGoTo, self.cpp.makeItStop = Mock(), Mock(), Mock()
        self.cpp.makeItStaticGetBall = Mock(side_effect=AssertionError("unexpected composite skill"))
        wrappers = NS()
        # 直接执行仓库中三个包装函数的 AST，不重新手写/模拟它们的函数体。
        tree = ast.parse((root / 'RoleMatch_LuaStyle/Skills/Skill.py').read_text())
        tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('SimpleGoTo', 'SmartGoTo', 'Stop')]
        namespace = dict(CppPackage=self.cpp, CGeoPoint=Point, CVector=Point, Player=self.player, Any=Any, typing=typing)
        exec(compile(tree, 'Skill.py', 'exec'), namespace)
        wrappers.SimpleGoTo, wrappers.SmartGoTo, wrappers.Stop = namespace['SimpleGoTo'], namespace['SmartGoTo'], namespace['Stop']
        self.world_model = NS(SPlayFSMSwitchClearAll=Mock())
        framework = NS()
        modules = {
            'CppPackage': self.cpp, 'Global': g,
            'Geometry': NS(CGeoPoint=Point, CVector=Point),
            'Vision': NS(Ball=self.ball, Player=self.player, ball=lambda: NS(Pos=self.ball.pos)),
            'WorldModel': NS(Params=self.params, kickStatus=self.kicks, worldModel=self.world_model, Flags=self.flags),
            'WorldModel.PowerCalculator': NS(evalPower=self.power, P=NS(NORMAL=1, HIGH=2)),
            'Utils': NS(DebugColor=NS(Yellow=1)),
            'Algorithm.munkre': NS(DoMunkresMatch=Mock(side_effect=AssertionError('fixed roles should not match'))),
            'RoleMatch_LuaStyle': framework,
            'RoleMatch_LuaStyle.Skills': NS(Skill=wrappers),
        }

        def load(name, relative):
            spec = importlib.util.spec_from_file_location(name, root / relative)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            return module

        with patch.dict('sys.modules', modules):
            task_module = load('real_task_test', 'RoleMatch_LuaStyle/Task.py')
            with patch.dict('sys.modules', {'RoleMatch_LuaStyle.Task': task_module}):
                framework.Task = task_module.Task
                framework.State = load('real_state_test', 'RoleMatch_LuaStyle/State.py').State
                machine = load('real_machine_test', 'RoleMatch_LuaStyle/StateMachine.py')
                framework.StateMachine = machine.StateMachine
                framework.declare_state_machine = machine.declare_state_machine
                base = load('real_corner_test', 'Play/Test/Test_CornerPassShot.py')
                with patch.dict('sys.modules', {'Play.Test.Test_CornerPassShot': base}):
                    self.module = load('real_flow_test', 'Play/Test/Test_GiveAndGo.py')
                    self.machine = self.module.Test_GiveAndGo()
                    self.state = self.machine.start_state

    def frame(self, now=100):
        with patch.object(self.module.time, 'monotonic', return_value=now), redirect_stdout(io.StringIO()):
            self.machine.planTasks()

    def test_real_framework_assigns_swapped_roles_and_runs_both_moves(self):
        self.positions[2] = Point(-100, 0)
        self.frame()
        self.assertEqual(self.state.near, 2)
        self.assertEqual(self.global_state.roleNumberStructTable['A'].currentRoleNumber, 2)
        self.assertEqual(self.global_state.roleNumberStructTable['B'].currentRoleNumber, 1)
        self.assertEqual({c.args[0] for c in self.cpp.makeItSmartGoTo.call_args_list}, {1, 2})
        self.frame(101)
        self.world_model.SPlayFSMSwitchClearAll.assert_called_once()

    def test_real_framework_complete_sequence_with_real_power_curve(self):
        # 力度入口及曲线后端执行仓库原代码；仅原生坐标/控制/视觉被替换。
        root = Path(__file__).resolve().parents[1]
        self.cpp.DebugEngine = NS(Instance=lambda: self.global_state.debugEngine)
        spec = importlib.util.spec_from_file_location("real_power_test", root / "WorldModel/PowerCalculator.py")
        power = importlib.util.module_from_spec(spec)
        with patch.dict('sys.modules', {'Global': self.global_state, 'CppPackage': self.cpp,
                                        'Vision': NS(Ball=self.ball, Player=self.player)}):
            spec.loader.exec_module(power)
        self.module.evalPower, self.module.P = power.evalPower, power.P
        self.frame(100)
        corner = Point(3900, -2400)
        angle = self.module.direction(Point(0, 0), corner)
        self.positions[1] = Point(-260 * math.cos(angle), -260 * math.sin(angle))
        self.angles[1] = angle
        self.positions[2], self.angles[2] = corner, angle + math.pi
        self.frame(101)
        self.frame(101.3)
        self.assertEqual(self.state.phase, 'PASS_OUT')
        self.positions[1] = Point(-110 * math.cos(angle), -110 * math.sin(angle))
        self.frame(101.4)
        self.assertTrue(self.state.pass_sent)
        self.assertGreater(self.kicks.setKick.call_args.args[1], 0)
        self.ball.pos = lambda: Point(200 * math.cos(angle), 200 * math.sin(angle))
        self.ball.velX, self.ball.velY = lambda: 1500 * math.cos(angle), lambda: 1500 * math.sin(angle)
        self.frame(101.6)
        self.assertEqual(self.state.phase, 'RETURN_SETUP')
        self.positions[1], self.angles[1] = Point(3150, 0), 0
        target = self.module.mouth(self.positions[1], 0)
        self.angles[2] = self.module.direction(corner, target)
        held = self.module.mouth(corner, self.angles[2])
        self.ball.pos = lambda: held
        self.ball.velX, self.ball.velY = lambda: 0, lambda: 0
        self.infrared[2] = True
        self.frame(102)
        self.frame(102.3)
        self.assertEqual(self.state.phase, 'RETURN_PASS')
        self.frame(102.4)
        angle = self.module.direction(held, target)
        self.ball.pos = lambda: Point(held.x() + 200 * math.cos(angle), held.y() + 200 * math.sin(angle))
        self.ball.velX, self.ball.velY = lambda: 1500 * math.cos(angle), lambda: 1500 * math.sin(angle)
        self.frame(102.6)
        self.assertEqual(self.state.phase, 'FINISH')
        self.ball.pos = lambda: Point(3270, 0)
        self.ball.velX, self.ball.velY = lambda: -1000, lambda: 0
        self.player.isInfraredOn = Mock(side_effect=AssertionError('no possession check in FINISH'))
        self.frame(103)
        self.assertEqual([c.args[0] for c in self.kicks.setKick.call_args_list], [1, 2, 1])
        self.assertTrue(all(math.isfinite(c.args[1]) and 0 < c.args[1] <= power.POWER_MAX
                            for c in self.kicks.setKick.call_args_list))
        self.frame(103.2)
        self.assertEqual(self.state.phase, 'DONE')
        self.cpp.makeItStaticGetBall.assert_not_called()
        for call in self.cpp.makeItSmartGoTo.call_args_list:
            self.assertEqual(call.args[3], self.flags.slowly | self.flags.allow_dss | self.flags.dodge_ball)
            self.assertEqual(call.args[5], 2000)

    def test_real_framework_direct_kick_then_terminal_stop(self):
        self.frame()
        self.state.phase, self.state.started = 'FINISH', 100
        self.positions[1] = Point(3150, 0)
        self.ball.pos, self.ball.velX, self.ball.velY = lambda: Point(3270, 0), lambda: -1000, lambda: 0
        self.player.isInfraredOn = Mock(side_effect=AssertionError('no possession check in FINISH'))
        self.cpp.setDribbleCommand.reset_mock()
        self.frame(101)
        self.kicks.setKick.assert_called_once_with(1, 4000)
        self.assertTrue(all(c.args[1] == 0 for c in self.cpp.setDribbleCommand.call_args_list))
        self.frame(101.2)
        self.assertEqual(self.state.phase, 'DONE')
        self.cpp.makeItStop.assert_any_call(1)
        self.cpp.makeItStop.assert_any_call(2)
        self.cpp.makeItStaticGetBall.assert_not_called()


if __name__ == '__main__':
    unittest.main()
