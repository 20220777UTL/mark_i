"""Finite grSim telemetry run for GoalieOnly movement-response parameters."""
from __future__ import annotations

import json
import math
import os
import ctypes
import random
from datetime import datetime
from pathlib import Path
import socket
import struct
import sys
import time

import CppPackage as C
import Global
from Play.Normal.GoalieOnly import GoalieOnly
from Vision import Ball, Player, vision
from WorldModel import Params, kickStatus


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S")
OUTPUT = Path(os.environ.get(
    "SRC_GOALIE_RESPONSE_OUT",
    str(ROOT.parent / "tmp" / f"goalie_response_{RUN_ID}"),
))
OUTPUT.mkdir(parents=True, exist_ok=True)
TELEMETRY = OUTPUT / "telemetry.jsonl"
RESULTS = OUTPUT / "results.json"

START_X_MM = (1500, 2800)
TARGET_FRACTIONS = (-0.85, -0.425, 0.0, 0.425, 0.85)
SPEEDS_M_S = (2.0, 5.0, 6.0)
REPEATS = (1, 2)
SETTLE_SECONDS = 0.8
SETTLE_TIMEOUT_SECONDS = 15.0
SHOT_TIMEOUT_SECONDS = 3.5
GOALIE_MOVE_SPEED_MM_S = 100.0
GOALIE_MOVE_DISTANCE_MM = 20.0
GOAL_LINE_X_MM = Params.pitchLength / 2
SAFE_HALF_GOAL_MM = Params.goalWidth / 2 - 90
ELLIPSE_HALF_X_MM = 300.0
ELLIPSE_HALF_Y_MM = 500.0
GOALIE_HOME_X_MM = GOAL_LINE_X_MM - ELLIPSE_HALF_X_MM
ORDER_SEED = 20261014


def _ellipse_target(ball_position):
    """Predicted point on the supplied goal-centered ellipse along ball ray."""
    dx = ball_position[0] - GOAL_LINE_X_MM
    dy = ball_position[1]
    normalized_radius = math.hypot(dx / ELLIPSE_HALF_X_MM,
                                   dy / ELLIPSE_HALF_Y_MM)
    if normalized_radius <= 1e-9:
        return [GOAL_LINE_X_MM, 0.0]
    scale = 1.0 / normalized_radius
    return [GOAL_LINE_X_MM + scale * dx, scale * dy]


def _percentile(values, fraction):
    if not values:
        return None
    ordered = sorted(values)
    index = round((len(ordered) - 1) * fraction)
    return ordered[index]


def _varint(value: int) -> bytes:
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def _integer(field: int, value: int) -> bytes:
    return _varint(field * 8) + _varint(int(value))


def _message(field: int, value: bytes) -> bytes:
    return _varint(field * 8 + 2) + _varint(len(value)) + value


def _double(field: int, value: float) -> bytes:
    return _varint(field * 8 + 1) + struct.pack("<d", float(value))


def _ball_message(ball_m, velocity_m_s=(0.0, 0.0)) -> bytes:
    bx, by = ball_m
    bvx, bvy = velocity_m_s
    return _message(1, _double(1, bx) + _double(2, by)
                    + _double(3, bvx) + _double(4, bvy))


def _ball_packet(ball_m, velocity_m_s=(0.0, 0.0)) -> bytes:
    return _message(2, _ball_message(ball_m, velocity_m_s))


def _send_replacement(ball_m, velocity_m_s=(0.0, 0.0)) -> None:
    """Send the documented grSim replacement packet to local loopback only."""
    payload = _ball_message(ball_m, velocity_m_s)
    robots = {
        # Blue remains stopped in its own half, outside every tested ball lane.
        (False, 0): (-3.8, -2.2, 0.0),
        (False, 1): (-3.8, 0.0, 0.0),
        (False, 2): (-3.8, 2.2, 0.0),
        # Yellow 0 protects the positive-X goal.
        (True, 0): (GOALIE_HOME_X_MM / 1000, 0.0, 180.0),
    }
    for yellow in (False, True):
        for number in range(16):
            enabled = (yellow, number) in robots
            x, y, angle = robots.get((yellow, number), (-4.7, -3.5-number*0.2, 0.0))
            robot = (_double(1, x) + _double(2, y) + _double(3, angle)
                     + _integer(4, number) + _integer(5, yellow) + _integer(6, enabled))
            payload += _message(2, robot)
    packet = _message(2, payload)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(packet, ("127.0.0.1", 20011))


def _launch_velocity(ball_m, target_y_mm, speed_m_s):
    bx_mm = ball_m[0] * 1000
    dx = GOAL_LINE_X_MM - bx_mm
    dy = target_y_mm
    length = math.hypot(dx, dy)
    vx = speed_m_s * dx / length
    vy = speed_m_s * dy / length
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(_ball_packet(ball_m, (vx, vy)), ("127.0.0.1", 20011))
    return vx, vy


def _point(point):
    return [float(point.x()), float(point.y())]


class GoalieResponseRun:
    """Telemetry wrapper that delegates every yellow command to GoalieOnly."""

    def __init__(self):
        if sys.version_info[:3] != (3, 12, 10):
            raise RuntimeError(f"Test requires Python 3.12.10, got {sys.version.split()[0]}")
        if not Global.isSimulation or not Global.isYellow or not Global.isRight:
            raise RuntimeError("Run as yellow, right-side simulation: --sim --team yellow --side right")
        self.goalie = GoalieOnly()
        self.trials = [
            {"start_x_mm": x, "target_fraction": fraction,
             "speed_m_s": speed, "repeat": repeat}
            for x in START_X_MM for fraction in TARGET_FRACTIONS
            for speed in SPEEDS_M_S for repeat in REPEATS
        ]
        random.Random(ORDER_SEED).shuffle(self.trials)
        self.trial_index = -1
        self.phase = "start"
        self.results = []
        self.samples = 0
        self.motion_count = 0
        self.motion_candidate = None
        self.previous = None
        self.crossing = None
        self.initial_keeper = None
        self.shot_started = None
        self.trial = None
        self.log = TELEMETRY.open("w", encoding="utf-8", buffering=1)
        self.log.write(json.dumps({
            "event": "start", "run_id": RUN_ID, "python": sys.version,
            "planned_trials": len(self.trials), "repeats": REPEATS,
            "order_seed": ORDER_SEED,
            "start_x_mm": START_X_MM, "target_fractions": TARGET_FRACTIONS,
            "speeds_m_s": SPEEDS_M_S, "safe_half_goal_mm": SAFE_HALF_GOAL_MM,
            "goal_line_x_mm": GOAL_LINE_X_MM,
            "goalie_target_ellipse_mm": [ELLIPSE_HALF_X_MM, ELLIPSE_HALF_Y_MM],
            "goalie_home_x_mm": GOALIE_HOME_X_MM,
            "blue_robots": "stationary at x=-3800 mm; yellow goalie 0 runs GoalieOnly",
            "units": {"position": "mm", "velocity": "mm/s", "time": "s"},
        }, ensure_ascii=False) + "\n")
        print(f"[GoalieResponse] START output={OUTPUT} trials={len(self.trials)}", flush=True)

    def _start_trial(self, now):
        self.trial_index += 1
        if self.trial_index >= len(self.trials):
            self.phase = "done"
            self._write_results()
            print(f"[GoalieResponse] DONE output={OUTPUT} trials={len(self.results)}", flush=True)
            self.log.close()
            return
        self.trial = dict(self.trials[self.trial_index])
        self.trial["target_y_mm"] = round(SAFE_HALF_GOAL_MM * self.trial["target_fraction"])
        self.trial["ball_start_m"] = (self.trial["start_x_mm"] / 1000, 0.0)
        self.motion_count = 0
        self.motion_candidate = None
        self.previous = None
        self.crossing = None
        self.initial_keeper = None
        self.shot_started = None
        self.samples = 0
        self.speed_samples = []
        self.acceleration_samples = []
        self.max_ball_speed = 0.0
        self.first_measured_ball_speed = None
        _send_replacement(self.trial["ball_start_m"])
        self.phase = "settling"
        self.phase_started = now
        self.log.write(json.dumps({"event": "reset", "trial": self.trial,
                                   "trial_index": self.trial_index + 1}, ensure_ascii=False) + "\n")
        print("[GoalieResponse] RESET " + json.dumps(self.trial, ensure_ascii=False), flush=True)

    def _sample(self, now):
        ball_valid = bool(Ball.valid())
        goalie_valid = bool(Player.isValid(0))
        ball_pos = _point(Ball.pos()) if ball_valid else None
        ball_vel_obj = Ball.vel() if ball_valid else None
        ball_vel = [float(ball_vel_obj.x()), float(ball_vel_obj.y())] if ball_valid else None
        keeper_pos = _point(Player.Pos(0)) if goalie_valid else None
        keeper_vel_obj = Player.vel(0) if goalie_valid else None
        keeper_vel = [float(keeper_vel_obj.x()), float(keeper_vel_obj.y())] if goalie_valid else None
        speed = Player.velMod(0) if goalie_valid else None
        t = max(0.0, now - self.shot_started)
        target = _ellipse_target(ball_pos) if ball_pos is not None else None
        target_error = math.dist(keeper_pos, target) if keeper_pos is not None and target is not None else None
        dt = t - self.previous["t"] if self.previous is not None else 0.0
        position_velocity = None
        acceleration = None
        if (goalie_valid and self.previous is not None and self.previous.get("goalie") is not None
                and dt > 1e-4):
            position_velocity = [(keeper_pos[i] - self.previous["goalie"][i]) / dt for i in (0, 1)]
        if (goalie_valid and keeper_vel is not None and self.previous is not None
                and self.previous.get("goalie_velocity") is not None and dt > 1e-4):
            acceleration = [(keeper_vel[i] - self.previous["goalie_velocity"][i]) / dt
                            for i in (0, 1)]
            magnitude = math.hypot(*acceleration)
            if t >= 0.05:
                self.acceleration_samples.append(magnitude)
        if goalie_valid and speed is not None:
            self.speed_samples.append(float(speed))
        measured_ball_speed = Ball.velMod() if ball_valid else None
        if measured_ball_speed is not None:
            self.max_ball_speed = max(self.max_ball_speed, measured_ball_speed)
            if measured_ball_speed > 100 and self.first_measured_ball_speed is None:
                self.first_measured_ball_speed = measured_ball_speed
        sample = {
            "event": "frame", "trial_index": self.trial_index + 1,
            "t": t, "cycle": int(vision.getCycle()),
            "ball_valid": ball_valid, "ball": ball_pos, "ball_velocity": ball_vel,
            "ball_speed": measured_ball_speed,
            "goalie_valid": goalie_valid, "goalie": keeper_pos,
            "goalie_velocity": keeper_vel, "goalie_speed": speed,
            "goalie_position_velocity": position_velocity,
            "goalie_acceleration": acceleration,
            "predicted_ellipse_target": target,
            "target_error_mm": target_error,
        }
        self.log.write(json.dumps(sample, ensure_ascii=False, allow_nan=False) + "\n")
        self.samples += 1

        if goalie_valid and self.initial_keeper is not None:
            displacement = math.dist(keeper_pos, self.initial_keeper)
            is_moving = (speed >= GOALIE_MOVE_SPEED_MM_S or displacement >= GOALIE_MOVE_DISTANCE_MM)
            if is_moving:
                if self.motion_count == 0:
                    self.motion_candidate = t
                self.motion_count += 1
                if self.motion_count >= 2 and self.trial.get("movement_start_s") is None:
                    self.trial["movement_start_s"] = self.motion_candidate
            else:
                self.motion_count = 0
                self.motion_candidate = None

        if (ball_valid and self.previous is not None
                and self.previous["ball"] is not None
                and self.previous["ball"][0] < GOAL_LINE_X_MM <= ball_pos[0]):
            x0, x1 = self.previous["ball"][0], ball_pos[0]
            ratio = (GOAL_LINE_X_MM - x0) / max(1e-9, x1 - x0)
            y_cross = self.previous["ball"][1] + ratio * (ball_pos[1] - self.previous["ball"][1])
            keeper_at_line = None
            if goalie_valid and self.previous.get("goalie") is not None:
                keeper_at_line = [self.previous["goalie"][i]
                                  + ratio * (keeper_pos[i] - self.previous["goalie"][i])
                                  for i in (0, 1)]
            crossing_t = self.previous["t"] + ratio * (t - self.previous["t"])
            self.crossing = {"time_s": crossing_t, "ball_y_mm": y_cross,
                             "goalie_position_mm": keeper_at_line,
                             "inside_posts": abs(y_cross) <= Params.goalWidth / 2}

        self.previous = {"t": t, "ball": ball_pos, "goalie": keeper_pos,
                         "goalie_velocity": keeper_vel}
        return t

    def _finish_trial(self, outcome, now):
        result = dict(self.trial)
        result.update({
            "trial_index": self.trial_index + 1,
            "outcome": outcome,
            "movement_start_s": result.get("movement_start_s"),
            "initial_goalie_position_mm": self.initial_keeper,
            "goal_line_crossing": self.crossing,
            "samples": self.samples,
            "elapsed_s": max(0.0, now - self.shot_started),
            "final_ball_position_mm": self.previous["ball"] if self.previous else None,
            "final_goalie_position_mm": self.previous["goalie"] if self.previous else None,
            "requested_velocity_m_s": list(self.requested_velocity),
            "first_measured_ball_speed_mm_s": self.first_measured_ball_speed,
            "max_measured_ball_speed_mm_s": self.max_ball_speed,
            "goalie_peak_speed_mm_s": max(self.speed_samples, default=0.0),
            "goalie_p95_speed_mm_s": _percentile(self.speed_samples, 0.95),
            "goalie_peak_acceleration_mm_s2": max(self.acceleration_samples, default=None),
            "goalie_p95_acceleration_mm_s2": _percentile(self.acceleration_samples, 0.95),
        })
        self.results.append(result)
        self.log.write(json.dumps({"event": "result", **result}, ensure_ascii=False,
                                  allow_nan=False) + "\n")
        self._write_results()
        print("[GoalieResponse] RESULT " + json.dumps(result, ensure_ascii=False), flush=True)
        self.phase = "start"

    def _write_results(self):
        RESULTS.write_text(json.dumps({
            "run_id": RUN_ID, "python": sys.version,
            "completed_trials": len(self.results), "planned_trials": len(self.trials),
            "goal_line_x_mm": GOAL_LINE_X_MM,
            "goalie_target_ellipse_mm": [ELLIPSE_HALF_X_MM, ELLIPSE_HALF_Y_MM],
            "goalie_home_x_mm": GOALIE_HOME_X_MM,
            "safe_half_goal_mm": SAFE_HALF_GOAL_MM,
            "movement_threshold_mm_s": GOALIE_MOVE_SPEED_MM_S,
            "movement_displacement_mm": GOALIE_MOVE_DISTANCE_MM,
            "results": self.results,
        }, indent=2, ensure_ascii=False, allow_nan=False), encoding="utf-8")

    def planTasks(self):
        now = time.monotonic()
        if self.phase == "done":
            C.setDribbleCommand(0, 0)
            kickStatus.clearAll()
            C.makeItStop(0)
            self.done_frames += 1
            if self.done_frames >= 20:
                try:
                    ctypes.CDLL("ucrtbase.dll").fflush(None)
                except (AttributeError, OSError):
                    pass
                os._exit(0)
            return

        if self.phase == "start":
            self._start_trial(now)
            if self.phase == "done":
                self.done_frames = 0
                return

        self.goalie.planTasks()

        if self.phase == "settling":
            if now - self.phase_started >= SETTLE_TIMEOUT_SECONDS:
                raise RuntimeError("Vision did not report the ball and yellow goalie within 15 seconds")
            if now - self.phase_started >= SETTLE_SECONDS and Player.isValid(0) and Ball.valid():
                self.initial_keeper = _point(Player.Pos(0))
                vx, vy = _launch_velocity(self.trial["ball_start_m"], self.trial["target_y_mm"],
                                          self.trial["speed_m_s"])
                self.requested_velocity = (vx, vy)
                self.shot_started = now
                self.trial["movement_start_s"] = None
                self.phase = "flight"
                self.previous = {"t": 0.0,
                                 "ball": [self.trial["start_x_mm"], 0.0],
                                 "goalie": self.initial_keeper,
                                 "goalie_velocity": [float(Player.vel(0).x()),
                                                     float(Player.vel(0).y())]}
                print(f"[GoalieResponse] LAUNCH {self.trial_index+1}/{len(self.trials)} "
                      f"speed={self.trial['speed_m_s']}m/s target_y={self.trial['target_y_mm']}mm "
                      f"keeper={self.initial_keeper}", flush=True)
            return

        if self.phase == "flight":
            elapsed = self._sample(now)
            if self.crossing is not None:
                self._finish_trial("goal_line_crossed", now)
            elif elapsed >= SHOT_TIMEOUT_SECONDS:
                self._finish_trial("no_goal_line_crossing_before_timeout", now)


class TestGoalieResponse:
    """Adapter used as Config.testStrategy in the dedicated test launcher."""
    def __init__(self):
        self.run = GoalieResponseRun()

    def planTasks(self):
        self.run.planTasks()
