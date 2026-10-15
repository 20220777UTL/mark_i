"""校赛入口：选手填写五个 Example 模板，三个官方裁判策略统一提供。

不使用点球；人工摆球期间沿用 GameHalt，所有车辆停止并关闭吸球和踢球。
"""

import os
import Global
from Play.Normal.ExampleNormalPlay import ExampleNormalPlay
from Play.RefPlay.ExampleKickOff import ExampleKickOff
from Play.RefPlay.ExampleKickOffDefend import ExampleKickOffDefend
from Play.RefPlay.ExampleFreeKick import ExampleFreeKick
from Play.RefPlay.ExampleFreeKickDefend import ExampleFreeKickDefend
from Play.RefPlay.GameHalt import GameHalt
from Play.RefPlay.GameStop import GameStop
from Play.RefPlay.OurTimeout import OurTimeout
from Play.Test.Test_Goalie2022 import Test_Goalie2022


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

if os.environ.get("SRC_GIVE_AND_GO_TEST") == "1":
    from Play.Test.Test_GiveAndGo import Test_GiveAndGo, ROBOT_IDS
    Global.isTestMode = True
    Global.controlledRobotNumbers = (Global.goalieNumber,) if Global.isYellow else ROBOT_IDS
    testStrategy = GameStrategy(Test_GiveAndGo(), Test_Goalie2022())
    team = "YELLOW" if Global.isYellow else "BLUE"
    play = "Test_Goalie2022" if Global.isYellow else "Test_GiveAndGo"
    print(f"[src-test] {team}: {play}; robots={Global.controlledRobotNumbers}", flush=True)
elif os.environ.get("SRC_CORNER_PASS_TEST") == "1":
    from Play.Test.Test_CornerPassShot import Test_CornerPassShot, PASSER, RECEIVER
    Global.controlledRobotNumbers = (PASSER, RECEIVER)
    testStrategy = GameStrategy(Test_CornerPassShot())
else:
    # 原始比赛包不含本仓库的默认策略；显式测试模式不依赖它。
    from Play.Normal.two_attack import two_attack
    testStrategy = GameStrategy(two_attack())

# 如需固定守门员车号，可在此设置并取消下面两行的注释。
# Global.goalieNumber = 0
# Global.defaultRoleNumberStructTable["G"] = Global.RoleNumberStruct(
#     Global.RoleNumberStruct.MatchType.Fixed, Global.goalieNumber
# )
