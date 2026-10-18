"""Yellow practice keeper using the supplied standard Goalie skill."""
import Global
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Goalie
from Play.Normal.PreliminaryAttack import Telemetry


class NativeGoalieState(State):
    def getTasks(self):
        return {'G': Task(Goalie(), fixedNumber=Global.goalieNumber)}

    def getMatchString(self):
        return ''

    def transFunction(self):
        return ''


@declare_state_machine(NativeGoalieState)
class PracticeNativeGoalie(Telemetry, StateMachine):
    pass
