import math

from engine.parser import DIFFICULTY_ORDER
from engine.analysis.difficulty_bands import build_aps_adaptive_bands


MANUAL_APS_TARGET_FIELDS = [
    "easy_min",
    "easy_max",
    "medium_min",
    "medium_max",
    "hard_min",
    "hard_max",
    "super_hard_min",
    "super_hard_max",
    "wall_min",
    "wall_max",
]

_FIELD_MAP = {
    "Easy": ("easy_min", "easy_max"),
    "Medium": ("medium_min", "medium_max"),
    "Hard": ("hard_min", "hard_max"),
    "Super Hard": ("super_hard_min", "super_hard_max"),
    "Wall": ("wall_min", "wall_max"),
}


def default_manual_aps_targets():
    return {field: None for field in MANUAL_APS_TARGET_FIELDS}


def normalize_manual_aps_targets(raw_targets):
    targets = default_manual_aps_targets()
    if not isinstance(raw_targets, dict):
        return targets

    for field in MANUAL_APS_TARGET_FIELDS:
        value = raw_targets.get(field)
        if value in (None, ""):
            targets[field] = None
            continue
        try:
            numeric = float(value)
        except (TypeError, ValueError):
            raise ValueError(f"Manual APS target '{field}' must be numeric.")
        if not math.isfinite(numeric):
            raise ValueError(f"Manual APS target '{field}' must be finite.")
        targets[field] = numeric
    return targets


def resolve_aps_target_bands(aps_values, aps_target_mode="adaptive", manual_aps_targets=None):
    if str(aps_target_mode or "adaptive").lower() == "manual":
        normalized = normalize_manual_aps_targets(manual_aps_targets)
        return _build_manual_bands(normalized)
    return build_aps_adaptive_bands(aps_values)


def _build_manual_bands(targets):
    bands = {}
    previous_max = None

    for index, bracket in enumerate(DIFFICULTY_ORDER):
        min_field, max_field = _FIELD_MAP[bracket]
        low = targets.get(min_field)
        high = targets.get(max_field)

        if low is None:
            raise ValueError(f"Manual APS target '{min_field}' is required in manual mode.")
        if index < len(DIFFICULTY_ORDER) - 1 and high is None:
            raise ValueError(f"Manual APS target '{max_field}' is required in manual mode.")
        if high is not None and high <= low:
            raise ValueError(f"Manual APS target '{max_field}' must be greater than '{min_field}'.")
        if previous_max is not None and low < previous_max:
            raise ValueError("Manual APS target bands must be monotonic and non-overlapping.")

        bands[bracket] = {"min": low, "max": high}
        previous_max = high if high is not None else previous_max

    return bands
