"""Rotate while holding the ball; only kick after the heading has settled.

Use through Task in getTasks(). This is not a get-ball skill. Angles are radians,
distances are millimetres. Rotation speed is controlled by the native movement
controller; maxRotVel is a firing threshold, not a commanded turning speed.
"""
import math

import CppPackage
from Vision import Ball, Player
from WorldModel import Flags, Positions, kickStatus

__all__ = ["TurnAndShootAligned"]


def TurnAndShootAligned(target=None, *, angle=None, power, isChip=False,
                       tolerance=math.radians(3), maxRotVel=0.5,
                       maxBallDistance=160, frontTolerance=math.radians(20),
                       flag=0):
    """Aim at target (default theirGoal), or at an absolute angle, then kick.

    target and angle are mutually exclusive. Recompute dynamic targets in
    getTasks(), or wrap the skill in Task(lambda: ...). No persistent counters
    are used, since this project's Task/skill closures are recreated each frame.
    The ball must be near and in front of the robot; no infrared is required.
    Repeated calls may kick while all gates remain satisfied; transition your
    play after detecting ball release when a single shot is required.
    """
    if target is not None and angle is not None:
        raise ValueError("Specify target or angle, not both")
    if target is None and angle is None:
        target = Positions.theirGoal
    power = float(power)
    if not math.isfinite(power) or power < 0:
        raise ValueError("power must be finite and non-negative")
    for name, value in (("tolerance", tolerance), ("maxRotVel", maxRotVel),
                        ("maxBallDistance", maxBallDistance),
                        ("frontTolerance", frontTolerance)):
        if not math.isfinite(value) or value <= 0:
            raise ValueError(f"{name} must be finite and positive")
    if angle is not None and not math.isfinite(angle):
        raise ValueError("angle must be finite")
    # force_kick must never bypass this skill's gate.
    move_flag = int(flag) & ~Flags.force_kick

    def error(a, b):
        return abs(math.atan2(math.sin(a - b), math.cos(a - b)))

    def stop(executor):
        CppPackage.setDribbleCommand(executor, 0)
        return CppPackage.makeItStop(executor)

    def skill_cpp(executor):
        # Clear this robot only; do not erase teammates' kick commands.
        kickStatus.setBothKick(executor, 0, 0)
        if not Player.isValid(executor) or not Ball.valid():
            return stop(executor)
        pos, ball_pos = Player.Pos(executor), Ball.pos()
        heading, omega = Player.direction(executor), Player.rotVel(executor)
        values = (pos.x(), pos.y(), ball_pos.x(), ball_pos.y(), heading, omega)
        if not all(math.isfinite(v) for v in values):
            return stop(executor)

        if angle is None:
            dx, dy = target.x() - ball_pos.x(), target.y() - ball_pos.y()
            if not all(math.isfinite(v) for v in (dx, dy)) or math.hypot(dx, dy) < 1:
                return stop(executor)
            desired = math.atan2(dy, dx)
        else:
            desired = math.atan2(math.sin(angle), math.cos(angle))

        # Stay at the current centre while rotating, without a native shooting task.
        CppPackage.setDribbleCommand(executor, 3)
        result = CppPackage.makeItSimpleGoTo(executor, pos, desired, move_flag)
        bx, by = ball_pos.x() - pos.x(), ball_pos.y() - pos.y()
        distance = math.hypot(bx, by)
        ready = (
            error(heading, desired) <= tolerance
            and abs(omega) <= maxRotVel
            and 1 < distance <= maxBallDistance
            and error(heading, math.atan2(by, bx)) <= frontTolerance
        )
        if ready:
            if isChip:
                kickStatus.setChipKick(executor, power)
            else:
                kickStatus.setKick(executor, power)
        return result

    def matchPos(executor):
        return Ball.pos()

    return skill_cpp, matchPos
