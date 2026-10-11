"""裁判入口：开球/任意球交给选手，暂停/停止统一处理。

校赛不使用点球和自动摆球；这些指令以及未知指令均执行 GameHalt。
"""

import Global


REFEREE_STRATEGIES = {
    "GameHalt": "GameHalt",
    "Ref_Halt": "GameHalt",
    "GameOver": "GameHalt",
    "GameStop": "GameStop",
    "OurKickOff": "KickOff",
    "TheirKickOff": "KickOffDef",
    "OurDirectKick": "FreeKick",
    "OurIndirectKick": "FreeKick",
    "TheirDirectKick": "FreeKickDef",
    "TheirIndirectKick": "FreeKickDef",
    "OurTimeout": "TimeOut",
    "TheirTimeout": "TimeOut",
    "OurPenaltyKick": "GameHalt",
    "TheirPenaltyKick": "GameHalt",
    "OurBallPlacement": "GameHalt",
    "TheirBallPlacement": "GameHalt",
}


def runRefPlay(curRefMsg: str):
    key = REFEREE_STRATEGIES.get(curRefMsg, "GameHalt")
    Global.gameStrategies[key].runStrategy()
