"""官方裁判策略共用配置：默认按视觉识别车辆，不限制比赛人数。

Config.py 可选择限定车号。停止指令覆盖受控车号范围，移动任务只分配给有效车辆。
"""

import CppPackage
import Global
from Geometry import CGeoPoint
from RoleMatch_LuaStyle import Task
from RoleMatch_LuaStyle.Skills import Stop
from Vision import Player
from WorldModel import Params, kickStatus


def controlled_numbers(visible_only=False):
    configured = Global.controlledRobotNumbers
    numbers = tuple(range(Params.maxPlayer)) if configured is None else tuple(configured)
    if any(type(number) is not int or not 0 <= number < Params.maxPlayer for number in numbers):
        raise ValueError("controlledRobotNumbers contains an invalid robot ID")
    if len(set(numbers)) != len(numbers):
        raise ValueError("controlledRobotNumbers contains duplicate robot IDs")
    return tuple(number for number in numbers if not visible_only or Player.valid(number))


def role_for(number):
    return "G" if number == Global.goalieNumber else f"Official{number}"


def stop_tasks():
    # 即使视觉暂时丢失，也向配置的车号下发停止。
    return {role_for(number): Task(Stop(), fixedNumber=number) for number in controlled_numbers()}


def disable_ball_actions():
    kickStatus.clearAll()
    for number in controlled_numbers():
        CppPackage.setDribbleCommand(number, 0)


def clamp_to_field(point):
    margin = Params.playerRadius + 50
    half_length = Params.pitchLength / 2 - margin
    half_width = Params.pitchWidth / 2 - margin
    return CGeoPoint(
        max(-half_length, min(point.x(), half_length)),
        max(-half_width, min(point.y(), half_width)),
    )
