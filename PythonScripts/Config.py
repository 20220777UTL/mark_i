"""初赛本机练习入口：蓝方双车进攻，黄方练习守门员。

不使用点球；人工摆球期间沿用 GameHalt，所有车辆停止并关闭吸球和踢球。
"""

import Global
from pathlib import Path
from Play.Normal.PreliminaryAttack import ATTACKERS, PreliminaryAttack, MoveCheck
from Play.Normal.PracticeNativeGoalie import PracticeNativeGoalie
from Play.Normal.GoalieFool import GoalieFool
from Play.Normal.ExampleNormalPlay import ExampleNormalPlay
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
# 按用户提供的官方初始图使用蓝方 0、1 号与黄方 0 号。
Global.controlledRobotNumbers = (0,) if Global.isYellow else ATTACKERS
Global.goalieNumber = 0
_mode = Path("practice_mode.txt").read_text(encoding="utf-8").strip()
if _mode not in ("move", "attack", "attack_v2", "pass_combo", "motion_calibration", "bare_rushtov4", "bare_simplegoto"):
    raise ValueError("Unknown practice_mode.txt selection")
if _mode == "bare_simplegoto":
    from Play.Test.BareSimpleGoTo import BareSimpleGoTo
    _blue = BareSimpleGoTo()
elif _mode == "bare_rushtov4":
    from Play.Test.BareRushToV4 import BareRushToV4
    _blue = BareRushToV4()
elif _mode == "motion_calibration":
    from Play.Test.MotionCalibration import MotionCalibration
    _blue = MotionCalibration()
elif _mode == "pass_combo":
    from Play.Normal.PreliminaryPassCombo import PreliminaryPassCombo
    _blue = PreliminaryPassCombo()
    if not Global.isYellow:
        Global.controlledRobotNumbers = None  # Stop/Halt covers every possible blue ID.
elif _mode == "attack_v2":
    from Play.Normal.PreliminaryAttackV2 import PreliminaryAttackV2
    _blue = PreliminaryAttackV2()
else:
    _blue = MoveCheck() if _mode == "move" else PreliminaryAttack()


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
    "NormalPlay": GameStrategy(_blue, PracticeNativeGoalie()),
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

testStrategy = GameStrategy(_blue, PracticeNativeGoalie())
print(f"[PRELIM] mode={_mode} team={'yellow' if Global.isYellow else 'blue'} referee=enabled", flush=True)

# 如需固定守门员车号，可在此设置并取消下面两行的注释。
# Global.goalieNumber = 0
# Global.defaultRoleNumberStructTable["G"] = Global.RoleNumberStruct(
#     Global.RoleNumberStruct.MatchType.Fixed, Global.goalieNumber
# )
