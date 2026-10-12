"""验证 Python 调度；不模拟球物理，也不证明原生技能能一脚出球。"""
import importlib.util
import io
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch

from test_two_attack_vision import Point


class CornerPassTests(unittest.TestCase):
    def setUp(self):
        self.ball = NS(valid=lambda: True, pos=lambda: Point(3900, -2400),
                       velX=lambda: 0, velY=lambda: 0)
        self.player = NS(isValid=lambda n: True,
                         Pos=lambda n: Point(3950, -2570) if n == 1 else Point(3150, 0),
                         direction=lambda n: -1.31 if n == 1 else 0,
                         velMod=lambda n: 0)
        self.skills = NS(**{name: Mock(side_effect=lambda *a, _name=name, **k: (_name, a, k))
                           for name in ("Stop", "SimpleGoTo", "StaticGetBall")})
        self.power = Mock(return_value=4000)
        self.cpp = NS(setDribbleCommand=Mock())
        self.kicks = NS(clearAll=Mock())
        self.params = NS(pitchLength=9000, pitchWidth=6000, penaltyDepth=1000,
                         penaltyWidth=2000, playerFrontToCenter=76)
        modules = {
            "CppPackage": self.cpp, "Global": NS(isPlaySwitched=False),
            "Geometry": NS(CGeoPoint=Point),
            "RoleMatch_LuaStyle": NS(State=object, StateMachine=object,
                                     Task=lambda skill, fixedNumber: NS(skill=skill, num=fixedNumber),
                                     declare_state_machine=lambda *a: lambda cls: cls),
            "RoleMatch_LuaStyle.Skills": NS(Skill=self.skills),
            "Vision": NS(Ball=self.ball, Player=self.player),
            "WorldModel": NS(Params=self.params, kickStatus=self.kicks),
            "WorldModel.PowerCalculator": NS(evalPower=self.power, P=NS(NORMAL=1, HIGH=2)),
        }
        path = Path(__file__).resolve().parents[1] / "Play/Test/Test_CornerPassShot.py"
        spec = importlib.util.spec_from_file_location("corner_test", path)
        self.module = importlib.util.module_from_spec(spec)
        with patch.dict("sys.modules", modules):
            spec.loader.exec_module(self.module)
        self.state = self.module.CornerPassShot()

    def frame(self, now=100):
        with patch.object(self.module.time, "monotonic", return_value=now), redirect_stdout(io.StringIO()):
            return self.state.getTasks()

    def start_pass(self):
        self.state.phase, self.state.started = "PASS", 100
        self.state.pass_origin = Point(3900, -2400)

    def assert_stops(self, tasks):
        self.assertEqual([t.skill[0] for t in tasks.values()], ["Stop", "Stop"])
        self.kicks.clearAll.assert_called()
        for n in (1, 2):
            self.cpp.setDribbleCommand.assert_any_call(n, 0)

    def test_setup_keeps_receiver_outside_box_and_does_not_kick(self):
        tasks = self.frame()
        receiver_target = tasks["B"].skill[1][0]
        self.assertLess(receiver_target.x() + 90, 3500)
        self.skills.StaticGetBall.assert_not_called()
        self.assertEqual(tasks["B"].skill[2]["angle"], 0)

    def test_both_ready_must_settle_before_pass(self):
        tasks = self.frame()
        behind = tasks["A"].skill[1][0]
        angle = tasks["A"].skill[2]["angle"]
        self.player.Pos = lambda n: behind if n == 1 else Point(3150, 0)
        self.player.direction = lambda n: angle if n == 1 else 0
        self.frame(101)
        self.frame(101.2)
        self.assertEqual(self.state.phase, "SETUP")
        self.frame(101.4)
        self.assertEqual(self.state.phase, "PASS")

    def test_receiver_holds_until_ball_departs(self):
        self.start_pass()
        tasks = self.frame()
        self.assertEqual(tasks["A"].skill[0], "StaticGetBall")
        self.assertEqual(tasks["B"].skill[0], "SimpleGoTo")
        target, power, chip = tasks["A"].skill[1]
        self.assertAlmostEqual(target.x(), 3248)
        self.assertEqual(chip, 0)

    def test_pass_departure_starts_shoot_skill_without_infrared(self):
        self.start_pass()
        self.ball.pos = lambda: Point(3850, -2200)
        self.ball.velX, self.ball.velY = lambda: -600, lambda: 2200
        tasks = self.frame()
        self.assertEqual(self.state.phase, "RECEIVE_SHOOT")
        self.assertEqual(tasks["A"].skill[0], "Stop")
        self.assertEqual(tasks["B"].skill[0], "StaticGetBall")
        self.assertEqual(tasks["B"].skill[1][0].x(), 4500)

    def test_wrong_way_ball_does_not_trigger_receiver(self):
        self.start_pass()
        self.ball.pos = lambda: Point(3950, -2600)
        self.ball.velX, self.ball.velY = lambda: 600, lambda: -2200
        self.assertEqual(self.frame()["B"].skill[0], "SimpleGoTo")

    def test_lost_vision_during_pass_latches_stop(self):
        self.start_pass()
        self.ball.valid = lambda: False
        self.assert_stops(self.frame())
        self.ball.valid = lambda: True
        self.assert_stops(self.frame())
        self.skills.StaticGetBall.assert_not_called()

    def test_timeout_clears_commands(self):
        self.start_pass()
        self.assert_stops(self.frame(109))
        self.assertEqual(self.state.phase, "DONE")

    def test_invalid_power_stops_before_native_skill(self):
        self.start_pass()
        self.power.return_value = float("nan")
        self.assert_stops(self.frame())
        self.skills.StaticGetBall.assert_not_called()

    def test_penalty_boundary_stops_receiver(self):
        self.player.Pos = lambda n: Point(3400, 0) if n == 2 else Point(3900, -2400)
        self.assert_stops(self.frame())

    def test_shot_candidate_stops_and_does_not_restart(self):
        self.state.phase, self.state.started = "RECEIVE_SHOOT", 100
        self.ball.pos = lambda: Point(3250, 0)
        self.frame()
        self.ball.pos, self.ball.velX = lambda: Point(3600, 0), lambda: 2500
        self.assert_stops(self.frame(100.1))
        self.assert_stops(self.frame(101))


if __name__ == "__main__":
    unittest.main()
