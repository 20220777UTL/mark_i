"""选手编写：常规比赛中的进攻、防守和角色切换。默认不下发任务。"""
import Global
from RoleMatch_LuaStyle import State, StateMachine, declare_state_machine
from RoleMatch_LuaStyle.Skills import *
from RoleMatch_LuaStyle import Task, State, declare_state_machine, StateMachine
from CppPackage import CGeoPoint
from Vision import Player
from WorldModel import *
import time

position_1 = CGeoPoint(1000,-500)
position_2 = CGeoPoint(1000,500)
pass_power = 6000
ARRIVAL_DISTANCE = 200
goalie = 0
player1 = 1
player2 = 2

def arrive_at(point: CGeoPoint, role: int):
    return (Player.pos(role).dist(point) < ARRIVAL_DISTANCE)

player1_flow = [
    {
        "description": "start",
        "next": (lambda : arrive_at(position_1, player1)),
        "task": Task(SimpleGoTo(position_1, angle=0, flag = 0)) #有可能需要用lambda
    },
    {
        "description": "arrived_at_p1",
        "next": (lambda : Player.isInfraredOn(player1)),
        "task": Task(GetBall(flag=0))
    },
    {
        "description": "got_ball_at_p1",
        "next": not (lambda : Player.isInfraredOn(player1)), 
        "task": Task(TurnAndShoot(target=position_2, power=6000, flag = 0))
    },
    {
        "description": "shot_ball_from_p1",
        "next": True,
        "task": Task(None)
    },
    {
        "description": "end",
        "next": False
    },
]
player2_flow = [
    {
        "description": "start",
        "next": True
    },
    {
        "description": "shot_ball_from_start",
        "next": True
    },
    {
        "description": "arrived_at_p2",
        "next": True
    },
    {
        "description": "got_ball_at_p2",
        "next": True
    },
    {
        "description": "shot_ball_from_p2",
        "next": True
    },
    {
        "description": "end",
        "next": False
    },
]

memory = {
    player1: {
        "status":{
            "description": "start",
            "time": "None"
        }
    },
    player2:{
        "status":{
            "description": "start",
            "time": "None"
        }
    }
}
"""
Statuses:
    player1: start, arrived_at_p1, got_ball_at_p1, shot_ball_from_p1, end
    player2: start, shot_ball_from_start, arrived_at_p2, got_ball_at_p2, shot_ball_from_p2, end
"""

class GeneralState(State):
    def getTasks(self):


        

@declare_state_machine(GeneralState)
class zz(StateMachine):
    pass