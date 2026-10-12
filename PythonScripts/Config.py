"""校赛入口：选手填写五个 Example 模板，三个官方裁判策略统一提供。

不使用点球；人工摆球期间沿用 GameHalt，所有车辆停止并关闭吸球和踢球。
"""

import Global
from Play.Normal.ExampleNormalPlay import ExampleNormalPlay
from Play.Normal.test_func import testMachine
from Play.RefPlay.ExampleKickOff import ExampleKickOff
from Play.RefPlay.ExampleKickOffDefend import ExampleKickOffDefend
from Play.RefPlay.ExampleFreeKick import ExampleFreeKick
from Play.RefPlay.ExampleFreeKickDefend import ExampleFreeKickDefend
from Play.RefPlay.GameHalt import GameHalt
from Play.RefPlay.GameStop import GameStop
from Play.RefPlay.OurTimeout import OurTimeout
from Play.Test.Test_Goalie2022 import Test_Goalie2022
from Play.Normal.two_attack import two_attack
from Play.Normal.zz import zz


Global.isTestMode = True
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
    "NormalPlay": GameStrategy(ExampleNormalPlay()),
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

testStrategy = GameStrategy(zz())

# 如需固定守门员车号，可在此设置并取消下面两行的注释。
# Global.goalieNumber = 0
# Global.defaultRoleNumberStructTable["G"] = Global.RoleNumberStruct(
#     Global.RoleNumberStruct.MatchType.Fixed, Global.goalieNumber
# )
