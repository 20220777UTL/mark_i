import math

import Utils
from Geometry import *
from Vision import Player, Ball
from WorldModel import Params
from WorldModel import Positions


def specified(num):
    def inner():
        return num * math.pi / 180
    return inner

def ballToPoint(p):
    tp = p() if callable(p) else p
    return (tp - Ball.pos()).dir()

def playerToPoint(target, role):
    if role is None:
        print("Invalid Role in ourPlayerToBall: ", role)
    tp = target() if callable(target) else target
    return (tp - Player.pos(role)).dir()

def ballToOurGoal():
    return (Positions.ourGoal - Ball.pos()).dir()

def ballToTheirGoal():
    return (Positions.theirGoal - Ball.pos()).dir()

def posToTheirGoal(p):
    return (Positions.theirGoal - p).dir()

def posToOurGoal(p):
    return (Positions.ourGoal - p).dir()

def theirGoalToBall():
    return (Ball.pos() - Positions.theirGoal).dir()

def ourGoalToBall():
    return (Ball.pos() - Positions.ourGoal).dir()

def playerToBall(role):
    if role is None:
        print("Invalid Role in ourPlayerToBall: ", role)
    return (Ball.pos() - Player.pos(role)).dir()

def ballToPlayer(role):
    if role is None:
        print("Invalid Role in ourPlayerToBall: ", role)
    return (Player.pos(role) - Ball.pos()).dir()

def ourPlayerToPlayer(role1, role2=None):
    if role2 is None:
        def inner(role2):
            return (Player.pos(role1) - Player.pos(role2)).dir()
        return inner
    else:
        return (Player.pos(role2) - Player.pos(role1)).dir()

def shoot(role):
    return posToTheirGoal(Player.pos(role))

# def evaluateTouch(p):
#     lastCycle = [0] * (Params.maxPlayer + 1)
#     lastDir = [0] * (Params.maxPlayer + 1)
#     def inner(role):
#         if isinstance(role, str):
#             role = gRoleNum[role]
#         elif isinstance(role, int) and 1 <= role <= Params.maxPlayer:
#             pass
#         else:
#             print("Error role in Directions.shoot")
#         if vision.getCycle() - lastCycle[role] > 6 or Player.toBallDist(role) > 50:
#             if p is None:
#                 kickDirection.GenerateShootDir(role, Player.pos(role))
#                 tmpRawDir = kickDirection.getRawKickDir()
#             else:
#                 tp = p() if callable(p) else p
#                 tmpRawDir = Player.toPointDir(tp, role)
#             tmpTotalAngle = (tmpRawDir - Player.toBallDir(role)) * 180 / math.pi
#             tmpAbsValue = abs(tmpTotalAngle)
#             tmpEvaluateValue = 0.0008 * tmpAbsValue * tmpAbsValue + 0.1145 * tmpAbsValue
#             if tmpTotalAngle <= 0:
#                 lastDir[role] = tmpRawDir + tmpEvaluateValue * math.pi / 180
#             else:
#                 lastDir[role] = tmpRawDir - tmpEvaluateValue * math.pi / 180
#         lastCycle[role] = vision.getCycle()
#         return lastDir[role]
#     return inner

# def compensate(p):
#     lastCycle = [0] * (Params.maxPlayer + 1)
#     lastDir = [0] * (Params.maxPlayer + 1)
#     def inner(role):
#         ipos = p() if callable(p) else p
#         if vision.getCycle() - lastCycle[role] > 6 or Player.toBallDist(role) > 50:
#             lastDir[role] = CCalCompensateDir(Player.num(role), ipos.x(), ipos.y())
#         lastCycle[role] = vision.getCycle()
#         return lastDir[role]
#     return inner

# -- 无角度补偿的射门方向，p为传入的目标点
# def nocompensation(p):
#     dir_arr = [0] * (Params.maxPlayer + 1)
#     def inner(role):
#         ipos = p() if callable(p) else p
#         dir_arr[role] = (p - Player.pos(role)).dir()
#         return dir_arr[role]
#     return inner

# def chase(role):
#     kickDirection.GenerateShootDir(Player.num(role), Player.pos(role))
#     return kickDirection.getRawKickDir()

def backBall(p):
    def inner():
        targetP = CGeoPoint(p.x(), Ball.antiY() * p.y())
        return Utils.Normalize((targetP - Ball.pos()).dir())
    return inner

def fakeDown(p):
    def inner():
        factor = -1 if Ball.posY() > 10 else 1
        targetP = CGeoPoint(p.x(), factor * p.y())
        faceVec = (targetP - Ball.pos()).rotate(factor * math.pi * 120 / 180)
        return faceVec.dir()
    return inner

def defendBackClear():
    NearGoalDist = -Params.pitchLength / 2 + 10
    def inner():
        if -Params.goalWidth / 2 <= Ball.posY() <= Params.goalWidth / 2:
            if Ball.posX() > NearGoalDist:
                angle_left = -math.pi / 2
                angle_right = math.pi / 2
            else:
                angle_left = -math.pi / 3
                angle_right = math.pi / 3
        elif Ball.posY() < -Params.goalWidth / 2:
            angle_left = -2 * math.pi / 3
            angle_right = math.pi / 2
        elif Ball.posY() > Params.goalWidth / 2:
            angle_left = -math.pi / 2
            angle_right = 2 * math.pi / 3
        return (angle_left + angle_right) / 2
    return inner

def defendMiddleClear(role):
    NearGoalDist = -Params.pitchLength / 2 + 10
    def inner():
        if Ball.posX() < -140:
            if -Params.goalWidth / 2 < Ball.posY() < Params.goalWidth / 2:
                if Ball.posX() > NearGoalDist:
                    angle_left = -math.pi / 3
                    angle_right = math.pi / 3
                else:
                    angle_left = -math.pi / 4
                    angle_right = math.pi / 4
            elif Ball.posY() < -Params.goalWidth:
                angle_left = -2 * math.pi / 3
                angle_right = math.pi / 3
            elif Ball.posY() > Params.goalWidth:
                angle_left = -math.pi / 3
                angle_right = 2 * math.pi / 3
            return (angle_left + angle_right) / 2
        else:
            return Player.toBallDir(role)
    return inner

# def backSmartGotoDir():
#     oppnum = skillUtils.getTheirBestPlayer()
#     if Utils.InOurPenaltyArea(Ball.pos(), 5) and enemy.posX(oppnum) < 0:
#         return (enemy.pos(oppnum) - Positions.ourGoal).dir()
#     else:
#         return (Ball.pos() - Positions.ourGoal).dir()

# def sideBackDir():
#     return (Positions.sideBackPos() - Positions.ourGoal).dir()

# def getTandemDir(role):
#     def inner():
#         return world.getTandemDir(gRoleNum[role])
#     return inner

def reflectDir(d):
    return Ball.refSyntYDir(d)

# -- 利用图像使车消失的点. 传入第一辆车的位置和角度,返回第二辆(会消失的那辆)的角度,位置在pos.lua里,
# -- i表示用车的左边顶还是右边顶,-1表示左边,1表示右边
def disappearDir(pos_, dir_, i):
    if i == -1:
        if callable(dir_):
            def inner():
                return Utils.Normalize(dir_() - (1 if Ball.posY() > 0 else -1) * math.pi * 3 / 4)
            return inner
        else:
            return Utils.Normalize(dir_ - (1 if Ball.posY() > 0 else -1) * math.pi * 3 / 4)
    elif i == 1:
        if callable(dir_):
            def inner():
                return Utils.Normalize(dir_() - (-1 if Ball.posY() > 0 else 1) * math.pi * 3 / 4)
            return inner
        else:
            return Utils.Normalize(dir_ - (-1 if Ball.posY() > 0 else 1) * math.pi * 3 / 4)

def dirForDribbleTurnKick():
    rotAngle = 0.6
    if Ball.posY() > 0:
        angle = Ball.toTheirGoalDir() - rotAngle
    else:
        angle = Ball.toTheirGoalDir() + rotAngle
    return Utils.Normalize(angle)