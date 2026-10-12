"""Check the strategy's vision gate without loading or commanding the C++ runtime."""
import importlib.util
import io
import os
import math
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch


class Point:
    def __init__(self, x, y):
        self._x, self._y = x, y

    def x(self):
        return self._x

    def y(self):
        return self._y


class VisionGateTests(unittest.TestCase):
    def setUp(self):
        self.ball = SimpleNamespace(valid=Mock(return_value=True),
                                    pos=Mock(return_value=Point(1800, 550)))
        self.player = SimpleNamespace(
            isValid=Mock(return_value=True), Pos=Mock(return_value=Point(1500, 550)),
            direction=Mock(return_value=0.0), toBallDir=Mock(return_value=0.5),
            isInfraredOn=Mock(return_value=False))
        self.executors = {kind: Mock(name=kind) for kind in ("stop", "kick", "move")}
        self.skill = SimpleNamespace(
            Stop=Mock(return_value=(self.executors["stop"], Mock())),
            GoAndTurnKick=Mock(return_value=(self.executors["kick"], Mock())),
            RushTo=Mock(return_value=(self.executors["move"], Mock())),
            SimpleGoTo=Mock(return_value=(self.executors["move"], Mock())))
        self.cpp = SimpleNamespace(setDribbleCommand=Mock())
        self.kick_status = SimpleNamespace(clearAll=Mock(), setKick=Mock())
        self.power = Mock(return_value=6000)
        modules = {
            "CppPackage": self.cpp,
            "RoleMatch_LuaStyle": SimpleNamespace(
                State=object, StateMachine=object,
                Task=lambda skill, fixedNumber: SimpleNamespace(skill=skill, number=fixedNumber),
                declare_state_machine=lambda *states: lambda cls: cls),
            "RoleMatch_LuaStyle.Skills": SimpleNamespace(Skill=self.skill),
            "Geometry": SimpleNamespace(CGeoPoint=Point, CVector=object),
            "Vision": SimpleNamespace(Ball=self.ball, Player=self.player, Enemy=object),
            "WorldModel": SimpleNamespace(
                Positions=object, kickStatus=self.kick_status,
                Params=SimpleNamespace(pitchLength=9000, pitchWidth=6000,
                                       penaltyDepth=1000, playerFrontToCenter=76)),
            "WorldModel.PowerCalculator": SimpleNamespace(evalPower=self.power,
                                                           P=SimpleNamespace(NORMAL=1)),
        }
        path = Path(__file__).resolve().parents[1] / "Play/Normal/two_attack.py"
        spec = importlib.util.spec_from_file_location("two_attack_under_test", path)
        module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", modules):
            spec.loader.exec_module(module)
        self.start_class = module.Start
        with patch.dict(os.environ, {"SRC_TWO_ATTACK_DIAG": "both"}):
            self.state = module.Start()

    def run_frame(self):
        with redirect_stdout(io.StringIO()):
            return self.state.getTasks()

    def assert_stopped(self):
        tasks = self.run_frame()
        self.assertEqual([t.number for t in tasks.values()], [1, 2])
        for task in tasks.values():
            task.skill[0](task.number)
        self.executors["stop"].assert_any_call(1)
        self.executors["stop"].assert_any_call(2)
        self.skill.GoAndTurnKick.assert_not_called()
        self.skill.RushTo.assert_not_called()
        self.player.toBallDir.assert_not_called()
        self.power.assert_not_called()
        self.kick_status.clearAll.assert_called_once()
        self.cpp.setDribbleCommand.assert_any_call(1, 0)
        self.cpp.setDribbleCommand.assert_any_call(2, 0)

    def test_missing_ball_does_not_read_its_position(self):
        self.ball.valid.return_value = False
        self.assert_stopped()
        self.ball.pos.assert_not_called()

    def test_missing_receiver_does_not_compute_direction(self):
        self.player.isValid.side_effect = lambda n: n != 2
        self.assert_stopped()

    def test_sentinel_robot_direction_stops(self):
        self.player.direction.return_value = -99999.2
        self.assert_stopped()

    def test_nonfinite_direction_stops(self):
        self.player.direction.return_value = float("nan")
        self.assert_stopped()

    def test_sentinel_position_stops(self):
        self.player.Pos.return_value = Point(-99999, -99999)
        self.assert_stopped()

    def test_ball_nonfinite_position_stops(self):
        self.ball.pos.return_value = Point(float("inf"), 0)
        self.assert_stopped()

    def test_valid_vision_resumes_basic_moves_without_composite_skills(self):
        self.ball.valid.return_value = False
        self.run_frame()
        self.ball.valid.return_value = True
        tasks = self.run_frame()
        self.assertEqual([t.number for t in tasks.values()], [1, 2])
        with redirect_stdout(io.StringIO()):
            for task in tasks.values():
                task.skill[0](task.number)
        self.executors["move"].assert_any_call(1)
        self.executors["move"].assert_any_call(2)
        self.skill.GoAndTurnKick.assert_not_called()
        self.skill.RushTo.assert_not_called()
        self.kick_status.setKick.assert_not_called()

    def test_passer_mode_stops_receiver(self):
        self.state.diagnostic_mode = "passer"
        tasks = self.run_frame()
        with redirect_stdout(io.StringIO()):
            for task in tasks.values():
                task.skill[0](task.number)
        self.executors["move"].assert_called_once_with(1)
        self.executors["stop"].assert_called_once_with(2)
        self.skill.RushTo.assert_not_called()

    def test_receiver_mode_stops_passer(self):
        self.state.diagnostic_mode = "receiver"
        tasks = self.run_frame()
        with redirect_stdout(io.StringIO()):
            for task in tasks.values():
                task.skill[0](task.number)
        self.executors["move"].assert_called_once_with(2)
        self.executors["stop"].assert_called_once_with(1)
        self.skill.GoAndTurnKick.assert_not_called()

    def test_stop_mode_does_not_call_attacking_skills(self):
        self.state.diagnostic_mode = "stop"
        self.assert_stopped()

    def test_trace_identifies_skill_that_did_not_return(self):
        tasks = self.run_frame()
        self.executors["move"].side_effect = RuntimeError("native call failed")
        output = io.StringIO()
        with redirect_stdout(output), self.assertRaises(RuntimeError):
            tasks["A"].skill[0](1)
        self.assertIn("ENTER A.BasicPass", output.getvalue())
        self.assertNotIn("RETURN A.BasicPass", output.getvalue())

    def test_invalid_diagnostic_mode_is_rejected(self):
        with patch.dict(os.environ, {"SRC_TWO_ATTACK_DIAG": "typo"}):
            with self.assertRaises(ValueError):
                self.start_class()

    def prepare_pass(self):
        self.ball.pos.return_value = Point(100, 0)
        self.player.Pos.side_effect = lambda n: Point(0, 0) if n == 1 else Point(3200, 0)
        self.player.direction.side_effect = lambda n: 0 if n == 1 else math.pi
        self.player.isInfraredOn.return_value = True
        return Point(3200, 0)

    def test_aligned_holder_can_kick_to_ready_receiver(self):
        target = self.prepare_pass()
        execute, _ = self.state._pass_skill(target, 6000)
        self.kick_status.setKick.assert_not_called()
        execute(1)
        self.kick_status.setKick.assert_called_once_with(1, 6000)

    def test_no_kick_without_infrared(self):
        target = self.prepare_pass()
        self.player.isInfraredOn.return_value = False
        self.state._pass_skill(target, 6000)[0](1)
        self.kick_status.setKick.assert_not_called()

    def test_no_kick_until_receiver_arrives(self):
        target = self.prepare_pass()
        self.player.Pos.side_effect = lambda n: Point(0, 0) if n == 1 else Point(2000, 0)
        self.state._pass_skill(target, 6000)[0](1)
        self.kick_status.setKick.assert_not_called()

    def test_no_kick_until_passer_aligned(self):
        target = self.prepare_pass()
        self.player.direction.side_effect = lambda n: .2 if n == 1 else math.pi
        self.state._pass_skill(target, 6000)[0](1)
        self.kick_status.setKick.assert_not_called()

    def test_bad_power_never_reaches_kick_command(self):
        target = self.prepare_pass()
        for power in (float("nan"), float("inf"), -1, 0):
            self.state._pass_skill(target, power)[0](1)
        self.kick_status.setKick.assert_not_called()

    def test_large_heading_error_rotates_before_translation(self):
        self.player.direction.return_value = 0
        target = Point(3200, 800)
        self.state._move_skill(2, target, math.pi / 2)
        self.skill.SimpleGoTo.assert_called_once_with(
            self.player.Pos.return_value, angle=math.pi / 2)


if __name__ == "__main__":
    unittest.main()
