"""Environment calibration and optional native feedback; no robot commands."""
import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

from Play.Normal import AttackParams as A

CALIBRATION_FILE = Path(__file__).resolve().parents[3] / 'data/two_attack_calibration.json'


def optional(call):
    # Native feedback is not implemented on every runtime. Failure means unknown.
    try:
        return call()
    except (AttributeError, RuntimeError, TypeError, ValueError, OverflowError, KeyError):
        return None


def finite(*values):
    return all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) for v in values)


def curve_fingerprint(payload, power_max):
    """Bind calibration to the actual chip curves, limits and global cap."""
    data = {'chip': payload['profiles']['chip'], 'power_max': float(power_max)}
    return hashlib.sha256(json.dumps(data, sort_keys=True, allow_nan=False).encode()).hexdigest()


def load_calibration(environment, path=CALIBRATION_FILE):
    try:
        payload = json.loads(path.read_text(encoding='utf-8-sig'))
        profile = payload[environment]
        if payload['version'] != 1 or not isinstance(profile, dict):
            raise ValueError('unsupported calibration')
        return profile
    except (OSError, ValueError, KeyError, TypeError):
        return {}


def chip_reason(profile, fingerprint, flight_distance, feedback_ok):
    chip = profile.get('chip', {})
    if not isinstance(chip, dict) or chip.get('calibrated') is not True:
        return 'chip_uncalibrated'
    if chip.get('distance_reference') != 'first_landing' or chip.get('sender') != 1:
        return 'chip_wrong_reference_or_sender'
    if not fingerprint or chip.get('curve_fingerprint') != fingerprint:
        return 'chip_curve_changed'
    if chip.get('observation_verified') is not True or not feedback_ok:
        return 'chip_landing_feedback_unavailable'
    low, high, lead = (chip.get(k) for k in ('min_distance_mm', 'max_distance_mm', 'landing_lead_mm'))
    if not finite(low, high, lead) or not 0 < low <= high or lead <= 0:
        return 'chip_invalid_measurements'
    if not low <= flight_distance <= high:
        return 'chip_outside_calibrated_range'
    return None


@dataclass(frozen=True)
class ChipFeedback:
    height: float | None = None
    airborne: bool | None = None
    remaining: float | None = None
    predicted: tuple | None = None

    @property
    def ground(self):
        return (self.height is not None and self.height <= 2 * A.BALL_RADIUS
                and self.airborne is not True and (self.remaining is None or self.remaining <= 0))

    @property
    def flying(self):
        return (self.airborne is True or (self.height is not None and self.height > 2 * A.BALL_RADIUS)
                or (self.remaining is not None and self.remaining > 0))


def chip_feedback(ball_module, observed):
    native = optional(lambda: ball_module.ball())
    if native is None:
        return ChipFeedback()
    real = optional(lambda: native.RealPos())
    xyz = optional(lambda: (real.x(), real.y(), real.z()))
    # All-zero defaults are NOT height feedback. Reject stale unrelated XYZ.
    height = None
    if (xyz is not None and finite(*xyz) and xyz != (0, 0, 0) and xyz[2] >= 0
            and math.dist(xyz[:2], observed) <= 4 * A.BALL_RADIUS):
        height = xyz[2]
    airborne = optional(lambda: native.ChipBallState())
    remaining = optional(lambda: native.ChipRestFlyTime())
    predict = optional(lambda: native.BestChipPredictPos())
    predict = optional(lambda: (predict.x(), predict.y()))
    return ChipFeedback(height, airborne if isinstance(airborne, bool) else None,
                        remaining if finite(remaining) and remaining >= 0 else None,
                        predict if predict is not None and finite(*predict) and predict != (0, 0) else None)
