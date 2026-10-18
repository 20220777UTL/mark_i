"""One fixed-point move using the supplied skill with default flags."""
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import SimpleGoTo, Stop


class BareMove(State):
    def getTasks(self):
        return {
            "Mover": Task(SimpleGoTo(CGeoPoint(4200, -1500)), fixedNumber=1),
            "Idle": Task(Stop(), fixedNumber=0),
        }

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(BareMove)
class BareSimpleGoTo(StateMachine):
    pass
