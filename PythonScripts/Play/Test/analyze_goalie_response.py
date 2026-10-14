"""Offline analysis for TestGoalieResponse telemetry (Python standard library only)."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import statistics
import sys


def _finite(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _percentile(values, q):
    clean = sorted(value for value in (_finite(v) for v in values) if value is not None)
    if not clean:
        return None
    position = (len(clean) - 1) * q
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return clean[lower]
    return clean[lower] * (upper - position) + clean[upper] * (position - lower)


def _median(values):
    clean = [value for value in (_finite(v) for v in values) if value is not None]
    return statistics.median(clean) if clean else None


def _vector(value):
    if not isinstance(value, (list, tuple)) or len(value) < 2:
        return None
    x, y = _finite(value[0]), _finite(value[1])
    return [x, y] if x is not None and y is not None else None


def _smooth_vectors(frames, window):
    half = window // 2
    vectors = [_vector(frame.get("goalie_velocity")) for frame in frames]
    result = []
    for index in range(len(frames)):
        nearby = [vectors[j] for j in range(max(0, index - half), min(len(frames), index + half + 1))
                  if vectors[j] is not None]
        if not nearby:
            result.append(None)
        else:
            result.append([statistics.median(v[axis] for v in nearby) for axis in (0, 1)])
    return result


def _derive_acceleration(frames, velocities):
    """Central-difference the smoothed velocity using observed timestamps."""
    derived = [None] * len(frames)
    for index in range(1, len(frames) - 1):
        before, after = velocities[index - 1], velocities[index + 1]
        t0, t1 = _finite(frames[index - 1].get("t")), _finite(frames[index + 1].get("t"))
        if before is None or after is None or t0 is None or t1 is None or t1 - t0 <= 1e-5:
            continue
        acceleration = [(after[axis] - before[axis]) / (t1 - t0) for axis in (0, 1)]
        speed = math.hypot(*velocities[index]) if velocities[index] else 0.0
        tangential = (sum(velocities[index][axis] * acceleration[axis] for axis in (0, 1)) / speed
                      if speed >= 150.0 else None)
        derived[index] = {
            "magnitude": math.hypot(*acceleration),
            "tangential": tangential,
        }
    return derived


def _movement_start(frames, baseline, speed_threshold, distance_threshold, confirm_frames):
    if baseline is None:
        return None
    count = 0
    first_time = None
    for frame in frames:
        position = _vector(frame.get("goalie"))
        speed = _finite(frame.get("goalie_speed"))
        timestamp = _finite(frame.get("t"))
        if position is None or timestamp is None:
            count, first_time = 0, None
            continue
        displacement = math.dist(position, baseline)
        moving = ((speed is not None and speed >= speed_threshold)
                  or displacement >= distance_threshold)
        if moving:
            if count == 0:
                first_time = timestamp
            count += 1
            if count >= confirm_frames:
                return first_time
        else:
            count, first_time = 0, None
    return None


def _analyze_trial(index, frames, spec, result, options):
    frames = sorted(frames, key=lambda row: _finite(row.get("t")) or 0.0)
    valid_positions = [_vector(frame.get("goalie")) for frame in frames]
    valid_positions = [position for position in valid_positions if position is not None]
    baseline = _vector(result.get("initial_goalie_position_mm")) or (valid_positions[0] if valid_positions else None)
    onset = _movement_start(
        frames, baseline, options.speed_threshold, options.distance_threshold, options.confirm_frames
    )
    smooth_velocity = _smooth_vectors(frames, options.smooth_window)
    acceleration = _derive_acceleration(frames, smooth_velocity)

    times = [_finite(frame.get("t")) for frame in frames]
    post_onset = [i for i, t in enumerate(times) if t is not None and (onset is None or t >= onset)]
    speed_samples = []
    ball_samples_early = []
    ball_samples_all = []
    target_errors = []
    for i in post_onset:
        speed = _finite(frames[i].get("goalie_speed"))
        if speed is None and smooth_velocity[i] is not None:
            speed = math.hypot(*smooth_velocity[i])
        if speed is not None:
            speed_samples.append(speed)
    for frame, timestamp in zip(frames, times):
        ball_speed = _finite(frame.get("ball_speed"))
        if ball_speed is not None:
            ball_samples_all.append(ball_speed)
            if timestamp is not None and timestamp <= 0.20:
                ball_samples_early.append(ball_speed)
        error = _finite(frame.get("target_error_mm"))
        if error is not None:
            target_errors.append(error)

    early_acceleration = []
    all_acceleration = []
    deceleration = []
    for i, metric in enumerate(acceleration):
        if metric is None or times[i] is None or (onset is not None and times[i] < onset):
            continue
        all_acceleration.append(metric["magnitude"])
        if onset is not None and times[i] <= onset + options.accel_window_s:
            early_acceleration.append(metric["magnitude"])
        if metric["tangential"] is not None and metric["tangential"] < 0:
            deceleration.append(-metric["tangential"])

    return {
        "trial_index": index,
        "start_x_mm": spec.get("start_x_mm"),
        "target_fraction": spec.get("target_fraction"),
        "target_y_mm": spec.get("target_y_mm"),
        "requested_speed_m_s": spec.get("speed_m_s"),
        "repeat": spec.get("repeat"),
        "outcome": result.get("outcome"),
        "frame_count": len(frames),
        "movement_start_logged_s": result.get("movement_start_s"),
        "movement_start_smoothed_rule_s": onset,
        "actual_ball_speed_first_200ms_mm_s": _median(ball_samples_early),
        "actual_ball_speed_peak_mm_s": max(ball_samples_all) if ball_samples_all else None,
        "goalie_speed_peak_after_onset_mm_s": max(speed_samples) if speed_samples else None,
        "goalie_speed_p95_after_onset_mm_s": _percentile(speed_samples, 0.95),
        "goalie_accel_p95_first_window_mm_s2": _percentile(early_acceleration, 0.95),
        "goalie_accel_p95_after_onset_mm_s2": _percentile(all_acceleration, 0.95),
        "goalie_decel_p95_after_onset_mm_s2": _percentile(deceleration, 0.95),
        "ellipse_target_error_p95_mm": _percentile(target_errors, 0.95),
        "goal_line_y_mm": (result.get("goal_line_crossing") or {}).get("ball_y_mm"),
        "goalie_at_goal_line_mm": _vector(
            (result.get("goal_line_crossing") or {}).get("goalie_position_mm")
        ),
    }


def _aggregate(rows, keys):
    groups = {}
    for row in rows:
        key = tuple(row.get(field) for field in keys)
        groups.setdefault(key, []).append(row)
    summaries = []
    value_fields = (
        "actual_ball_speed_first_200ms_mm_s",
        "movement_start_smoothed_rule_s",
        "goalie_speed_p95_after_onset_mm_s",
        "goalie_accel_p95_first_window_mm_s2",
        "goalie_decel_p95_after_onset_mm_s2",
        "ellipse_target_error_p95_mm",
    )
    for key in sorted(groups, key=lambda item: tuple(str(value) for value in item)):
        members = groups[key]
        summary = {field: value for field, value in zip(keys, key)}
        summary["trials"] = len(members)
        for field in value_fields:
            values = [row.get(field) for row in members]
            summary[field + "_median"] = _median(values)
            summary[field + "_p95"] = _percentile(values, 0.95)
        summaries.append(summary)
    return summaries


def _load_telemetry(path):
    events = []
    malformed = 0
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    has_incomplete_tail = bool(text) and not text.endswith(("\n", "\r"))
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            if has_incomplete_tail and line_number == len(lines):
                malformed += 1
            else:
                raise ValueError(f"Malformed JSON at {path}:{line_number}") from exc
    return events, malformed


def analyze(telemetry_path, options):
    events, malformed = _load_telemetry(telemetry_path)
    specs, results, frames = {}, {}, {}
    metadata = {}
    for event in events:
        kind = event.get("event")
        index = event.get("trial_index")
        if kind == "start":
            metadata = event
        elif kind == "reset" and index is not None:
            specs[index] = event.get("trial", {})
        elif kind == "result" and index is not None:
            results[index] = event
        elif kind == "frame" and index is not None:
            frames.setdefault(index, []).append(event)
    if not frames:
        raise ValueError("No frame samples found; run the goalie test to completion before analysis.")

    indices = sorted(set(frames) | set(specs) | set(results))
    trial_rows = []
    for index in indices:
        trial_rows.append(_analyze_trial(index, frames.get(index, []), specs.get(index, {}),
                                         results.get(index, {}), options))
    by_speed = _aggregate(trial_rows, ["requested_speed_m_s"])
    by_speed_and_target = _aggregate(trial_rows, ["requested_speed_m_s", "target_fraction"])
    completed = sum(1 for row in trial_rows if row.get("outcome"))
    report = {
        "source": str(telemetry_path.resolve()),
        "run_id": metadata.get("run_id"),
        "python": metadata.get("python"),
        "planned_trials": metadata.get("planned_trials"),
        "trials_with_frames": len(frames),
        "completed_trials": completed,
        "malformed_trailing_lines": malformed,
        "smoothing": {
            "method": "centered component-wise median",
            "window_frames": options.smooth_window,
            "acceleration": "central difference of smoothed velocity and observed timestamps",
        },
        "thresholds": {
            "movement_speed_mm_s": options.speed_threshold,
            "movement_distance_mm": options.distance_threshold,
            "consecutive_frames": options.confirm_frames,
            "early_acceleration_window_s": options.accel_window_s,
        },
        "trial_metrics": trial_rows,
        "by_requested_speed": by_speed,
        "by_requested_speed_and_target": by_speed_and_target,
        "interpretation_note": (
            "Requested ball speeds are condition labels. Use actual_ball_speed_first_200ms_mm_s "
            "to decide which velocity range was physically achieved. Acceleration values are "
            "smoothed estimates; the one-frame raw peak is intentionally excluded."
        ),
    }
    return report


def _write_csv(path, rows):
    if not rows:
        return
    columns = list(dict.fromkeys(key for row in rows for key in row))
    with path.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_markdown(path, report):
    lines = [
        "# Goalie response analysis",
        "",
        f"- Run: `{report.get('run_id')}`",
        f"- Trials with frames: {report['trials_with_frames']}; completed: {report['completed_trials']} / {report.get('planned_trials')}",
        f"- Velocity smoothing: centered median, {report['smoothing']['window_frames']} frames.",
        "- Requested speed labels are not treated as measured speeds.",
        "",
        "| Requested speed (m/s) | Trials | Actual ball speed median (mm/s) | Move latency median / p95 (s) | Goalie speed p95 median (mm/s) | Early acceleration p95 median (mm/s²) |",
        "|---:|---:|---:|---:|---:|---:|",
    ]
    for group in report["by_requested_speed"]:
        latency = group.get("movement_start_smoothed_rule_s_median")
        latency_p95 = group.get("movement_start_smoothed_rule_s_p95")
        lines.append(
            f"| {group.get('requested_speed_m_s')} | {group['trials']} | "
            f"{_fmt(group.get('actual_ball_speed_first_200ms_mm_s_median'))} | "
            f"{_fmt(latency)} / {_fmt(latency_p95)} | "
            f"{_fmt(group.get('goalie_speed_p95_after_onset_mm_s_median'))} | "
            f"{_fmt(group.get('goalie_accel_p95_first_window_mm_s2_median'))} |"
        )
    lines.extend([
        "",
        "Acceleration is derived from smoothed velocity and real frame timestamps. Review `trial_metrics.csv` and `by_requested_speed_and_target` before selecting controller limits; missing latency or braking samples mean the current trajectories did not identify that parameter.",
        "",
    ])
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt(value):
    return "—" if value is None else f"{value:.1f}"


def main(argv=None):
    parser = argparse.ArgumentParser(description="Summarize GoalieOnly movement-response telemetry.")
    parser.add_argument("input", type=Path,
                        help="run folder, telemetry.jsonl, or results.json from a completed run")
    parser.add_argument("--output", type=Path, help="output directory (default: input run folder)")
    parser.add_argument("--smooth-window", type=int, default=5, help="odd median-filter window in frames")
    parser.add_argument("--speed-threshold", type=float, default=100.0, help="movement onset threshold in mm/s")
    parser.add_argument("--distance-threshold", type=float, default=20.0, help="movement onset threshold in mm")
    parser.add_argument("--confirm-frames", type=int, default=2)
    parser.add_argument("--accel-window-s", type=float, default=0.5,
                        help="time after movement onset used for launch acceleration estimate")
    args = parser.parse_args(argv)
    if args.smooth_window < 3 or args.smooth_window % 2 == 0:
        parser.error("--smooth-window must be an odd integer >= 3")
    if args.confirm_frames < 1 or args.accel_window_s <= 0:
        parser.error("--confirm-frames and --accel-window-s must be positive")

    source = args.input
    if source.is_dir():
        telemetry = source / "telemetry.jsonl"
    elif source.name.lower() == "results.json":
        telemetry = source.with_name("telemetry.jsonl")
    else:
        telemetry = source
    if not telemetry.is_file():
        parser.error(f"telemetry file not found: {telemetry}")
    output = args.output or telemetry.parent
    output.mkdir(parents=True, exist_ok=True)

    try:
        report = analyze(telemetry, args)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        parser.error(str(exc))
    (output / "analysis.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8"
    )
    _write_csv(output / "trial_metrics.csv", report["trial_metrics"])
    _write_csv(output / "speed_summary.csv", report["by_requested_speed"])
    _write_csv(output / "speed_target_summary.csv", report["by_requested_speed_and_target"])
    _write_markdown(output / "analysis_summary.md", report)
    print(f"Analyzed {report['trials_with_frames']} trials with frame data; "
          f"{report['completed_trials']} completed.")
    print(f"Summary: {output / 'analysis_summary.md'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
