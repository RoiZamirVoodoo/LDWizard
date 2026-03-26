"""
LD Wizard — QQF (Quality Qualification Framework)
Deterministic quality scoring for level design within target difficulty tags.
"""

import math
import pandas as pd

from engine.parser import DIFFICULTY_ORDER
from engine.analysis.strategic import CHURN_METRIC_OPTIONS, DEFAULT_DR_CHURN_METRIC
from engine.analysis.aps_targets import resolve_aps_target_bands
from engine.analysis.difficulty_bands import format_band_label


QQF_MIN_LEVEL = 51
SINK_CHURN_FLOOR = 0.0025


def compute_qqf_analysis(df, scope=None, options=None):
    if df is None or len(df) == 0:
        return {"available": False, "reason": "No level data is loaded."}

    options = options or {}
    churn_metric = str(options.get("churn_metric") or DEFAULT_DR_CHURN_METRIC)
    aps_target_mode = str(options.get("aps_target_mode") or "adaptive")
    manual_aps_targets = options.get("manual_aps_targets") or {}

    working = df.copy().sort_values("level").reset_index(drop=True)
    current_scope = scope or {
        "start": int(working["level"].min()),
        "end": int(working["level"].max()),
        "loop_start": None,
    }
    working = working[
        (working["level"] >= int(current_scope["start"]))
        & (working["level"] <= int(current_scope["end"]))
        & (working["level"] >= QQF_MIN_LEVEL)
    ].copy()

    if len(working) < 5:
        return {
            "available": False,
            "reason": "QQF needs at least 5 scoped levels after onboarding.",
        }

    if "target_bracket" not in working.columns or "aps" not in working.columns:
        return {
            "available": False,
            "reason": "QQF needs target bracket and APS columns.",
        }

    metric = _resolve_churn_metric(working, churn_metric)
    if metric is None:
        return {
            "available": False,
            "reason": "The selected churn metric is unavailable in this dataset.",
        }

    aps_bands = resolve_aps_target_bands(
        working["aps"].tolist(),
        aps_target_mode=aps_target_mode,
        manual_aps_targets=manual_aps_targets,
    )
    working = _prepare_metrics(working, metric["column"])

    rows = []
    tier_cards = []
    for bracket in DIFFICULTY_ORDER:
        subset = working[working["target_bracket"] == bracket].copy()
        if len(subset) == 0:
            continue

        _apply_metric_scores(subset, "completion_rate", high_is_good=True, prefix="completion")
        _apply_metric_scores(subset, metric["column"], high_is_good=False, prefix="churn")
        _apply_metric_scores(subset, "iap_users_pct", high_is_good=True, prefix="payer")
        _apply_metric_scores(subset, "sink_efficiency", high_is_good=True, prefix="sink")

        band = aps_bands.get(bracket, {})
        subset["aps_modifier"] = subset["aps"].apply(lambda value: _aps_modifier(value, band))
        subset["selected_churn_pct"] = subset[metric["column"]].fillna(0.0) * 100.0
        subset["qqf_score"] = (
            subset["completion_score"]
            + subset["churn_score"]
            + subset["payer_score"]
            + subset["sink_score"]
            + subset["aps_modifier"]
        )
        subset["qqf_status"] = subset["qqf_score"].apply(_status_for_score)
        subset["qqf_reason"] = subset.apply(
            lambda row: _build_reason(row, metric["label"], band, bracket),
            axis=1,
        )
        rows.extend(subset.to_dict("records"))
        tier_cards.append(_build_tier_card(subset, band, bracket))

    if not rows:
        return {"available": False, "reason": "No QQF-eligible levels were found in the selected scope."}

    all_rows = pd.DataFrame(rows)
    counts = {status: int((all_rows["qqf_status"] == status).sum()) for status in ["Star", "Stable", "Watch", "Killzone"]}
    all_rows = all_rows.sort_values(["qqf_score", "level"], ascending=[False, True]).reset_index(drop=True)

    return {
        "available": True,
        "headline": _build_headline(counts),
        "scope_start_level": int(current_scope["start"]),
        "scope_end_level": int(current_scope["end"]),
        "onboarding_cutoff": QQF_MIN_LEVEL - 1,
        "churn_metric": metric["key"],
        "churn_label": metric["label"],
        "aps_target_mode": aps_target_mode,
        "bands": [
            {
                "bracket": bracket,
                "min": round(float(band["min"]), 3) if band.get("min") is not None else None,
                "max": round(float(band["max"]), 3) if band.get("max") is not None else None,
                "label": format_band_label(band.get("min"), band.get("max"), open_ended=bracket == DIFFICULTY_ORDER[-1]),
            }
            for bracket, band in aps_bands.items()
        ],
        "overview": {
            "total_levels": int(len(all_rows)),
            "star_count": counts["Star"],
            "stable_count": counts["Stable"],
            "watch_count": counts["Watch"],
            "killzone_count": counts["Killzone"],
            "aps_alignment_pct": round(float((all_rows["aps_modifier"] == 0).mean()) * 100, 1),
        },
        "tiers": tier_cards,
        "top_stars": _shape_levels(all_rows[all_rows["qqf_status"] == "Star"].head(10)),
        "top_killzones": _shape_levels(all_rows[all_rows["qqf_status"] == "Killzone"].sort_values(["qqf_score", "level"]).head(10)),
        "watchlist": _shape_levels(all_rows[all_rows["qqf_status"].isin(["Watch", "Killzone"])].sort_values(["qqf_score", "level"]).head(12)),
        "metric_note": f"QQF compares levels inside their target tag using completion, {metric['label'].lower()}, payer rate, sink efficiency, and APS target fit.",
    }


def _prepare_metrics(df, churn_col):
    working = df.copy()
    users = working.get("users", pd.Series(index=working.index, dtype=float)).replace(0, pd.NA)
    soft_currency = working.get("soft_currency_used", pd.Series(0.0, index=working.index)).fillna(0.0)
    sink_users = working.get("sink_users_pct", pd.Series(0.0, index=working.index)).fillna(0.0)
    working["completion_rate"] = working.get("completion_rate", pd.Series(0.0, index=working.index)).fillna(0.0).clip(lower=0.0, upper=1.0)
    working["iap_users_pct"] = working.get("iap_users_pct", pd.Series(0.0, index=working.index)).fillna(0.0).clip(lower=0.0, upper=1.0)
    working[churn_col] = working.get(churn_col, pd.Series(0.0, index=working.index)).fillna(0.0).clip(lower=0.0)
    sink_per_user = (soft_currency / users).replace([pd.NA, math.inf, -math.inf], 0).fillna(0.0)
    sink_signal = sink_per_user.where(sink_per_user > 0, sink_users)
    working["sink_efficiency"] = sink_signal / working[churn_col].clip(lower=SINK_CHURN_FLOOR)
    working["sink_efficiency"] = working["sink_efficiency"].replace([math.inf, -math.inf], 0).fillna(0.0)
    return working


def _apply_metric_scores(df, column, high_is_good, prefix):
    values = df[column].fillna(0.0).astype(float)
    low = float(values.quantile(0.2))
    high = float(values.quantile(0.8))

    def _score(value):
        numeric = float(value)
        if high <= low:
            return 0
        if high_is_good:
            if numeric >= high:
                return 1
            if numeric <= low:
                return -1
            return 0
        if numeric <= low:
            return 1
        if numeric >= high:
            return -1
        return 0

    df[f"{prefix}_score"] = values.apply(_score)


def _resolve_churn_metric(df, churn_metric):
    preferred = CHURN_METRIC_OPTIONS.get(churn_metric) or CHURN_METRIC_OPTIONS[DEFAULT_DR_CHURN_METRIC]
    if preferred["column"] in df.columns and df[preferred["column"]].notna().any():
        return {"key": churn_metric, **preferred}

    for key, option in CHURN_METRIC_OPTIONS.items():
        if option["column"] in df.columns and df[option["column"]].notna().any():
            return {"key": key, **option}
    return None


def _aps_modifier(aps_value, band):
    low = band.get("min")
    high = band.get("max")
    if low is None:
        return 0

    if high is None:
        margin = max(0.2, low * 0.08)
        if aps_value >= low:
            return 0
        if aps_value >= low - margin:
            return -1
        return -2

    width = max(high - low, 0.15)
    margin = max(0.15, width * 0.2)
    if low <= aps_value <= high:
        return 0
    if low - margin <= aps_value <= high + margin:
        return -1
    return -2


def _status_for_score(score):
    if score >= 3:
        return "Star"
    if score >= 0:
        return "Stable"
    if score >= -2:
        return "Watch"
    return "Killzone"


def _build_reason(row, churn_label, band, bracket):
    reasons = []
    if row.get("completion_score", 0) > 0:
        reasons.append("strong completion")
    elif row.get("completion_score", 0) < 0:
        reasons.append("weak completion")

    if row.get("churn_score", 0) > 0:
        reasons.append(f"low {churn_label.lower()}")
    elif row.get("churn_score", 0) < 0:
        reasons.append(f"high {churn_label.lower()}")

    if row.get("payer_score", 0) > 0:
        reasons.append("strong payer rate")
    elif row.get("payer_score", 0) < 0:
        reasons.append("weak payer rate")

    if row.get("sink_score", 0) > 0:
        reasons.append("efficient sink usage")
    elif row.get("sink_score", 0) < 0:
        reasons.append("weak sink efficiency")

    if row.get("aps_modifier", 0) < 0:
        reasons.append(f"APS misses the {bracket} target band {format_band_label(band.get('min'), band.get('max'), open_ended=bracket == DIFFICULTY_ORDER[-1])}")

    if not reasons:
        return "Balanced inside its target tag."
    return ", ".join(reasons[:3]).capitalize() + "."


def _build_tier_card(subset, band, bracket):
    counts = subset["qqf_status"].value_counts().to_dict()
    aps_in_band = float((subset["aps_modifier"] == 0).mean() * 100)
    sorted_rows = subset.sort_values(["qqf_score", "level"], ascending=[False, True])
    weakest_rows = subset.sort_values(["qqf_score", "level"], ascending=[True, True])
    return {
        "bracket": bracket,
        "level_count": int(len(subset)),
        "band_label": format_band_label(band.get("min"), band.get("max"), open_ended=bracket == DIFFICULTY_ORDER[-1]),
        "avg_score": round(float(subset["qqf_score"].mean()), 2),
        "aps_alignment_pct": round(aps_in_band, 1),
        "status_counts": {
            "Star": int(counts.get("Star", 0)),
            "Stable": int(counts.get("Stable", 0)),
            "Watch": int(counts.get("Watch", 0)),
            "Killzone": int(counts.get("Killzone", 0)),
        },
        "top_levels": _shape_levels(sorted_rows.head(3)),
        "bottom_levels": _shape_levels(weakest_rows.head(3)),
    }


def _shape_levels(rows):
    if isinstance(rows, pd.DataFrame):
        records = rows.to_dict("records")
    else:
        records = list(rows)
    shaped = []
    for row in records:
        shaped.append({
            "level": int(row["level"]),
            "target_bracket": row.get("target_bracket"),
            "qqf_score": round(float(row.get("qqf_score", 0)), 2),
            "qqf_status": row.get("qqf_status"),
            "aps": round(float(row.get("aps", 0)), 3) if row.get("aps") is not None else None,
            "completion_pct": round(float(row.get("completion_rate", 0)) * 100, 1) if row.get("completion_rate") is not None else None,
            "churn_pct": round(float(row.get("selected_churn_pct", 0)), 2) if row.get("selected_churn_pct") is not None else None,
            "payer_pct": round(float(row.get("iap_users_pct", 0)) * 100, 2) if row.get("iap_users_pct") is not None else None,
            "reason": row.get("qqf_reason"),
        })
    return shaped


def _build_headline(counts):
    if counts["Killzone"] > counts["Star"]:
        return "QQF finds more fragile levels than stars in the current scope."
    if counts["Star"] >= max(counts["Watch"], counts["Killzone"]):
        return "QQF finds a healthy base of star and stable levels in the current scope."
    return "QQF shows a mixed quality profile with a material watchlist."
