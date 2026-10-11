import math
from numbers import Number
import CppPackage
from CppPackage import VisionModule, CGeoPoint, CGeoSegment
from Vision import Player, Enemy
from WorldModel import Params

# 这样写是错误的！第一次import的时候只执行一次。原cpp代码要求每一帧都重新调用ball()函数！
# ball:"CppPackage.BallVisionT" = CppPackage.VisionModule.Instance().ball()

def ball() -> "CppPackage.BallVisionT":
    return CppPackage.VisionModule.Instance().ball()

def pos():
    return ball().Pos()

def Pos():
    """
    与老lua脚本兼容
    :return:
    """
    return ball().Pos()

def posX():
    return ball().X()

def posY():
    return ball().Y()

def X():
    return ball().X()

def Y():
    return ball().Y()

def bestChipPredictPos():
    return ball().BestChipPredictPos()

def ChipFlyTime():
    return ball().ChipFlyTime()

def rawPos():
    return VisionModule.Instance().rawBall().Pos()

def vel():
    return ball().Vel()

def velX():
    return ball().VelX()

def velY():
    return ball().VelY()

def velDir():
    return ball().Vel().dir()

def velMod():
    return ball().Vel().mod()

def valid():
    return ball().Valid()

def placementPos():
    return VisionModule.Instance().getBallPlacementPosition()

def toPlayerDir(role):
    return (Player.Pos(role) - pos()).dir()

def toEnemyDir(role):
    return (Enemy.pos(role) - pos()).dir()

def toPlayerHeadDir(recver):
    def inner(passer):
        tmpPlayerHead = Player.Pos(recver) + CppPackage.Polar2Vector(Params.playerFrontToCenter,
                                                                     Player.direction(recver))
        return (tmpPlayerHead - Player.Pos(passer)).dir()
    return inner

def toPlayerHeadDist(role):
    tmpPlayerHead = Player.Pos(role) + CppPackage.Polar2Vector(10, Player.direction(role))
    return (pos() - tmpPlayerHead).mod()

def toPlayerDist(role):
    return (Player.Pos(role) - pos()).mod()

def toEnemyDist(role):
    return (Enemy.pos(role) - pos()).mod()

def toTheirGoalDist():
    return pos().dist(CGeoPoint(Params.pitchLength / 2.0, 0))

def toTheirGoalDir():
    return (CGeoPoint(Params.pitchLength / 2.0, 0) - pos()).dir()

def toOurGoalDist():
    return pos().dist(CGeoPoint(-Params.pitchLength / 2.0, 0))

def toOurGoalDir():
    return (CGeoPoint(-Params.pitchLength / 2.0, 0) - pos()).dir()

def toOurPenaltyDist():
    dist = toOurGoalDist() - Params.penaltyDepth
    return dist

def toPointDir(p):
    if callable(p):
        return (p() - pos()).direction()
    else:
        return (p - pos()).dir()


def toPointDist(p):
    if callable(p):
        p = p()
    return pos().dist(p)

def antiY():
    if posY() > 0:
        return -1
    else:
        return 1

def syntY():
    return -1 * antiY()

def antiYPos(p):
    if callable(p):
        return CGeoPoint(p().x(), antiY() * p().y())
    else:
        return CGeoPoint(p.x(), antiY() * p.y())

def syntYPos(p):
    return CGeoPoint(p.x(), syntY() * p.y())

def toFuncDir(f):
    return (f() - pos()).direction()

# def antiYDir(p):
#     if isinstance(p, type(ball().Pos())):
#         return (antiYPos(p)() - pos()).dir()
#     elif isinstance(p, (int, float)):
#         return antiY() * p
#     elif callable(p):
#         return (antiYPos(p())() - pos()).dir()

def syntYDir(p):
    if isinstance(p, type(ball().Pos())):
            return (syntYPos(p)() - pos()).dir()
    elif isinstance(p, (int, float)):
        return syntY() * p
    elif callable(p):
        return (syntYPos(p())() - pos()).dir()

# def goRush(deltaX=None, Y=None):
#     ix = deltaX if deltaX is not None else 100
#     iy = Y if Y is not None else 300
#     def inner():
#         return CGeoPoint(refPosX() + ix, iy * refAntiY())
#     return inner

# def goRush4kicker():
#     def inner():
#         return CGeoPoint(refPosX() - 59.5, 220 * refAntiY())
#     return inner

def cornerStay(toballdist, dir, step, num, p=None):
    def inner():
        if p is None:
            if antiY() == 1:
                return CGeoPoint(posX(), posY()) + CppPackage.Polar2Vector(25, (dir - math.pi / 2)) + CppPackage.Polar2Vector(toballdist + step * num, dir)
            else:
                return CGeoPoint(posX(), posY()) + CppPackage.Polar2Vector(25, -(dir - math.pi / 2)) + CppPackage.Polar2Vector(toballdist + step * num, -dir)
        else:
            if antiY() == 1:
                return p + CppPackage.Polar2Vector(toballdist, dir)
            else:
                return p + CppPackage.Polar2Vector(toballdist, -dir)
    return inner

def waitChipPos():
    def inner():
        return CGeoPoint(refPosX() + 100, 220 * refAntiY())
    return inner

def backDir(p, anti):
    def inner():
        idir = None
        if callable(p):
            idir = p()
        elif isinstance(p, (int, float)):
            idir = p
        elif isinstance(p, type(ball().Pos())):
            if not anti:
                idir = CppPackage.Normalize((p - pos()).dir())
            else:
                targetP = CGeoPoint(p.x(), antiY() * p.y())
                idir = CppPackage.Normalize((targetP - pos()).dir())
        elif isinstance(p, str):
            idir = CppPackage.Normalize((Player.Pos(p) - pos()).dir())
        if isinstance(idir, type(ball().Pos())):
            if not anti:
                idir = CppPackage.Normalize((idir - pos()).dir())
            else:
                temP = CGeoPoint(idir.x(), antiY() * idir.y())
                idir = CppPackage.Normalize((temP - pos()).dir())
        return idir
    return inner

# def backPos(p, d=None, s=None, anti=None):
#     def inner():
#         nonlocal d, s
#         idir = backDir(p, anti)()
#         if d is None:
#             d = 30
#         if s is None:
#             s = 0
#         shiftVec = CppPackage.Polar2Vector(s, idir).rotate(syntY() * math.pi / 2)
#         ipos = pos() + shiftVec + CppPackage.Polar2Vector(d, CppPackage.Normalize(idir + math.pi))
#         return ipos
#     return inner

# def jamPos(p, d=None, s=None):
#     def inner():
#         nonlocal d, s
#         if d is None:
#             d = 55
#         if s is None:
#             s = 0
#         targetP = CGeoPoint(p.x(), p.y() * antiY())
#         faceDir = (targetP - pos()).dir()
#         shiftVec = CppPackage.Polar2Vector(s, faceDir).rotate(antiY() * math.pi / 2)
#         return pos() + CppPackage.Polar2Vector(d, faceDir) + shiftVec
#     return inner

# def jaminner(dist=None):
#     def inner():
#         ballp = pos()
#         gate = CGeoPoint(Params.pitchLength / 2, 0)
#         balltoGate = gate - ballp
#         d = dist if dist is not None else 580
#         jamVec = balltoGate.rotate(antiY() * 0.39) / balltoGate.mod() * d
#         return ballp + jamVec
#     return inner
#
# def jamouter(dist=None):
#     def inner():
#         ballp = pos()
#         gate = CGeoPoint(Params.pitchLength / 2, 0)
#         balltoGate = gate - ballp
#         d = dist if dist is not None else 580
#         jamVec = balltoGate.rotate(antiY() * -0.39) / balltoGate.mod() * d
#         return ballp + jamVec
#     return inner

gRefMsg:"dict[str, Number]" = {
    "lastCycle": 0,  # 上一次定位球的Cycle
    "ballX": 0,      # 本次定位球开始时球的X位置
    "ballY": 0,      # 本次定位球开始时球的Y位置
    "antiY": 1,      # 本次定位球的antiY参数
    # "isOurBall": False
}

def updateRefMsg():
    gRefMsg["ballX"] = posX()
    gRefMsg["ballY"] = posY()
    gRefMsg["antiY"] = antiY()
    # gRefMsg["isOurBall"] = world.IsOurBallByAutoReferee()
    gRefMsg["lastCycle"] = VisionModule.Instance().getCycle()

def updateRef2PlacePos():
    dist = (placementPos() - pos()).mod()
    if dist > 15:
        gRefMsg["ballX"] = placementPos().x()
        gRefMsg["ballY"] = placementPos().y()
        gRefMsg["antiY"] = -1 if placementPos().y() > 0 else 1
    else:
        gRefMsg["ballX"] = posX()
        gRefMsg["ballY"] = posY()
        gRefMsg["antiY"] = antiY()

def refPos():
    return CGeoPoint(gRefMsg["ballX"], gRefMsg["ballY"])

def refPosX():
    return gRefMsg["ballX"]

def refPosY():
    return gRefMsg["ballY"]

def refAntiY():
    return gRefMsg["antiY"]

def refAntiYPos(p):
    if callable(p):
        return CGeoPoint(p().x(), gRefMsg["antiY"] * p().y())
    else:
        return CGeoPoint(p.x(), gRefMsg["antiY"] * p.y())

def refSyntYPos(p):
    return CGeoPoint(p.x(), -1 * gRefMsg["antiY"] * p.y())

def refAntiYDir(p):
    def inner():
        return gRefMsg["antiY"] * p
    return inner

def refSyntYDir(p):
    def inner():
        if callable(p):
            return -1 * gRefMsg["antiY"] * p()
        else:
            return -1 * gRefMsg["antiY"] * p
    return inner

def isMovingTo(role):
    if valid() and velMod() > 1 and abs(CppPackage.Normalize(velDir() - toPlayerDir(role))) < math.pi / 9:
        return True
    return False

def chipFixBuf(chipPower):
    fixBuf = (-0.0000015498 * chipPower * chipPower + 0.0025344180 * chipPower + 0.2463515283) * Params.frameRate
    return fixBuf

def getFixBuf(p):
    if callable(p):
        p = p()
    ballRefPos = CGeoPoint(refPosX(), refPosY())
    dist = ballRefPos.dist(p)
    chipPower = dist * 0.50
    return chipFixBuf(chipPower)

def ifOnLine(originpos, targetpos, maxdist):
    if callable(originpos):
        p1 = originpos()
    else:
        p1 = originpos
    if callable(targetpos):
        p2 = targetpos()
    else:
        p2 = targetpos
    if callable(maxdist):
        d = maxdist()
    else:
        d = maxdist
    seg = CGeoSegment(p1, p2)
    dist = seg.projection(pos()).dist(pos())
    isprjon = seg.IsPointOnLineOnSegment(seg.projection(pos()))
    if dist < maxdist and isprjon:
        return True
    return False

# def chippassvel(targetPosition:CGeoPoint):
#     ballp = pos()
#     CHIP_DIST_RATIO = 0.8
#     if callable(targetPosition):
#         ipos = targetPosition()
#     else:
#         ipos = targetPosition
#     distance = dist(ipos)
#     chipdist = distance * CHIP_DIST_RATIO
#     passvel = chipdist / 1.266
#     if passvel > 4000:
#         passvel = 4000
#     if passvel < 500:
#         passvel = 500
#     return passvel

def toOurGoalPostDistSum():
    dist1 = pos().dist(CGeoPoint(-Params.pitchLength / 2.0, -Params.goalWidth / 2.0))
    dist2 = pos().dist(CGeoPoint(-Params.pitchLength / 2.0, Params.goalWidth / 2.0))
    return dist1 + dist2

# ————————————————已弃用————————————————
# def toBestEnemyDist():
#     enemyNum = skillUtils.getTheirBestPlayer()
#     if CppPackage.PlayerNumValid(enemyNum):
#         return toEnemyDist(enemyNum)
#     else:
#         return 1000
#
# def enemyDistMinusPlayerDist(role):
#     return toBestEnemyDist() - toPlayerDist(role)
