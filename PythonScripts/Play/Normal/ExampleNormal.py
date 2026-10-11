"""常规比赛策略占位。请在 getTasks() 中填写机器人任务。"""

from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine


class NormalState(State):
    def getTasks(self):
        # 例如在此返回 {"A": Task(...)}；空表表示暂不下发任务。
        return {}

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(NormalState)
class ExampleNormal(StateMachine):
    pass
