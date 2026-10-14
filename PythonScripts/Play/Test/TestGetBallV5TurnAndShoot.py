"""Finite grSim test: acquire with GetBallV5, then finish with TurnAndShoot."""
import json
import math
from datetime import datetime
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
from WorldModel import Params, kickStatus
from WorldModel.PowerCalculator import evalPower, P


ROOT = Path(__file__).resolve().parents[3]
RUN_ID = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
OUTPUT = ROOT.parent / "tmp" / f"getball_v5_turn_and_shoot_{RUN_ID}"
OUTPUT.mkdir(parents=True, exist_ok=True)
TELEMETRY = OUTPUT / "telemetry.jsonl"
RESULT = OUTPUT / "result.json"

# grSim replacement packets use metres and degrees.
CASES = (
    {"name": "stationary_500mm", "ball": (0.5, 0.0, 0.0, 0.0), "robot": (0.0, 0.0, 0.0)},
    {"name": "head_on_2mps", "ball": (1.0, 0.0, -2.0, 0.0), "robot": (0.0, 0.0, 0.0)},
    {"name": "crossing_slow", "ball": (0.082, 0.8, 0.0, -1.0), "robot": (0.0, 0.0, 0.0)},
    {"name": "crossing_fast", "ball": (0.082, 1.0, 0.0, -2.0), "robot": (0.0, 0.0, 0.0)},
    {"name": "crossing_fast_turned", "ball": (0.082, 1.0, 0.0, -2.0), "robot": (0.0, 0.0, 90.0)},
)
THRESHOLDS_MM = (200, 250, 300)
MAX_ACQUIRE_SECONDS = 6.0
MAX_SHOOT_SECONDS = 5.0
MAX_FLIGHT_SECONDS = 3.0
SETTLE_SECONDS = 1.2
SETTLE_TIMEOUT = 5.0
COOLDOWN_SECONDS = 0.4
CAPTURE_CONFIRM_FRAMES = 3
BALL_RADIUS = 50.0


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
    bx, by, vx, vy = case["ball"]
    payload = _message(1, _double(1, bx) + _double(2, by) + _double(3, vx) + _double(4, vy))
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.sendto(_message(2, payload), ("127.0.0.1", 20011))


class GetBallV5TurnAndShootState(State):
    def __init__(self):
        super().__init__()
        if sys.version_info[:3] != (3, 12, 10):
            raise RuntimeError(f"Test requires Python 3.12.10, got {sys.version.split()[0]}")
        self.trials = [(case_index, threshold) for case_index in range(len(CASES))
                       for threshold in THRESHOLDS_MM]
        self.trial_index = -1
        self.phase = "start"
        self.phase_started = 0.0
        self.acquire_started = 0.0
        self.shoot_started = 0.0
        self.flight_started = 0.0
        self.frame = 0
        self.confirm_frames = 0
        self.samples = 0
        self.min_distance = float("inf")
        self.initial_sample = None
        self.final_sample = None
        self.transition = None
        self.kick = None
        self.shot_projection = None
        self.previous_ball = None
        self.goal_result = None
        self.results = []
        self.log = TELEMETRY.open("w", encoding="utf-8", buffering=1)
        self.log.write(json.dumps({
            "event": "start", "run_id": RUN_ID, "python": sys.version,
            "started_at": datetime.now().astimezone().isoformat(),
            "cases": [c["name"] for c in CASES],
            "scenarios": CASES,
            "scenario_units": {"positions": "metres in scene config; millimetres in vision samples",
                               "angles": "degrees in scene config; radians in vision samples",
                               "velocity": "m/s in scene config; mm/s in vision samples"},
            "thresholds_mm": THRESHOLDS_MM, "confirm_frames": CAPTURE_CONFIRM_FRAMES,
            "planned_trials": len(self.trials),
            "target": "their_goal_center", "infrared_used": False,
            "dribbler_command": 3, "power_level": "P.HIGH",
        }) + "\n")
        print(f"[GetBallV5TurnAndShoot] START {OUTPUT}", flush=True)

    def _stop_tasks(self):
        kickStatus.clearAll()
        for number in (0, 1, 2):
            C.setDribbleCommand(number, 0)
        return {
            "A": Task(Skill.Stop(), fixedNumber=0),
            "B": Task(Skill.Stop(), fixedNumber=1),
            "C": Task(Skill.Stop(), fixedNumber=2),
        }

    def _begin_trial(self, now):
        self.trial_index += 1
        if self.trial_index >= len(self.trials):
            self.phase = "done"
            self._write_result()
            print("[GetBallV5TurnAndShoot] DONE", flush=True)
            return
        self.case_index, self.threshold = self.trials[self.trial_index]
        self.case = CASES[self.case_index]
        self.phase = "settling"
        self.phase_started = now
        self.acquire_started = 0.0
        self.shoot_started = 0.0
        self.flight_started = 0.0
        self.confirm_frames = 0
        self.samples = 0
        self.min_distance = float("inf")
        self.initial_sample = None
        self.final_sample = None
        self.transition = None
        self.kick = None
        self.shot_projection = None
        self.previous_ball = None
        self.goal_result = None
        self.turn_skill = None
        self.shot_power = 0.0
        _replace_scene(self.case)
        bx, by, bvx, bvy = self.case["ball"]
        rx, ry, heading = self.case["robot"]
        self.log.write(json.dumps({
            "event": "reset", "trial_index": self.trial_index,
            "case": self.case["name"], "threshold_mm": self.threshold,
            "scene": {
                "ball_m": [bx, by], "ball_velocity_m_s": [bvx, bvy],
                "blue_robot0_m": [rx, ry], "blue_robot0_heading_deg": heading,
                "yellow_goalie0_m": [4.2, 2.0],
            },
        }) + "\n")
        print(f"[GetBallV5TurnAndShoot] RESET {self.case['name']} / {self.threshold}mm", flush=True)

    def _sample(self, now):
        robot, ball = Player.Pos(0), Ball.pos()
        heading = Player.direction(0)
        dx, dy = ball.x() - robot.x(), ball.y() - robot.y()
        forward = dx * math.cos(heading) + dy * math.sin(heading)
        sideways = -dx * math.sin(heading) + dy * math.cos(heading)
        distance = math.hypot(dx, dy)
        velocity = Ball.vel()
        row = {
            "event": "sample", "trial_index": self.trial_index,
            "case": self.case["name"], "threshold_mm": self.threshold,
            "phase": self.phase, "t": round(now - self.acquire_started, 4) if self.acquire_started else 0.0,
            "cycle": int(vision.getCycle()), "valid": bool(Ball.valid() and Player.isValid(0)),
            "robot": [robot.x(), robot.y()], "heading": heading,
            "ball": [ball.x(), ball.y()], "ball_velocity": [velocity.x(), velocity.y()],
            "ball_speed_mm_s": Ball.velMod(),
            "distance": distance, "forward": forward, "sideways": sideways,
        }
        self.min_distance = min(self.min_distance, distance)
        self.samples += 1
        if self.initial_sample is None:
            self.initial_sample = row
        self.final_sample = row
        self.log.write(json.dumps(row) + "\n")
        self.previous_ball = (ball.x(), ball.y())
        return row

    def _turn_task(self):
        def execute(number):
            C.setDribbleCommand(number, 3)
            result = self.turn_skill(number)
            if self.kick is None and kickStatus.needKick(number):
                now = time.monotonic()
                ball, velocity = Ball.pos(), Ball.vel()
                target_angle = math.atan2(self.target.y() - ball.y(), self.target.x() - ball.x())
                angle_error = abs((target_angle - Player.direction(number) + math.pi) % (2 * math.pi) - math.pi)
                self.kick = {
                    "t_since_transition": round(now - self.shoot_started, 4),
                    "power": kickStatus.getKickPower(number),
                    "ball": [ball.x(), ball.y()],
                    "ball_velocity_before_release": [velocity.x(), velocity.y()],
                    "heading_error_to_target_rad": angle_error,
                }
                self.flight_started = now
                self.phase = "flight"
                self.log.write(json.dumps({"event": "kick", "trial_index": self.trial_index,
                                           "case": self.case["name"],
                                           "threshold_mm": self.threshold, **self.kick}) + "\n")
                print(f"[GetBallV5TurnAndShoot] KICK {self.case['name']} / {self.threshold}mm", flush=True)
            return result

        return {"A": Task((execute, lambda n: self.turn_match_pos(n)), fixedNumber=0,
                           description="TurnAndShoot test"),
                "B": Task(Skill.Stop(), fixedNumber=1),
                "C": Task(Skill.Stop(), fixedNumber=2)}

    def _finish_trial(self, now, outcome):
        elapsed = now - self.acquire_started if self.acquire_started else now - self.phase_started
        result = {
            "trial_index": self.trial_index,
            "case": self.case["name"], "threshold_mm": self.threshold, "outcome": outcome,
            "transitioned": self.transition is not None,
            "transition": self.transition,
            "kick": self.kick,
            "shot_projection": self.shot_projection,
            "goal_result": self.goal_result,
            "min_distance_mm": round(self.min_distance, 2) if math.isfinite(self.min_distance) else None,
            "elapsed_s": round(elapsed, 4), "samples": self.samples,
            "initial": self.initial_sample, "final": self.final_sample,
        }
        self.results.append(result)
        self.log.write(json.dumps({"event": "result", **result}) + "\n")
        self.phase = "cooldown"
        self.phase_started = now
        print("[GetBallV5TurnAndShoot] RESULT " + json.dumps(result), flush=True)

    def _write_result(self):
        by_threshold = {}
        for threshold in THRESHOLDS_MM:
            trials = [r for r in self.results if r["threshold_mm"] == threshold]
            transitioned = [r for r in trials if r["transitioned"]]
            kicked = [r for r in trials if r["kick"] is not None]
            goals = [r for r in trials if r["goal_result"] and r["goal_result"]["scored"]]
            delays = [r["kick"]["t_since_transition"] for r in kicked]
            transition_speeds = [r["transition"]["ball_speed_mm_s"] for r in transitioned]
            by_threshold[str(threshold)] = {
                "trials": len(trials), "transitions": len(transitioned),
                "handoff_rate": len(transitioned) / len(trials) if trials else None,
                "kick_commands": len(kicked), "goals": len(goals),
                "mean_transition_ball_speed_mm_s": (sum(transition_speeds) / len(transition_speeds)
                                                     if transition_speeds else None),
                "mean_transition_to_kick_s": sum(delays) / len(delays) if delays else None,
                "outcomes": {name: sum(r["outcome"] == name for r in trials)
                             for name in sorted({r["outcome"] for r in trials})},
            }
        payload = {
            "run_id": RUN_ID,
            "skill_sequence": ["GetBallV5", "TurnAndShoot"],
            "scenarios": CASES,
            "thresholds_mm": THRESHOLDS_MM,
            "threshold_condition": "center_distance <= threshold for 3 consecutive valid frames",
            "acquire_timeout_s": MAX_ACQUIRE_SECONDS,
            "shoot_timeout_s": MAX_SHOOT_SECONDS,
            "flight_observation_s": MAX_FLIGHT_SECONDS,
            "target": "their_goal_center",
            "power": "evalPower(Ball.pos(), target, P.HIGH)",
            "infrared_used": False,
            "planned_trials": len(self.trials),
            "completed_trials": len(self.results),
            "by_threshold": by_threshold,
            "results": self.results,
        }
        result_tmp = RESULT.with_suffix(".json.tmp")
        result_tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        result_tmp.replace(RESULT)
        self.log.close()
        try:
            from Play.Test.AnalyzeGetBallV5TurnAndShoot import analyze
            report, analysis_path, csv_path, markdown_path = analyze(TELEMETRY)
            print(f"[GetBallV5TurnAndShoot] ANALYSIS {analysis_path} / {csv_path} / {markdown_path} "
                  f"({report['completed_trials']}/{report['planned_trials']} trials)", flush=True)
        except Exception as error:
            print(f"[GetBallV5TurnAndShoot] ANALYSIS_FAILED {error}", flush=True)

    def getTasks(self):
        if not Global.isSimulation or Global.isYellow:
            print("[GetBallV5TurnAndShoot] ABORT: requires blue simulation strategy", flush=True)
            self.phase = "done"
            if not self.log.closed:
                self.log.write(json.dumps({"event": "abort", "simulation": Global.isSimulation,
                                           "yellow": Global.isYellow}) + "\n")
                self._write_result()
            return self._stop_tasks()

        now = time.monotonic()
        self.frame += 1
        if self.phase == "start":
            self._begin_trial(now)
            return self._stop_tasks()
        if self.phase == "settling":
            if now - self.phase_started < SETTLE_SECONDS:
                return self._stop_tasks()
            if not (Ball.valid() and Player.isValid(0)):
                if now - self.phase_started >= SETTLE_TIMEOUT:
                    self.acquire_started = now
                    self._finish_trial(now, "vision_unavailable")
                return self._stop_tasks()
            self.acquire_started = now
            _launch_ball_velocity(self.case)
            self.phase = "acquire"
            print(f"[GetBallV5TurnAndShoot] ACQUIRE {self.case['name']} / {self.threshold}mm", flush=True)

        if self.phase == "cooldown":
            if now - self.phase_started >= COOLDOWN_SECONDS:
                self._begin_trial(now)
            return self._stop_tasks()
        if self.phase == "done":
            return self._stop_tasks()

        if self.phase in ("acquire", "shooting", "flight"):
            if not (Ball.valid() and Player.isValid(0)):
                self._finish_trial(now, "vision_lost")
                return self._stop_tasks()
            previous_ball = self.previous_ball
            row = self._sample(now)
            if C.InTheirPenaltyArea(Player.Pos(0), Params.playerRadius + 70):
                self._finish_trial(now, "opponent_penalty_guard")
                self.phase = "done"
                self.log.write(json.dumps({"event": "aborted", "trial_index": self.trial_index,
                                           "reason": "opponent_penalty_guard",
                                           "case": self.case["name"], "threshold_mm": self.threshold}) + "\n")
                self._write_result()
                return self._stop_tasks()

            if self.phase == "acquire":
                self.confirm_frames = self.confirm_frames + 1 if row["distance"] <= self.threshold else 0
                if self.confirm_frames >= CAPTURE_CONFIRM_FRAMES:
                    ball = Ball.pos()
                    self.target = C.CGeoPoint(Params.pitchLength / 2, 0)
                    self.transition = {
                        "t_since_acquire_s": round(now - self.acquire_started, 4),
                        "distance_mm": row["distance"], "ball_speed_mm_s": Ball.velMod(),
                        "forward_mm": row["forward"], "sideways_mm": row["sideways"],
                        "heading_error_to_center_rad": abs((math.atan2(self.target.y() - ball.y(),
                            self.target.x() - ball.x()) - Player.direction(0) + math.pi) % (2 * math.pi) - math.pi),
                    }
                    self.shot_power = evalPower(Ball.pos(), self.target, P.HIGH)
                    self.turn_skill, self.turn_match_pos = Skill.TurnAndShoot(
                        target=self.target, power=self.shot_power
                    )
                    self.shoot_started = now
                    self.phase = "shooting"
                    self.log.write(json.dumps({"event": "transition", "trial_index": self.trial_index,
                                               "case": self.case["name"],
                                               "threshold_mm": self.threshold, **self.transition}) + "\n")
                    print(f"[GetBallV5TurnAndShoot] TRANSITION {self.case['name']} / {self.threshold}mm", flush=True)
                    return self._turn_task()
                if now - self.acquire_started >= MAX_ACQUIRE_SECONDS:
                    self._finish_trial(now, "acquire_timeout")
                    return self._stop_tasks()
                direction = math.radians(self.case["robot"][2])
                v5_cpp, match_pos = Skill.GetBallV5(direction, ifIntercept=True)

                def execute_v5(number):
                    C.setDribbleCommand(number, 3)
                    return v5_cpp(number)

                return {"A": Task((execute_v5, match_pos), fixedNumber=0,
                                   description="GetBallV5 acquire"),
                        "B": Task(Skill.Stop(), fixedNumber=1),
                        "C": Task(Skill.Stop(), fixedNumber=2)}

            if self.phase == "shooting":
                if now - self.shoot_started >= MAX_SHOOT_SECONDS:
                    self._finish_trial(now, "turnandshoot_timeout")
                    return self._stop_tasks()
                return self._turn_task()

            if self.phase == "flight":
                if self.kick is None:
                    self._finish_trial(now, "kick_status_missing")
                    return self._stop_tasks()
                velocity = Ball.vel()
                goal_x = Params.pitchLength / 2
                if self.shot_projection is None and velocity.x() > 200:
                    projected_y = Ball.posY() + (goal_x - Ball.posX()) * velocity.y() / velocity.x()
                    self.shot_projection = {
                        "ball_speed_mm_s": Ball.velMod(), "goal_line_y_mm": projected_y,
                        "ball": [Ball.posX(), Ball.posY()],
                        "ball_velocity_mm_s": [velocity.x(), velocity.y()],
                        "direction_deg": math.degrees(math.atan2(velocity.y(), velocity.x())),
                        "on_target": abs(projected_y) <= Params.goalWidth / 2 - BALL_RADIUS,
                    }
                    self.log.write(json.dumps({"event": "trajectory", "trial_index": self.trial_index,
                                               "case": self.case["name"],
                                               "threshold_mm": self.threshold, **self.shot_projection}) + "\n")
                current_ball = (Ball.posX(), Ball.posY())
                if previous_ball is not None and previous_ball[0] < goal_x <= current_ball[0]:
                    ratio = (goal_x - previous_ball[0]) / max(1e-9, current_ball[0] - previous_ball[0])
                    crossing_y = previous_ball[1] + ratio * (current_ball[1] - previous_ball[1])
                    scored = abs(crossing_y) <= Params.goalWidth / 2 - BALL_RADIUS
                    self.goal_result = {"scored": scored, "goal_line_y_mm": crossing_y}
                    self._finish_trial(now, "goal" if scored else "shot_missed_goal")
                    return self._stop_tasks()
                if abs(Ball.posY()) > Params.pitchWidth / 2 or Ball.posX() > goal_x + Params.goalDepth:
                    self.goal_result = {"scored": False, "reason": "out_of_field"}
                    self._finish_trial(now, "shot_out_of_field")
                    return self._stop_tasks()
                if now - self.flight_started >= MAX_FLIGHT_SECONDS:
                    self._finish_trial(now, "shot_no_goal_before_timeout")
                    return self._stop_tasks()
                return self._stop_tasks()

        return self._stop_tasks()

    def getMatchString(self):
        return ""

    def transFunction(self):
        return ""


@declare_state_machine(GetBallV5TurnAndShootState)
class TestGetBallV5TurnAndShoot(StateMachine):
    pass
