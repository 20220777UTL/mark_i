from enum import Enum

import CppPackage

from .Positions import *
from .PowerCalculator import (
    # 核心接口
    evalPower, shootPower, passPower,
    # 等级
    PowerLevel, P,
    # 常量
    POWER_MAX,
    # 兼容层
    KickPower_toTargetPos, KickPower_getKickPower,
    ChipPower_toTargetPos, ChipPower_toTargetPlayer,
)
from PowerCurveBackend import (
    CURVE_NAMES,
    clamp_with_limits,
    curve_limits_snapshot,
    curve_snapshot,
    curve_store,
    default_curve_file,
    default_curve_template_file,
    default_curve_payload,
    ensure_curve_file_exists,
    reload_curve_store,
)

taskMediator = CppPackage.TaskMediator.Instance()
worldModel = CppPackage.WorldModel.Instance()
kickStatus = CppPackage.KickStatus.Instance()
ballStatus = CppPackage.BallStatus.Instance()

class KickMode(Enum):
    none = 0,
    flat = 1,
    chip = 2,
