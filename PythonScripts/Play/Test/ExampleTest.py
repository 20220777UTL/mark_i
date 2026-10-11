"""测试模式策略占位。使用 main.py --test 启用。"""

from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine


class TestState(State):
    def getTasks(self):
        # 在此填写要单独测试的机器人任务。

        return {}

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(TestState)
class ExampleTest(StateMachine):
    pass
