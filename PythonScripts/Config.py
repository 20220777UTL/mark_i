"""校赛入口：选手填写五个 Example 模板，三个官方裁判策略统一提供。

不使用点球；人工摆球期间沿用 GameHalt，所有车辆停止并关闭吸球和踢球。
"""

import Global
import os
import sys
from pathlib import Path
from Play.Normal.ExampleNormalPlay import ExampleNormalPlay
from Play.Normal.SimplePassPlay import SimplePassPlay
from Play.RefPlay.ExampleKickOff import ExampleKickOff
from Play.RefPlay.ExampleKickOffDefend import ExampleKickOffDefend
from Play.RefPlay.ExampleFreeKick import ExampleFreeKick
from Play.RefPlay.ExampleFreeKickDefend import ExampleFreeKickDefend
from Play.RefPlay.GameHalt import GameHalt
from Play.RefPlay.GameStop import GameStop
from Play.RefPlay.OurTimeout import OurTimeout
from Play.Test.Test_Goalie2022 import Test_Goalie2022


Global.isTestMode = False
Global.needDetailedRuntimeDebugInfo = False
# 默认按视觉识别场上车辆，不限制人数或车号；也可填车号元组限定受控车辆。
Global.controlledRobotNumbers = None


class GameStrategy:
    def __init__(self, blueTeam, yellowTeam=None):
        self.blueTeam = blueTeam
        self.yellowTeam = yellowTeam if yellowTeam is not None else blueTeam

    def runStrategy(self):
        if Global.isYellow:
            self.yellowTeam.planTasks()
        else:
            self.blueTeam.planTasks()


# key 由 GameControl/Referee.py 和 SelectPlay.py 使用；替换值时请保留 key。
Global.gameStrategies = {
    "NormalPlay": GameStrategy(SimplePassPlay()),
    "KickOff": GameStrategy(ExampleKickOff()),
    "KickOffDef": GameStrategy(ExampleKickOffDefend()),
    "FreeKick": GameStrategy(ExampleFreeKick()),
    "FreeKickDef": GameStrategy(ExampleFreeKickDefend()),
    "ourDirectKick": GameStrategy(ExampleFreeKick()),
    "theirDirectKick": GameStrategy(ExampleFreeKickDefend()),
    "TimeOut": GameStrategy(OurTimeout()),
    "GameStop": GameStrategy(GameStop()),
    "GameHalt": GameStrategy(GameHalt()),
    "PenaltyKick": GameStrategy(GameHalt()),
    "theirPenaltyKick": GameStrategy(GameHalt()),
    "BallPlace": GameStrategy(GameHalt()),
    "TheirBallPlace": GameStrategy(GameHalt()),
    "IfHalfField": False,
    "USE_ZPASS": False,
}

testStrategy = GameStrategy(ExampleNormalPlay())

# Client's blue/yellow Medusa buttons read this file directly. In simulation,
# run the two-attacker/one-practice-keeper scenario without a separate shell.
Global.autoPreparePreliminaryScene = False
clientPractice = (
    Global.isSimulation and Path(sys.executable).name.lower() == 'medusa.exe' and
    (Path(__file__).resolve().parents[1] / '.client_practice_enabled').is_file() and
    not any(os.environ.get(name) == '1' for name in
            ('SRC_PRELIM', 'SRC_KICK_CALIBRATION', 'SRC_SIMPLE_PASS'))
)
if clientPractice:
    from Play.Normal.PreliminaryAttack import PreliminaryPracticeKeeper

    Global.controlledRobotNumbers = (0,) if Global.isYellow else (1, 2)
    Global.isTestMode = True
    testStrategy = GameStrategy(SimplePassPlay(), PreliminaryPracticeKeeper())
    Global.autoPreparePreliminaryScene = not Global.isYellow

# Explicit local calibration/legacy modes still override the Client default.
if os.environ.get("SRC_PRELIM") == "1":
    from Play.Normal.PreliminaryAttack import PreliminaryAttack, PreliminaryPracticeKeeper
    Global.controlledRobotNumbers = (0,) if Global.isYellow else (1, 2)
    Global.isTestMode = True
    testStrategy = GameStrategy(PreliminaryAttack(), PreliminaryPracticeKeeper())
    Global.gameStrategies["NormalPlay"] = testStrategy

if os.environ.get("SRC_KICK_CALIBRATION") == "1":
    if not Global.isSimulation or Global.isYellow:
        raise ValueError("Kick calibration is supported only for blue-team simulation")
    if os.environ.get("SRC_KICK_SIMPLE") == "1":
        from Play.Test.SimpleKickCalibration import SimpleKickCalibration as KickCalibration
    else:
        from Play.Test.KickCalibration import KickCalibration
    Global.controlledRobotNumbers = (1,)
    Global.isTestMode = True
    testStrategy = GameStrategy(KickCalibration())

if os.environ.get("SRC_SIMPLE_PASS") == "1":
    if not Global.isSimulation or Global.isYellow:
        raise ValueError("Simple pass practice requires blue-team simulation")
    Global.controlledRobotNumbers = (1, 2)
    Global.isTestMode = True
    testStrategy = GameStrategy(SimplePassPlay())

if clientPractice:
    from ClientPractice import stage_next_team

    stage_next_team('zss.ini', Global.isYellow)
    print(f'CLIENT_NEXT_TEAM {"blue/left" if Global.isYellow else "yellow/right"}', flush=True)

# 如需固定守门员车号，可在此设置并取消下面两行的注释。
# Global.goalieNumber = 0
# Global.defaultRoleNumberStructTable["G"] = Global.RoleNumberStruct(
#     Global.RoleNumberStruct.MatchType.Fixed, Global.goalieNumber
# )
