"""选手编写：对方开球时的防守站位。默认不下发任务。"""

import Global
from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine
from WorldModel import Conditions


class KickOffDefendState(State):
    def getTasks(self):
        return {}

    def getMatchString(self):
        return ""

    def transFunction(self):
        return "exit" if Conditions.isGameOn() else ""


@declare_state_machine(KickOffDefendState)
class ExampleKickOffDefend(StateMachine):
    def hookBeforePlanTasks(self):
        Global.hasFinishedRefPlay = False
