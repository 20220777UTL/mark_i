"""
Curve-based power backend for distance(mm) -> power evaluation.

This module is intentionally pure Python so it can be reused by the runtime,
tests, and the standalone editor without pulling in SciPy.
"""

from __future__ import annotations

import json
import time
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

try:
    import Global  # type: ignore
except Exception:
    Global = None


DEFAULT_CURVE_VERSION = 1
CURVE_NAMES = ("Low", "Normal", "High")
PROFILE_KEYS = ("flat", "chip")
PROFILE_DISPLAY_NAMES = {
    "flat": "Flat",
    "chip": "Chip",
}
_CURVE_DIR = Path(__file__).resolve().parents[1] / "data" / "power_curve"
_DEFAULT_CURVE_FILE = _CURVE_DIR / "active_curve.json"
_DEFAULT_TEMPLATE_FILE = _CURVE_DIR / "default_curve.json"


def _global_attr(name: str, default: Any) -> Any:
    if Global is None:
        return default
    return getattr(Global, name, default)


def default_curve_file() -> Path:
    configured = _global_attr("powerCurveFile", None)
    if not configured:
        return _DEFAULT_CURVE_FILE
    configured_path = Path(configured)
    if not configured_path.is_absolute():
        configured_path = Path(__file__).resolve().parents[1] / configured_path
    return configured_path


def default_curve_template_file() -> Path:
    return _DEFAULT_TEMPLATE_FILE


def normalize_profile_key(profile: str | None) -> str:
    if not profile:
        return "flat"
    lowered = profile.lower()
    if lowered not in PROFILE_KEYS:
        raise ValueError(f"Unknown power curve profile '{profile}'")
    return lowered


def _builtin_profile_block(curves: dict[str, list[dict[str, float]]], max_power: float) -> dict[str, Any]:
    return {
        "limits": {
            "min_power": 0,
            "max_power": float(max_power),
        },
        "curves": {
            curve_name: {"points": [dict(point) for point in points]}
            for curve_name, points in curves.items()
        },
    }


def _builtin_default_curve_payload() -> dict[str, Any]:
    max_power = float(_global_attr("powerMax", 12700))
    flat_curves = {
        "Low": [
            {"position_mm": 0, "power": 0},
            {"position_mm": 800, "power": 1600},
            {"position_mm": 1800, "power": 3200},
            {"position_mm": 3200, "power": 5200},
            {"position_mm": 5200, "power": 7800},
            {"position_mm": 8000, "power": 11000},
        ],
        "Normal": [
            {"position_mm": 0, "power": 0},
            {"position_mm": 800, "power": 2200},
            {"position_mm": 1800, "power": 4200},
            {"position_mm": 3200, "power": 6400},
            {"position_mm": 5200, "power": 9200},
            {"position_mm": 8000, "power": 13000},
        ],
        "High": [
            {"position_mm": 0, "power": 0},
            {"position_mm": 800, "power": 2800},
            {"position_mm": 1800, "power": 5200},
            {"position_mm": 3200, "power": 7800},
            {"position_mm": 5200, "power": 11200},
            {"position_mm": 8000, "power": 16000},
        ],
    }
    return {
        "version": DEFAULT_CURVE_VERSION,
        "metadata": {
            "name": "Default Match Curve Profiles",
            "description": "Editable distance(mm) -> power curves for flat/chip and Low/Normal/High.",
        },
        "profiles": {
            "flat": _builtin_profile_block(flat_curves, max_power),
            "chip": _builtin_profile_block(flat_curves, max_power),
        },
    }


def ensure_default_curve_template_exists(template_file: Path | None = None) -> Path:
    target = template_file or default_curve_template_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(_builtin_default_curve_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def default_curve_payload() -> dict[str, Any]:
    template_file = ensure_default_curve_template_exists()
    try:
        payload = json.loads(template_file.read_text(encoding="utf-8"))
        _validate_payload(payload)
        return payload
    except Exception as exc:
        print(f"[PowerCurveBackend] Failed to load default template '{template_file}': {exc}")
        return _builtin_default_curve_payload()


def ensure_curve_file_exists(curve_file: Path | None = None) -> Path:
    target = curve_file or default_curve_file()
    target.parent.mkdir(parents=True, exist_ok=True)
    if not target.exists():
        target.write_text(json.dumps(default_curve_payload(), ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def atomic_write_curve_file(payload: dict[str, Any], curve_file: Path | None = None) -> Path:
    target = ensure_curve_file_exists(curve_file)
    temp_file = target.with_suffix(target.suffix + ".tmp")
    temp_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    temp_file.replace(target)
    return target


def _normalize_limits(payload: dict[str, Any]) -> dict[str, float]:
    raw_limits = payload.get("limits", {})
    if raw_limits is None:
        raw_limits = {}
    if not isinstance(raw_limits, dict):
        raise ValueError("'limits' must be a mapping")

    try:
        min_power = float(raw_limits.get("min_power", 0.0))
        max_power = float(raw_limits.get("max_power", _global_attr("powerMax", 12700)))
    except (TypeError, ValueError) as exc:
        raise ValueError("Curve limits must be numeric") from exc

    if min_power < 0:
        raise ValueError("min_power must be >= 0")
    if max_power < 0:
        raise ValueError("max_power must be >= 0")
    if max_power < min_power:
        raise ValueError("max_power must be >= min_power")
    return {
        "min_power": min_power,
        "max_power": max_power,
    }


def _normalize_points(raw_points: Iterable[dict[str, Any]]) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for raw in raw_points:
        try:
            position = float(raw["position_mm"])
            power = float(raw["power"])
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"Invalid curve point: {raw!r}") from exc
        if position < 0:
            raise ValueError(f"position_mm must be >= 0, got {position}")
        if power < 0:
            raise ValueError(f"power must be >= 0, got {power}")
        points.append((position, power))
    points.sort(key=lambda item: item[0])
    if len(points) < 2:
        raise ValueError("Each curve requires at least 2 points")
    for index in range(1, len(points)):
        if points[index][0] <= points[index - 1][0]:
            raise ValueError("position_mm values must be strictly increasing")
    return points


def _normalize_profile_block(profile_payload: dict[str, Any]) -> tuple[dict[str, list[tuple[float, float]]], dict[str, float]]:
    curves = profile_payload.get("curves")
    if not isinstance(curves, dict):
        raise ValueError("Missing 'curves' mapping in profile")

    normalized: dict[str, list[tuple[float, float]]] = {}
    for curve_name in CURVE_NAMES:
        curve_entry = curves.get(curve_name)
        if not isinstance(curve_entry, dict):
            raise ValueError(f"Missing curve '{curve_name}'")
        points = curve_entry.get("points")
        if not isinstance(points, list):
            raise ValueError(f"Curve '{curve_name}' must provide a points list")
        normalized[curve_name] = _normalize_points(points)
    return normalized, _normalize_limits(profile_payload)


def _canonicalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
    builtin = _builtin_default_curve_payload()
    canonical = {
        "version": payload.get("version", DEFAULT_CURVE_VERSION),
        "metadata": dict(builtin["metadata"]),
        "profiles": {},
    }
    if isinstance(payload.get("metadata"), dict):
        canonical["metadata"].update(payload["metadata"])

    profiles = payload.get("profiles")
    if isinstance(profiles, dict):
        for profile_key in PROFILE_KEYS:
            profile_payload = profiles.get(profile_key)
            if not isinstance(profile_payload, dict):
                raise ValueError(f"Missing profile '{profile_key}'")
            curves, limits = _normalize_profile_block(profile_payload)
            canonical["profiles"][profile_key] = {
                "limits": limits,
                "curves": {
                    curve_name: {
                        "points": [
                            {"position_mm": point[0], "power": point[1]}
                            for point in curves[curve_name]
                        ]
                    }
                    for curve_name in CURVE_NAMES
                },
            }
        return canonical

    # Backward compatibility: legacy payload with root-level curves/limits becomes flat+chip clone.
    legacy_curves, legacy_limits = _normalize_profile_block(payload)
    legacy_profile = {
        "limits": legacy_limits,
        "curves": {
            curve_name: {
                "points": [
                    {"position_mm": point[0], "power": point[1]}
                    for point in legacy_curves[curve_name]
                ]
            }
            for curve_name in CURVE_NAMES
        },
    }
    canonical["profiles"]["flat"] = json.loads(json.dumps(legacy_profile))
    canonical["profiles"]["chip"] = json.loads(json.dumps(legacy_profile))
    canonical["metadata"]["description"] += " Migrated from legacy single-profile format."
    return canonical


def _validate_payload(
    payload: dict[str, Any]
) -> tuple[dict[str, dict[str, list[tuple[float, float]]]], dict[str, dict[str, float]], dict[str, Any]]:
    canonical = _canonicalize_payload(payload)
    normalized_profiles: dict[str, dict[str, list[tuple[float, float]]]] = {}
    limits_profiles: dict[str, dict[str, float]] = {}
    profiles = canonical["profiles"]
    for profile_key in PROFILE_KEYS:
        normalized_profiles[profile_key], limits_profiles[profile_key] = _normalize_profile_block(profiles[profile_key])
    return normalized_profiles, limits_profiles, canonical


def _sign(value: float) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _endpoint_slope(h_this: float, h_next: float, d_this: float, d_next: float) -> float:
    slope = ((2.0 * h_this + h_next) * d_this - h_this * d_next) / (h_this + h_next)
    if _sign(slope) != _sign(d_this):
        return 0.0
    if _sign(d_this) != _sign(d_next) and abs(slope) > abs(3.0 * d_this):
        return 3.0 * d_this
    return slope


@dataclass(frozen=True)
class MonotoneCubicCurve:
    xs: tuple[float, ...]
    ys: tuple[float, ...]
    ms: tuple[float, ...]

    @classmethod
    def from_points(cls, points: Iterable[tuple[float, float]]) -> "MonotoneCubicCurve":
        normalized = list(points)
        xs = [point[0] for point in normalized]
        ys = [point[1] for point in normalized]
        if len(xs) == 2:
            slope = (ys[1] - ys[0]) / (xs[1] - xs[0])
            return cls(tuple(xs), tuple(ys), (slope, slope))

        hs = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        ds = [(ys[i + 1] - ys[i]) / hs[i] for i in range(len(hs))]
        ms = [0.0] * len(xs)

        ms[0] = _endpoint_slope(hs[0], hs[1], ds[0], ds[1])
        ms[-1] = _endpoint_slope(hs[-1], hs[-2], ds[-1], ds[-2])

        for i in range(1, len(xs) - 1):
            if ds[i - 1] == 0.0 or ds[i] == 0.0 or _sign(ds[i - 1]) != _sign(ds[i]):
                ms[i] = 0.0
                continue
            w1 = 2.0 * hs[i] + hs[i - 1]
            w2 = hs[i] + 2.0 * hs[i - 1]
            ms[i] = (w1 + w2) / ((w1 / ds[i - 1]) + (w2 / ds[i]))

        return cls(tuple(xs), tuple(ys), tuple(ms))

    def evaluate(self, distance_mm: float) -> float:
        if distance_mm <= self.xs[0]:
            return self.ys[0]
        if distance_mm >= self.xs[-1]:
            return self.ys[-1]

        index = bisect_right(self.xs, distance_mm) - 1
        h = self.xs[index + 1] - self.xs[index]
        t = (distance_mm - self.xs[index]) / h

        h00 = 2.0 * t ** 3 - 3.0 * t ** 2 + 1.0
        h10 = t ** 3 - 2.0 * t ** 2 + t
        h01 = -2.0 * t ** 3 + 3.0 * t ** 2
        h11 = t ** 3 - t ** 2
        return (
            h00 * self.ys[index]
            + h10 * h * self.ms[index]
            + h01 * self.ys[index + 1]
            + h11 * h * self.ms[index + 1]
        )


class PowerCurveStore:
    def __init__(self, curve_file: Path | None = None, reload_interval_sec: float | None = None):
        self.curve_file = Path(curve_file) if curve_file else default_curve_file()
        self.reload_interval_sec = float(
            reload_interval_sec if reload_interval_sec is not None else _global_attr("powerCurveReloadIntervalSec", 0.2)
        )
        self._last_checked_at = 0.0
        self._last_mtime_ns: int | None = None
        self._last_error: str | None = None
        self._payload: dict[str, Any] | None = None
        self._curves: dict[str, dict[str, MonotoneCubicCurve]] = {
            profile_key: {}
            for profile_key in PROFILE_KEYS
        }
        self._limits: dict[str, dict[str, float]] = {
            profile_key: {
                "min_power": 0.0,
                "max_power": float(_global_attr("powerMax", 12700)),
            }
            for profile_key in PROFILE_KEYS
        }

    def configure(self, curve_file: str | Path | None = None, reload_interval_sec: float | None = None) -> None:
        if curve_file is not None:
            self.curve_file = Path(curve_file)
        if reload_interval_sec is not None:
            self.reload_interval_sec = float(reload_interval_sec)

    def reload_if_needed(self, force: bool = False) -> None:
        now = time.monotonic()
        if not force and self._payload is not None and now - self._last_checked_at < self.reload_interval_sec:
            return

        self._last_checked_at = now
        curve_file = ensure_curve_file_exists(self.curve_file)
        stat = curve_file.stat()
        if not force and self._payload is not None and self._last_mtime_ns == stat.st_mtime_ns:
            return

        try:
            payload = json.loads(curve_file.read_text(encoding="utf-8"))
            normalized_profiles, limits_profiles, canonical_payload = _validate_payload(payload)
            curves = {
                profile_key: {
                    curve_name: MonotoneCubicCurve.from_points(points)
                    for curve_name, points in normalized_profiles[profile_key].items()
                }
                for profile_key in PROFILE_KEYS
            }
        except Exception as exc:
            message = f"[PowerCurveBackend] Failed to reload '{curve_file}': {exc}"
            if message != self._last_error:
                print(message)
            self._last_error = message
            return

        self._curves = curves
        self._limits = limits_profiles
        self._payload = canonical_payload
        self._last_mtime_ns = stat.st_mtime_ns
        self._last_error = None

    def evaluate(self, distance_mm: float, curve_name: str, *, profile: str = "flat") -> float:
        self.reload_if_needed()
        profile_key = normalize_profile_key(profile)
        curve = self._curves.get(profile_key, {}).get(curve_name)
        if curve is None:
            self.reload_if_needed(force=True)
            curve = self._curves.get(profile_key, {}).get(curve_name)
        if curve is None:
            raise RuntimeError(f"Curve '{curve_name}' is unavailable for profile '{profile_key}'")
        return curve.evaluate(max(0.0, float(distance_mm)))

    def snapshot(self) -> dict[str, Any]:
        self.reload_if_needed()
        if self._payload is None:
            self.reload_if_needed(force=True)
        if self._payload is None:
            return default_curve_payload()
        return json.loads(json.dumps(self._payload))

    def limits_snapshot(self, *, profile: str = "flat") -> dict[str, float]:
        self.reload_if_needed()
        if self._payload is None:
            self.reload_if_needed(force=True)
        profile_key = normalize_profile_key(profile)
        return dict(self._limits[profile_key])


curve_store = PowerCurveStore()


def reload_curve_store(force: bool = False) -> None:
    curve_store.configure(default_curve_file(), _global_attr("powerCurveReloadIntervalSec", 0.2))
    curve_store.reload_if_needed(force=force)


def evaluate_distance(distance_mm: float, curve_name: str, *, profile: str = "flat") -> float:
    curve_store.configure(default_curve_file(), _global_attr("powerCurveReloadIntervalSec", 0.2))
    return curve_store.evaluate(distance_mm, curve_name, profile=profile)


def curve_snapshot() -> dict[str, Any]:
    curve_store.configure(default_curve_file(), _global_attr("powerCurveReloadIntervalSec", 0.2))
    return curve_store.snapshot()


def curve_limits_snapshot(*, profile: str = "flat") -> dict[str, float]:
    curve_store.configure(default_curve_file(), _global_attr("powerCurveReloadIntervalSec", 0.2))
    return curve_store.limits_snapshot(profile=profile)


def clamp_with_limits(power: float, limits: dict[str, float], *, hard_max: float | None = None) -> float:
    lower = max(0.0, float(limits.get("min_power", 0.0)))
    upper = float(limits.get("max_power", _global_attr("powerMax", 12700)))
    if hard_max is not None:
        upper = min(upper, float(hard_max))
    if upper < lower:
        upper = lower
    if power < lower:
        return lower
    if power > upper:
        return upper
    return float(power)
