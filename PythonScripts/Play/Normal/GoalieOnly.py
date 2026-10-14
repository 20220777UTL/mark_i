"""黄队测试对手：只让 0 号执行内置 Goalie。"""
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill


class KeepGoal(State):
    def getTasks(self):
        # 将 G 角色固定到 0 号机器人，由内置守门技能负责站位和扑救。
        return {"G": Task(Skill.Goalie(), fixedNumber=0)}

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(KeepGoal)
class GoalieOnly(StateMachine):
    pass
