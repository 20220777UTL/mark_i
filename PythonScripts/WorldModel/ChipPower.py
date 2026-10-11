"""
ChipPower 兼容层 — 所有调用重定向到 PowerCalculator

原 ChipPower 模块已合并进 PowerCalculator。
本文件仅做兼容桥接，不新增逻辑。

迁移指南:
    from WorldModel.ChipPower import getChipPower
    →  from WorldModel.PowerCalculator import evalPower, P
    →  evalPower(Ball.pos(), target, P.LOW, is_chip=True)

    from WorldModel.ChipPower import toTargetPos
    →  from WorldModel.PowerCalculator import ChipPower_toTargetPos
"""

from WorldModel.PowerCalculator import (
    ChipPower_toTargetPos as toTargetPos,
    ChipPower_toTargetPlayer as toTargetPlayer,
)
