"""Goalie2022 仿真测试：固定 Global.goalieNumber，只执行守门员任务。

在仿真中向我方球门射球观察扑救，将慢球放入禁区观察清球。
常规防守需要裁判状态为比赛进行中；测试点球时将 MODE 改为 "penalty"。
使用前需重新配置 CMake 并编译 MedusaCore 和 CppPackage。
"""

import Global
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Goalie2022


MODE = "normal"


class Goalie2022State(State):
    def getTasks(self):
        return {
            "G": Task(Goalie2022(mode=MODE), fixedNumber=Global.goalieNumber),
        }

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(Goalie2022State)
class Test_Goalie2022(StateMachine):
    pass
