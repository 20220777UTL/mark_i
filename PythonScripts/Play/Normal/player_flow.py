"""Two-player passing and shooting example, implemented as explicit status flows."""
from __future__ import annotations

import time
from typing import Optional

from CppPackage import CGeoPoint
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import GetBall, RushTo, SimpleGoTo, StaticGetBall, TurnAndShoot
from Vision import Ball, Player
from WorldModel import Flags
from WorldModel.Positions import theirGoal

position_1 = CGeoPoint(2000, -1000)
position_2 = CGeoPoint(2000, 1000)
pass_power = 6000
ARRIVAL_DISTANCE = 600
GET_BALL_DISTANCE = 50
GET_BALL_ANGLE = 0.5
goalie = 0
player1 = 1
player2 = 2

# Minimum time a status remains active. Ball actions get a longer minimum so
# their task is sent for several decision cycles before a transition is allowed.
MOVE_DELAY_SECONDS = 0.12
BALL_ACTION_DELAY_SECONDS = 0.25


def arrive_at(point: CGeoPoint, role: int):
    return (Player.pos(role).dist(point) < ARRIVAL_DISTANCE)


def got_ball(role: int):
    # return (Player.pos(role).dist(Ball.pos()) < GET_BALL_DISTANCE and -GET_BALL_ANGLE < (Player.direction(role) - float(Player.toBallDir(role))) < GET_BALL_ANGLE)
    return arrive_at(Ball.pos(), role)

class FlowStatus:
    """One named status in a player's flow."""

    name = "status"
    delay = MOVE_DELAY_SECONDS

    def __init__(self):
        self.next: Optional[FlowStatus] = None

    def get_task(self) -> Optional[Task]:
        return None

    def can_advance(self, state: GeneralState) -> bool:
        return False


class P1Start(FlowStatus):
    name = "start"

    def get_task(self) -> Optional[Task]:
        # return Task(SimpleGoTo(position_1, angle=0, flag=0), fixedNumber=player1)
        return None

    def can_advance(self, state: GeneralState) -> bool:
        return arrive_at(position_1, player1)


class P1ReceivePass(FlowStatus):
    name = "arrived_at_p1"
    delay = BALL_ACTION_DELAY_SECONDS

    def get_task(self) -> Optional[Task]:
        return Task(GetBall(flag=Flags.quickly), fixedNumber=player1)

    def can_advance(self, state: GeneralState) -> bool:
        p2_status = state.player_flows[player2].memory.status
        return p2_status.name == "shot_ball_from_start" and got_ball(player1)


class P1PassToP2(FlowStatus):
    name = "got_ball_at_p1"
    delay = BALL_ACTION_DELAY_SECONDS

    def get_task(self) -> Optional[Task]:
        return Task(
            TurnAndShoot(target=position_2, power=pass_power, flag=0),
            fixedNumber=player1,
        )

    def can_advance(self, state: GeneralState) -> bool:
        return not got_ball(player1)


class P1End(FlowStatus):
    name = "end"
    delay = 0.0


class P2Start(FlowStatus):
    name = "start"
    delay = BALL_ACTION_DELAY_SECONDS

    def get_task(self) -> Optional[Task]:
        return Task(
            RushTo(
                Ball.pos(),
                angle=Player.toBallDir(player2),
                flag=Flags.quickly,
                needDribble=True,
            ),
            fixedNumber=player2,
        )

    def can_advance(self, state: GeneralState) -> bool:
        return got_ball(player2)

class P2Test(FlowStatus):
    name = "test"
    delay = 0
    def get_task(self):
        return Task(
            SimpleGoTo(
                CGeoPoint(-3000,2000),
                angle=0,
                flag=0
            ),
            fixedNumber=player2
        )

    def can_advance(self, state: GeneralState) -> bool:
        return False

class P2PassToP1(FlowStatus):
    name = "found_ball"
    delay = BALL_ACTION_DELAY_SECONDS

    def get_task(self) -> Optional[Task]:
        return Task(
            StaticGetBall(target=position_1, kickPower=10000, chipPower=0),
            fixedNumber=player2,
        )

    def can_advance(self, state: GeneralState) -> bool:
        return not got_ball(player2)


class P2MoveToPosition2(FlowStatus):
    name = "shot_ball_from_start"

    def get_task(self) -> Optional[Task]:
        return Task(SimpleGoTo(position_2), fixedNumber=player2)

    def can_advance(self, state: GeneralState) -> bool:
        p1_status = state.player_flows[player1].memory.status
        return p1_status.name == "end" and arrive_at(position_2, player2)


class P2ReceiveAtPosition2(FlowStatus):
    name = "arrived_at_p2"
    delay = BALL_ACTION_DELAY_SECONDS

    def get_task(self) -> Optional[Task]:
        return Task(
            RushTo(
                Ball.pos(),
                angle=Player.toBallDir(player2),
                flag=Flags.quickly,
                needDribble=True,
            ),
            fixedNumber=player2,
        )

    def can_advance(self, state: GeneralState) -> bool:
        return got_ball(player2)


class P2ShootToGoal(FlowStatus):
    name = "got_ball_at_p2"
    delay = BALL_ACTION_DELAY_SECONDS

    def get_task(self) -> Optional[Task]:
        return Task(
            StaticGetBall(target=theirGoal, kickPower=16000, chipPower=300),
            fixedNumber=player2,
        )

    def can_advance(self, state: GeneralState) -> bool:
        return not got_ball(player2)


class P2End(FlowStatus):
    name = "end"
    delay = 0.0


class PlayerFlow:
    """A reusable flow runner; each player gets its own instance and memory."""

    def __init__(self, player_number: int, role_name: str, statuses: list[FlowStatus]):
        self.player_number = player_number
        self.role_name = role_name
        self.statuses = {status.name: status for status in statuses}
        self.memory = FlowMemory(statuses[0])

    def next_status_if_ready(self, state: GeneralState, now: float) -> Optional[FlowStatus]:
        current = self.memory.status
        if current.next is None:
            return None
        if now - self.memory.status_entered_at < current.delay:
            return None
        if current.can_advance(state):
            return current.next
        return None


class FlowMemory:
    """Current status plus the monotonic time it was entered."""

    def __init__(self, initial_status: FlowStatus):
        self.status = initial_status
        self.status_entered_at = time.monotonic()

    def enter(self, status: FlowStatus, now: float) -> None:
        self.status = status
        self.status_entered_at = now


def make_player1_flow() -> PlayerFlow:
    start = P1Start()
    receive_pass = P1ReceivePass()
    pass_to_p2 = P1PassToP2()
    end = P1End()

    # Explicit graph: start -> receive -> pass -> end.
    start.next = receive_pass
    receive_pass.next = pass_to_p2
    pass_to_p2.next = end
    end.next = None

    return PlayerFlow(player1, "A", [start, receive_pass, pass_to_p2, end])


def make_player2_flow() -> PlayerFlow:
    start = P2Start()
    pass_to_p1 = P2PassToP1()
    move_to_p2 = P2MoveToPosition2()
    receive_at_p2 = P2ReceiveAtPosition2()
    shoot_to_goal = P2ShootToGoal()
    test = P2Test()
    end = P2End()

    # Explicit graph: collect/pass -> move -> receive -> shoot -> end.
    # start.next = pass_to_p1
    start.next = test
    pass_to_p1.next = move_to_p2
    move_to_p2.next = receive_at_p2
    receive_at_p2.next = shoot_to_goal
    shoot_to_goal.next = end
    end.next = None

    return PlayerFlow(
        player2,
        "B",
        [start, pass_to_p1, move_to_p2, receive_at_p2, shoot_to_goal, end, test],
    )


class GeneralState(State):
    def __init__(self):
        super().__init__()
        self.player_flows = {
            player1: make_player1_flow(),
            player2: make_player2_flow(),
        }
    def getTasks(self) -> dict[str, Task]:
        tasks: dict[str, Task] = {}
        for flow in self.player_flows.values():
            task = flow.memory.status.get_task()
            if task is not None:
                tasks[flow.role_name] = task
        return tasks

    def getMatchString(self) -> str:
        return ""

    def transFunction(self) -> str:
        now = time.monotonic()
        transitions = []

        # State.run calls transFunction after this frame's tasks have run.
        # Evaluate both flows against the same frame, then commit transitions.
        for flow in self.player_flows.values():
            next_status = flow.next_status_if_ready(self, now)
            if next_status is not None:
                transitions.append((flow, next_status))

        for flow, next_status in transitions:
            flow.memory.enter(next_status, now)

        return ""


@declare_state_machine(GeneralState)
class zz(StateMachine):
    pass
