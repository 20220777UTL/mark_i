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
        return {
            "A": Task(RushTo(pos=Ball.pos(), angle=Player.toBallDir(1), flag=Flags.quickly, needDribble=True), fixedNumber=1)
        }
    def getMatchString(self) -> str:
        return ""

    def transFunction(self) -> str:
        if Player.isInfraredOn(1) :
            return "test_shoot"
        else :
            return ""


class test_shoot(State):
    def getTasks(self):
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