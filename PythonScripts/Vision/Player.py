import math
import typing
from typing import overload, Union
from Geometry import *
import CppPackage
import Global
import Utils
import Vision
from CppPackage import CGeoPoint
from Vision import Ball, Enemy
from WorldModel import Params, worldModel

def instance(role)->"CppPackage.PlayerVisionT":
    if isinstance(role, str):
        realIns = Vision.ourPlayer(Global.getRoleNumber(role))
    elif isinstance(role, int):
        realIns = Vision.ourPlayer(role)
    else:
        print("Invalid role in player.instance!!!2222222")
        return None
    return realIns

def ourPlayer(num):
    return CppPackage.VisionModule.Instance().ourPlayer(num)


def theirPlayer(num):
    return CppPackage.VisionModule.Instance().theirPlayer(num)


def isValid(num: int) -> bool:
    """
    判断我方的车号是否有效
    :Params num: 车号
    :return: 是否有效
    """
    return Vision.ourPlayer(num).Valid()

def getAllValidNumbers() -> "list[int]":
    """寻找所有有效车号"""
    result = []
    for i in range(Params.maxPlayer - 1):
        if Vision.Player.ourPlayer(i).Valid():
            result.append(i)
    return result


def ourPlayerPos(num: int) -> CppPackage.CGeoPoint:
    """
    获取球员位置
    :Params num: 车号
    :return: 球员位置
    """
    return Vision.ourPlayer(num).Pos()

# def toBallDir(num: int) -> numbers:
#     """
#     获取我方球员指向球的方向
#     :Params num: 车号
#     :return: 球员指向球的方向
#     """
#     return (Vision.Ball.Pos() - Vision.ourPlayer(num).Pos()).dir()


@overload
def Pos(num: int) -> CppPackage.CGeoPoint: ...
@overload
def Pos(roleName: str) -> CppPackage.CGeoPoint: ...

def Pos(role: Union[int,str]) -> CppPackage.CGeoPoint:
    """
    获取球员位置
    :Params role: 球员角色名称或车号
    :return: 球员位置
    """
    if isinstance(role, int):
        return Vision.ourPlayer(role).Pos()
    elif isinstance(role, str):
        roleName = role
        if roleName not in Global.roleNumberStructTable.keys():
            print(f"Invalid role name: {roleName}")
            return Vision.Ball.Pos()
            # raise ValueError(f"Invalid role name: {roleName}")
        if Global.getRoleNumber(roleName) < 0:
            print(f"Role {roleName} is not assigned a valid number.")
            return Vision.Ball.Pos()
            # raise ValueError(f"Role {roleName} is not assigned a valid number.")
        return Vision.ourPlayer(Global.getRoleNumber(roleName)).Pos()
    return Vision.Ball.Pos()



def getActualRoleNumber(role: "str | int")-> int:
    if isinstance(role, str):
        return Global.getRoleNumber(role)
    elif isinstance(role, int):
        return role
    else:
        print("Invalid role in player.instance!!!")
        return -1

def pos(role)-> "CGeoPoint":
    return instance(role).Pos()

def posX(role):
    return instance(role).X()

def posY(role):
    return instance(role).Y()

def direction(role: Union[int, str]) -> float:
    return instance(role).Dir()

def vel(role):
    return instance(role).Vel()

def velDir(role):
    return vel(role).dir()

def velMod(role):
    return vel(role).mod()

def rotVel(role):
    return instance(role).RotVel()

def rawPos(role):
    return instance(role).RawPos()

def rawVel(role):
    return instance(role).RawVel()

def rawVelMod(role):
    return rawVel(role).mod()

def valid(role):
    return instance(role).Valid()

def valid1(role):
    return lambda: valid(role)

# def myvalid(role):
#     return number(role) != -1

def toBallDist(role):
    return pos(role).dist(Ball.pos())

def toBallDir(role)->typing.SupportsFloat:
    return (Ball.pos() - pos(role)).dir()

def backBallDir(role):
    return (pos(role) - Ball.pos()).dir()

def toTheirGoalDist(role):
    return pos(role).dist(CGeoPoint(Params.pitchLength / 2.0, 0))

def toOurGoalDist(role):
    return pos(role).dist(CGeoPoint(-Params.pitchLength / 2.0, 0))

def toTheirGoalDir(role):
    return (CGeoPoint(Params.pitchLength / 2.0, 0) - pos(role)).dir()

def toOurGoalDir(role):
    return (CGeoPoint(-Params.pitchLength / 2.0, 0) - pos(role)).dir()

def toPlayerDir(role1, role2=None):
    """
    如果role2没有指定，则返回一个lambda，实际上就是到自身的dir！这样在大多数情况下是不正确的！尽量自行指定！或者使用语义更加明确的toSelfDir
    """
    if role2 is None:
        return lambda role2: (pos(role1) - pos(role2)).dir()
    else:
        return (pos(role2) - pos(role1)).dir()

def toPlayerDirFromSelf(role):
    """
    计算role相对于自身的方向，是(pos(role) - pos(selfRole)).dir()
    :param role:
    :return:
    """
    return lambda selfRole: (pos(role) - pos(selfRole)).dir()

def toPlayerHeadDir(role1, role2=None):
    if role2 is None:
        def inner(role2):
            tmpPlayerHead = pos(role1) + Utils.Polar2Vector(76, direction(role1))
            return (tmpPlayerHead - pos(role2)).dir()
        return inner
    else:
        tmpPlayerHead = pos(role2) + Utils.Polar2Vector(76, direction(role2))
        return (tmpPlayerHead - pos(role1)).dir()

def toPlayerDist(role1, role2=None):
    if role2 is None:
        return lambda role2: (pos(role1) - pos(role2)).mod()
    else:
        return (pos(role2) - pos(role1)).mod()

def toTargetTime(p, role=None):
    if role is None:
        def inner(role):
            target = p() if callable(p) else p
            return worldModel.timeToTarget(getActualRoleNumber(role), target) * Params.frameRate
        return inner
    else:
        target = p() if callable(p) else p
        return worldModel.timeToTarget(getActualRoleNumber(role), target) * Params.frameRate

def toTargetDist(role):
    """
    计算role到其matchPos的距离
    """
    p = Global.getRolePos(role)
    return pos(role).dist(p)

def blocked():
    pl = Params.pitchLength
    num_ = -1
    dist = 99999
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            d = (CGeoPoint(pl/2, 0) - pos(i)).mod()
            if d < dist:
                dist = d
                num_ = i
    if Enemy.toBallDist(num_) < 120 and abs(Enemy.toBallDir(num_) - Enemy.dir(num_)) < math.pi/5:
        return True
    return False

def toTargetDir(targetPoint, role=None):
    if role is None:
        return lambda role: (targetPoint - pos(role)).dir()
    else:
        def inner():
            if callable(targetPoint):
                return (targetPoint() - pos(role)).dir()
            else:
                return (targetPoint - pos(role)).dir()
        return inner

def toTheirPenaltyDist(role):
    tmpToGoalDist = (CGeoPoint(Params.pitchLength/2.0, 0) - pos(role)).mod()
    return tmpToGoalDist - 80

def toPointDist(role, p):
    pos_ = p() if callable(p) else p
    return pos(role).dist(pos_)

def backShootPos(p):
    tmpShootDir = (p - CGeoPoint(Params.pitchLength / 2.0, 0)).dir()
    return p + Utils.Polar2Vector(9, tmpShootDir)

def toPointDir(p, role=None):
    if role is None:
        if callable(p):
            return lambda role1: (p() - pos(role1)).dir()
        else:
            return lambda role1: (p - pos(role1)).dir()
    else:
        return (p - pos(role)).dir()

def kickBall(role):
    """判断小车是否下发了setKick或者setChipKick指令
    而不是实际中视觉判断的是不是把球踢出了

    Args:
        role (_type_): _description_

    Returns:
        _type_: _description_
    """
    return worldModel.IsBallKicked(getActualRoleNumber(role))

def isBallKicked(role):
    return worldModel.IsBallKicked(getActualRoleNumber(role))

def kickBallVision(role):
    return worldModel.IsBallKickedVision(getActualRoleNumber(role))

def isInfraredOn(role):
    return worldModel.IsInfraredOn(getActualRoleNumber(role))

def infraredOn(role):
    return worldModel.IsInfraredOn(getActualRoleNumber(role))

def infraredCount(role):
    return worldModel.InfraredOnCount(getActualRoleNumber(role))

def infraredOffCount(role):
    return worldModel.InfraredOffCount(getActualRoleNumber(role))

def toShootOrRobot(role1):
    def inner(role2):
        shootDir = (CGeoPoint(Params.pitchLength / 2.0, 0) - pos(role2)).dir()
        if toBallDist(role1) > 50:
            faceDir = (Ball.pos() - pos(role2)).dir()
        else:
            faceDir = (pos(role1) - pos(role2)).dir()
        if abs(Utils.Normalize(shootDir - faceDir)) > math.pi * 30 / 180:
            return faceDir
        else:
            return shootDir
    return inner

# def canBreak(role):
#     for i in range(Params.maxPlayer):
#         if Enemy.valid(i):
#             p = gRolePos[role]() if callable(gRolePos[role]) else gRolePos[role]
#             breakSeg = CGeoSegment(pos(role), p)
#             projP = breakSeg.projection(Enemy.pos(i))
#             if breakSeg.IsPointOnLineOnSegment(projP):
#                 if Enemy.pos(i).dist(projP) < 400:
#                     return False
#     return True

def isMarked(role):
    closestDist = 99999
    defennum = None
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            dir1 = toPointDir(CGeoPoint(Params.pitchLength / 2.0, 0), role)
            dirDiff = Utils.Normalize(dir1 - toPointDir(Enemy.pos(i), role))
            if abs(dirDiff) < math.pi/2:
                tmpDist = toPointDist(role, Enemy.pos(i))
                if tmpDist < closestDist:
                    closestDist = tmpDist
                    defennum = i
    return closestDist < 400

def DisMarked(role):
    closestDist = 99999
    defennum = None
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            dir1 = toPointDir(CGeoPoint(Params.pitchLength / 2, 0), role)
            dirDiff = Utils.Normalize(dir1 - toPointDir(Enemy.pos(i), role))
            if abs(dirDiff) < math.pi/2:
                tmpDist = toPointDist(role, Enemy.pos(i))
                if tmpDist < closestDist:
                    closestDist = tmpDist
                    defennum = i
    return closestDist < 800

def testPassPos(role):
    def inner():
        factor = -1 if posX(role) > 0 else 1
        return CGeoPoint(150 * factor, 0)
    return inner

def canFlatPassTo(role1, role2):
    p1 = pos(role1)
    p2 = pos(role2) + Utils.Polar2Vector(Params.playerFrontToCenter, direction(role2))
    seg = CGeoSegment(p1, p2)
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            dist = seg.projection(Enemy.pos(i)).dist(Enemy.pos(i))
            isprjon = seg.IsPointOnLineOnSegment(seg.projection(Enemy.pos(i)))
            if dist < 200 and isprjon:
                return False
    return True

def ifBlockBallLine(role, originpos, targetpos):
    p1 = originpos() if callable(originpos) else originpos
    p2 = targetpos() if callable(targetpos) else targetpos
    seg = CGeoSegment(p1, p2)
    dist = seg.projection(pos(role)).dist(pos(role))
    isprjon = seg.IsPointOnLineOnSegment(seg.projection(pos(role)))
    if dist < 20 and isprjon:
        return True
    return False

def canFlatPassToPos(role, targetpos):
    p1 = pos(role)
    id_ = getActualRoleNumber(role) if isinstance(role, str) else role
    p2 = targetpos() if callable(targetpos) else targetpos
    seg = CGeoSegment(p1, p2)
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            dist = seg.projection(Enemy.pos(i)).dist(Enemy.pos(i))
            isprjon = seg.IsPointOnLineOnSegment(seg.projection(Enemy.pos(i)))
            if dist < 140 and isprjon:
                return False
    for j in range(Params.maxPlayer):
        if valid(j) and j != id_ and pos(j).dist(p2) > 200:
            dist = seg.projection(pos(j)).dist(pos(j))
            isprjon = seg.IsPointOnLineOnSegment(seg.projection(pos(j)))
            if dist < 120 and isprjon:
                return False
    return True

def GetBestPower(role1, role2):
    p1 = pos(role1)
    if callable(role2):
        p2 = role2()
    elif isinstance(role2, str) or isinstance(role2, int):
        p2 = pos(role2)
    else:
        p2 = role2
    defence = None
    seg = CGeoSegment(p1, p2)
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            dist = seg.projection(Enemy.pos(i)).dist(Enemy.pos(i))
            isprjon = seg.IsPointOnLineOnSegment(seg.projection(Enemy.pos(i)))
            if dist < 120 and isprjon:
                defence = i
    if (Enemy.pos(defence) - Ball.pos()).mod() < 800:
        return 250
    else:
        return 300

def canFlatReceive(passer, receiver):
    p1 = pos(passer)
    if callable(receiver):
        p2 = receiver()
    elif isinstance(receiver, (str, int)):
        p2 = pos(receiver) + Utils.Polar2Vector(Params.playerFrontToCenter, direction(receiver))
    else:
        p2 = receiver
    p1 = pos(passer) + Utils.Polar2Vector(1000, (p2 - p1).dir())
    seg = CGeoSegment(p1, p2)
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            dist = seg.projection(Enemy.pos(i)).dist(Enemy.pos(i))
            isprjon = seg.IsPointOnLineOnSegment(seg.projection(Enemy.pos(i)))
            if dist < 200 and isprjon:
                return False
    return True

def canDirectShoot(role1, d=70, proj_d=12):
    p1 = pos(role1)
    p2 = pos(role1) + Utils.Polar2Vector(d, direction(role1))
    seg = CGeoSegment(p1, p2)
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            dist = seg.projection(Enemy.pos(i)).dist(Enemy.pos(i))
            isprjon = seg.IsPointOnLineOnSegment(seg.projection(Enemy.pos(i)))
            if dist < proj_d and isprjon:
                return False
    return True

def canChipPassTo(role1, role2):
    p1 = pos(role1)
    p2 = pos(role2)
    for i in range(Params.maxPlayer):
        if Enemy.valid(i):
            dist1 = Enemy.pos(i).dist(p1)
            dist2 = Enemy.pos(i).dist(p2)
            if dist1 < 300 or dist2 < 300:
                return False
    return True

def isBallPassed(role1, role2):
    p1 = pos(role1)
    p2 = pos(role2)
    ptrDir = (p2 - p1).dir()
    return abs(Utils.Normalize(Ball.velDir() - ptrDir)) < math.pi / 18 and Ball.velMod() > 800

def isBallPassedNormalPlay(role1, role2):
    passerDir = direction(role1)
    p1 = pos(role1)
    p2 = pos(role2)
    ptrDir = (p2 - p1).dir()
    return (abs(Utils.Normalize(Ball.velDir() - ptrDir)) < math.pi / 18 and
            abs(Utils.Normalize(Ball.velDir() - passerDir)) < math.pi / 10 and
            Ball.velMod() > 1600)

def passIntercept(role):
    receiver = pos(role)
    ptrDir = (receiver - Ball.pos()).dir()
    if Ball.toPointDist(receiver) > 50:
        if abs(Utils.Normalize(Ball.velDir() - ptrDir)) > math.pi / 10 or Ball.velMod() < 120:
            return True
        else:
            return False
    else:
        return False

# def antiYDir(p): # 反人类的东西
#     def inner(role):
#         if isinstance(p, type('userdata')):
#             return (Ball.antiYPos(p)() - pos(role)).dir()
#     return inner

def faceball2target(role, t, diff=None):
    if diff is None:
        d = 0.2
    elif callable(diff):
        d = diff()
    else:
        d = diff
    target = t() if callable(t) else t
    temp = Ball.toPointDir(target)
    if abs(temp() - direction(role)) <= d or abs(temp() - direction(role)) >= 6.28 - d:
        return True
    else:
        return False

def isInForbiddenZone4ballplace(role):
    thereShouldDist = 60
    p1 = CGeoPoint(Ball.placementPos().x(), Ball.placementPos().y())
    p2 = Ball.pos()
    seg = CGeoSegment(p1, p2)
    dist = seg.projection(pos(role)).dist(pos(role))
    isprjon = seg.IsPointOnLineOnSegment(seg.projection(pos(role)))
    if (toBallDist(role) <= thereShouldDist or
            toPointDist(role, p1) <= thereShouldDist or
            (dist <= thereShouldDist and isprjon)):
        return True
    else:
        return False

def stayPos4ballplace(role):
    thereShouldDist = 70
    myposX = None
    myposY = None
    def TargetPos():
        return CGeoPoint(Ball.placementPos().x(), Ball.placementPos().y())
    def compute():
        nonlocal myposX, myposY
        if isInForbiddenZone4ballplace(role):
            seg = CGeoSegment(Ball.pos(), TargetPos())
            projectPoint = CGeoPoint(seg.projection(pos(role)).x(), seg.projection(pos(role)).y())
            myposX = (projectPoint + Utils.Polar2Vector(-thereShouldDist, toPointDir(projectPoint, role))).x()
            myposY = (projectPoint + Utils.Polar2Vector(-thereShouldDist, toPointDir(projectPoint, role))).y()
            if ((abs(myposX) > (Params.pitchLength / 2 - Params.penaltyDepth) and abs(myposY) < (
                    Params.penaltyWidth / 2)) or
                    abs(myposX) > Params.pitchLength / 2 or abs(myposY) > Params.pitchWidth / 2):
                myposX = (projectPoint + Utils.Polar2Vector(thereShouldDist, toPointDir(projectPoint, role))).x()
                myposY = (projectPoint + Utils.Polar2Vector(thereShouldDist, toPointDir(projectPoint, role))).y()
        else:
            myposX = posX(role)
            myposY = posY(role)
        return CGeoPoint(myposX, myposY)
    return compute

def realNumExist(n):
    return valid(n)

def backballpos(role):
    def inner():
        stand = Ball.pos() + Utils.Polar2Vector(Params.playerFrontToCenter, Utils.Normalize(direction(role) + math.pi))
        return stand
    return inner

def canshoot(role):
    ipos = pos(role)
    idir = direction(role)
    upgoal = CGeoPoint(Params.pitchLength/2, Params.goalWidth/2)
    downgoal = CGeoPoint(Params.pitchLength/2, -Params.goalWidth/2)
    if (downgoal - ipos).dir() < idir < (upgoal - ipos).dir():
        return True
    else:
        return False

def shootGen(dist, dir=None):  # 与球有关站在球附近的位置 dist为与球距离 dir为在球的什么方向
    theirgoal = CGeoPoint(Params.pitchLength / 2, 0)
    pos = None
    if not dir:
        dir = (Ball.pos() - theirgoal).dir()
    pos = Ball.pos() + Utils.Polar2Vector(dist, dir)
    return pos


# -----------------------没有用的函数---------------------------
# def InfoControlled(role):
#     roleNum = num(role)
#     return skillUtils.getOurBestPlayer() == roleNum