"""来自 skill/stable@4a807407 的 OurTimeout：前往统一暂停点位。

改为按受控车号分配 Positions.getTimeOutPos，目标保留车体到边线的余量。
"""

import Global
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import RushTo
from WorldModel import Conditions, Flags, Positions
from Play.RefPlay.OfficialSupport import (
    clamp_to_field, controlled_numbers, disable_ball_actions, role_for, stop_tasks,
)


class Move(State):
    def getTasks(self):
        tasks = stop_tasks()
        for index, number in enumerate(controlled_numbers(visible_only=True)):
            tasks[role_for(number)] = Task(
                RushTo(clamp_to_field(Positions.getTimeOutPos(index)),
                       angle=0, maxAcc=2000, flag=Flags.allow_dss),
                fixedNumber=number,
            )
        return tasks

    def getMatchString(self):
        return ""

    def transFunction(self):
        return "exit" if Conditions.isGameOn() else ""


@declare_state_machine(Move)
class OurTimeout(StateMachine):
    def hookBeforePlanTasks(self):
        Global.hasFinishedRefPlay = False
        disable_ball_actions()
