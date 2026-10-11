"""
KickPower 兼容层 — 所有调用重定向到 PowerCalculator

原 KickPower 模块已合并进 PowerCalculator。
本文件仅做兼容桥接，不新增逻辑。

迁移指南:
    from WorldModel.KickPower import getKickPower
    →  from WorldModel.PowerCalculator import evalPower, P
    →  evalPower(Ball.pos(), target, P.LOW)

    from WorldModel.KickPower import toTargetPos
    →  from WorldModel.PowerCalculator import KickPower_toTargetPos
"""

from WorldModel.PowerCalculator import (
    KickPower_getKickPower as getKickPower,
    KickPower_toTargetPos as toTargetPos,
    evalPower,
    P,
)
from Vision import Player, Ball

def toTargetPlayer(targetPlayer):
    """球到 targetPlayer 位置所需的平射力度"""
    return evalPower(Ball.pos(), Player.Pos(targetPlayer), P.LOW)
