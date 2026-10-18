"""One fixed-point move using the supplied skill with default flags."""
import math
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import RushToV4, Stop


class BareMove(State):
    def getTasks(self):
        return {
            "Mover": Task(RushToV4(CGeoPoint(4200, -1500), math.pi), fixedNumber=1),
            "Idle": Task(Stop(), fixedNumber=0),
        }

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(BareMove)
class BareRushToV4(StateMachine):
    pass
