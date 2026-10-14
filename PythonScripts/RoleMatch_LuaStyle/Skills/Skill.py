import typing
# from numbers import Number
from typing import Any

import CppPackage
import Utils
import WorldModel
from Geometry import *
from Strategy import messiDecision
from Vision import Player
from Vision import ball, Ball
from Vision import vision
from WorldModel import Flags, Params
from WorldModel import Positions
from WorldModel import taskMediator, Directions, KickMode, Precision, kickStatus, \
    ChipPower
from WorldModel.PowerCalculator import evalPower, P, POWER_MAX as _CALC_MAX
from .AlignedShot import TurnAndShootAligned

"""
步骤：copy之前的定义，然后从CppPackage.pyi中复制函数签名（除了返回值签名），把第一个参数executor去掉，剩下的参数保持不变。

似乎可以使用from functools import partial，用partial进行部分绑定实现同样的效果。
调用过程类似于"A": Task((partial(CppPackage.makeItGoalie, pos=Positions.ourGoal, flag=0), matchPos), fixedNumber=0)

**WARNING: Python 的函数默认参数 只在函数定义时计算一次！！！不是cpp一样每次调用时重新计算。所以默认参数一定要在函数体内部重新计算！**
"""


def Goalie2022(mode: str | None = None, flag: typing.SupportsInt = 0):

    if mode not in (None, "normal", "penalty"):
        raise ValueError('Goalie2022 mode must be None, "normal", or "penalty"')

    def skill_cpp(executor: int) -> Any:
        taskMediator.registerRole(executor, "goalie")
        return CppPackage.makeItGoalie2022(executor, mode == "penalty", flag)

    def matchPos(executor: int) -> CGeoPoint:
        return Positions.ourGoal

    return skill_cpp, matchPos


def Goalie(pos: CGeoPoint = None, flag: typing.SupportsInt = 0):
    if not pos:
        pos = messiDecision.goaliePassPos()

    def skill_cpp(executor: int) -> Any:
        taskMediator.registerRole(executor, "goalie")
        CppPackage.TaskMediator.Instance().registerRole(executor, "goalie")
        return CppPackage.makeItGoalie(executor, pos, flag)

    def matchPos(executor: int) -> CGeoPoint:
        """
        获取守门员的匹配位置。
        """
        return Positions.ourGoal

    return skill_cpp, matchPos


def SimpleGoTo(point: CppPackage.CGeoPoint, angle: float = 0, flag: int = 0):
    """
    Execute the SimpleGoto task.
    """

    def skill_cpp(executor: int) -> Any:
        return CppPackage.makeItSimpleGoTo(executor, point, angle, flag)

    def matchPos(executor: int) -> CppPackage.CGeoPoint:
        return point

    return skill_cpp, matchPos


def RushTo(pos: CGeoPoint, angle: typing.Union[typing.Callable, typing.SupportsFloat] = None, maxAcc: typing.Optional[typing.SupportsFloat]= None,
           flag: typing.SupportsInt = 0, *, needDribble: bool = False, vel: CVector = CVector(0, 0),
           registerRole: str = "", sender: typing.SupportsInt = 0):
    """
    原函数签名：
--~ p为要走的点,d默认为射门朝向(就是这边的angel) a 加速度 f 标志位
-- 这边的r是mrec判断是否吸球  gty 2016-6-15，我已经修改成RushTo中的needDribble

function goCmuRush(p, d, a, f, r, v, role)
    ...
    local mexe, mpos = GoCmuRush{pos = p, dir = idir, acc = a, flag = f,rec = r,vel = v,srole = role}
	return {mexe, mpos}
end

role是什么？

    :param pos:
    :param angle:到达目标点时的朝向（弧度）。默认为射门朝向。如果传入一个闭包，则会延迟到执行时计算，填入一个参数为executor。
    实例：RushTo(pos, angle=Player.toBallDir("B"))， 这时候toBallDir("B")返回的是一个闭包，待填入第一个参数！
    :param maxAcc: 最大加速度限制（0 表示无限制）
    :param flag:任务标志位，默认0。
    :param needDribble: 原来的rec参数，表示是否需要吸球
    :param vel: ???，默认(0,0)。
    :param registerRole: 用于后面registerRole的注册角色名称，一般无需指定！
    :param sender: 出球者号码/传球者编号，默认0。
    :return:
    """
    if not maxAcc:
        maxAcc = 0
    def skill_cpp(executor: int) -> Any:
        nonlocal angle
        if angle is None:
            angle = Directions.shoot(executor)
        elif callable(angle):
            angle = angle(executor)

        if needDribble:
            CppPackage.setDribbleCommand(executor, 3)
        CppPackage.TaskMediator.Instance().registerRole(executor, "fetchBall")
        return CppPackage.makeItRushTo(executor, pos, angle, flag, sender, maxAcc, needDribble, vel)

    def matchPos(executor: int) -> CGeoPoint:
        """
        获取RushTo的匹配位置。
        """
        return pos

    return skill_cpp, matchPos

def RushToV4(pos, mydir, flag = 0):

    def skill_cpp(executor: int) -> Any:
        if not mydir:
            idir = Player.toTheirGoalDir(executor)
        else:
            idir = mydir

        return CppPackage.makeItSmartGoToV4(executor, pos, idir, flag)

    def matchPos(executor: int) -> CGeoPoint:
        """
        获取RushTo的匹配位置。
        """
        return pos

    return skill_cpp, matchPos


def Stop():
    def skill_cpp(executor: int) -> Any:
        return CppPackage.makeItStop(executor)

    def matchPos(executor: int) -> CGeoPoint:
        return Player.Pos(executor)

    return skill_cpp, matchPos


def StaticGetBall(target: CGeoPoint, kickPower, chipPower):
    def skill_cpp(executor: int) -> Any:
        return CppPackage.makeItStaticGetBall(executor, target, kickPower, chipPower)

    def matchPos(executor: int) -> CGeoPoint:
        return Ball.pos() + Utils.Polar2Vector(90, (Ball.pos() - target).dir())

    return skill_cpp, matchPos


def JustKick(power, isChip: bool = False, needDribble: bool = True):
    def skill_cpp(executor: int) -> Any:
        if isChip:
            kickStatus.setChipKick(executor, power)
        else:
            kickStatus.setKick(executor, power)
        # return CppPackage.makeItStop(executor)
        return CppPackage.makeItRushTo(executor, ball().Pos(), Player.toBallDir(executor), needDribble=needDribble)

    def matchPos(executor: int) -> CGeoPoint:
        return Ball.pos()

    return skill_cpp, matchPos


def Shoot(target: CGeoPoint=None, direction: typing.SupportsFloat = None, *, isChip: bool=False, power: typing.SupportsFloat = None,
          flag=Flags.nothing, precision: typing.SupportsFloat = Precision.HIGH, needDribble: bool = False):
    if not target:
        target = Positions.theirGoal
    def skill_cpp(executor: int) -> Any:
        # 先原始处理一些参数，下发指令。对应原lua层的Play.lua中对后面几个参数的处理
        nonlocal direction, isChip, needDribble, power

        # handle direction
        if not direction:
            direction = Directions.shoot(executor)
        isDirOk = WorldModel.worldModel.KickDirArrived(vision.getCycle(), direction, precision, executor) or Player.isInfraredOn(executor)

        # handle dribble
        #needDribble = needDribble or (flag & Flags.dribble)
        needDribble = True
        if needDribble:
            CppPackage.setDribbleCommand(executor, 3)

        # handle kick/chip
        if isDirOk or (flag & Flags.force_kick):
            kickMode = KickMode.chip if isChip else KickMode.flat
            match kickMode:
                case KickMode.flat:
                    if not power:
                        power = evalPower(Ball.pos(), target, P.LOW)
                    kickStatus.setKick(executor, power)
                case KickMode.chip:
                    if not power:
                        power = evalPower(Ball.pos(), target, P.LOW, is_chip=True)
                    kickStatus.setChipKick(executor, power)
                case _:
                    raise ValueError(f"Unsupported kick mode: {kickMode}")
        gotoPoint = Ball.pos()
        if (Player.isInfraredOn(executor)):
            gotoPoint = Player.pos(executor)
        return CppPackage.makeItRushTo(executor, gotoPoint, direction, maxAcc=0, flag=flag)


    def matchPos(executor: int) -> CGeoPoint:
        return target

    return skill_cpp, matchPos

def GoAndTurnKick(target:CGeoPoint = Positions.theirGoal, registerRole="leader", *, power, flag=0, useInter: bool = False):
    """

    :param target: 射门的点
    :param registerRole: 用于后面的registerRole的注册角色名称，一般无需指定！
    :param power:
    :param flag:
    :return:
    """

    def skill_cpp(executor: int) -> Any:
        taskMediator.registerRole(executor, registerRole)
        return CppPackage.makeItGoAndTurnKick(executor, target, useInter, power, flag)

    def matchPos(executor: int) -> CGeoPoint:
        return CppPackage.WeBestGetBallPosition(executor)

    return skill_cpp, matchPos

def TurnAndShoot(target: CGeoPoint = Positions.theirGoal, registerRole="leader", *, power: typing.SupportsFloat, flag: typing.SupportsInt = 0):
    def skill_cpp(executor: int) -> Any:
        taskMediator.registerRole(executor, registerRole)
        return CppPackage.makeItTurnAndShoot(executor, target, power, flag)

    def matchPos(executor: int) -> CGeoPoint:
        return CppPackage.WeBestGetBallPosition(executor)

    return skill_cpp, matchPos

def SmartGoTo(target: CGeoPoint, dir: typing.SupportsFloat, flag: typing.SupportsInt=0, *, sender: typing.SupportsInt=0, maxAcc: typing.SupportsInt=0, Velocity: CVector = CVector(0,0)) -> Any:
    """
    原来的task.goSpeciPos使用的就是SmartGoTo! 底层是SmartGoToPosition
    :param target:
    :param dir:
    :param flag:
    :param sender: 出球者号码
    :param maxAcc:
    :param Velocity:
    :return:
    """
    def skill_cpp(executor: int) -> Any:
        return CppPackage.makeItSmartGoTo(executor, target, dir, flag, sender, maxAcc, Velocity)

    def matchPos(executor: int) -> CGeoPoint:
        return target

    return skill_cpp, matchPos


def FetchBall(target, power, mode):
    def skill_cpp(executor: int) -> Any:
        return CppPackage.makeItFetchBall(executor, target, power, mode)

    def matchPos(executor: int) -> CGeoPoint:
        return Ball.pos()

    return skill_cpp, matchPos


def GetBall(flag: typing.SupportsInt = 0):
    def skill_cpp(executor: int) -> Any:
        return CppPackage.makeItGetBall(executor, flag)

    def matchPos(executor: int) -> CGeoPoint:
        """
        获取守门员的匹配位置。
        """
        return Positions.ourGoal

    return skill_cpp, matchPos

def NormalShoot(power: typing.SupportsFloat, isChip: bool = False, flag: typing.SupportsInt = 0, type: int = 0):
    #type=0：kick type=1：breakshoot
    def skill_cpp(executor: int) -> Any:
        return CppPackage.makeItNormalShoot(executor, power, isChip, flag, type)

    def matchPos(executor: int) -> CGeoPoint:
        return Ball.pos()

    return skill_cpp, matchPos

def GetBallV5(direction: typing.SupportsFloat, ifIntercept: bool = False, flag :typing.SupportsInt=0):
    def skill_cpp(executor: int) -> Any:
        return CppPackage.makeItGetBallV5(executor, direction, ifIntercept, flag)

    def matchPos(executor: int) -> CGeoPoint:
        return ball().Pos()

    return skill_cpp, matchPos


def GetBallV4(pos):

    def skill_cpp(executor: int) -> Any:
        direction = Player.toPointDir(pos, executor)
        return CppPackage.makeItGetBallV4(executor, direction)

    def matchPos(executor: int) -> CGeoPoint:
        return Ball.pos()

    return skill_cpp, matchPos

def StaticGetBallV4(pos, anti = False, flag = 0, direction: typing.Union[typing.Callable, typing.SupportsFloat] = None, power : typing.SupportsFloat = 10000, isChip : bool = False):
    def skill_cpp(executor: int) -> Any:
        nonlocal direction
        if direction is None:
            direction = Ball.backDir(pos, anti)()
        elif callable(direction):
            direction = direction(executor)
        CppPackage.setDribbleCommand(executor, 3)
        return CppPackage.makeItStaticGetBallV4(executor, direction, power, isChip, flag)

    def matchPos(executor: int) -> CGeoPoint:
        #return Ball.pos()
        return pos
        # return Ball.pos()

    return skill_cpp, matchPos
