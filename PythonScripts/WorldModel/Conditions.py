import math

import Global
from Vision import vision, Ball, Player, Enemy
from WorldModel import worldModel, Params


def ourBallPlace():
    return vision.getCurrentRefereeMsg() == "OurBallPlacement"

def theirBallPlace():
    return vision.getCurrentRefereeMsg() == "TheirBallPlacement"

def ballMoved():
    return (Ball.pos() - Ball.refPos()).mod() > 300 and not theirBallPlace() and not ourBallPlace()

def ballPlaceFinish():
    return worldModel.getBPFinished()

def ballPlaceUnfinish():
    return (Ball.pos() - Ball.placementPos()).mod() > 120

def isGameOn():
    # return vision.gameState().gameOn()
    return vision.isGameOn()

def isGameStop():
    return vision.getCurrentRefereeMsg() == "GameStop"

def isNormalStart():
    return vision.canEitherKickBall()

# def bestPlayerChanged():
#     return worldModel.IsBestPlayerChanged()

# def canShootOnBallPos(role):
#     return worldModel.canShootOnBallPos(vision.getCycle(), Global.getRoleNumber(role))

# def canPassOnBallPos(role, passPos, guisePos):
#     return worldModel.canPassOnBallPos(vision.getCycle(), passPos, guisePos, Global.getRoleNumber(role))

def validNum():
    return vision.getValidNum()

# def ourvalidNum():
#     num = 0
#     for i in range(Params.maxPlayer):
#         if Player.isValid(i):
#             num += 1
#     return num

def canDefenceExit():
    return worldModel.CanDefenceExit()

def timeRemain():
    return vision.timeRemain()

# 包装，但是接口名字不对吧？
# def ourGoal():
#     return vision.ourGoal()
# 合理怀疑一手，先标记在这里

def ourGoal():
    return vision.getOurGoal()

# 同上
# def theirGoal():
#     return vision.theirGoal()
# 同上

def theirGoal():
    return vision.getTheirGoal()

# def judgeFieldArea():
#     if gNormalPlay == "NormalPlayNew":
#         MiddleFrontLine = 100 * Params.lengthRatio
#         BackMiddleLine = -80 * Params.lengthRatio
#         bufferX = 30
#         if gCurrentFieldArea == "MiddleField":
#             if ball().posX() > MiddleFrontLine + bufferX:
#                 return "FrontField"
#             if ball().posX() < BackMiddleLine - bufferX:
#                 return "BackField"
#         if gCurrentFieldArea == "BackField":
#             if ball().posX() > BackMiddleLine + bufferX:
#                 return "MiddleField"
#         if gCurrentFieldArea == "FrontField":
#             if ball().posX() < MiddleFrontLine - bufferX:
#                 return "MiddleField"
#     elif gNormalPlay in ["NormalPlayDefend", "NormalPlayMark", "NormalPlayLongchip"]:
#         BackFrontLine = 0
#         bufferX = 30
#         if gCurrentFieldArea == "BackField":
#             if ball().posX() > BackFrontLine + bufferX:
#                 return "FrontField"
#         if gCurrentFieldArea == "FrontField":
#             if ball().posX() < BackFrontLine - bufferX:
#                 return "BackField"
#     elif gNormalPlay == "NormalPlayOneState":
#         BackFrontLine = -120 * Params.lengthRatio
#         bufferX = 30
#         if gCurrentFieldArea == "BackField":
#             if ball().posX() > BackFrontLine + bufferX:
#                 return "FrontField"
#         if gCurrentFieldArea == "FrontField":
#             if ball().posX() < BackFrontLine - bufferX:
#                 return "BackField"
#     return gCurrentFieldArea

def getBallStatus():
    nearDist = 99999
    nearNum = 0
    ournearDist = 99999
    ournearNum = 0
    for i in range(Params.maxPlayer):
        theDist = Enemy.pos(i).dist(Ball.pos())
        if Enemy.valid(i) and nearDist > theDist:
            nearDist = theDist
            nearNum = i
        ourtheDist = Player.ourPlayerPos(i).dist(Ball.pos())
        if Player.isValid(i) and ournearDist > ourtheDist:
            ournearDist = ourtheDist
            ournearNum = i
    if Player.ourPlayerPos(ournearNum).dist(Ball.pos()) < 200 and Enemy.pos(nearNum).dist(Ball.pos()) < 200 and Player.infraredCount(ournearNum) == 0:
        return "StandOff"
    elif Player.infraredCount(ournearNum) > 5 or (Enemy.pos(nearNum).dist(Ball.pos()) > 180 and Player.ourPlayerPos(ournearNum).dist(Ball.pos()) < 180 and abs(
            (Ball.pos() - Player.ourPlayerPos(ournearNum)).direction() - Player.direction(ournearNum)) < math.pi / 6):
        return "OurBall"
    elif Player.ourPlayerPos(ournearNum).dist(Ball.pos()) > 200 and Enemy.pos(nearNum).dist(Ball.pos()) < 150 and abs(
            (Ball.pos() - Enemy.pos(nearNum)).direction() - Enemy.dir(nearNum)) < math.pi / 6:
        return "TheirBall"
    else:
        return "None"

def canexitDef():
    if (Enemy.nearest1() - Ball.pos()).mod() > 500 and Ball.velMod() < 1000:
        return True
    else:
        return False

def needExitAttackDef(p1, p2, str_):
    if callable(p1):
        mp1 = p1()
    else:
        mp1 = p1
    if callable(p2):
        mp2 = p2()
    else:
        mp2 = p2
    mode = None
    if str_ == "horizal":
        mode = 2
    if str_ == "vertical":
        mode = 1
    return worldModel.NeedExitAttackDef(mp1, mp2, mode)

def dist4ball2MarkTouch(p1, p2):
    if callable(p1):
        mp1 = p1()
    else:
        mp1 = p1
    if callable(p2):
        mp2 = p2()
    else:
        mp2 = p2
    return worldModel.ball2MarkingTouch(mp1, mp2)

def canExitMiddleDef():
    return Ball.velMod() < 100

def canExitMRLFrontDef():
    return Ball.velMod() < 150 and vision.ballVelValid()

def canExitRoboDragonMarkingFront():
    return Ball.velMod() < 50

# def canBeImmortalShoot():
#     return ball().toPointDist(Enemy.bestPos()) < 50 and vision.ballVelValid()

def checkBallPassed(p1, p2):
    # 该函数的状态变量需要外部管理，建议用类或闭包实现
    # 这里只做结构转换，未实现完整状态保存
    return False  # 需要根据实际需求实现

def getValidMarkingTouchArea(p1, p2, p3, p4):
    return worldModel.getMarkingTouchArea(p1, p2, p3, p4)

def markingFrontValid(p1, p2):
    return worldModel.isMarkingFrontValid(p1, p2)

def kickOffEnemyNum():
    return worldModel.getEnemyKickOffNum()

def kickOffEnemyNumChanged():
    return worldModel.checkEnemyKickOffNumChanged()

def canPassAndShoot(role):
    return Global.getRoleNumber(role) != 0 and not worldModel.isPassLineBlocked(Global.getRoleNumber(role)) and not worldModel.isShootLineBlocked(Global.getRoleNumber(role))

def findChance(role1, role2=None, role3=None, role4=None, role5=None):
    for role in [role1, role2, role3, role4, role5]:
        if role is not None and isinstance(role, str):
            if Global.getRoleNumber(role) != 0 and not worldModel.isBeingMarked(Global.getRoleNumber(role)) and canPassAndShoot(role):
                return role
    return "None"

# randNumLast = 0
"""
是通过生成随机数的方式，实现Ref_KickOffV1 Ref_KickOffV2 等不同脚本的随机使用。
已经弃用。不支持字符串直接索引脚本。需要重新设计逻辑
"""
# def getOpponentScript(str_, script, MaxRandom):
#     global randNumLast
#     import random
#     if isinstance(script, list):
#         totalNum = len(script)
#         randNum = 1
#         for _ in range(2):
#             randNum = random.randint(1, totalNum)
#             if randNum != randNumLast:
#                 break
#         randNumLast = randNum
#         if isinstance(script[randNum-1], str):
#             return script[randNum-1]
#         else:
#             return str_ + str(script[randNum-1])
#     elif isinstance(script, str):
#         if script == "random":
#             randNum = random.randint(1, MaxRandom)
#             print("randNum", str_ + str(randNum))
#             return str_ + str(randNum)
#         else:
#             return script
#     else:
#         print("Error in getOpponentScript", str_)

# def canNorPass2Def(kickDir=None):
#     if kickDir is None:
#         return Ball.velMod() < gNorPass2NorDefBallVel and vision.ballVelValid()
#     else:
#         return (Ball.velMod() < gNorPass2NorDefBallVel or abs(Utils.Normalize(ball().velDir() - kickDir)) > math.pi / 2) and vision.ballVelValid()