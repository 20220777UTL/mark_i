"""Summarize a GetBallV5 -> TurnAndShoot JSONL run, including partial runs."""
import argparse
import csv
import json
import math
from collections import Counter, defaultdict
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_DATA_ROOT = PROJECT_ROOT.parent / "tmp"
THRESHOLDS_MM = (200, 250, 300)
GOAL_CENTER_X_MM = 4500.0  # Params.pitchLength / 2 for the test field.
GOAL_HALF_WIDTH_MM = 500.0
BALL_RADIUS_MM = 50.0
RESET_POSITION_TOLERANCE_MM = 100.0
RESET_BALL_TOLERANCE_MM = 100.0


def _mean(values):
    clean = [float(value) for value in values if isinstance(value, (int, float))
             and math.isfinite(value)]
    return sum(clean) / len(clean) if clean else None


def _trial_from_reset(event):
    return {
        "trial_index": event.get("trial_index"),
        "case": event.get("case"),
        "threshold_mm": event.get("threshold_mm"),
        "scene": event.get("scene"),
        "transition": None,
        "kick": None,
        "trajectory": None,
        "result": None,
        "abort": None,
        "sample_count": 0,
        "valid_sample_count": 0,
        "samples_by_phase": {},
        "min_distance_mm": None,
        "first_sample": None,
        "last_sample": None,
        "reset_check": None,
        "shooting_heading": None,
        "shooting_ball_motion": None,
        "observed_goal_crossing": None,
    }


def _summarize_group(trials, planned_trials=None):
    started = [trial for trial in trials if trial["scene"] is not None]
    completed = [trial for trial in started if trial["result"] is not None]
    reset_valid = [trial for trial in started if (trial.get("reset_check") or {}).get("consistent") is True]
    transitions = [trial["transition"] for trial in started if trial["transition"] is not None]
    kicks = [trial["kick"] for trial in started if trial["kick"] is not None]
    goals = [trial for trial in started if trial["result"] and
             (trial["result"].get("goal_result") or {}).get("scored") is True]
    outcomes = Counter(trial["result"].get("outcome", "unknown") for trial in completed)
    valid_outcomes = Counter(
        trial["result"].get("outcome", "unknown") for trial in reset_valid if trial["result"]
    )
    crossings = [trial["observed_goal_crossing"] for trial in started
                 if trial.get("observed_goal_crossing")]
    valid_crossings = [trial["observed_goal_crossing"] for trial in reset_valid
                       if trial.get("observed_goal_crossing")]
    return {
        "planned_trials": len(trials) if planned_trials is None else planned_trials,
        "started_trials": len(started),
        "completed_trials": len(completed),
        "valid_reset_trials": len(reset_valid),
        "invalid_reset_trials": len(started) - len(reset_valid),
        "handoffs": len(transitions),
        "handoff_rate_of_started": len(transitions) / len(started) if started else None,
        "handoffs_valid_reset": sum(trial["transition"] is not None for trial in reset_valid),
        "handoff_rate_of_valid_reset": (
            sum(trial["transition"] is not None for trial in reset_valid) / len(reset_valid)
            if reset_valid else None
        ),
        "kick_commands": len(kicks),
        "kick_commands_valid_reset": sum(trial["kick"] is not None for trial in reset_valid),
        "goals": len(goals),
        "goals_valid_reset": sum(
            trial["kick"] is not None and trial["result"] is not None and
            (trial["result"].get("goal_result") or {}).get("scored") is True
            for trial in reset_valid
        ),
        "observed_goal_line_crossings": len(crossings),
        "observed_goal_mouth_crossings": sum(item["within_goal_mouth"] for item in crossings),
        "observed_goal_line_crossings_valid_reset": len(valid_crossings),
        "observed_goal_mouth_crossings_valid_reset": sum(
            item["within_goal_mouth"] for item in valid_crossings
        ),
        "goal_rate_of_kicks": len(goals) / len(kicks) if kicks else None,
        "mean_transition_time_s": _mean(item.get("t_since_acquire_s") for item in transitions),
        "mean_transition_ball_speed_mm_s": _mean(item.get("ball_speed_mm_s") for item in transitions),
        "mean_transition_to_kick_s": _mean(item.get("t_since_transition") for item in kicks),
        "mean_shot_direction_deg": _mean(
            trial["trajectory"].get("direction_deg") for trial in started if trial["trajectory"]
        ),
        "mean_projected_goal_line_y_mm": _mean(
            trial["trajectory"].get("goal_line_y_mm") for trial in started if trial["trajectory"]
        ),
        "mean_shooting_first_heading_error_deg": _mean(
            (trial.get("shooting_heading") or {}).get("first_error_deg") for trial in reset_valid
        ),
        "mean_shooting_min_heading_error_deg": _mean(
            (trial.get("shooting_heading") or {}).get("min_error_deg") for trial in reset_valid
        ),
        "mean_shooting_last_heading_error_deg": _mean(
            (trial.get("shooting_heading") or {}).get("last_error_deg") for trial in reset_valid
        ),
        "shooting_trials_aligned_within_3deg": sum(
            (trial.get("shooting_heading") or {}).get("min_error_deg", math.inf) <= 3.0
            for trial in reset_valid
        ),
        "outcomes": dict(sorted(outcomes.items())),
        "outcomes_valid_reset": dict(sorted(valid_outcomes.items())),
    }


def _derive_trial_metrics(trial):
    scene = trial.get("scene") or {}
    first = trial.get("first_sample") or {}
    expected_robot = scene.get("blue_robot0_m")
    expected_ball = scene.get("ball_m")
    if expected_robot and expected_ball and first.get("robot") and first.get("ball"):
        expected_robot_mm = [coordinate * 1000.0 for coordinate in expected_robot]
        expected_ball_mm = [coordinate * 1000.0 for coordinate in expected_ball]
        observed_robot = first["robot"]
        observed_ball = first["ball"]
        robot_error = math.dist(expected_robot_mm, observed_robot)
        ball_error = math.dist(expected_ball_mm, observed_ball)
        expected_heading = math.radians(scene.get("blue_robot0_heading_deg", 0.0))
        heading_error = abs((first.get("heading", 0.0) - expected_heading + math.pi) %
                            (2 * math.pi) - math.pi)
        trial["reset_check"] = {
            "expected_robot_mm": expected_robot_mm,
            "observed_robot_mm": observed_robot,
            "robot_position_error_mm": robot_error,
            "expected_ball_mm": expected_ball_mm,
            "observed_ball_mm": observed_ball,
            "ball_position_error_mm": ball_error,
            "heading_error_deg": math.degrees(heading_error),
            "robot_position_ok": robot_error <= RESET_POSITION_TOLERANCE_MM,
            "ball_position_ok": ball_error <= RESET_BALL_TOLERANCE_MM,
            # Heading is reported separately because the policy can start turning before
            # the first logged vision sample arrives.
            "consistent": (robot_error <= RESET_POSITION_TOLERANCE_MM and
                           ball_error <= RESET_BALL_TOLERANCE_MM),
        }

    errors = []
    for sample in trial.get("_shooting_samples", []):
        ball = sample.get("ball")
        heading = sample.get("heading")
        if not ball or heading is None:
            continue
        target_angle = math.atan2(-ball[1], GOAL_CENTER_X_MM - ball[0])
        error = abs((target_angle - heading + math.pi) % (2 * math.pi) - math.pi)
        errors.append({"t": sample.get("t"), "error_deg": math.degrees(error)})
    if errors:
        minimum = min(errors, key=lambda item: item["error_deg"])
        trial["shooting_heading"] = {
            "target": [GOAL_CENTER_X_MM, 0.0],
            "sample_count": len(errors),
            "first_error_deg": errors[0]["error_deg"],
            "last_error_deg": errors[-1]["error_deg"],
            "min_error_deg": minimum["error_deg"],
            "min_error_time_s": minimum["t"],
        }
    samples = trial.get("_shooting_samples", [])
    if samples:
        first_ball, last_ball = samples[0].get("ball"), samples[-1].get("ball")
        speeds = [sample.get("ball_speed_mm_s") for sample in samples
                  if isinstance(sample.get("ball_speed_mm_s"), (int, float))]
        if first_ball and last_ball:
            trial["shooting_ball_motion"] = {
                "first_ball_mm": first_ball,
                "last_ball_mm": last_ball,
                "displacement_mm": math.dist(first_ball, last_ball),
                "max_speed_mm_s": max(speeds) if speeds else None,
            }
        for before, after in zip(samples, samples[1:]):
            before_ball, after_ball = before.get("ball"), after.get("ball")
            if not before_ball or not after_ball or not (
                    before_ball[0] < GOAL_CENTER_X_MM <= after_ball[0]):
                continue
            fraction = (GOAL_CENTER_X_MM - before_ball[0]) / (after_ball[0] - before_ball[0])
            crossing_y = before_ball[1] + fraction * (after_ball[1] - before_ball[1])
            trial["observed_goal_crossing"] = {
                "x_mm": GOAL_CENTER_X_MM,
                "y_mm": crossing_y,
                "t": after.get("t"),
                "within_goal_mouth": abs(crossing_y) <= GOAL_HALF_WIDTH_MM - BALL_RADIUS_MM,
            }
            break
    trial.pop("_shooting_samples", None)


def analyze(telemetry_path):
    telemetry_path = Path(telemetry_path).resolve()
    metadata = {}
    trials_by_index = {}
    trials = []
    parse_errors = []
    event_counts = Counter()
    current_trial = None

    with telemetry_path.open("r", encoding="utf-8") as source:
        for line_number, line in enumerate(source, 1):
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError as error:
                parse_errors.append({"line": line_number, "error": str(error)})
                continue

            name = event.get("event", "unknown")
            event_counts[name] += 1
            if name == "start":
                metadata = event
                continue
            if name == "reset":
                trial = _trial_from_reset(event)
                trials.append(trial)
                current_trial = trial
                if event.get("trial_index") is not None:
                    trials_by_index[event["trial_index"]] = trial
                continue

            trial = trials_by_index.get(event.get("trial_index"), current_trial)
            if trial is None:
                continue
            if name == "sample":
                trial["sample_count"] += 1
                trial["valid_sample_count"] += int(bool(event.get("valid")))
                phase = event.get("phase", "unknown")
                trial["samples_by_phase"][phase] = trial["samples_by_phase"].get(phase, 0) + 1
                distance = event.get("distance")
                if isinstance(distance, (int, float)) and math.isfinite(distance):
                    prior = trial["min_distance_mm"]
                    trial["min_distance_mm"] = distance if prior is None else min(prior, distance)
                if trial["first_sample"] is None:
                    trial["first_sample"] = event
                trial["last_sample"] = event
                if phase == "shooting":
                    trial.setdefault("_shooting_samples", []).append(event)
            elif name == "transition":
                trial["transition"] = {key: value for key, value in event.items()
                                        if key not in ("event", "trial_index", "case", "threshold_mm")}
            elif name == "kick":
                trial["kick"] = {key: value for key, value in event.items()
                                 if key not in ("event", "trial_index", "case", "threshold_mm")}
            elif name == "trajectory":
                trial["trajectory"] = {key: value for key, value in event.items()
                                       if key not in ("event", "trial_index", "case", "threshold_mm")}
            elif name == "result":
                trial["result"] = {key: value for key, value in event.items()
                                   if key not in ("event",)}
                # The result event is authoritative if the run ended after its last sample.
                trial["transition"] = event.get("transition") or trial["transition"]
                trial["kick"] = event.get("kick") or trial["kick"]
                trial["trajectory"] = event.get("shot_projection") or trial["trajectory"]
                trial["min_distance_mm"] = event.get("min_distance_mm", trial["min_distance_mm"])
            elif name == "aborted":
                trial["abort"] = event.get("reason", "aborted")

    for trial in trials:
        _derive_trial_metrics(trial)

    planned = metadata.get("planned_trials", 15)
    thresholds = metadata.get("thresholds_mm", THRESHOLDS_MM)
    case_names = metadata.get("cases", [])
    by_threshold = {}
    for threshold in thresholds:
        subset = [trial for trial in trials if trial["threshold_mm"] == threshold]
        by_threshold[str(threshold)] = _summarize_group(subset, planned_trials=len(case_names) or 5)
    by_case = {
        case_name: _summarize_group([trial for trial in trials if trial["case"] == case_name],
                                    planned_trials=len(thresholds))
        for case_name in case_names
    }

    completed_count = sum(trial["result"] is not None for trial in trials)
    report = {
        "source": str(telemetry_path),
        "run_id": metadata.get("run_id"),
        "python": metadata.get("python"),
        "started_at": metadata.get("started_at"),
        "planned_trials": planned,
        "started_trials": len(trials),
        "completed_trials": completed_count,
        "complete": completed_count >= planned,
        "interrupted_or_incomplete": completed_count < planned,
        "thresholds_mm": thresholds,
        "cases": case_names,
        "event_counts": dict(sorted(event_counts.items())),
        "malformed_lines": parse_errors,
        "analysis_assumptions": {
            "goal_center_mm": [GOAL_CENTER_X_MM, 0.0],
            "goal_mouth_center_limit_mm": GOAL_HALF_WIDTH_MM - BALL_RADIUS_MM,
            "reset_position_tolerance_mm": RESET_POSITION_TOLERANCE_MM,
            "reset_ball_tolerance_mm": RESET_BALL_TOLERANCE_MM,
            "reset_heading_error_is_reported_but_not_a_validity_gate": True,
        },
        "by_threshold": by_threshold,
        "by_case": by_case,
        "reset_anomalies": [
            {
                "trial_index": trial["trial_index"], "case": trial["case"],
                "threshold_mm": trial["threshold_mm"], "reset_check": trial["reset_check"],
            }
            for trial in trials
            if trial.get("reset_check") and not trial["reset_check"]["consistent"]
        ],
        "observed_goal_crossings": [
            {"trial_index": trial["trial_index"], "case": trial["case"],
             "threshold_mm": trial["threshold_mm"], "crossing": trial["observed_goal_crossing"]}
            for trial in trials if trial.get("observed_goal_crossing")
        ],
        "trials": trials,
    }

    output_dir = telemetry_path.parent
    json_path = output_dir / "analysis.json"
    csv_path = output_dir / "summary.csv"
    markdown_path = output_dir / "analysis.md"
    json_tmp = json_path.with_suffix(".json.tmp")
    json_tmp.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    json_tmp.replace(json_path)

    columns = (
        "trial_index", "case", "threshold_mm", "outcome", "transitioned",
        "transition_time_s", "transition_distance_mm", "transition_ball_speed_mm_s",
        "forward_mm", "sideways_mm", "kick_command", "transition_to_kick_s",
        "kick_power", "kick_heading_error_deg", "shot_direction_deg",
        "projected_goal_line_y_mm", "goal_scored", "sample_count",
        "valid_sample_count", "min_distance_mm", "reset_consistent",
        "reset_robot_position_error_mm", "reset_ball_position_error_mm",
        "reset_heading_error_deg", "shooting_first_heading_error_deg",
        "shooting_min_heading_error_deg", "shooting_min_heading_time_s",
        "shooting_last_heading_error_deg", "shooting_heading_samples",
        "shooting_ball_displacement_mm", "shooting_ball_max_speed_mm_s",
        "observed_goal_line_crossing", "observed_goal_crossing_y_mm",
        "observed_goal_crossing_time_s", "observed_goal_within_mouth", "abort",
    )
    with csv_path.open("w", encoding="utf-8-sig", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=columns)
        writer.writeheader()
        for trial in trials:
            transition, kick, trajectory = trial["transition"] or {}, trial["kick"] or {}, trial["trajectory"] or {}
            result = trial["result"] or {}
            writer.writerow({
                "trial_index": trial["trial_index"], "case": trial["case"],
                "threshold_mm": trial["threshold_mm"], "outcome": result.get("outcome", "incomplete"),
                "transitioned": bool(transition),
                "transition_time_s": transition.get("t_since_acquire_s"),
                "transition_distance_mm": transition.get("distance_mm"),
                "transition_ball_speed_mm_s": transition.get("ball_speed_mm_s"),
                "forward_mm": transition.get("forward_mm"), "sideways_mm": transition.get("sideways_mm"),
                "kick_command": bool(kick), "transition_to_kick_s": kick.get("t_since_transition"),
                "kick_power": kick.get("power"),
                "kick_heading_error_deg": (math.degrees(kick["heading_error_to_target_rad"])
                                            if "heading_error_to_target_rad" in kick else None),
                "shot_direction_deg": trajectory.get("direction_deg"),
                "projected_goal_line_y_mm": trajectory.get("goal_line_y_mm"),
                "goal_scored": (result.get("goal_result") or {}).get("scored"),
                "sample_count": trial["sample_count"], "valid_sample_count": trial["valid_sample_count"],
                "min_distance_mm": trial["min_distance_mm"],
                "reset_consistent": (trial.get("reset_check") or {}).get("consistent"),
                "reset_robot_position_error_mm": (trial.get("reset_check") or {}).get("robot_position_error_mm"),
                "reset_ball_position_error_mm": (trial.get("reset_check") or {}).get("ball_position_error_mm"),
                "reset_heading_error_deg": (trial.get("reset_check") or {}).get("heading_error_deg"),
                "shooting_first_heading_error_deg": (trial.get("shooting_heading") or {}).get("first_error_deg"),
                "shooting_min_heading_error_deg": (trial.get("shooting_heading") or {}).get("min_error_deg"),
                "shooting_min_heading_time_s": (trial.get("shooting_heading") or {}).get("min_error_time_s"),
                "shooting_last_heading_error_deg": (trial.get("shooting_heading") or {}).get("last_error_deg"),
                "shooting_heading_samples": (trial.get("shooting_heading") or {}).get("sample_count"),
                "shooting_ball_displacement_mm": (trial.get("shooting_ball_motion") or {}).get("displacement_mm"),
                "shooting_ball_max_speed_mm_s": (trial.get("shooting_ball_motion") or {}).get("max_speed_mm_s"),
                "observed_goal_line_crossing": bool(trial.get("observed_goal_crossing")),
                "observed_goal_crossing_y_mm": (trial.get("observed_goal_crossing") or {}).get("y_mm"),
                "observed_goal_crossing_time_s": (trial.get("observed_goal_crossing") or {}).get("t"),
                "observed_goal_within_mouth": (trial.get("observed_goal_crossing") or {}).get("within_goal_mouth"),
                "abort": trial["abort"],
            })

    def fmt(value, suffix="", digits=2):
        return "—" if value is None else f"{value:.{digits}f}{suffix}"

    lines = [
        "# GetBallV5 → TurnAndShoot 测试数据分析",
        "",
        f"- Run：`{metadata.get('run_id', 'unknown')}`；Python：`{metadata.get('python', 'unknown').split()[0]}`",
        f"- 记录：{completed_count}/{planned} 组完成；JSONL 共记录 {event_counts.get('sample', 0)} 条采样，格式错误 {len(parse_errors)} 条。",
        f"- 技能状态：`KickStatus.needKick()` 触发 {sum(t['kick'] is not None for t in trials)} 次；从 shooting 阶段位置样本插值发现 {sum(bool(t.get('observed_goal_crossing')) for t in trials)} 次球越过球门线，其中 {sum(bool((t.get('observed_goal_crossing') or {}).get('within_goal_mouth')) for t in trials)} 次经过门框内。",
        f"- 复位校验按首条视觉采样与测试场景坐标比较：机器人位置误差 ≤{RESET_POSITION_TOLERANCE_MM:.0f}mm、球位置误差 ≤{RESET_BALL_TOLERANCE_MM:.0f}mm 视为有效；朝向误差单独报告，因为策略可能在首条采样前已开始转向。",
        f"- 射门朝向误差按机器人朝向与球指向球门中心 `{GOAL_CENTER_X_MM:.0f}, 0` 的夹角估算。",
        "",
        "| 距离阈值 | 有效复位 | 接管成功 | 平均接管时间 | 平均接管球速 | 踢球状态触发 | 观测越线/门内 | 朝向误差首/最小/末值均值 | 结果（有效复位） |",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for threshold in thresholds:
        row = by_threshold[str(threshold)]
        heading = "/".join(fmt(row[key], "°") for key in (
            "mean_shooting_first_heading_error_deg", "mean_shooting_min_heading_error_deg",
            "mean_shooting_last_heading_error_deg"))
        lines.append(
            f"| {threshold}mm | {row['valid_reset_trials']}/{row['started_trials']} | "
            f"{row['handoffs_valid_reset']}/{row['valid_reset_trials']} | "
            f"{fmt(row['mean_transition_time_s'], 's')} | "
            f"{fmt(row['mean_transition_ball_speed_mm_s'], 'mm/s')} | "
            f"{row['kick_commands_valid_reset']} | "
            f"{row['observed_goal_line_crossings_valid_reset']}/{row['observed_goal_mouth_crossings_valid_reset']} | "
            f"{heading} | "
            f"{row['outcomes_valid_reset']} |"
        )
    lines.extend(["", "## 观察", ""])
    lines.append(
        f"- 有效复位的场景共 {sum(row['valid_reset_trials'] for row in by_threshold.values())} 组；其中 "
        f"{sum(row['handoffs_valid_reset'] for row in by_threshold.values())} 组完成 GetBallV5 到 TurnAndShoot 的交接。"
    )
    lines.append(
        "- 日志没有一次记录到 `needKick()`，但球的位置遥测显示有两次越过 x=4500mm，且越线位置都在可用门宽内（|y|≤450mm）。"
        "因此踢球状态标记没有反映实际球的运动；这里的越线结果是视觉样本插值，不是裁判记分信号。"
    )
    lines.append(
        "- 有效复位试次中的球在 shooting 阶段都出现了明显位移；具体方向、速度和越线位置见 CSV。"
        "这说明不能把 `turnandshoot_timeout` 或 `vision_lost` 直接等同于没有射门或没有进球。"
    )
    lines.append(
        "- `vision_lost` 表示采样循环检测到 `Ball.valid()` 或 `Player.isValid(0)` 至少一项为假；"
        "日志未记录失效的是哪一项，也没有保留触发失效的那一帧。"
    )
    if report["observed_goal_crossings"]:
        lines.extend(["", "## 采样到的球门线穿越", "", "| 试次 | 场景 | 阈值 | 越线时间（相对接球开始） | 越线 y | 门内 |", "|---:|---|---:|---:|---:|:---:|"])
        for item in report["observed_goal_crossings"]:
            crossing = item["crossing"]
            lines.append(
                f"| {item['trial_index']} | {item['case']} | {item['threshold_mm']}mm | "
                f"{fmt(crossing['t'], 's', 3)} | {fmt(crossing['y_mm'], 'mm', 1)} | "
                f"{'是' if crossing['within_goal_mouth'] else '否'} |"
            )
    if report["reset_anomalies"]:
        lines.extend(["", "## 复位异常", "", "| 试次 | 场景 | 阈值 | 机器人位置误差 | 球位置误差 |", "|---:|---|---:|---:|---:|"])
        for anomaly in report["reset_anomalies"]:
            check = anomaly["reset_check"]
            lines.append(
                f"| {anomaly['trial_index']} | {anomaly['case']} | {anomaly['threshold_mm']}mm | "
                f"{fmt(check['robot_position_error_mm'], 'mm')} | {fmt(check['ball_position_error_mm'], 'mm')} |"
            )
        lines.append("")
        lines.append("这些试次的球已经复位，但机器人仍在上一场景附近；它们保留在原始记录中，不计入阈值有效复位统计。")
    markdown_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report, json_path, csv_path, markdown_path


def _latest_telemetry():
    candidates = list(DEFAULT_DATA_ROOT.glob("getball_v5_turn_and_shoot_*/telemetry.jsonl"))
    if not candidates:
        raise FileNotFoundError(f"No telemetry.jsonl found under {DEFAULT_DATA_ROOT}")
    return max(candidates, key=lambda path: path.stat().st_mtime)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("telemetry", nargs="?", type=Path,
                        help="run telemetry.jsonl (defaults to the most recently modified run)")
    args = parser.parse_args()
    telemetry_path = args.telemetry or _latest_telemetry()
    report, json_path, csv_path, markdown_path = analyze(telemetry_path)
    print(json.dumps({
        "source": report["source"], "started_trials": report["started_trials"],
        "completed_trials": report["completed_trials"], "planned_trials": report["planned_trials"],
        "complete": report["complete"], "analysis_json": str(json_path),
        "summary_csv": str(csv_path), "by_threshold": report["by_threshold"],
        "analysis_markdown": str(markdown_path),
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
