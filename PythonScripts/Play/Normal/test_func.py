import Global
from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine
from RoleMatch_LuaStyle.Skills import *
from RoleMatch_LuaStyle import Task, State, declare_state_machine, StateMachine
from CppPackage import CGeoPoint
from Vision import Player
from WorldModel import *
import time



class test(State):
    def getTasks(self):
        # 1 号持续追球并启用吸球；此状态只负责接近和控球。
        return {
            "A": Task(RushTo(pos=Ball.pos(), angle=Player.toBallDir(1), flag=Flags.quickly, needDribble=True), fixedNumber=1)
        }
    def getMatchString(self) -> str:
        return ""

    def transFunction(self) -> str:
        # 红外传感器检测到球后再切换到射门状态，避免未控球时提前踢球。
        if Player.isInfraredOn(1) :
            return "test_shoot"
        else :
            return ""


class test_shoot(State):
    def getTasks(self):
        # 红外触发后的后续状态：面向对方球门执行射门。
        return {
            "A": Task(TurnAndShoot(target=Positions.theirGoal, power=16000), fixedNumber=1)
        }
    def getMatchString(self) -> str:
        return ""

    def transFunction(self) -> str:
        return ""

        

@declare_state_machine(test)
class testMachine(StateMachine):
    pass
