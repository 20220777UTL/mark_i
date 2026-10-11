"""适配 skill/stable@4a807407 的 Stop -> Run 流程和 STOP 点位（mode=1）。

删去原版 11V11 的 WBack/WMarking/自动守门分支，使用基础 RushTo 退球站位。
按实际有效车辆站位，可在 Config.py 限定车号；球不可见时明确停止。
"""

import Global
from CppPackage import getPosModulePos
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import RushTo
from Vision import Ball, Player
from WorldModel import Conditions, Flags
from Play.RefPlay.OfficialSupport import (
    clamp_to_field, controlled_numbers, disable_ball_actions, role_for, stop_tasks,
)


ACC = 2000
# C++ PosModule 的每组 STOP 点位只有七个；其余车辆保持停止，避免索引越界。
STOP_POSITION_COUNT = 7
STOP_DSS = Flags.slowly | Flags.dodge_ball | Flags.allow_dss | Flags.avoid_stop_ball_circle


class StopState(State):
    def getTasks(self):
        return stop_tasks()

    def getMatchString(self):
        return ""

    def transFunction(self):
        return "exit" if Conditions.isGameOn() else "Run"


class Run(State):
    def getTasks(self):
        tasks = stop_tasks()
        if not Ball.ball().Valid():
            return tasks
        for index, number in enumerate(controlled_numbers(visible_only=True)[:STOP_POSITION_COUNT]):
            tasks[role_for(number)] = Task(
                RushTo(clamp_to_field(getPosModulePos(index, 1)),
                       angle=Player.toBallDir(number), maxAcc=ACC, flag=STOP_DSS),
                fixedNumber=number,
            )
        return tasks

    def getMatchString(self):
        return ""

    def transFunction(self):
        return "exit" if Conditions.isGameOn() else ""


@declare_state_machine(StopState, Run)
class GameStop(StateMachine):
    def hookBeforePlanTasks(self):
        Global.hasFinishedRefPlay = False
        disable_ball_actions()
