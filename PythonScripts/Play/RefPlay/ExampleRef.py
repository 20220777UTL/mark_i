"""裁判指令策略占位。可复制此文件，为不同指令编写独立策略。"""

from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine


class RefState(State):
    def getTasks(self):
        # 在此填写当前裁判指令下的机器人任务。
        return {}

    def getMatchString(self):
        return ""

    def transFunction(self):
        # 如需主动结束裁判策略，可返回 "exit"。
        return ""


@declare_state_machine(RefState)
class ExampleRef(StateMachine):
    pass
