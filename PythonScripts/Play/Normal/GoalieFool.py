"""单状态练习守门员：距球门线 200 mm，在门前两端往返，不追踪球。"""

import Global
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import RushTo
from Vision import Player
from WorldModel import Params, taskMediator


GOAL_LINE_OFFSET = 200
ARRIVAL_DISTANCE = 80
MAX_ACC = 1000


class SweepState(State):
    def __init__(self):
        super().__init__()
        self.target_side = 1

    def getTasks(self):
        goalie = Global.goalieNumber
        x = -Params.pitchLength / 2 + GOAL_LINE_OFFSET
        # 目标限制在两门柱内并为机器人半径留边，避免巡逻点贴住门柱。
        half_span = max(0, Params.goalWidth / 2 - Params.playerRadius)
        target = CGeoPoint(x, self.target_side * half_span)
        # 到达当前一侧后翻转方向，下一帧开始往另一侧巡逻。
        if Player.Pos(goalie).dist(target) < ARRIVAL_DISTANCE:
            self.target_side *= -1
            target = CGeoPoint(x, self.target_side * half_span)

        # RushTo 在禁区内执行，需要先向 C++ 注册守门员身份。
        taskMediator.registerRole(goalie, "goalie")
        return {
            "G": Task(
                RushTo(target, angle=0, maxAcc=MAX_ACC),
                fixedNumber=goalie,
            )
        }

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(SweepState)
class GoalieFool(StateMachine):
    pass
