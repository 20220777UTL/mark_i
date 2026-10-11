"""选手编写：我方开球的站位、开球和状态切换。默认不下发任务。"""

import Global
from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine
from WorldModel import Conditions


class KickOffState(State):
    def getTasks(self):
        return {}

    def getMatchString(self):
        return ""

    def transFunction(self):
        # 写完开球流程后，可以在自定条件满足时返回 "exit"。
        return "exit" if Conditions.isGameOn() else ""


@declare_state_machine(KickOffState)
class ExampleKickOff(StateMachine):
    def hookBeforePlanTasks(self):
        Global.hasFinishedRefPlay = False
