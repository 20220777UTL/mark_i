"""实际 Config 入口的颜色路由；仅替换策略对象，避免加载 Windows 原生模块。"""
import ast
from contextlib import redirect_stdout
import importlib.util
import io
from pathlib import Path
from types import SimpleNamespace as NS
import typing
import unittest
from unittest.mock import Mock, patch


ROOT = Path(__file__).resolve().parents[1]
PLAYS = {
    "Normal": ("ExampleNormalPlay", "two_attack"),
    "RefPlay": ("ExampleKickOff", "ExampleKickOffDefend", "ExampleFreeKick",
                "ExampleFreeKickDefend", "GameHalt", "GameStop", "OurTimeout"),
    "Test": ("Test_Goalie2022", "Test_GiveAndGo", "Test_CornerPassShot"),
}


class RoutingTests(unittest.TestCase):
    def load_config(self, yellow, environment, default_available=True):
        state = NS(isYellow=yellow, goalieNumber=0)
        modules = {"Global": state}
        for folder, names in PLAYS.items():
            for name in names:
                constructor = Mock(return_value=NS(name=name, planTasks=Mock()))
                modules[f"Play.{folder}.{name}"] = NS(**{name: constructor},
                                                       ROBOT_IDS=(1, 2), PASSER=1, RECEIVER=2)
        if not default_available:
            modules["Play.Normal.two_attack"] = None
        spec = importlib.util.spec_from_file_location("routing_test_config", ROOT / "Config.py")
        config = importlib.util.module_from_spec(spec)
        output = io.StringIO()
        with patch.dict("sys.modules", modules), patch.dict("os.environ", environment, clear=True), redirect_stdout(output):
            spec.loader.exec_module(config)
        return config, state, output.getvalue()

    def test_blue_runs_attacker_only(self):
        config, state, output = self.load_config(False, {"SRC_GIVE_AND_GO_TEST": "1"})
        config.testStrategy.runStrategy()
        self.assertTrue(state.isTestMode)
        self.assertEqual(state.controlledRobotNumbers, (1, 2))
        self.assertEqual(config.testStrategy.blueTeam.name, "Test_GiveAndGo")
        config.testStrategy.blueTeam.planTasks.assert_called_once_with()
        config.testStrategy.yellowTeam.planTasks.assert_not_called()
        self.assertIn("BLUE: Test_GiveAndGo; robots=(1, 2)", output)

    def test_yellow_runs_keeper_only(self):
        config, state, output = self.load_config(True, {"SRC_GIVE_AND_GO_TEST": "1"})
        config.testStrategy.runStrategy()
        self.assertEqual(state.controlledRobotNumbers, (0,))
        self.assertEqual(config.testStrategy.yellowTeam.name, "Test_Goalie2022")
        config.testStrategy.yellowTeam.planTasks.assert_called_once_with()
        config.testStrategy.blueTeam.planTasks.assert_not_called()
        self.assertIn("YELLOW: Test_Goalie2022; robots=(0,)", output)

    def test_default_entry_is_unchanged(self):
        for yellow in (False, True):
            with self.subTest(yellow=yellow):
                config, state, _ = self.load_config(yellow, {})
                self.assertIsNone(state.controlledRobotNumbers)
                self.assertEqual(config.testStrategy.blueTeam.name, "two_attack")
                self.assertIs(config.testStrategy.blueTeam, config.testStrategy.yellowTeam)

    def test_explicit_tests_work_without_repo_only_default_strategy(self):
        for yellow in (False, True):
            for flag in ("SRC_GIVE_AND_GO_TEST", "SRC_CORNER_PASS_TEST"):
                with self.subTest(yellow=yellow, flag=flag):
                    config, _, _ = self.load_config(yellow, {flag: "1"}, default_available=False)
                    config.testStrategy.runStrategy()

    def test_legacy_corner_entry_is_unchanged(self):
        config, state, _ = self.load_config(False, {"SRC_CORNER_PASS_TEST": "1"})
        self.assertEqual(state.controlledRobotNumbers, (1, 2))
        self.assertEqual(config.testStrategy.blueTeam.name, "Test_CornerPassShot")
        self.assertIs(config.testStrategy.blueTeam, config.testStrategy.yellowTeam)

    def test_full_flow_overrides_legacy_environment(self):
        config, state, _ = self.load_config(True, {"SRC_CORNER_PASS_TEST": "1", "SRC_GIVE_AND_GO_TEST": "1"})
        config.testStrategy.runStrategy()
        self.assertEqual(state.controlledRobotNumbers, (0,))
        self.assertEqual(config.testStrategy.yellowTeam.name, "Test_Goalie2022")
        config.testStrategy.yellowTeam.planTasks.assert_called_once_with()

    def test_supplied_keeper_wrapper_registers_role_and_forwards_normal_mode(self):
        # 执行原包装函数体，核对正常守门调用参数；不冒充原生守门行为测试。
        tree = ast.parse((ROOT / "RoleMatch_LuaStyle/Skills/Skill.py").read_text())
        tree.body = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "Goalie2022"]
        cpp, mediator, goal = Mock(), Mock(), object()
        namespace = dict(typing=typing, Any=typing.Any, CGeoPoint=object,
                         CppPackage=cpp, taskMediator=mediator, Positions=NS(ourGoal=goal))
        exec(compile(tree, "Skill.py", "exec"), namespace)
        execute, match = namespace["Goalie2022"](mode="normal")
        execute(0)
        mediator.registerRole.assert_called_once_with(0, "goalie")
        cpp.makeItGoalie2022.assert_called_once_with(0, False, 0)
        self.assertIs(match(0), goal)


if __name__ == "__main__":
    unittest.main()
