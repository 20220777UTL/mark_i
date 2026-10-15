"""真实 StateMachine/State/Task 和技能包装器执行，替身只负责视觉及原生接口。"""
import ast
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
from typing import Any
import unittest
from unittest.mock import Mock, patch

import test_give_and_go as flow_tests


class Point(flow_tests.Point):
    def __add__(self, other):
        return Point(self.x() + other.x(), self.y() + other.y())


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
        self.cpp.makeItSimpleGoTo, self.cpp.makeItStop = Mock(), Mock()
        self.cpp.makeItStaticGetBall = Mock(side_effect=AssertionError("unexpected composite skill"))
        wrappers = NS()
        # 直接执行仓库中两个包装函数的 AST，不重新手写/模拟它们的函数体。
        tree = ast.parse((root / 'RoleMatch_LuaStyle/Skills/Skill.py').read_text())
        tree.body = [n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name in ('SimpleGoTo', 'Stop')]
        namespace = dict(CppPackage=self.cpp, CGeoPoint=Point, Player=self.player, Any=Any)
        exec(compile(tree, 'Skill.py', 'exec'), namespace)
        wrappers.SimpleGoTo, wrappers.Stop = namespace['SimpleGoTo'], namespace['Stop']
        self.world_model = NS(SPlayFSMSwitchClearAll=Mock())
        framework = NS()
        modules = {
            'CppPackage': self.cpp, 'Global': g,
            'Geometry': NS(CGeoPoint=Point, CVector=Point),
            'Vision': NS(Ball=self.ball, Player=self.player, ball=lambda: NS(Pos=self.ball.pos)),
            'WorldModel': NS(Params=self.params, kickStatus=self.kicks, worldModel=self.world_model),
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
        self.assertEqual({c.args[0] for c in self.cpp.makeItSimpleGoTo.call_args_list}, {1, 2})
        self.frame(101)
        self.world_model.SPlayFSMSwitchClearAll.assert_called_once()

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
