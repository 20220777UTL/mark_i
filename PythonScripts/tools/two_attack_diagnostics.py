"""Read-only chip trace report and curve fingerprint; never commands a robot."""
import argparse
import json
import math
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from Play.Normal.AttackFeedback import curve_fingerprint


def report(rows):
    attempts, current = [], None
    fallbacks = {}
    for row in rows:
        kind = row.get('type')
        if kind == 'return_mode' and row.get('reason'):
            reason = row['reason']
            fallbacks[reason] = fallbacks.get(reason, 0) + 1
        if kind == 'chip_start':
            current = dict(environment=row['environment'], source=row['source'],
                target=row['plan']['landing'], contact=row['plan']['contact'],
                curve_fingerprint=row['curve_fingerprint'], first_landing=None,
                flight_seconds=None, landing_error_mm=None, contact_speed=None,
                after_landing_mm=None, observation_gap=False)
            attempts.append(current)
        elif current is not None:
            if kind == 'frame' and row.get('valid') is False:
                current['observation_gap'] = True
            elif kind == 'chip_landing_observed' and current['first_landing'] is None:
                current.update(first_landing=row['ball'], flight_seconds=row['flight_seconds'],
                               landing_error_mm=row['landing_error_mm'])
                current['measured_flight_distance_mm'] = math.dist(current['source'], row['ball'])
            elif kind == 'chip_contact':
                current.update(contact_speed=row['speed'], after_landing_mm=row['after_landing_mm'])
                current = None
            elif kind == 'chip_aborted':
                current['aborted_reason'] = row['reason']
                current = None
            elif kind == 'state' and row.get('state') in ('FirstPass', 'Done'):
                current = None
    return {'attempts': attempts, 'fallbacks': fallbacks,
            'note': 'Observed first low-height sample; gaps/bounces require inspection. No automatic calibration approval.'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    fingerprint = commands.add_parser('fingerprint', help='Print chip-curve fingerprint for calibration')
    fingerprint.add_argument('curve_file', type=Path)
    fingerprint.add_argument('--power-max', type=float, required=True)
    trace = commands.add_parser('report', help='Summarize a SRC_TWO_ATTACK_TELEMETRY JSONL file')
    trace.add_argument('trace_file', type=Path)
    args = parser.parse_args()
    if args.command == 'fingerprint':
        payload = json.loads(args.curve_file.read_text(encoding='utf-8-sig'))
        print(curve_fingerprint(payload, args.power_max))
    else:
        with args.trace_file.open(encoding='utf-8-sig') as stream:
            print(json.dumps(report(json.loads(line) for line in stream if line.strip()), indent=2))


if __name__ == '__main__':
    main()
