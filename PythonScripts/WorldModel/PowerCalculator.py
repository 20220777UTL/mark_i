"""
PowerCalculator - RoboCup SSL 力度计算统一接口

本模块是 Medusa 战术系统中所有力度计算的唯一对外入口。
脚本层（Play、Skill 等）应始终通过本模块获取力度，禁止绕过本模块
自行编写力度映射。

架构位置::

    Play / Skill / Test
          │
          ▼
    PowerCalculator.evalPower()   ← 唯一对外接口
          │
          ▼
    PowerCurveBackend
    （距离到力度的端到端曲线）

可调参数全部在 Global.py 中，本文件仅保留默认定义。

使用示例::

    from WorldModel.PowerCalculator import evalPower, P

    # 常规传球
    power = evalPower(Ball.pos(), teammate_pos, P.NORMAL)

    # 射门
    power = evalPower(Ball.pos(), Positions.theirGoal, P.HIGH)

    # 挑射（使用 chip profile）
    power = evalPower(Ball.pos(), target, P.NORMAL, is_chip=True)
"""

from __future__ import annotations

from enum import Enum
from typing import Union, Callable, Optional

import Global
from CppPackage import CGeoPoint
from Vision import Ball, Player
from CppPackage import DebugEngine
from PowerCurveBackend import (
    clamp_with_limits as clamp_curve_with_limits,
    curve_limits_snapshot,
    evaluate_distance as evaluate_curve_distance,
)

debugengine = DebugEngine.Instance()

# ============================================================================
# 力度常量（默认值，可由 Global.py 覆盖）
# ============================================================================

POWER_MAX: int = getattr(Global, 'powerMax', 7400)
"""正常输出上限 — 比赛规则允许的最大踢球力度"""

DEFAULT_VT: int = 0
"""默认目标末速度 (mm/s)，已弃用，保留兼容"""

def reloadFromGlobal():
    """从 Global.py 重新加载可调参数（在 Global 初始化后调用）"""
    global POWER_MAX
    POWER_MAX = getattr(Global, 'powerMax', 7400)

# ============================================================================
# 评估等级
# ============================================================================

class PowerLevel(Enum):
    """力度评估等级"""
    LOW = 0       # 保守传球
    NORMAL = 1    # 常规力度
    HIGH = 2      # 高力度曲线


# 短名别名
P = PowerLevel


# ============================================================================
# 内部计算函数
# ============================================================================

def _clamp_curve_power(power: float, *, is_chip: bool = False) -> float:
    """曲线后端按曲线 limits 截断，并且绝不超过 Global.powerMax。"""
    profile = "chip" if is_chip else "flat"
    return clamp_curve_with_limits(power, curve_limits_snapshot(profile=profile), hard_max=POWER_MAX)


def _curve_name_for_level(level: PowerLevel) -> str:
    if level == PowerLevel.LOW:
        return "Low"
    if level == PowerLevel.NORMAL:
        return "Normal"
    return "High"


def _curve_profile_for_kick(is_chip: bool) -> str:
    return "chip" if is_chip else "flat"


# ============================================================================
# 公共接口（唯一对外接口）
# ============================================================================

def evalPower(
    A: Union[CGeoPoint, str, int, Callable[[], CGeoPoint]],
    B: Union[CGeoPoint, str, int, Callable[[], CGeoPoint]],
    level: Union[PowerLevel, int] = PowerLevel.NORMAL,
    *,
    is_chip: bool = False,
    vt: float = DEFAULT_VT,
) -> float:
    """
    计算从 A 踢球到 B 所需的力度。

    平射和挑射分别使用 PowerCurveBackend 中对应的曲线配置。

    Args:
        A: 起点，可以是 CGeoPoint / 角色名(str) / 车号(int) / callable。
           通常传入 Ball.pos()。
        B: 终点（目标位置），类型同 A。
        level: 评估等级。
            - PowerLevel.LOW (0):    保守传球
            - PowerLevel.NORMAL (1): 常规力度曲线
            - PowerLevel.HIGH (2):   高力度曲线
        is_chip: False 使用 flat profile，True 使用 chip profile。
        vt: 已弃用，保留参数兼容。

    Returns:
        曲线计算结果，最终不超过 POWER_MAX。
        坐标无效或曲线异常时返回 0。
    """
    # 统一等级类型
    if isinstance(level, int):
        level = PowerLevel(level)

    # 解析坐标
    pos_a = _resolve(A)
    pos_b = _resolve(B)
    if pos_a is None or pos_b is None:
        return 0.0

    # 端到端曲线后端：按距离、力度等级和踢球类型直接得到最终力度。
    try:
        distance_mm = (pos_b - pos_a).mod()
        result = evaluate_curve_distance(
            distance_mm,
            _curve_name_for_level(level),
            profile=_curve_profile_for_kick(is_chip),
        )
    except Exception as e:
        print(f"[PowerCalculator] 曲线计算异常: {e}")
        return 0.0
    return _clamp_curve_power(result, is_chip=is_chip)


# ============================================================================
# 便捷函数
# ============================================================================

def shootPower() -> float:
    """射门力度（快捷方式，等同于 evalPower(..., level=HIGH)）"""
    return float(POWER_MAX)


def passPower(
    target: Union[CGeoPoint, str, int, Callable[[], CGeoPoint]],
    *,
    from_pos: Union[CGeoPoint, str, int, Callable[[], CGeoPoint], None] = None,
    level: Union[PowerLevel, int] = PowerLevel.LOW,
) -> float:
    """
    传球力度（快捷方式，起点默认球位置）。

    Args:
        target: 传球目标
        from_pos: 起点，默认 Ball.pos()
        level: 评估等级，默认 LOW

    Returns:
        力度值
    """
    A = from_pos if from_pos is not None else Ball.pos()
    return evalPower(A, target, level)


# ============================================================================
# 参数解析（内部）
# ============================================================================

def _resolve(target) -> Optional[CGeoPoint]:
    """将各种形式的目标统一解析为 CGeoPoint"""
    if target is None:
        return None
    if isinstance(target, CGeoPoint):
        return target
    if callable(target):
        try:
            r = target()
            return r if isinstance(r, CGeoPoint) else None
        except Exception:
            return None
    try:
        return Player.Pos(target)
    except Exception:
        return None


# ============================================================================
# 兼容层（供旧代码平滑迁移）
# ============================================================================

def KickPower_toTargetPos(targetPos: CGeoPoint) -> float:
    """兼容旧 KickPower.toTargetPos 接口"""
    return evalPower(Ball.pos(), targetPos, PowerLevel.LOW)


def KickPower_getKickPower(target: CGeoPoint, Vt: float = DEFAULT_VT) -> float:
    """兼容旧 KickPower.getKickPower 接口，统一转发到端到端曲线。"""
    return evalPower(Ball.pos(), target, PowerLevel.LOW, vt=Vt)


def ChipPower_toTargetPos(targetPos: CGeoPoint) -> float:
    """兼容旧 ChipPower.toTargetPos 接口"""
    return evalPower(Ball.pos(), targetPos, PowerLevel.NORMAL)


def ChipPower_toTargetPlayer(targetPlayer) -> float:
    """兼容旧 ChipPower.toTargetPlayer 接口"""
    return max(2400, evalPower(Ball.pos(), targetPlayer, PowerLevel.HIGH))


# ============================================================================
# 配置 / 调试
# ============================================================================

def getConfig() -> dict:
    """获取当前配置快照"""
    return {
        "POWER_MAX":      POWER_MAX,
        "POWER_CURVE_FILE": getattr(Global, "powerCurveFile", ""),
    }
