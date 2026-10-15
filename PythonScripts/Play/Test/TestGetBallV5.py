"""Bounded local-grSim test for the native GetBallV5 skill."""
import json
import math
from pathlib import Path
import socket
import struct
import sys
import time

import CppPackage as C
import Global
from RoleMatch_LuaStyle import State, StateMachine, Task, declare_state_machine
from RoleMatch_LuaStyle.Skills import Skill
from Vision import Ball, Player, vision
from WorldModel import kickStatus

from Play.Normal import AttackParams as A
from Play.Normal.two_attack import Control, receive


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT.parent / "tmp" / "getball_v5_20261014"
OUTPUT.mkdir(parents=True, exist_ok=True)
TELEMETRY = OUTPUT / "telemetry.jsonl"
RESULT = OUTPUT / "result.json"

# grSim uses metres and degrees in replacement packets.
CASES = (
    {"name": "stationary_250mm", "ball": (0.25, 0.0, 0.0, 0.0), "robot": (0.0, 0.0, 0.0)},
    {"name": "head_on_2mps", "ball": (1.0, 0.0, -2.0, 0.0), "robot": (0.0, 0.0, 0.0)},
    {"name": "crossing_slow", "ball": (0.082, 0.8, 0.0, -1.0), "robot": (0.0, 0.0, 0.0)},
    {"name": "crossing_fast", "ball": (0.082, 1.0, 0.0, -2.0), "robot": (0.0, 0.0, 0.0)},
    {"name": "crossing_fast_turned", "ball": (0.082, 1.0, 0.0, -2.0), "robot": (0.0, 0.0, 90.0)},
)
MAX_CASE_SECONDS = 6.0
SETTLE_SECONDS = 1.2
SETTLE_TIMEOUT = 5.0
COOLDOWN_SECONDS = 0.4
MODES = ("current_rushto", "getball_v5")


def _varint(value):
    out = bytearray()
    while value > 127:
        out.append((value & 127) | 128)
        value >>= 7
    out.append(value)
    return bytes(out)


def _integer(field, value):
    return _varint(field * 8) + _varint(int(value))


def _message(field, value):
    return _varint(field * 8 + 2) + _varint(len(value)) + value


def _double(field, value):
    return _varint(field * 8 + 1) + struct.pack("<d", value)


def _replace_scene(case):
    bx, by, _, _ = case["ball"]
    rx, ry, heading = case["robot"]
    robots = {
        (False, 0): (rx, ry, heading),
        (False, 1): (-3.8, -2.4, 0.0),
        (False, 2): (-3.8, 2.4, 0.0),
        (True, 0): (4.2, 2.0, 180.0),
    }
    payload = _message(1, _double(1, bx) + _double(2, by) + _double(3, 0.0) + _double(4, 0.0))
    for yellow in (False, True):
        for number in range(16):
            enabled = (yellow, number) in robots
            x, y, angle = robots.get((yellow, number), (-4.7, -3.5 - number * 0.2, 0.0))
            robot = _double(1, x) + _double(2, y) + _double(3, angle)
            robot += _integer(4, number) + _integer(5, yellow) + _integer(6, enabled)
            payload += _message(2, robot)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(_message(2, payload), ("127.0.0.1", 20011))


def _launch_ball_velocity(case):
    _, _, vx, vy = case["ball"]
    payload = _message(1, _double(1, case["ball"][0]) + _double(2, case["ball"][1])
                       + _double(3, vx) + _double(4, vy))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(_message(2, payload), ("127.0.0.1", 20011))


class GetBallV5State(State):
    def __init__(self):
        super().__init__()
        if sys.version_info[:3] != (3, 12, 10):
            raise RuntimeError(f"GetBallV5 test requires Python 3.12.10, got {sys.version.split()[0]}")
        self.case_index = -1
        self.mode_index = -1
        self.mode = ""
        self.phase = "start"
        self.phase_started = 0.0
        self.case_started = 0.0
        self.frame = 0
        self.min_distance = float("inf")
        self.valid_frames = 0
        self.samples = 0
        self.rows = []
        self.results = []
        self.control = Control()
        self.log = TELEMETRY.open("w", encoding="utf-8", buffering=1)
        self.log.write(json.dumps({"event": "start", "python": sys.version,
                                   "cases": [c["name"] for c in CASES], "modes": MODES}) + "\n")
        print("[GetBallV5Test] START", flush=True)

    def _stop_tasks(self):
        kickStatus.clearAll()
        for number in (0, 1, 2):
            C.setDribbleCommand(number, 0)
        return {
            "A": Task(Skill.Stop(), fixedNumber=0),
            "B": Task(Skill.Stop(), fixedNumber=1),
            "C": Task(Skill.Stop(), fixedNumber=2),
        }

    def _begin_case(self, now):
        if self.case_index < 0:
            self.case_index = 0
            self.mode_index = 0
        else:
            self.mode_index += 1
        if self.mode_index >= len(MODES):
            self.mode_index = 0
            self.case_index += 1
        if self.case_index >= len(CASES):
            self.phase = "done"
            self._write_result()
            print("[GetBallV5Test] DONE", flush=True)
            return
        case = CASES[self.case_index]
        self.mode = MODES[self.mode_index]
        _replace_scene(case)
        self.phase = "settling"
        self.phase_started = now
        self.min_distance = float("inf")
        self.valid_frames = 0
        self.samples = 0
        self.rows = []
        self.control = Control()
        self.log.write(json.dumps({"event": "reset", "case": case["name"], "mode": self.mode}) + "\n")
        print(f"[GetBallV5Test] RESET {case['name']} / {self.mode}", flush=True)

    def _relative_ball(self):
        robot, ball = Player.Pos(0), Ball.pos()
        dx, dy = ball.x() - robot.x(), ball.y() - robot.y()
        heading = Player.direction(0)
        return (dx * math.cos(heading) + dy * math.sin(heading),
                -dx * math.sin(heading) + dy * math.cos(heading), robot, ball, heading)

    def _record(self, now):
        forward, sideways, robot, ball, heading = self._relative_ball()
        distance = math.hypot(forward, sideways)
        ball_velocity = Ball.vel()
        row = {
            "case": CASES[self.case_index]["name"],
            "mode": self.mode,
            "t": round(now - self.case_started, 4),
            "cycle": int(vision.getCycle()),
            "valid": bool(Ball.valid() and Player.isValid(0)),
            "robot": [robot.x(), robot.y()],
            "heading": heading,
            "ball": [ball.x(), ball.y()],
            "ball_velocity": [ball_velocity.x(), ball_velocity.y()],
            "distance": distance,
            "forward": forward,
            "sideways": sideways,
        }
        self.min_distance = min(self.min_distance, distance)
        self.samples += 1
        self.valid_frames += int(row["valid"])
        self.rows.append(row)
        if self.frame % 6 == 0:
            self.log.write(json.dumps(row) + "\n")
        row["held"] = self.control.held[0]
        return row

    def _finish_case(self, now, captured):
        case = CASES[self.case_index]
        elapsed = now - self.case_started if self.case_started else now - self.phase_started
        result = {
            "case": case["name"],
            "mode": self.mode,
            "captured": captured,
            "capture_time": round(now - self.case_started, 4) if captured else None,
            "elapsed": round(elapsed, 4),
            "min_distance": round(self.min_distance, 2) if math.isfinite(self.min_distance) else None,
            "valid_fraction": self.valid_frames / self.samples if self.samples else 0.0,
            "samples": self.samples,
            "initial": self.rows[0] if self.rows else None,
            "final": self.rows[-1] if self.rows else None,
        }
        self.results.append(result)
        self.log.write(json.dumps({"event": "result", **result}) + "\n")
        self.phase = "cooldown"
        self.phase_started = now
        print("[GetBallV5Test] RESULT " + json.dumps(result), flush=True)

    def _write_result(self):
        def mode_summary(mode):
            successful = [item["capture_time"] for item in self.results
                          if item["mode"] == mode and item["captured"]]
            return {
                "captured": len(successful),
                "cases": sum(item["mode"] == mode for item in self.results),
                "mean_capture_time": sum(successful) / len(successful) if successful else None,
            }

        payload = {
            "skill": "GetBallV5",
            "ifIntercept": True,
            "baseline": "two_attack.receive() using RushTo, same dribbler command and scene reset",
            "capture_rule": {
                "mouth_offset_mm": self.control.offsets[0],
                "contact_tolerance_mm": A.CONTACT_TOLERANCE,
                "relative_speed_max": A.CAPTURE_STABLE_SPEED,
                "confirm_seconds": A.POSSESSION_SECONDS,
            },
            "results": self.results,
            "capture_count": sum(item["captured"] for item in self.results),
            "case_count": len(self.results),
            "by_mode": {mode: mode_summary(mode) for mode in MODES},
        }
        RESULT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        self.log.close()

    def getTasks(self):
        if not Global.isSimulation or Global.isYellow:
            print("[GetBallV5Test] ABORT: requires the blue simulation strategy", flush=True)
            self.phase = "done"
            return self._stop_tasks()

        now = time.monotonic()
        self.frame += 1
        if self.phase == "start":
            self._begin_case(now)
            return self._stop_tasks()
        if self.phase == "settling":
            if now - self.phase_started < SETTLE_SECONDS:
                return self._stop_tasks()
            if not (Ball.valid() and Player.isValid(0)):
                if now - self.phase_started >= SETTLE_TIMEOUT:
                    self._finish_case(now, False)
                return self._stop_tasks()
            self.case_started = now
            _launch_ball_velocity(CASES[self.case_index])
            self.phase = "running"
            print(f"[GetBallV5Test] RUN {CASES[self.case_index]['name']} / {self.mode}", flush=True)
        elif self.phase == "cooldown":
            if now - self.phase_started >= COOLDOWN_SECONDS:
                self._begin_case(now)
            return self._stop_tasks()
        elif self.phase == "done":
            return self._stop_tasks()

        if self.phase == "running":
            if not (Ball.valid() and Player.isValid(0)):
                self._finish_case(now, False)
                return self._stop_tasks()
            self.control.update()
            row = self._record(now)
            if self.control.held[0]:
                self._finish_case(now, True)
                return self._stop_tasks()
            if now - self.case_started >= MAX_CASE_SECONDS:
                self._finish_case(now, False)
                return self._stop_tasks()
            if self.mode == "current_rushto":
                task = receive(0, self.control)
                return {
                    "A": task,
                    "B": Task(Skill.Stop(), fixedNumber=1),
                    "C": Task(Skill.Stop(), fixedNumber=2),
                }

            direction = math.radians(CASES[self.case_index]["robot"][2])
            v5_cpp, match_pos = Skill.GetBallV5(direction, ifIntercept=True)

            def execute(number):
                # GetBallV5's Python wrapper does not set the dribbler itself.
                C.setDribbleCommand(number, 3)
                return v5_cpp(number)

            return {
                "A": Task((execute, match_pos), fixedNumber=0, description="GetBallV5 test"),
                "B": Task(Skill.Stop(), fixedNumber=1),
                "C": Task(Skill.Stop(), fixedNumber=2),
            }
        return self._stop_tasks()

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(GetBallV5State)
class TestGetBallV5(StateMachine):
    pass
