import math
import CppPackage
from CppPackage import VisionModule, CGeoPoint, CGeoSegment, PlayerVisionT
from Global import debugEngine
from Vision import Player, Ball
from WorldModel import Params
ball:"CppPackage.BallVisionT" = CppPackage.VisionModule.Instance().ball()

defenceInfo = CppPackage.DefenceInfo.Instance()
def instance(role) -> "PlayerVisionT":
    if isinstance(role, int):
        return VisionModule.Instance().theirPlayer(role)
    else:
        print("Invalid role in Enemy.instance!!!")
        return None

def pos(role):
    return instance(role).Pos()

def posX(role):
    return instance(role).X()

def posY(role):
    return instance(role).Y()

def dir(role):
    return instance(role).Dir()

def vel(role):
    return instance(role).Vel()

def velDir(role):
    return vel(role).dir()

def velMod(role):
    return vel(role).mod()

def rotVel(role):
    return instance(role).RotVel()

def valid(role):
    return instance(role).Valid()

def toBallDir(role):
    return (Ball.Pos() - pos(role)).dir()

def toBallDist(role):
    return pos(role).dist(Ball.Pos())

def attackNum():
    return defenceInfo.getAttackNum()

lastnum = 0
def myattackNum():
    global lastnum
    num = 0
    for i in range(Params.maxPlayer):
        if valid(i):
            if posX(i) < Params.pitchLength / 8:
                num += 1
    lastnum = num
    if num == 0:
        return 1
    else:
        return num

def myattackNum1():
    num = 0
    for i in range(Params.maxPlayer):
        if valid(i):
            if posX(i) < -Params.pitchLength / 8:
                num += 1
    return num

def situChanged():
    return defenceInfo.getTriggerState()

def mysituChanged():
    global lastnum
    num = 0
    for i in range(Params.maxPlayer):
        if valid(i):
            if posX(i) < -Params.pitchLength / 8:
                num += 1
    if lastnum != num:
        return True
    else:
        return False

def isGoalie(role):
    if pos(role).dist(CGeoPoint(Params.pitchLength / 2.0, 0)) < 850:
        return True
    return False

def isDefender(role):
    if pos(role).dist(CGeoPoint(Params.pitchLength / 2.0, 0)) < 120 and not isGoalie(role):
        return True
    return False

def isMarking(role):
    # 原Lua代码有误，这里假设只要不是后卫且有位置就算marking
    if pos(role) and not isDefender(role):
        return True
    return False

def isAttacker(role):
    if posX(role) < 0 and not isMarking(role):
        return True
    return False

def isBallFacer(role):
    if pos(role).dist(Ball.Pos()) < 600:
        return True
    return False

# def hasReceiver():
#     return CEnemyHasReceiver()

gEnemyMsg = {
    "goaliePos": CGeoPoint(Params.pitchLength / 2.0, 0)
}

# def updateCorrectGoaliePos():
#     theirGoalieNum = skillUtils.getTheirGoalie()
#     if valid(theirGoalieNum):
#         gEnemyMsg["goaliePos"] = pos(theirGoalieNum)
#     return gEnemyMsg["goaliePos"]

def getTheirGoaliePos():
    return gEnemyMsg["goaliePos"]

def nearest():
    nearDist = 99999
    nearNum = 0
    for i in range(Params.maxPlayer):
        theDist = pos(i).dist(Ball.Pos())
        if valid(i) and nearDist > theDist:
            nearDist = theDist
            nearNum = i
    return pos(nearNum), dir(nearNum)

iNum = 0
def nearest1():
    global iNum
    nearDist = 99999
    nearNum = 0
    pp = CGeoPoint(-6000, 900)
    if Ball.posY() > 0:
        pp = CGeoPoint(-6000, -900)
    for i in range(Params.maxPlayer):
        theDist = pos(i).dist(pp)
        if valid(i) and nearDist > theDist:
            nearDist = theDist
            nearNum = i
    iNum = nearNum
    return pos(nearNum)

def IsTooClose2Ball(role):
    if toBallDist(role) < 900:
        return True
    return False

def nearNum():
    nearDist = 99999
    result = 0
    for i in range(Params.maxPlayer):
        theDist = pos(i).dist(Ball.Pos())
        if valid(i) and nearDist > theDist:
            nearDist = theDist
            result = i
    return result

def markPos():
    return pos(iNum)

def findgoalie():
    for i in range(Params.maxPlayer):
        if valid(i):
            if isGoalie(i):
                return i
    return -1

def shootp():
    upgoal = CGeoPoint(Params.pitchLength / 2, Params.goalWidth / 2 - 100)
    down = CGeoPoint(Params.pitchLength / 2, -Params.goalWidth / 2 + 100)
    if posY(findgoalie()) > 0:
        pos_ = down
    else:
        pos_ = upgoal
    return pos_

def togoaldirjud(role):
    upgoal = CGeoPoint(Params.pitchLength / 2, Params.goalWidth / 2 - 100)
    down = CGeoPoint(Params.pitchLength / 2, -Params.goalWidth / 2 + 100)
    if posY(findgoalie()) > 0:
        dir_ = (down - Player.Pos(role)).dir()
    else:
        dir_ = (upgoal - Player.Pos(role)).dir()
    return dir_

def isnearball():
    for i in range(Params.maxPlayer):
        if valid(i) and (pos(i) - Ball.Pos()).mod() < 300:
            return True
    return False

def isblocked(pos1, pos2, threshold_distance=150):
    path_line = CGeoSegment(pos1, pos2)
    for i in range(Params.maxPlayer):
        if not valid(i):
            continue       
        player_pos = pos(i)
        projection_point = path_line.projection(player_pos)
        vertical_dist = projection_point.dist(player_pos)
        is_on_segment = path_line.IsPointOnLineOnSegment(projection_point)
        if vertical_dist < threshold_distance and is_on_segment:
            return True  
    return False

def judgetbest():
    up = 0
    down = 0
    for i in range(Params.maxPlayer):
        if valid(i):
            if posY(i) < 0:
                down += 1
            else:
                up += 1
    if down > up:
        return True
    else:
        return False

def judthierget():
    for i in range(Params.maxPlayer):
        if valid(i):
            if (pos(i) - Ball.Pos()).mod() < 105 and abs(dir(i) - (Ball.Pos() - pos(i)).dir()) < math.pi / 8:
                return True
    return False

# def penaltyjud(role, p):
#     p1 = Player.Pos(role)
#     if callable(p):
#         p2 = p()
#     elif isinstance(p, CGeoPoint):
#         p2 = p
#     else:
#         p2 = Player.Pos(p)
#     their = pos(findgoalie())
#     line = CGeoSegment(p1, p2)
#     dist = line.projection(their).dist(their)
#     isprjon = line.IsPointOnLineOnSegment(line.projection(their))
#     if dist < 300:
#         return False
#     else:
#         return True

lastnum = -1 #什么傻逼东西在外面定义了
def findenemy():
    global lastnum
    if Ball.posY() > 0:
        for i in range(Params.maxPlayer):
            if valid(i) and posY(i) < 0:
                lastnum = i
                return pos(i)
    else:
        for i in range(Params.maxPlayer):
            if valid(i) and posY(i) > 0:
                lastnum = i
                return pos(i)
    return None

realnum = 16
def enemypos1():
    global realnum, lastnum
    num = -1
    if not isBallFacer(realnum) and realnum != 16 and posX(realnum) < Params.pitchLength / 8:
        return pos(realnum)
    else:
        realnum = 16
    if realnum == -1:
        fe = findenemy()
        if fe is not None:
            realnum = lastnum
            return fe
        else:
            for i in range(Params.maxPlayer):
                if valid(i):
                    if i != findgoalie():
                        if posX(i) > 0:
                            if not isBallFacer(i):
                                realnum = i
                                return pos(i)
            if posX(realnum) < -6500 or isBallFacer(realnum):
                return CGeoPoint(-200, Params.pitchWidth / 4)
            else:
                debugEngine.gui_debug_msg(CGeoPoint(1000, 0), 1)
                return pos(realnum)
    else:
        return pos(realnum)

def Leftpos():
    for i in range(Params.maxPlayer):
        if valid(i):
            if posX(i) < Params.pitchLength / 8:
                if posY(i) <= 0 and pos(i).dist(Ball.Pos()) > 1000:
                    return pos(i)
    return CGeoPoint(150, -Params.pitchWidth / 4 - 500)

def Rightpos():
    for i in range(Params.maxPlayer):
        if valid(i):
            if posX(i) < Params.pitchLength / 8:
                if posY(i) > 0 and pos(i).dist(Ball.Pos()) > 1000:
                    return pos(i)
    return CGeoPoint(150, Params.pitchWidth / 4 + 500)

def getneddpos(str_, max_):
    def inner():
        this = 0
        topos = {}
        if str_ == "Zero":
            num = 0
        elif str_ == "First":
            num = 1
        elif str_ == "Second":
            num = 2
        elif str_ == "Third":
            num = 3
        elif str_ == "Fourth":
            num = 4
        elif str_ == "Fifth":
            num = 5
        elif str_ == "Sixth":
            num = 6
        elif str_ == "Seventh":
            num = 7
        elif str_ == "Eighth":
            num = 8
        elif str_ == "Nineth":
            num = 9
        elif str_ == "Tenth":
            num = 10
        else:
            print("Error Priority in Marking Skill!!!!!")
            num = 0
        for i in range(Params.maxPlayer):
            if valid(i):
                if not isBallFacer(i) and posX(i) < max_:
                    this += 1
                    topos[this] = pos(i)
        return topos.get(num)
    return inner

# --------------------没有用的函数--------------------
# def best():
#     return SkillUtils.getTheirBestPlayer()
# 
# def bestVelMod():
#     return velMod(best())
# 
# def bestPos():
#     return pos(best())
# 
# def bestDir():
#     return dir(best())
# 
# def bestToBallDist():
#     return pos(best()).dist(Ball.Pos())
# 
# def bestToBallDir():
#     return (Ball.Pos() - pos(best())).dir()