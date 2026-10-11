"""
Medusa C++ Python Bindings
        Geometry Module in Medusa
        -----------------------

        .. currentmodule:: Geometry

        .. autosummary::
           (class) GeoPoint
    
        Utils Module in Medusa
        -----------------------

        .. currentmodule:: Utils

        .. autosummary::
           (class) DebugEngine
    
        ParamManager in Medusa
        -----------------------

        .. currentmodule:: ParamManager

        .. autosummary::
           (class) ParamManager
		   (class) ParamManagerZSS
    
		BufferCounter in Medusa
		-----------------------

		.. currentmodule:: BufferCounter

		.. autosummary::
			:toctree: _autosummary

			isTimeOut
	
        Strategy Module in Medusa
        -----------------------

        .. currentmodule:: Utils

        .. autosummary::
           (class) DebugEngine
    
        Skill Module in Medusa
        -----------------------

        .. currentmodule:: Skill

        .. autosummary::
    
"""
from __future__ import annotations
import collections.abc
import typing
__all__: list[str] = ['AngleBetween', 'BallStatus', 'BallVisionT', 'BeckhamDecision', 'Bool', 'BoxedBool', 'BoxedDouble', 'BoxedInt', 'BoxedString', 'CBetween', 'CGeoCircle', 'CGeoEllipse', 'CGeoLine', 'CGeoLineCircleIntersection', 'CGeoLineEllipseIntersection', 'CGeoLineLineIntersection', 'CGeoLineRectangleIntersection', 'CGeoPoint', 'CGeoRectangle', 'CGeoSegment', 'CGeoSegmentCircleIntersection', 'CGeoShape', 'CVector', 'CVector3', 'CenterOfTwoPoint', 'DebugEngine', 'DefenceInfo', 'DefenceSequence', 'Deg2Rad', 'Double', 'FieldBottom', 'FieldLeft', 'FieldRight', 'FieldTop', 'GetInterPos', 'GetOutSidePenaltyPos', 'GetOutTheirSidePenaltyPos', 'GetTheirInterPos', 'InBetween', 'InOurPenaltyArea', 'InTheirPenaltyArea', 'InTheirPenaltyAreaWithVel', 'Int', 'IsInField', 'IsInFieldV2', 'KickStatus', 'LeftTop', 'MakeInField', 'MakeOutOfCircle', 'MakeOutOfCircleAndInField', 'MakeOutOfCircleAndOutOfPenalty', 'MakeOutOfLongCircle', 'MakeOutOfOurPenaltyArea', 'MakeOutOfRectangle', 'MakeOutOfTheirPenaltyArea', 'MessiDecision', 'Normalize', 'ObjectPoseT', 'ParamManager', 'ParamManagerZSS', 'ParamType', 'PlayerCapabilityT', 'PlayerNumValid', 'PlayerPoseT', 'PlayerTypeT', 'PlayerVisionT', 'Polar2Vector', 'Rad2Deg', 'RightBottom', 'Sign', 'SquareRootFloat', 'String', 'SystemRunner', 'TaskMediator', 'VectorDot', 'VisionModule', 'VisionObjectT', 'WeBestGetBallPosition', 'WorldModel', 'dirDiff', 'flatpower', 'getBackPos_CGuardPos', 'getPosModulePos', 'getWMarkingPos', 'isTimeOut', 'makeItCalibrationSpeed', 'makeItFetchBall', 'makeItGetBall', 'makeItGetBallV4', 'makeItGetBallV5', 'makeItGoAndTurnKick', 'makeItGoalie', 'makeItGoalie2022', 'makeItNormalShoot', 'makeItRushTo', 'makeItSimpleGoTo', 'makeItSmartGoTo', 'makeItSmartGoToV4', 'makeItStaticGetBall', 'makeItStaticGetBallV4', 'makeItStop', 'makeItTurnAndShoot', 'pointToLineDist', 'setDribbleCommand']
class BallStatus:
    """
    / 球状态封装类
    """
    @staticmethod
    def Instance() -> BallStatus:
        ...
    @typing.overload
    def IsBallKickedOut(self) -> bool:
        """
        球被踢出,便返回true(可能是挑射,也可能是平射)
        """
    @typing.overload
    def IsBallKickedOut(self, num: typing.SupportsInt) -> bool:
        """
        球被某个角色踢出,便返回true(可能是挑射,也可能是平射)
        """
    @typing.overload
    def IsChipKickedOut(self) -> bool:
        """
        球踢出,且是挑球指令踢出,才返回true
        """
    @typing.overload
    def IsChipKickedOut(self, num: typing.SupportsInt) -> bool:
        """
        球被某个角色踢出,且是挑球指令踢出,才返回true;
        """
    def ballChipLine(self) -> CGeoLine:
        ...
    def ballMovingVel(self) -> CVector:
        """
        获取球运动速度
        """
    def ballToucherChanged(self) -> bool:
        ...
    def getBallPossession(self, isOurPlayer: bool, id: typing.SupportsInt) -> float:
        ...
    def getBallToucher(self) -> int:
        ...
    def getKickerNum(self) -> int:
        """
        得到踢球队员的号码
        """
    def getLastBallToucher(self) -> int:
        ...
class BallVisionT(ObjectPoseT, VisionObjectT):
    def __init__(self) -> None:
        ...
class BeckhamDecision:
    """
    """
    @staticmethod
    def Instance() -> BeckhamDecision:
        ...
    def KickNumChanged(self) -> bool:
        ...
    def chipPassVel(self) -> float:
        ...
    def firstrecvNum(self) -> int:
        ...
    def flatPassVel(self) -> float:
        ...
    def get_kickBall(self) -> bool:
        ...
    def get_leaderPos(self) -> CGeoPoint:
        ...
    def get_passPos(self) -> CGeoPoint:
        ...
    def get_waitPos(self, index: typing.SupportsInt) -> CGeoPoint:
        ...
    def judgeExitState(self) -> bool:
        ...
    def kickNum(self) -> int:
        ...
    def leaderKicked(self) -> bool:
        ...
    def nextKicker(self) -> int:
        ...
    def reset(self) -> None:
        ...
    def rotradio(self) -> float:
        ...
    def secondrecvNum(self) -> int:
        ...
    def update(self, pVision: VisionModule) -> None:
        ...
class BoxedBool:
    """
    """
    value: bool
    def __init__(self, v: bool = False) -> None:
        ...
    def __repr__(self) -> str:
        ...
class BoxedDouble:
    """
    """
    def __init__(self, v: typing.SupportsFloat = 0.0) -> None:
        ...
    def __repr__(self) -> str:
        ...
    @property
    def value(self) -> float:
        ...
    @value.setter
    def value(self, arg0: typing.SupportsFloat) -> None:
        ...
class BoxedInt:
    """
    """
    def __init__(self, v: typing.SupportsInt = 0) -> None:
        ...
    def __repr__(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
    @value.setter
    def value(self, arg0: typing.SupportsInt) -> None:
        ...
class BoxedString:
    """
    """
    value: str
    def __init__(self, v: str = '') -> None:
        ...
    def __repr__(self) -> str:
        ...
class CGeoCircle(CGeoShape):
    """
    *********************************************************************** /
    
    /*                        CGeoCircle                                    */
    /***********************************************************************
    """
    def Center(self) -> CGeoPoint:
        ...
    def HasPoint(self, p: CGeoPoint) -> bool:
        ...
    def Radius(self) -> float:
        ...
    def Radius2(self) -> float:
        ...
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, c: CGeoPoint, r: typing.SupportsFloat) -> None:
        ...
class CGeoEllipse(CGeoShape):
    """
    ***********************************************************************/
    /*                        CGeoEllipse,此椭圆的轴与坐标轴垂直  ,方程为(x-c.x())^2/m^2+(y-c.y())^2/n^2 =1                                 */
    /***********************************************************************
    """
    def Center(self) -> CGeoPoint:
        ...
    def HasPoint(self, p: CGeoPoint) -> bool:
        ...
    def Xaxis(self) -> float:
        ...
    def Yaxis(self) -> float:
        ...
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, c: CGeoPoint, m: typing.SupportsFloat, n: typing.SupportsFloat) -> None:
        ...
class CGeoLine:
    """
    ***********************************************************************/
    /*                        CGeoLine                                      */
    /***********************************************************************"
    """
    __hash__: typing.ClassVar[None] = None
    def Intersection(self, line: CGeoLine) -> CGeoPoint:
        ...
    def __eq__(self, rhs: CGeoLine) -> bool:
        ...
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, p1: CGeoPoint, p2: CGeoPoint) -> None:
        ...
    @typing.overload
    def __init__(self, p: CGeoPoint, angle: typing.SupportsFloat) -> None:
        ...
    def __repr__(self) -> str:
        ...
    def __str__(self) -> str:
        ...
    def a(self) -> float:
        ...
    def b(self) -> float:
        ...
    def c(self) -> float:
        ...
    def calABC(self) -> None:
        ...
    def point1(self) -> CGeoPoint:
        ...
    def point2(self) -> CGeoPoint:
        ...
    def projection(self, p: CGeoPoint) -> CGeoPoint:
        ...
class CGeoLineCircleIntersection:
    """
    ***********************************************************************/
    /*                      CGeoLineCircleIntersection                      */
    /***********************************************************************
    """
    def __init__(self, line: CGeoLine, circle: CGeoCircle) -> None:
        ...
    def intersectant(self) -> bool:
        ...
    def point1(self) -> CGeoPoint:
        ...
    def point2(self) -> CGeoPoint:
        ...
class CGeoLineEllipseIntersection:
    """
    ***********************************************************************/
    /*                      CGeoLineCircleIntersection                      */
    /***********************************************************************
    """
    def __init__(self, line: CGeoLine, circle: CGeoEllipse) -> None:
        ...
    def intersectant(self) -> bool:
        ...
    def point1(self) -> CGeoPoint:
        ...
    def point2(self) -> CGeoPoint:
        ...
class CGeoLineLineIntersection:
    """
    """
    def IntersectPoint(self) -> CGeoPoint:
        ...
    def Intersectant(self) -> bool:
        ...
    def __init__(self, line_1: CGeoLine, line_2: CGeoLine) -> None:
        ...
class CGeoLineRectangleIntersection:
    """
    ***********************************************************************/
    /*                        CGeoLineRectangleIntersection                 */
    /***********************************************************************
    """
    def __init__(self, line: CGeoLine, rect: CGeoRectangle) -> None:
        ...
    def intersectant(self) -> bool:
        ...
    def point1(self) -> CGeoPoint:
        ...
    def point2(self) -> CGeoPoint:
        ...
class CGeoPoint:
    """
    *********************************************************************** /
    
    /*                       CGeoPoint                                      */
    /***********************************************************************
    """
    __hash__: typing.ClassVar[None] = None
    def __add__(self, v: CVector) -> CGeoPoint:
        ...
    def __eq__(self, rhs: CGeoPoint) -> bool:
        ...
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def __init__(self, p: CGeoPoint) -> None:
        ...
    def __mul__(self, a: typing.SupportsFloat) -> CGeoPoint:
        ...
    def __repr__(self) -> str:
        ...
    def __str__(self) -> str:
        ...
    def __sub__(self, p: CGeoPoint) -> CVector:
        ...
    def dist(self, p: CGeoPoint) -> float:
        ...
    def dist2(self, p: CGeoPoint) -> float:
        ...
    def fill(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> bool:
        ...
    def midPoint(self, p: CGeoPoint) -> CGeoPoint:
        ...
    def setX(self, x: typing.SupportsFloat) -> None:
        ...
    def setY(self, y: typing.SupportsFloat) -> None:
        ...
    def x(self) -> float:
        ...
    def y(self) -> float:
        ...
class CGeoRectangle(CGeoShape):
    """
    ***********************************************************************/
    /*                        CGeoRectangle                                 */
    /***********************************************************************
    """
    def HasPoint(self, p: CGeoPoint) -> bool:
        ...
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, leftTop: CGeoPoint, rightDown: CGeoPoint) -> None:
        ...
    @typing.overload
    def __init__(self, x1: typing.SupportsFloat, y1: typing.SupportsFloat, x2: typing.SupportsFloat, y2: typing.SupportsFloat) -> None:
        ...
    def calPoint(self, x1: typing.SupportsFloat, y1: typing.SupportsFloat, x2: typing.SupportsFloat, y2: typing.SupportsFloat) -> None:
        ...
    def dist2Point(self, p: CGeoPoint) -> float:
        ...
class CGeoSegment(CGeoLine):
    """
    ***********************************************************************/
    /*                       CGeoSegment / 线段                             */
    /***********************************************************************
    """
    def IsPointOnLineOnSegment(self, p: CGeoPoint) -> bool:
        ...
    def IsSegmentsIntersect(self, p: CGeoSegment) -> bool:
        ...
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, p1: CGeoPoint, p2: CGeoPoint) -> None:
        ...
    def __repr__(self) -> str:
        ...
    def __str__(self) -> str:
        ...
    def center(self) -> CGeoPoint:
        ...
    def dist2Point(self, p: CGeoPoint) -> float:
        ...
    def dist2Segment(self, s: CGeoSegment) -> float:
        ...
    def end(self) -> CGeoPoint:
        ...
    def segmentsIntersectPoint(self, p: CGeoSegment) -> CGeoPoint:
        ...
    def start(self) -> CGeoPoint:
        ...
class CGeoSegmentCircleIntersection:
    """
    ********************************************************************/
    /*                     CGeoSegmentCircleIntersection                 */
    /*******************************************************************
    """
    def __init__(self, line: CGeoSegment, circle: CGeoCircle) -> None:
        ...
    def intersectant(self) -> bool:
        ...
    def point1(self) -> CGeoPoint:
        ...
    def point2(self) -> CGeoPoint:
        ...
    def size(self) -> int:
        ...
class CGeoShape:
    """
    ***********************************************************************/
    /*                        CGeoShape                                     */
    /***********************************************************************
    """
class CVector:
    """
    """
    def __add__(self, v: CVector) -> CVector:
        ...
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def __init__(self, v: CVector) -> None:
        ...
    @typing.overload
    def __mul__(self, a: typing.SupportsFloat) -> CVector:
        ...
    @typing.overload
    def __mul__(self, b: CVector) -> float:
        ...
    def __neg__(self) -> CVector:
        ...
    def __repr__(self) -> str:
        ...
    def __str__(self) -> str:
        ...
    def __sub__(self, v: CVector) -> CVector:
        ...
    def __truediv__(self, a: typing.SupportsFloat) -> CVector:
        ...
    def dir(self) -> float:
        ...
    def mod(self) -> float:
        ...
    def mod2(self) -> float:
        ...
    def rotate(self, angle: typing.SupportsFloat) -> CVector:
        ...
    def setVector(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> bool:
        ...
    def theta(self, v: CVector) -> float:
        ...
    def unit(self) -> CVector:
        ...
    def value(self, angle: typing.SupportsFloat) -> float:
        ...
    def x(self) -> float:
        ...
    def y(self) -> float:
        ...
class CVector3:
    """
    """
    @typing.overload
    def __init__(self) -> None:
        ...
    @typing.overload
    def __init__(self, x: typing.SupportsFloat, y: typing.SupportsFloat, z: typing.SupportsFloat) -> None:
        ...
    def __repr__(self) -> str:
        ...
    def __str__(self) -> str:
        ...
    def add(self, a: CVector3) -> None:
        ...
    def addNew(self, a: CVector3) -> CVector3:
        ...
    def addz(self, a: typing.SupportsFloat) -> CVector3:
        ...
    @typing.overload
    def formXYZ(self, x: typing.SupportsFloat = 0, y: typing.SupportsFloat = 0, z: typing.SupportsFloat = 0) -> None:
        ...
    @typing.overload
    def formXYZ(self, pos2: CGeoPoint, z: typing.SupportsFloat = 0) -> None:
        ...
    def mod(self) -> float:
        ...
    def multiply(self, a: typing.SupportsFloat) -> None:
        ...
    def multiplyNew(self, a: typing.SupportsFloat) -> CVector3:
        ...
    def x(self) -> float:
        ...
    def y(self) -> float:
        ...
    def z(self) -> float:
        ...
class DebugEngine:
    @staticmethod
    def Instance() -> DebugEngine:
        """
        Get the singleton instance of CGDebugEngine
        """
    def gui_debug_arc(self, p: CGeoPoint, r: typing.SupportsFloat, start_angle: typing.SupportsFloat, span_angle: typing.SupportsFloat, debug_color: typing.SupportsInt = 1, RGB_value: typing.SupportsInt = 0) -> None:
        ...
    def gui_debug_curve(self, num: typing.SupportsFloat, maxLimit: typing.SupportsFloat, minLimit: typing.SupportsFloat, debug_color: typing.SupportsInt = 1, RGB_value: typing.SupportsInt = 0) -> None:
        ...
    def gui_debug_line(self, p1: CGeoPoint, p2: CGeoPoint, debug_color: typing.SupportsInt = 1, RGB_value: typing.SupportsInt = 0) -> None:
        ...
    def gui_debug_msg(self, p: CGeoPoint, msgstr: str, debug_color: typing.SupportsInt = 1, RGB_value: typing.SupportsInt = 0, size: typing.SupportsFloat = 90, weight: typing.SupportsInt = 50) -> None:
        ...
    def gui_debug_points(self, points: collections.abc.Sequence[CGeoPoint], debug_color: typing.SupportsInt = 1, RGB_value: typing.SupportsInt = 0) -> None:
        ...
    def gui_debug_robot(self, p: CGeoPoint, robot_dir: typing.SupportsFloat, debug_color: typing.SupportsInt = 1, RGB_value: typing.SupportsInt = 0) -> None:
        ...
    def gui_debug_triangle(self, p1: CGeoPoint, p2: CGeoPoint, p3: CGeoPoint, debug_color: typing.SupportsInt = 1, RGB_value: typing.SupportsInt = 0) -> None:
        ...
    def gui_debug_x(self, p: CGeoPoint, debug_color: typing.SupportsInt = 1, RGB_value: typing.SupportsInt = 0) -> None:
        ...
    def send(self, teamIsBlue: bool) -> None:
        ...
class DefenceInfo:
    """
    """
    @staticmethod
    def Instance() -> DefenceInfo:
        ...
    def clearAll(self) -> None:
        ...
    def clearNoChangeFlag(self) -> None:
        ...
    def clearNoMarkingField(self, upLeft: CGeoPoint, downRight: CGeoPoint) -> None:
        ...
    def getAttackNum(self) -> int:
        ...
    def getAttackOppNumByPri(self, i: typing.SupportsInt) -> int:
        ...
    def getOurMarkDefender(self, enemyNum: typing.SupportsInt) -> int:
        ...
    def getSteadyAttackOppNumByPri(self, i: typing.SupportsInt) -> int:
        ...
    def getTriggerState(self) -> bool:
        ...
    def initialization(self) -> None:
        ...
    def queryMarked(self, i: typing.SupportsInt) -> bool:
        ...
    def resetMarkingInfo(self) -> None:
        ...
    def setNoChangeFlag(self) -> None:
        ...
    def setNoMarkingField(self, upLeft: CGeoPoint, downRight: CGeoPoint) -> None:
        ...
    def setNoMarkingNum(self, enemyNum: typing.SupportsInt) -> None:
        """
        开球区域剔除挡位车
        """
class DefenceSequence:
    """
    """
    @staticmethod
    def Instance() -> DefenceSequence:
        ...
    def attackerAmount(self) -> int:
        ...
    def dangerAmount(self) -> int:
        ...
    def enemyOrderChanged(self) -> bool:
        ...
    def enemyOrderChangedNew(self) -> bool:
        ...
    def getAttackNum(self, order: typing.SupportsInt) -> int:
        ...
    def getDangerNum(self, order: typing.SupportsInt) -> int:
        ...
    def getFreeDefNum(self, order: typing.SupportsInt) -> int:
        ...
    def getMarkingNum(self, order: typing.SupportsInt) -> int:
        ...
    def getSupportPos(self, index: typing.SupportsInt) -> CGeoPoint:
        ...
    def markingAmount(self) -> int:
        ...
    def supportAmount(self) -> int:
        ...
    def update(self) -> None:
        """
        ————————end 下面是原暴露给lua层的接口
        """
class KickStatus:
    """
    """
    @staticmethod
    def Instance() -> KickStatus:
        ...
    def clearAll(self) -> None:
        ...
    def getChipKickDist(self, num: typing.SupportsInt) -> float:
        ...
    def getKickPower(self, num: typing.SupportsInt) -> float:
        ...
    def getKiker(self) -> int:
        ...
    def getPassDist(self, num: typing.SupportsInt) -> float:
        ...
    def isForceClosed(self) -> bool:
        ...
    def needKick(self, num: typing.SupportsInt) -> bool:
        ...
    def resetKick2ForceClose(self, forceClose: bool = False, forceCloseCycle: typing.SupportsInt = 0) -> None:
        ...
    def setAllKick(self, num: typing.SupportsInt, kick: typing.SupportsFloat, chip: typing.SupportsFloat, pass_: typing.SupportsFloat) -> None:
        ...
    def setBothKick(self, num: typing.SupportsInt, kick: typing.SupportsFloat, chip: typing.SupportsFloat) -> None:
        ...
    def setChipKick(self, num: typing.SupportsInt, power: typing.SupportsFloat) -> None:
        ...
    def setKick(self, num: typing.SupportsInt, power: typing.SupportsFloat) -> None:
        ...
    def updateForceClose(self, currentCycle: typing.SupportsInt) -> None:
        ...
class MessiDecision:
    """
    """
    class MapName:
        """
        
        
        Members:
        
          enemy2ballLinePrjDist : 
        
          enemy2PassLinePrjDist : 
        
          enemy2Me : 
        
          enemy2Ball : 
        """
        __members__: typing.ClassVar[dict[str, MessiDecision.MapName]]  # value = {'enemy2ballLinePrjDist': <MapName.enemy2ballLinePrjDist: 0>, 'enemy2PassLinePrjDist': <MapName.enemy2PassLinePrjDist: 1>, 'enemy2Me': <MapName.enemy2Me: 2>, 'enemy2Ball': <MapName.enemy2Ball: 3>}
        enemy2Ball: typing.ClassVar[MessiDecision.MapName]  # value = <MapName.enemy2Ball: 3>
        enemy2Me: typing.ClassVar[MessiDecision.MapName]  # value = <MapName.enemy2Me: 2>
        enemy2PassLinePrjDist: typing.ClassVar[MessiDecision.MapName]  # value = <MapName.enemy2PassLinePrjDist: 1>
        enemy2ballLinePrjDist: typing.ClassVar[MessiDecision.MapName]  # value = <MapName.enemy2ballLinePrjDist: 0>
        def __and__(self, other: typing.Any) -> typing.Any:
            ...
        def __eq__(self, other: typing.Any) -> bool:
            ...
        def __ge__(self, other: typing.Any) -> bool:
            ...
        def __getstate__(self) -> int:
            ...
        def __gt__(self, other: typing.Any) -> bool:
            ...
        def __hash__(self) -> int:
            ...
        def __index__(self) -> int:
            ...
        def __init__(self, value: typing.SupportsInt) -> None:
            ...
        def __int__(self) -> int:
            ...
        def __invert__(self) -> typing.Any:
            ...
        def __le__(self, other: typing.Any) -> bool:
            ...
        def __lt__(self, other: typing.Any) -> bool:
            ...
        def __ne__(self, other: typing.Any) -> bool:
            ...
        def __or__(self, other: typing.Any) -> typing.Any:
            ...
        def __rand__(self, other: typing.Any) -> typing.Any:
            ...
        def __repr__(self) -> str:
            ...
        def __ror__(self, other: typing.Any) -> typing.Any:
            ...
        def __rxor__(self, other: typing.Any) -> typing.Any:
            ...
        def __setstate__(self, state: typing.SupportsInt) -> None:
            ...
        def __str__(self) -> str:
            ...
        def __xor__(self, other: typing.Any) -> typing.Any:
            ...
        @property
        def name(self) -> str:
            ...
        @property
        def value(self) -> int:
            ...
    @staticmethod
    def Instance() -> MessiDecision:
        ...
    def UseDirectCmd(self) -> int:
        ...
    def firstChipDir(self) -> float:
        ...
    def firstChipPos(self) -> CGeoPoint:
        ...
    def flatPassPos(self) -> CGeoPoint:
        ...
    def freeKickPosCPU(self) -> CGeoPoint:
        ...
    def freeKickPosGPU(self) -> CGeoPoint:
        ...
    def freePassVel(self) -> float:
        ...
    def generateAttackDecision(self, pVision: VisionModule) -> None:
        ...
    def generateEnemyInformation(self, pVision: VisionModule) -> None:
        ...
    def getBallPos(self) -> CGeoPoint:
        ...
    def getBestFreePos(self) -> CGeoPoint:
        ...
    def getMarkingLeaderPos(self) -> CGeoPoint:
        ...
    def globalDebug(self, pVision: VisionModule) -> None:
        ...
    def goaliePassPos(self) -> CGeoPoint:
        ...
    def isDanger(self) -> bool:
        ...
    def isFlat(self) -> bool:
        ...
    def isFlytime(self) -> bool:
        ...
    def isFreeFlat(self) -> bool:
        ...
    def judgePassModule(self, playerNumer: typing.SupportsInt, passPos: CGeoPoint) -> bool:
        ...
    def leaderNum(self) -> int:
        ...
    def leaderPos(self) -> CGeoPoint:
        ...
    def needChip(self) -> bool:
        ...
    def needKick(self) -> bool:
        ...
    def nextState(self) -> str:
        ...
    def noUpdate(self) -> bool:
        ...
    def otherPos(self, index: typing.SupportsInt) -> CGeoPoint:
        ...
    def passPos(self) -> CGeoPoint:
        ...
    def passVel(self) -> float:
        ...
    def receiverNum(self) -> int:
        ...
    def receiverPos(self) -> CGeoPoint:
        ...
    def setUseFreeRec(self, useFreeRec: bool) -> None:
        ...
    def worstNum(self) -> int:
        ...
class ObjectPoseT:
    def Acc(self) -> CVector:
        ...
    def AccX(self) -> float:
        ...
    def AccY(self) -> float:
        ...
    def Pos(self) -> CGeoPoint:
        ...
    def RawDir(self) -> float:
        ...
    def RawPos(self) -> CGeoPoint:
        ...
    def RawVel(self) -> CVector:
        ...
    @typing.overload
    def SetAcc(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def SetAcc(self, acc: CVector) -> None:
        ...
    @typing.overload
    def SetPos(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def SetPos(self, pos: CGeoPoint) -> None:
        ...
    def SetRawDir(self, rawdir: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def SetRawPos(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def SetRawPos(self, pos: CGeoPoint) -> None:
        ...
    @typing.overload
    def SetRawVel(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def SetRawVel(self, vel: CVector) -> None:
        ...
    def SetTargetVel(self, target_vel: CVector) -> None:
        ...
    def SetValid(self, v: bool) -> None:
        ...
    @typing.overload
    def SetVel(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def SetVel(self, vel: CVector) -> None:
        ...
    def TargetVel(self) -> CVector:
        ...
    def Valid(self) -> bool:
        ...
    def Vel(self) -> CVector:
        ...
    def VelX(self) -> float:
        ...
    def VelY(self) -> float:
        ...
    def X(self) -> float:
        ...
    def Y(self) -> float:
        ...
    def __init__(self) -> None:
        ...
class ParamManager:
    """
    """
    def clear(self) -> None:
        ...
    def getParam(self, key: str, type: ParamType, defaultValue: typing.Any = None) -> typing.Any:
        """
        getParam(key, type, defaultValue=None)
        
        获取参数值，并根据 type 返回对应类型的结果。
        
        参数:
            key (str): 参数键名
            type (ParamType): 返回值类型（ParamType.Int/Double/Bool/String）
            defaultValue (Any, 可选): 如果未找到参数，返回Python对象None
        
        返回:
            int/float/bool/str/None: 参数值，类型由 type 决定，未找到时返回 defaultValue 或 None
        
        示例：
        ```python
        Config.isYellow = ParamManagerZSS.getParam("ZAlert/IsYellow",ParamType.Bool,False)
        ```
        """
    def sync(self) -> None:
        ...
class ParamManagerZSS(ParamManager):
    """
    """
    @staticmethod
    def Instance() -> ParamManagerZSS:
        ...
class ParamType:
    """
    Members:
    
      Int
    
      Double
    
      Bool
    
      String
    """
    Bool: typing.ClassVar[ParamType]  # value = <ParamType.Bool: 2>
    Double: typing.ClassVar[ParamType]  # value = <ParamType.Double: 1>
    Int: typing.ClassVar[ParamType]  # value = <ParamType.Int: 0>
    String: typing.ClassVar[ParamType]  # value = <ParamType.String: 3>
    __members__: typing.ClassVar[dict[str, ParamType]]  # value = {'Int': <ParamType.Int: 0>, 'Double': <ParamType.Double: 1>, 'Bool': <ParamType.Bool: 2>, 'String': <ParamType.String: 3>}
    def __eq__(self, other: typing.Any) -> bool:
        ...
    def __getstate__(self) -> int:
        ...
    def __hash__(self) -> int:
        ...
    def __index__(self) -> int:
        ...
    def __init__(self, value: typing.SupportsInt) -> None:
        ...
    def __int__(self) -> int:
        ...
    def __ne__(self, other: typing.Any) -> bool:
        ...
    def __repr__(self) -> str:
        ...
    def __setstate__(self, state: typing.SupportsInt) -> None:
        ...
    def __str__(self) -> str:
        ...
    @property
    def name(self) -> str:
        ...
    @property
    def value(self) -> int:
        ...
class PlayerCapabilityT:
    def __init__(self) -> None:
        ...
    @property
    def maxAccel(self) -> float:
        """
        最大加速度
        """
    @maxAccel.setter
    def maxAccel(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def maxAngularAccel(self) -> float:
        """
        最大角加速度
        """
    @maxAngularAccel.setter
    def maxAngularAccel(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def maxAngularDec(self) -> float:
        """
        最大角减速度
        """
    @maxAngularDec.setter
    def maxAngularDec(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def maxAngularSpeed(self) -> float:
        """
        最大角速度
        """
    @maxAngularSpeed.setter
    def maxAngularSpeed(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def maxDec(self) -> float:
        """
        最大减速度
        """
    @maxDec.setter
    def maxDec(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def maxSpeed(self) -> float:
        """
        最大速度
        """
    @maxSpeed.setter
    def maxSpeed(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def maxSpeedX(self) -> float:
        """
        最大纵向速度 by Tyh
        """
    @maxSpeedX.setter
    def maxSpeedX(self, arg0: typing.SupportsFloat) -> None:
        ...
    @property
    def maxSpeedY(self) -> float:
        """
        最大横向速度 by Tyh
        """
    @maxSpeedY.setter
    def maxSpeedY(self, arg0: typing.SupportsFloat) -> None:
        ...
class PlayerPoseT(ObjectPoseT):
    def Dir(self) -> float:
        ...
    def ImuDir(self) -> float:
        ...
    def ImuRotateVel(self) -> float:
        ...
    def RawRotVel(self) -> float:
        ...
    def RotVel(self) -> float:
        ...
    def SetDir(self, d: typing.SupportsFloat) -> None:
        ...
    def SetImuDir(self, imudir: typing.SupportsFloat) -> None:
        ...
    def SetImuRotateVel(self, imurotatevel: typing.SupportsFloat) -> None:
        ...
    def SetRawRotVel(self, d: typing.SupportsFloat) -> None:
        ...
    def SetRotVel(self, d: typing.SupportsFloat) -> None:
        ...
    def __init__(self) -> None:
        ...
class PlayerTypeT:
    def SetType(self, t: typing.SupportsInt) -> None:
        ...
    def Type(self) -> int:
        ...
    def __init__(self) -> None:
        ...
class PlayerVisionT(PlayerPoseT, VisionObjectT, PlayerTypeT):
    def __init__(self) -> None:
        ...
class SystemRunner:
    """
    """
    @staticmethod
    def Instance() -> SystemRunner:
        ...
    def init(self, configFilePathName: str = 'zss.ini') -> None:
        """
        对应原函数 while 之前的初始化部分；接受 Python str 并转换为 QString，传入init函数初始化ZSSParamManager的位置
        """
    def postDecision(self) -> None:
        """
        第三步：递归调用，然后下发指令
        """
    def preDecision(self) -> None:
        """
        第一步：进行视觉更新，清空已有指令 （第二步：Python层SelectPlay）
        """
class TaskMediator:
    """
    """
    @staticmethod
    def Instance() -> TaskMediator:
        ...
    def registerRole(self, num: typing.SupportsInt, role: str) -> None:
        ...
class VisionModule:
    @staticmethod
    def Instance() -> VisionModule:
        ...
    def allPlayer(self, num: typing.SupportsInt) -> PlayerVisionT:
        ...
    @typing.overload
    def ball(self) -> BallVisionT:
        ...
    @typing.overload
    def ball(self, cycle: typing.SupportsInt) -> BallVisionT:
        ...
    def canEitherKickBall(self) -> bool:
        ...
    def getBallPlacementPosition(self) -> CGeoPoint:
        ...
    def getCurrentRefereeMsg(self) -> str:
        """
        include ball place
        """
    def getCycle(self) -> int:
        ...
    def getLastCycle(self) -> int:
        ...
    def getLastRefereeMsg(self) -> str:
        ...
    def getNextRefereeMsg(self) -> str:
        ...
    def getOurGoal(self) -> int:
        ...
    def getOurRawPlayerSpeed(self, num: typing.SupportsInt) -> CVector:
        ...
    def getSide(self) -> int:
        ...
    def getTheirGoal(self) -> int:
        ...
    def getTheirPenaltyNum(self) -> int:
        ...
    def getTheirRawPlayerSpeed(self, num: typing.SupportsInt) -> CVector:
        ...
    def getTheirValidNum(self) -> int:
        ...
    def getTimeRemain(self) -> int:
        ...
    def getValidNum(self) -> int:
        ...
    def isGameOn(self) -> bool:
        ...
    @typing.overload
    def ourPlayer(self, num: typing.SupportsInt) -> PlayerVisionT:
        ...
    @typing.overload
    def ourPlayer(self, cycle: typing.SupportsInt, num: typing.SupportsInt) -> PlayerVisionT:
        """
        会自动处理num<0或者大于maxPlayer的情形，不抛出异常
        """
    def rawBall(self) -> ObjectPoseT:
        ...
    def resetTheirPenaltyNum(self) -> None:
        ...
    def setNewVision(self) -> None:
        ...
    def startReceiveThread(self) -> None:
        ...
    @typing.overload
    def theirPlayer(self, num: typing.SupportsInt) -> PlayerVisionT:
        ...
    @typing.overload
    def theirPlayer(self, cycle: typing.SupportsInt, num: typing.SupportsInt) -> PlayerVisionT:
        ...
class VisionObjectT:
    def BestChipPredictPos(self) -> CGeoPoint:
        ...
    def ChipBallState(self) -> bool:
        ...
    def ChipFlyTime(self) -> float:
        ...
    def ChipPredictPos(self) -> CGeoPoint:
        ...
    def ChipRestFlyTime(self) -> float:
        ...
    def LastToucher(self) -> int:
        ...
    def RealPos(self) -> CVector3:
        ...
    def SecondChipPos(self) -> CGeoPoint:
        ...
    def SetBestChipPredictPos(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    def SetChipBallState(self, state: typing.SupportsInt) -> None:
        ...
    def SetChipFlyTime(self, t: typing.SupportsFloat) -> None:
        ...
    def SetChipKickVel(self, x: typing.SupportsFloat, y: typing.SupportsFloat, z: typing.SupportsFloat) -> None:
        ...
    @typing.overload
    def SetChipPredict(self, chipPos: CGeoPoint) -> None:
        ...
    @typing.overload
    def SetChipPredict(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    def SetChipRestFlyTime(self, t: typing.SupportsFloat) -> None:
        ...
    def SetLastToucher(self, id: typing.SupportsInt) -> None:
        ...
    @typing.overload
    def SetRealPos(self, realPos: CVector3) -> None:
        ...
    @typing.overload
    def SetRealPos(self, x: typing.SupportsFloat, y: typing.SupportsFloat, z: typing.SupportsFloat) -> None:
        ...
    def SetSecondChipPos(self, x: typing.SupportsFloat, y: typing.SupportsFloat) -> None:
        ...
    def SetValidCount(self, v: typing.SupportsInt) -> None:
        ...
    def ValidCount(self) -> int:
        ...
    def __init__(self) -> None:
        ...
    def chipKickVel(self) -> CVector3:
        ...
class WorldModel:
    @staticmethod
    def Instance() -> WorldModel:
        ...
    def InfraredOffCount(self, param_0: typing.SupportsInt) -> int:
        ...
    def InfraredOnCount(self, param_0: typing.SupportsInt) -> int:
        ...
    def IsBallKicked(self, param_0: typing.SupportsInt) -> bool:
        ...
    def IsBallKickedVision(self, param_0: typing.SupportsInt) -> bool:
        ...
    def IsInfraredOn(self, param_0: typing.SupportsInt) -> bool:
        ...
    def KickDirArrived(self, current_cycle: typing.SupportsInt, kickdir: typing.SupportsFloat, kickdirprecision: typing.SupportsFloat, myNum: typing.SupportsInt = 0) -> bool:
        ...
    def SPlayFSMSwitchClearAll(self, clear_flag: bool = False) -> None:
        """
        Full name: SelectPlay Finite State Machine Switch Clear All
        """
    def getBPFinished(self) -> bool:
        """
        BP: ball placement，判断ball placement是否完成
        """
    def getEnemyKickOffNum(self) -> int:
        ...
    def timeToTarget(self, player: typing.SupportsInt, target: CGeoPoint) -> float:
        ...
def AngleBetween(d: typing.SupportsFloat, d1: typing.SupportsFloat, d2: typing.SupportsFloat, buffer: typing.SupportsFloat = 0.10471975511965977) -> bool:
    """
     三个均为向量的方向弧度, 判断是否满足v的方向夹在v1和v2之间
     如果v和v1或v2中的任意一个夹角小于buffer, 则也认为满足条件.
    """
def CBetween(v: typing.SupportsFloat, v1: typing.SupportsFloat, v2: typing.SupportsFloat) -> bool:
    """
    @brief	判断一个浮点数是否在其余两个浮点数之间
    """
def CenterOfTwoPoint(p1: CGeoPoint, p2: CGeoPoint) -> CGeoPoint:
    ...
def Deg2Rad(angle: typing.SupportsFloat) -> float:
    ...
def FieldBottom() -> float:
    ...
def FieldLeft() -> float:
    ...
def FieldRight() -> float:
    ...
def FieldTop() -> float:
    ...
def GetInterPos(dir: typing.SupportsFloat, targetPoint: CGeoPoint = ...) -> CGeoPoint:
    ...
def GetOutSidePenaltyPos(dir: typing.SupportsFloat, delta: typing.SupportsFloat, targetPoint: CGeoPoint = ...) -> CGeoPoint:
    ...
def GetOutTheirSidePenaltyPos(dir: typing.SupportsFloat, delta: typing.SupportsFloat, targetPoint: CGeoPoint) -> CGeoPoint:
    ...
def GetTheirInterPos(dir: typing.SupportsFloat, targetPoint: CGeoPoint) -> CGeoPoint:
    ...
@typing.overload
def InBetween(p: CGeoPoint, p1: CGeoPoint, p2: CGeoPoint) -> bool:
    """
    判断p是否在p1,p2之间
    """
@typing.overload
def InBetween(v: typing.SupportsFloat, v1: typing.SupportsFloat, v2: typing.SupportsFloat) -> bool:
    """
    判断v是否在v1和v2之间
    """
@typing.overload
def InBetween(v: CVector, v1: CVector, v2: CVector, buffer: typing.SupportsFloat = 0.10471975511965977) -> bool:
    """
     判断三个共起点向量, v的方向是否夹在v1和v2之间,
     buffer表示余量, 表示当v不在v1,v2之间时,
     如果v和v1或v2中的任意一个夹角小于buffer, 则也认为满足条件.
    """
def InOurPenaltyArea(p: CGeoPoint, buffer: typing.SupportsFloat) -> bool:
    ...
def InTheirPenaltyArea(p: CGeoPoint, buffer: typing.SupportsFloat) -> bool:
    ...
def InTheirPenaltyAreaWithVel(me: PlayerVisionT, buffer: typing.SupportsFloat) -> bool:
    ...
def IsInField(p: CGeoPoint, buffer: typing.SupportsFloat = 0) -> bool:
    """
    判断点是否在场地内, 第二个参数为边界缓冲
    """
def IsInFieldV2(p: CGeoPoint, buffer: typing.SupportsFloat = 0) -> bool:
    """
    判断点是否在场地内, 且不在禁区内， 第二个参数为边界缓冲
    """
def LeftTop() -> CGeoPoint:
    ...
def MakeInField(p: CGeoPoint, buffer: typing.SupportsFloat = 0) -> CGeoPoint:
    """
    让点在场内
    """
def MakeOutOfCircle(center: CGeoPoint, radius: typing.SupportsFloat, target: CGeoPoint, buffer: typing.SupportsFloat, isBack: bool = False, mePos: CGeoPoint = ..., adjustVec: CVector = ...) -> CGeoPoint:
    ...
def MakeOutOfCircleAndInField(center: CGeoPoint, radius: typing.SupportsFloat, p: CGeoPoint, buffer: typing.SupportsFloat) -> CGeoPoint:
    """
    确保点在圆外
    """
def MakeOutOfCircleAndOutOfPenalty(center: CGeoPoint, radius: typing.SupportsFloat, p: CGeoPoint, buffer: typing.SupportsFloat) -> CGeoPoint:
    ...
def MakeOutOfLongCircle(seg_start: CGeoPoint, seg_end: CGeoPoint, radius: typing.SupportsFloat, target: CGeoPoint, buffer: typing.SupportsFloat, adjustVec: CVector = ...) -> CGeoPoint:
    ...
@typing.overload
def MakeOutOfOurPenaltyArea(p: CGeoPoint, buffer: typing.SupportsFloat) -> CGeoPoint:
    ...
@typing.overload
def MakeOutOfOurPenaltyArea(p: CGeoPoint, buffer: typing.SupportsFloat, dir: typing.SupportsFloat) -> CGeoPoint:
    ...
def MakeOutOfRectangle(recP1: CGeoPoint, recP2: CGeoPoint, target: CGeoPoint, buffer: typing.SupportsFloat) -> CGeoPoint:
    ...
def MakeOutOfTheirPenaltyArea(p: CGeoPoint, buffer: typing.SupportsFloat, dir: typing.SupportsFloat = -100000000.0) -> CGeoPoint:
    ...
def Normalize(angle: typing.SupportsFloat) -> float:
    """
    /<把角度规范化到(-PI,PI]
    """
def PlayerNumValid(num: typing.SupportsInt) -> bool:
    ...
def Polar2Vector(m: typing.SupportsFloat, angle: typing.SupportsFloat) -> CVector:
    """
    /<极坐标转换到直角坐标
    """
def Rad2Deg(angle: typing.SupportsFloat) -> float:
    ...
def RightBottom() -> CGeoPoint:
    ...
def Sign(d: typing.SupportsFloat) -> int:
    ...
def SquareRootFloat(number: typing.SupportsFloat) -> float:
    ...
def VectorDot(v1: CVector, v2: CVector) -> float:
    """
    向量点乘
    """
def WeBestGetBallPosition(robotNum: typing.SupportsInt = -1) -> CGeoPoint:
    """
    / 返回我方最佳拿球position（匹配的matchPos）
    / @param robotNum 为-1则自动计算robotNum = ZSkillUtils::instance()->getOurBestPlayer();
    / @return 
    """
def dirDiff(v1: CVector, v2: CVector) -> float:
    """
    { return fabs(Normalize(v1.ir() - v2.ir()));}
    """
def flatpower(ball: BallVisionT, receiver: PlayerVisionT, passPos: CGeoPoint, buffer: typing.SupportsFloat) -> float:
    ...
def getBackPos_CGuardPos(guardNum: typing.SupportsInt, index: typing.SupportsInt, realNum: typing.SupportsInt, defendNum: typing.SupportsInt) -> CGeoPoint:
    ...
def getPosModulePos(index: typing.SupportsInt, mode: typing.SupportsInt) -> CGeoPoint:
    ...
def getWMarkingPos(robotNum: typing.SupportsInt, priority: typing.SupportsInt, flag: typing.SupportsInt, num: typing.SupportsInt) -> CGeoPoint:
    """
    原lua的CGetWMarkingPos，
    而getMarkingLeaderPos是在MessiDecision中
    """
def isTimeOut(condition: bool, buffer_frame: typing.SupportsInt, max_count_frame: typing.SupportsInt) -> bool:
    """
    "
    /// @brief 在新一轮检测周期（cycle）开始时，初始化一个新的计数任务。
    /// @param condition 当前条件（如传感器/行为条件）
    /// @param buffer_frame 缓冲帧数（条件需连续成立多少帧才算成立）
    /// @param max_count_frame 计数帧数（最大检测帧数，超时阈值）
    """
def makeItCalibrationSpeed(num: typing.SupportsInt, speedX: typing.SupportsFloat, speedY: typing.SupportsFloat, rotSpeed: typing.SupportsFloat) -> None:
    ...
def makeItFetchBall(runner: typing.SupportsInt, target: CGeoPoint, power: typing.SupportsFloat, mode: typing.SupportsInt = 0) -> None:
    ...
def makeItGetBall(runner: typing.SupportsInt, flag: typing.SupportsInt = 0) -> None:
    """
    Execute the GetBall task. From naqiu in lua.
    
    Args:
    	runner (int): 执行该任务的球员编号。
    	flag (int): 任务标志位。
    """
def makeItGetBallV4(num: typing.SupportsInt, dir: typing.SupportsFloat, flags: typing.SupportsInt = 0) -> None:
    ...
def makeItGetBallV5(num: typing.SupportsInt, dir: typing.SupportsFloat, ifIntercept: bool, flags: typing.SupportsInt = 0) -> None:
    ...
def makeItGoAndTurnKick(runner: typing.SupportsInt, target: CGeoPoint, useInter: bool, power: typing.SupportsFloat, flag: typing.SupportsInt = 0) -> None:
    """
    				Execute the GoAndTurnKick task.
    
    				Args:
    					runner (int): 执行该任务的球员编号。
    					target (CGeoPoint): 目标点。
    					useInter (bool): 是否使用插值控制。
    					power (float): 踢球力度。
    					flag (int): 任务标志位。
    """
def makeItGoalie(num: typing.SupportsInt, pos: CGeoPoint, flag: typing.SupportsInt = 0) -> None:
    """
                    Execute the Goalie task.
    
                    Args:
                        num (int): The player number.
                        pos (CGeoPoint): The position of the goalie will shoot to.
                        flag (int, optional): Flags for the task. Defaults to 0.
    """
def makeItGoalie2022(runner: typing.SupportsInt, isPenalty: bool = False, flag: typing.SupportsInt = 0) -> None:
    ...
def makeItNormalShoot(runner: typing.SupportsInt, power: typing.SupportsFloat, isChip: bool = False, flag: typing.SupportsInt = 0, type: typing.SupportsInt = 0) -> None:
    ...
def makeItRushTo(executor: typing.SupportsInt, target: CGeoPoint, angle: typing.SupportsFloat, flag: typing.SupportsInt = 0, sender: typing.SupportsInt = 0, maxAcc: typing.SupportsFloat = 0, needDribble: bool = False, vel: CVector = ...) -> None:
    """
    				Execute the RushTo (CMU Trajectory) task.
    
    				Args:
    					executor (int): 执行该任务的球员编号。
    					target (CGeoPoint): 目标点坐标。
    					angle (float): 到达目标点时的朝向（弧度）。
    					flag (int, optional): 任务标志位，默认0。
    					sender (int, optional): 传球者编号，默认0。
    					maxAcc (float, optional): 最大加速度，默认0，表示不限制最大加速度
    					needDribble (bool, optional): 是否需要带球，默认False。
    					vel (CVector, optional): 期望速度向量，默认(0,0)。
    """
def makeItSimpleGoTo(num: typing.SupportsInt, target: CGeoPoint, dir: typing.SupportsFloat, flags: typing.SupportsInt = 0) -> None:
    """
                    Execute the SimpleGoto task.
    
                    Args:
                        num (int): The player number.
                        target (CGeoPoint): The target position.
                        dir (float): The direction angle.
                        flags (int, optional): Flags for the task. Defaults to 0.
    """
def makeItSmartGoTo(runner: typing.SupportsInt, target: CGeoPoint, dir: typing.SupportsFloat, flag: typing.SupportsInt, sender: typing.SupportsInt, maxAcc: typing.SupportsInt, Velocity: CVector) -> None:
    ...
def makeItSmartGoToV4(runner: typing.SupportsInt, target: CGeoPoint, dir: typing.SupportsFloat, flags: typing.SupportsInt = 0) -> None:
    ...
def makeItStaticGetBall(runner: typing.SupportsInt, target: CGeoPoint, kpower: typing.SupportsFloat, cpower: typing.SupportsFloat) -> None:
    ...
def makeItStaticGetBallV4(num: typing.SupportsInt, dir: typing.SupportsFloat, power: typing.SupportsFloat, isChip: bool = False, flags: typing.SupportsInt = 0) -> None:
    ...
def makeItStop(num: typing.SupportsInt, flags: typing.SupportsInt = 0) -> None:
    ...
def makeItTurnAndShoot(runner: typing.SupportsInt, target: CGeoPoint, power: typing.SupportsFloat, flag: typing.SupportsInt = 0) -> None:
    """
    				Execute the TurnAndShoot task.
    
    				Args:
    					runner (int): 执行该任务的球员编号。
    					target (CGeoPoint): 射门目标点。
    					power (float): 平射力度。
    					flag (int): 任务标志位。
    """
def pointToLineDist(p: CGeoPoint, l: CGeoLine) -> float:
    """
    @brief	计算点到直线的距离
    """
def setDribbleCommand(num: typing.SupportsInt, power: typing.SupportsInt = 3) -> None:
    """
    Args:
    	num:
    	power: 下发一般是3! 吸球力度严格在0~255之间！！！不然会下发的时候越界！！！！
    """
Bool: ParamType  # value = <ParamType.Bool: 2>
Double: ParamType  # value = <ParamType.Double: 1>
Int: ParamType  # value = <ParamType.Int: 0>
String: ParamType  # value = <ParamType.String: 3>
