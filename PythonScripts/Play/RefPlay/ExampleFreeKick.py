"""选手编写：我方直接、间接任意球的进攻。默认不下发任务。"""

import Global
from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine
from WorldModel import Conditions


class FreeKickState(State):
    def getTasks(self):
        return {}

    def getMatchString(self):
        return ""

    def transFunction(self):
        # 可以按出球、接球等条件自行结束任意球流程。
        return "exit" if Conditions.isGameOn() else ""


@declare_state_machine(FreeKickState)
class ExampleFreeKick(StateMachine):
    def hookBeforePlanTasks(self):
        Global.hasFinishedRefPlay = False
