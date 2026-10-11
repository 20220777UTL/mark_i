"""来自 skill/stable@4a807407 的 GameHalt：明确停止；按校赛受控车号适配。

人工摆球和不使用的点球指令也映射到本策略，关闭吸球和踢球。
"""

from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine
from Play.RefPlay.OfficialSupport import disable_ball_actions, stop_tasks


class Halt(State):
    def getTasks(self):
        return stop_tasks()

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(Halt)
class GameHalt(StateMachine):
    def hookBeforePlanTasks(self):
        disable_ball_actions()
