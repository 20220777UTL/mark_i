import numbers
from enum import IntEnum
import typing
from CppPackage import Polar2Vector, Normalize
from .BufferedCondition import *
from CppPackage import Normalize, Polar2Vector, VectorDot, dirDiff, InBetween, InBetween, AngleBetween, \
    CenterOfTwoPoint, InBetween, CBetween, pointToLineDist, Deg2Rad, Rad2Deg, MakeInField, IsInField, IsInFieldV2, \
    FieldLeft, FieldRight, FieldTop, FieldBottom, LeftTop, RightBottom, Sign, MakeOutOfOurPenaltyArea, \
    MakeOutOfOurPenaltyArea, MakeOutOfTheirPenaltyArea, MakeOutOfCircleAndInField, MakeOutOfCircle, MakeOutOfLongCircle, \
    MakeOutOfRectangle, MakeOutOfCircleAndOutOfPenalty, InOurPenaltyArea, InTheirPenaltyArea, InTheirPenaltyAreaWithVel, \
    PlayerNumValid, GetOutSidePenaltyPos, GetOutTheirSidePenaltyPos, GetInterPos, GetTheirInterPos, SquareRootFloat, \
    flatpower

class DebugColor(IntEnum):
    """颜色枚举类"""
    White = 0
    Red = 1
    Orange = 2
    Yellow = 3
    Green = 4
    Cyan = 5
    Blue = 6
    Purple = 7
    Gray = 8
    Black = 9
    UseRgb = 10

debugEngine = CppPackage.DebugEngine.Instance()  # 使用CppPackage.DebugEngine()是一样的，pybind层写好了，等价于获取单例

def constrain(value: typing.SupportsFloat, lowerBound: typing.SupportsFloat = float('-inf'), upperBound: typing.SupportsFloat = float('inf')):
    if value < lowerBound:
        value = lowerBound
    elif value > upperBound:
        value = upperBound
    return value
