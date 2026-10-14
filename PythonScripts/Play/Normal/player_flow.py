"""Two-player passing and shooting example, implemented as explicit status flows."""
from __future__ import annotations

import time
from typing import Optional

from CppPackage import CGeoPoint
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import *
from Vision import Ball, Player
from WorldModel import Flags
from WorldModel.Positions import theirGoal
import math

position_1 = CGeoPoint(2000, -1000)
position_2 = CGeoPoint(2000, 1000)
pass_power = 6000
ARRIVAL_DISTANCE = 150
GET_BALL_DISTANCE = 50
GET_BALL_ANGLE = 0.5
goalie = 0
player1 = 1
player2 = 2

# Minimum time a status remains active. Ball actions get a longer minimum so
# their task is sent for several decision cycles before a transition is allowed.
MOVE_DELAY_SECONDS = 0.1
BALL_ACTION_DELAY_SECONDS = 0.1


def arrive_at(point: CGeoPoint, role: int, dist: float = ARRIVAL_DISTANCE):
    # 统一用机器人中心到目标点的距离判断到位，dist 可为不同阶段单独放宽。
    return (Player.pos(role).dist(point) < dist)

def got_ball(role: int, dist: float = ARRIVAL_DISTANCE):
    # return (Player.pos(role).dist(Ball.pos()) < GET_BALL_DISTANCE and -GET_BALL_ANGLE < (Player.direction(role) - float(Player.toBallDir(role))) < GET_BALL_ANGLE)
    # 当前示例把“拿到球”近似为机器人进入球附近；朝向检测留作更严格的替代条件。
    return arrive_at(Ball.pos(), role, dist)

def kick_ball_pos(ballpos: CGeoPoint, target: CGeoPoint, prep_length: float = 100):
    """Return the kick angle and a point prep_length behind the ball."""
    dx = target.x() - ballpos.x()
    dy = target.y() - ballpos.y()
    # 球与目标重合时没有可定义的踢球方向，尽早报错，避免生成无效站位。
    if dx == 0 and dy == 0:
        raise ValueError("kick target must differ from ball position")

    angle = math.atan2(dy, dx)
    ret_pos = CGeoPoint(
        ballpos.x() - math.cos(angle) * prep_length,
        ballpos.y() - math.sin(angle) * prep_length,
    )
    return angle, ret_pos

def good_angle(role: int, target: CGeoPoint):
    xrole, yrole = Player.posX(role), Player.posY(role)
    xball, yball = Ball.posX(), Ball.posY()
    xtarget, ytarget = target.x(), target.y()
    ball_dx, ball_dy = xball - xrole, yball - yrole
    target_dx, target_dy = xtarget - xrole, ytarget - yrole
    # 机器人正好与球或目标重合时，方向角无定义，不能判定为准备好。
    if (ball_dx == 0 and ball_dy == 0) or (target_dx == 0 and target_dy == 0):
        return False

    angle_role_ball = math.atan2(ball_dy, ball_dx)
    angle_role_target = math.atan2(target_dy, target_dx)
    angle_error = math.atan2(
        math.sin(angle_role_ball - angle_role_target),
        math.cos(angle_role_ball - angle_role_target),
    )
    return abs(angle_error) < GET_BALL_ANGLE

def ready_to_shoot(role: int, target: CGeoPoint):
    # 先确认进入球附近，再检查从机器人看球和传球目标是否大致处于同一方向。
    if not arrive_at(Ball.pos(), role):
        return False
    else:
        return (
            good_angle(role, target)
        )

def kick_moving_ball_pos(ballpos: CGeoPoint, target: CGeoPoint, prep_length: float = 150):#todo: take ball speed into consideration
    """Return the kick angle and a point prep_length behind the moving ball."""
    dx = target.x() - ballpos.x()
    dy = target.y() - ballpos.y()
    # 同样拒绝无方向的目标，避免后续速度补偿基于无效角度。
    if dx == 0 and dy == 0:
        raise ValueError("kick target must differ from ball position")

    angle = math.atan2(dy, dx)

    ball_vx = Ball.velX()
    ball_vy = Ball.velY()

    ret_pos = CGeoPoint(
        ballpos.x() - math.cos(angle) * prep_length + ball_vx * 100,
        ballpos.y() - math.sin(angle) * prep_length + ball_vy * 100,
    )
    return angle, ret_pos


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

class FlowMemory:
    """Current status plus the monotonic time it was entered."""

    def __init__(self, initial_status: FlowStatus):
        self.status = initial_status
        self.status_entered_at = time.monotonic()

    def enter(self, status: FlowStatus, now: float) -> None:
        self.status = status
        self.status_entered_at = now

class PlayerFlow:
    """A reusable flow runner; each player gets its own instance and memory."""

    def __init__(self, player_number: int, role_name: str, statuses: list[FlowStatus]):
        self.player_number = player_number
        self.role_name = role_name
        self.statuses = {status.name: status for status in statuses}
        self.memory = FlowMemory(statuses[0])

    def next_status_if_ready(self, state: GeneralState, now: float) -> Optional[FlowStatus]:
        current = self.memory.status
        # 末状态没有后继；其他状态也必须先满足最短驻留时间，避免每帧重复触发。
        if current.next is None:
            return None
        if now - self.memory.status_entered_at < current.delay:
            return None
        if current.can_advance(state):
            # 条件只负责确认当前阶段已完成，具体后继由状态图中的 next 指定。
            return current.next
        return None


class Player1Flow(PlayerFlow):
    class P1Start(FlowStatus):
        name = "start"

        def get_task(self) -> Optional[Task]:
            return Task(SimpleGoTo(point=kick_ball_pos(position_1, position_2)[1], angle=kick_ball_pos(position_1, position_2)[0], flag=Flags.quickly), fixedNumber=player1)
            # return None

        def can_advance(self, state: GeneralState) -> bool:
            return got_ball(player1, 400)

    class P1ReceivePass(FlowStatus):
        name = "arrived_at_p1"
        delay = 0.05

        def get_task(self) -> Optional[Task]:
            return Task(SimpleGoTo(kick_ball_pos(Ball.pos(),position_2)[1], kick_ball_pos(Ball.pos(),position_2)[0],flag=Flags.quickly), fixedNumber=player1)
            return None
        
        def can_advance(self, state: GeneralState) -> bool:
            p2_status = state.player_flows[player2].memory.status
            """
            现在一个核心问题是如何在运动中传球。
            首先，等球过来再启动的方案已经否决了。
            """
            # 只有队员 2 已进入接应跑位阶段，且队员 1 到球、球与目标相对位置满足传球几何条件，才允许传球。
            return p2_status.name == "shot_ball_from_start" and ready_to_shoot(role=player1, target=position_2)

    class P1PassToP2(FlowStatus):
        name = "got_ball_at_p1"
        delay = BALL_ACTION_DELAY_SECONDS

        def get_task(self) -> Optional[Task]:
            return Task(
                StaticGetBall(target=position_2, kickPower=6000, chipPower=0),
                fixedNumber=player1,
            )

        def can_advance(self, state: GeneralState) -> bool:
            # 队员 1 的传球阶段暂不自动结束，保留手动/后续策略接管空间。
            # return not got_ball(player1)
            return False

    class P1End(FlowStatus):
        name = "end"
        delay = 0.0

    def __init__(self):
        start = self.P1Start()
        receive_pass = self.P1ReceivePass()
        pass_to_p2 = self.P1PassToP2()
        end = self.P1End()

        # Explicit graph: start -> receive -> pass -> end.
        start.next = receive_pass
        receive_pass.next = pass_to_p2
        pass_to_p2.next = end
        end.next = None

        super().__init__(player1, "A", [start, receive_pass, pass_to_p2, end])


class Player2Flow(PlayerFlow):
    class P2Start(FlowStatus):
        name = "start"
        delay = BALL_ACTION_DELAY_SECONDS

        def get_task(self) -> Optional[Task]:
            return Task( #todo: here we should actually make a lambda function, or the Task will be fixed once the class is declared.
                SimpleGoTo(
                    # Ball.pos(),
                    point=kick_ball_pos(Ball.pos(), position_1)[1],
                    angle=kick_ball_pos(Ball.pos(), position_1)[0],
                    # position_1,
                    flag=Flags.quickly,
                ),
                fixedNumber=player2,
            )

        def can_advance(self, state: GeneralState) -> bool:
            # 双条件都满足才启动传球：队员 2 控球，队员 1 已抵达接球位置。
            return got_ball(player2) and arrive_at(position_1, player1)

    class P2PassToP1(FlowStatus):
        name = "found_ball"
        delay = BALL_ACTION_DELAY_SECONDS

        def get_task(self) -> Optional[Task]:
            return Task(
                TurnAndShoot(target=position_1, power=6000, flag=Flags.nothing),
                fixedNumber=player2,
            )

        def can_advance(self, state: GeneralState) -> bool:
            # 球离开队员 2 的控制范围后，认为传球动作已发出并进入跑位阶段。
            return not got_ball(player2)

    class P2MoveToPosition2(FlowStatus):
        name = "shot_ball_from_start"

        def get_task(self) -> Optional[Task]:
            return Task(SimpleGoTo(position_2), fixedNumber=player2)

        def can_advance(self, state: GeneralState) -> bool:
            p1_status = state.player_flows[player1].memory.status
            # return p1_status.name == "end" and arrive_at(position_2, player2)
            # 该阶段当前刻意不自动结束，避免接球流程尚未准备好就继续推进。
            return False

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
            # 机器人重新进入球附近后，才切换到射门任务。
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
            # 球离开控制范围表示射门动作已发出，随后进入结束状态。
            return not got_ball(player2)

    class P2End(FlowStatus):
        name = "end"
        delay = 0.0

    def __init__(self):
        start = self.P2Start()
        pass_to_p1 = self.P2PassToP1()
        move_to_p2 = self.P2MoveToPosition2()
        receive_at_p2 = self.P2ReceiveAtPosition2()
        shoot_to_goal = self.P2ShootToGoal()
        end = self.P2End()

        # Explicit graph: collect/pass -> move -> receive -> shoot -> end.
        # start.next = pass_to_p1
        start.next = pass_to_p1
        pass_to_p1.next = move_to_p2
        move_to_p2.next = receive_at_p2
        receive_at_p2.next = shoot_to_goal
        shoot_to_goal.next = end
        end.next = None

        super().__init__(
            player2,
            "B",
            [start, pass_to_p1, move_to_p2, receive_at_p2, shoot_to_goal, end],
        )


def make_player1_flow() -> PlayerFlow:
    return Player1Flow()


def make_player2_flow() -> PlayerFlow:
    return Player2Flow()


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
            # 无任务的状态不写入映射，避免覆盖其他角色或下发空任务。
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
            # 先收集本帧所有可转移项，再统一提交，避免一个队员的更新影响另一个队员本帧的判断。
            if next_status is not None:
                transitions.append((flow, next_status))

        for flow, next_status in transitions:
            flow.memory.enter(next_status, now)

        return ""


@declare_state_machine(GeneralState)
class zz(StateMachine):
    pass
