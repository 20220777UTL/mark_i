"""选手编写：对方直接、间接任意球的防守。默认不下发任务。"""

import Global
from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine
from WorldModel import Conditions


class FreeKickDefendState(State):
    def getTasks(self):
        return {}

    def getMatchString(self):
        return ""

    def transFunction(self):
        return "exit" if Conditions.isGameOn() else ""


@declare_state_machine(FreeKickDefendState)
class ExampleFreeKickDefend(StateMachine):
    def hookBeforePlanTasks(self):
        Global.hasFinishedRefPlay = False
