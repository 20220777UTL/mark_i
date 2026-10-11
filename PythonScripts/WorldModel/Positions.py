import math

import Global
import Utils
from Geometry import *
from Vision import Ball
from WorldModel import Directions
from WorldModel import Params

ourGoal = CGeoPoint(-Params.pitchLength / 2.0, 0)
theirGoal = CGeoPoint(Params.pitchLength / 2.0, 0)

def specified(p):
    def inner():
        return p
    return inner

def LEADER_STOP_POS():
    dir1 = (theirGoal - Ball.Pos()).dir()
    dir2 = (Ball.Pos() - ourGoal).dir()
    x1 = Params.pitchLength / 2
    x2 = Params.pitchLength / 3
    x = Ball.X()
    if x > x1:
        idir = dir1
    elif x < x2:
        idir = dir2
    else:
        idir = dir1 + (dir2 - dir1) * (x - x1) / (x2 - x1)
    return Ball.Pos() + Utils.Polar2Vector(-650, idir)

def rollpolingPos():
    side = -1 if Global.isYellow else 1
    return CGeoPoint(-100, (Params.pitchWidth / 2 - 200) * side * -1)

def getTimeOutPos(index):
    side = -1 if Global.isRight else 1
    return CGeoPoint(side * 300 + 300 * index * side, Params.pitchWidth / 2 * side * -1)

def refStopAroundBall():
    BLOCK_DIST = Params.freeKickAvoidBallDist + 4 * Params.playerRadius
    AWAY_DIST = 25 + Params.playerRadius
    BLOCK_ANGLE = math.asin(AWAY_DIST / BLOCK_DIST) * 2
    # factor = Ball.antiY
    SIDE_POS = Ball.Pos() + Utils.Polar2Vector(BLOCK_DIST, Directions.ballToOurGoal() + BLOCK_ANGLE)
    INTER_POS = Ball.Pos() + Utils.Polar2Vector(BLOCK_DIST, Directions.ballToOurGoal() - BLOCK_ANGLE)
    MIDDLE_POS = Ball.Pos() + Utils.Polar2Vector(BLOCK_DIST, Directions.ballToOurGoal())
    SIDE2_POS = Ball.Pos() + Utils.Polar2Vector(BLOCK_DIST, Directions.ballToOurGoal() + 2 * BLOCK_ANGLE)
    INTER2_POS = Ball.Pos() + Utils.Polar2Vector(BLOCK_DIST, Directions.ballToOurGoal() - 2 * BLOCK_ANGLE)
    return SIDE_POS, MIDDLE_POS, INTER_POS, SIDE2_POS, INTER2_POS

def backBall(p):
    def inner():
        targetP = CGeoPoint(p.x(), Ball.antiY() * p.y())
        return Ball.Pos() + Utils.Polar2Vector(180, Utils.Normalize((Ball.Pos() - targetP).dir()))
    return inner

def fakeDown(p):
    def inner():
        factor = -1 if Ball.posY() > 100 else 1
        targetP = CGeoPoint(p.x(), factor * p.y())
        standVec = (targetP - Ball.Pos()).rotate(factor * math.pi * 100 / 180)
        return Ball.Pos() + Utils.Polar2Vector(300, standVec.dir())
    return inner

# def oneKickDefPos(p1, p2, p3, p4, p5, p6):
#     def inner():
#         mp1 = p1() if callable(p1) else p1
#         mp2 = p2() if callable(p2) else p2
#         mp3 = p3() if callable(p3) else p3
#         mp4 = p4() if callable(p4) else p4
#         mp5 = p5() if callable(p5) else p5
#         mp6 = p6() if callable(p6) else p6
#         return indirectDefender.getTwoDefPos(vision, mp1, mp2, mp3, mp4, mp5, mp6).getOnePos()
#     return inner

# def anotherKickDefPos(p1, p2, p3, p4, p5, p6):
#     def inner():
#         mp1 = p1() if callable(p1) else p1
#         mp2 = p2() if callable(p2) else p2
#         mp3 = p3() if callable(p3) else p3
#         mp4 = p4() if callable(p4) else p4
#         mp5 = p5() if callable(p5) else p5
#         mp6 = p6() if callable(p6) else p6
#         return indirectDefender.getTwoDefPos(vision, mp1, mp2, mp3, mp4, mp5, mp6).getAnotherPos()
#     return inner

def testTwoKickOffPos1():
    BLOCK_DIST = 30
    def inner():
        return Ball.Pos() + Utils.Polar2Vector(BLOCK_DIST, Directions.theirGoalToBall())
    return inner

def testTwoKickOffPos2():
    BLOCK_DIST = 30
    AWAY_DIST = 7.5 + Params.playerRadius
    BLOCK_ANGLE = math.asin(AWAY_DIST / BLOCK_DIST) * 2
    factor = Ball.antiY
    def inner():
        return Ball.Pos() + Utils.Polar2Vector(BLOCK_DIST, Directions.theirGoalToBall() + factor() * BLOCK_ANGLE)
    return inner

def reflectPos(x, y):
    def inner():
        if Ball.posY() < 0:
            return Ball.refAntiYPos(CGeoPoint(Ball.X() + x, -(abs(Ball.posY()) + y)))
        else:
            return Ball.refSyntYPos(CGeoPoint(Ball.X() + x, abs(Ball.posY()) + y))
    return inner

def passForTouch(p):
    length = 95
    return p + Utils.Polar2Vector(length, Directions.posToTheirGoal(p))

def chipPassForTouch(p):
    length = 100
    return p + Utils.Polar2Vector(length, Directions.posToTheirGoal(p))

def passForHead(p):
    return p + Utils.Polar2Vector(100, Directions.posToTheirGoal(p))

# def disappearPos(Pos, dir_, i):
#     if i == -1:
#         if callable(Pos):
#             if callable(dir_):
#                 def inner():
#                     return Pos() + Utils.Polar2Vector(15.0, Utils.Normalize(dir_() + (1 if Ball.posY() > 0 else -1) * math.pi / 4))
#                 return inner
#             else:
#                 def inner():
#                     return Pos() + Utils.Polar2Vector(15.0, Utils.Normalize(dir_ + (1 if Ball.posY() > 0 else -1) * math.pi / 4))
#                 return inner
#         else:
#             if callable(dir_):
#                 return Pos + Utils.Polar2Vector(15.0, Utils.Normalize(dir_() + (1 if Ball.posY() > 0 else -1) * math.pi / 4))
#             else:
#                 return Pos + Utils.Polar2Vector(15.0, Utils.Normalize(dir_ + (1 if Ball.posY() > 0 else -1) * math.pi / 4))
#     elif i == 1:
#         if callable(Pos):
#             if callable(dir_):
#                 def inner():
#                     return Pos() + Utils.Polar2Vector(15.0, Utils.Normalize(dir_() + (-1 if Ball.posY() > 0 else 1) * math.pi / 4))
#                 return inner
#             else:
#                 def inner():
#                     return Pos() + Utils.Polar2Vector(15.0, Utils.Normalize(dir_ + (-1 if Ball.posY() > 0 else 1) * math.pi / 4))
#                 return inner
#         else:
#             if callable(dir_):
#                 return Pos + Utils.Polar2Vector(15.0, Utils.Normalize(dir_() + (-1 if Ball.posY() > 0 else 1) * math.pi / 4))
#             else:
#                 return Pos + Utils.Polar2Vector(15.0, Utils.Normalize(dir_ + (-1 if Ball.posY() > 0 else 1) * math.pi / 4))

def getBackPos():
    def bPos():
        if Ball.X() > 0:
            bx = -Params.pitchLength / 6 * (1 - (Ball.X() / (Params.pitchLength / 2)))
            by = Ball.posY() / (Params.pitchWidth / 2) * (2 * (Params.pitchWidth / 2) / 3)
        elif Ball.posY() > 0:
            bx = -Params.pitchLength / 12
            by = -Params.pitchWidth / 4
        else:
            bx = -Params.pitchLength / 12
            by = Params.pitchWidth / 4
        return CGeoPoint(bx, by)
    return bPos