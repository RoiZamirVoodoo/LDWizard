"""
LD Wizard — Strategic views
Purpose-built analyses for late APS trend, end-game loop health,
and diminishing returns.
"""

import math
import statistics
import pandas as pd
from engine.analysis.recommendations import ONBOARDING_LEVELS


DEFAULT_LATE_APS_TARGET_MIN = 1.9
DEFAULT_LATE_APS_TARGET_MAX = 2.4
WINDOW_SIZE = 50
OPTIMIZATION_WINDOW_SIZE = 10
APS_BUCKETS = [
    (1.0, 1.5),
    (1.5, 2.0),
    (2.0, 2.5),
    (2.5, 3.0),
    (3.0, 4.0),
    (4.0, 5.0),
    (5.0, 7.0),
    (7.0, 10.0),
    (10.0, 15.0),
    (15.0, None),
]


def compute_strategic_views(df, scope, tutorial_max_level=0):
    if df is None or len(df) == 0:
        return {
            "late_aps_trend": {"available": False, "reason": "No data loaded."},
            "end_game_loop": {"available": False, "reason": "No data loaded."},
            "diminishing_returns": {"available": False, "reason": "No data loaded."},
        }

    current_scope = scope or {
        "start": int(df["level"].min()),
        "end": int(df["level"].max()),
        "loop_start": None,
    }
    df = df.copy().sort_values("level").reset_index(drop=True)
    onboarding_cutoff = max(ONBOARDING_LEVELS, int(tutorial_max_level or 0))

    return {
        "late_aps_trend": compute_late_aps_trend(df, current_scope, onboarding_cutoff),
        "end_game_loop": compute_end_game_loop(df, current_scope),
        "diminishing_returns": compute_diminishing_returns_view(df, current_scope),
    }


def compute_late_aps_trend(df, scope, onboarding_cutoff):
    start_level = max(int(scope["start"]), onboarding_cutoff + 1)
    end_level = int(scope["end"])

    subset = df[(df["level"] >= start_level) & (df["level"] <= end_level)].copy()
    if len(subset) < 10:
        return {
            "available": False,
            "reason": "Not enough post-onboarding levels in the selected range.",
        }

    buckets = _bucket_level_windows(subset, start_level, end_level, window_size=WINDOW_SIZE)
    optimization_buckets = _bucket_level_windows(
        subset,
        start_level,
        end_level,
        window_size=OPTIMIZATION_WINDOW_SIZE,
    )
    if not buckets:
        return {"available": False, "reason": "No late-game buckets available."}

    target_band = _derive_optimal_aps_band(optimization_buckets, OPTIMIZATION_WINDOW_SIZE)
    for bucket in buckets:
        bucket["efficiency_score"] = round(float(bucket.get("efficiency_score", 0)), 3)
        avg_aps = bucket["avg_aps"]
        if avg_aps < target_band["min"]:
            bucket["status"] = "slump"
        elif avg_aps > target_band["max"]:
            bucket["status"] = "spike"
        else:
            bucket["status"] = "healthy"

    weak_ranges = []
    previous = None
    for bucket in buckets:
        if bucket["status"] != "healthy":
            weak_ranges.append({
                "range_label": bucket["range_label"],
                "reason": (
                    f"Average APS {bucket['avg_aps']:.2f} is below the optimized zone."
                    if bucket["status"] == "slump"
                    else f"Average APS {bucket['avg_aps']:.2f} is above the optimized zone."
                ),
                "severity": "high" if bucket["status"] == "slump" else "medium",
            })

        if previous is not None:
            delta = round(bucket["avg_aps"] - previous["avg_aps"], 3)
            bucket["delta_from_previous"] = delta
            if delta <= -0.35:
                weak_ranges.append({
                    "range_label": bucket["range_label"],
                    "reason": f"APS drops by {abs(delta):.2f} vs the previous 50-level window.",
                    "severity": "high",
                })
        previous = bucket

    total_delta = round(buckets[-1]["avg_aps"] - buckets[0]["avg_aps"], 3)
    if total_delta <= -0.4:
        headline = "Late APS trends downward across the selected range."
        verdict = "downward"
    elif total_delta >= 0.4:
        headline = "Late APS trends upward across the selected range."
        verdict = "upward"
    else:
        headline = "Late APS is broadly stable across the selected range."
        verdict = "stable"

    return {
        "available": True,
        "headline": headline,
        "verdict": verdict,
        "onboarding_cutoff": onboarding_cutoff,
        "target_band": target_band,
        "bucket_size": WINDOW_SIZE,
        "buckets": buckets,
        "weak_ranges": weak_ranges[:6],
    }


def compute_end_game_loop(df, scope):
    loop_start = scope.get("loop_start")
    if loop_start is None:
        return {
            "available": False,
            "reason": "Set a loop start level to analyze the repeating end-game loop.",
        }

    start_level = int(loop_start)
    end_level = int(scope["end"])
    subset = df[(df["level"] >= start_level) & (df["level"] <= end_level)].copy()
    if len(subset) < 10:
        return {
            "available": False,
            "reason": "Not enough levels remain after the loop start to analyze the end-game loop.",
        }

    buckets = _bucket_level_windows(subset, start_level, end_level)
    if not buckets:
        return {"available": False, "reason": "No end-game loop buckets available."}

    baseline_aps = sum(bucket["avg_aps"] for bucket in buckets[:min(2, len(buckets))]) / min(2, len(buckets))
    baseline_d3 = sum(bucket["avg_d3_churn_pct"] for bucket in buckets[:min(2, len(buckets))]) / min(2, len(buckets))
    issues = []

    for bucket in buckets:
        aps_drift = round(bucket["avg_aps"] - baseline_aps, 3)
        d3_drift = round(bucket["avg_d3_churn_pct"] - baseline_d3, 2)
        bucket["aps_drift"] = aps_drift
        bucket["d3_drift"] = d3_drift

        if aps_drift <= -0.35:
            bucket["status"] = "softening"
            issues.append({
                "range_label": bucket["range_label"],
                "reason": f"Loop APS is {abs(aps_drift):.2f} below the early-loop baseline.",
                "severity": "high",
            })
        elif aps_drift >= 0.45:
            bucket["status"] = "hardening"
            issues.append({
                "range_label": bucket["range_label"],
                "reason": f"Loop APS is {aps_drift:.2f} above the early-loop baseline.",
                "severity": "medium",
            })
        else:
            bucket["status"] = "stable"

        if baseline_d3 > 0 and bucket["avg_d3_churn_pct"] > baseline_d3 * 1.4:
            issues.append({
                "range_label": bucket["range_label"],
                "reason": f"D3 churn rises to {bucket['avg_d3_churn_pct']:.2f}% vs {baseline_d3:.2f}% early-loop baseline.",
                "severity": "high",
            })

    last_bucket = buckets[-1]
    if last_bucket["aps_drift"] <= -0.35:
        headline = "The end-game loop softens over time."
        verdict = "softening"
    elif last_bucket["aps_drift"] >= 0.45:
        headline = "The end-game loop hardens over time."
        verdict = "hardening"
    else:
        headline = "The end-game loop is broadly stable."
        verdict = "stable"

    return {
        "available": True,
        "headline": headline,
        "verdict": verdict,
        "bucket_size": WINDOW_SIZE,
        "baseline_aps": round(baseline_aps, 3),
        "baseline_d3_churn_pct": round(baseline_d3, 2),
        "buckets": buckets,
        "issues": issues[:6],
    }


def compute_diminishing_returns_view(df, scope):
    start_level = int(scope["start"])
    end_level = int(scope["end"])
    subset = df[(df["level"] >= start_level) & (df["level"] <= end_level)].copy()
    if len(subset) < 10:
        return {
            "available": False,
            "reason": "Not enough levels in the selected range for diminishing-returns analysis.",
        }

    buckets = _build_aps_buckets(subset)
    valid = [bucket for bucket in buckets if bucket["count"] >= 3]
    if len(valid) < 3:
        return {
            "available": False,
            "reason": "Not enough APS buckets with sufficient data.",
        }

    _attach_iap_composite(valid)

    for bucket in valid:
        bucket["revenue_per_k_users"] = round(
            bucket.get("avg_iap_revenue", 0.0) / max(bucket.get("avg_users", 0.0), 1.0) * 1000.0,
            3,
        )

    for index, bucket in enumerate(valid):
        bucket["smooth_d3_churn_pct"] = round(_neighbor_average(valid, index, "avg_d3_churn_pct"), 3)
        bucket["smooth_iap_users_pct"] = round(_neighbor_average(valid, index, "avg_iap_users_pct"), 3)
        bucket["smooth_iap_composite"] = round(_neighbor_average(valid, index, "iap_composite"), 4)
        bucket["smooth_revenue_per_k_users"] = round(_neighbor_average(valid, index, "revenue_per_k_users"), 3)

    revenue_values = [bucket["smooth_revenue_per_k_users"] for bucket in valid]
    payer_values = [bucket["smooth_iap_users_pct"] for bucket in valid]
    user_values = [bucket.get("avg_users", 0.0) for bucket in valid]
    churn_values = [bucket["smooth_d3_churn_pct"] for bucket in valid]

    revenue_low, revenue_high = _percentile(revenue_values, 0.10), _percentile(revenue_values, 0.90)
    payer_low, payer_high = _percentile(payer_values, 0.10), _percentile(payer_values, 0.90)
    users_low, users_high = _percentile(user_values, 0.20), _percentile(user_values, 0.90)
    churn_low, churn_high = _percentile(churn_values, 0.10), _percentile(churn_values, 0.85)

    for bucket in valid:
        revenue_strength = _scale_to_unit(bucket["smooth_revenue_per_k_users"], revenue_low, revenue_high)
        payer_strength = _scale_to_unit(bucket["smooth_iap_users_pct"], payer_low, payer_high)
        volume_strength = _scale_to_unit(bucket.get("avg_users", 0.0), users_low, users_high)
        monetization_strength = (
            0.65 * revenue_strength + 0.20 * payer_strength + 0.15 * bucket["smooth_iap_composite"]
        )
        # Treat high churn as a steep tax, not a gentle tradeoff.
        churn_gate = 1.0 / (1.0 + math.exp((bucket["smooth_d3_churn_pct"] - 2.2) / 0.45))
        bucket["sweet_spot_score"] = round(
            monetization_strength * churn_gate * (0.85 + 0.15 * volume_strength),
            4,
        )

    for index, bucket in enumerate(valid):
        bucket["smooth_score"] = round(_neighbor_average(valid, index, "sweet_spot_score"), 4)

    peak_index = max(range(len(valid)), key=lambda idx: valid[idx]["smooth_score"])
    peak_bucket = valid[peak_index]
    peak_score = peak_bucket["smooth_score"]
    peak_churn = max(peak_bucket["smooth_d3_churn_pct"], 0.01)

    sweet_start = peak_index
    sweet_end = peak_index
    while sweet_start > 0 and valid[sweet_start - 1]["smooth_score"] >= peak_score * 0.88:
        sweet_start -= 1
    while sweet_end < len(valid) - 1 and valid[sweet_end + 1]["smooth_score"] >= peak_score * 0.88:
        sweet_end += 1

    safe_start = sweet_start
    while safe_start > 0:
        candidate = valid[safe_start - 1]
        if candidate["smooth_score"] >= peak_score * 0.70 and candidate["smooth_d3_churn_pct"] <= peak_churn * 1.20:
            safe_start -= 1
            continue
        break
    safe_end = sweet_start - 1

    overstretched_start = None
    for index in range(sweet_end + 1, len(valid) - 1):
        current = valid[index]
        following = valid[index + 1]
        score_falling = current["smooth_score"] <= peak_score * 0.55 and following["smooth_score"] <= peak_score * 0.55
        churn_elevated = current["smooth_d3_churn_pct"] >= peak_churn * 1.25 and following["smooth_d3_churn_pct"] >= peak_churn * 1.25
        if score_falling and churn_elevated:
            overstretched_start = index
            break

    if overstretched_start is None:
        for index in range(sweet_end + 1, len(valid)):
            current = valid[index]
            if current["smooth_score"] <= peak_score * 0.45 and current["smooth_d3_churn_pct"] >= peak_churn * 1.35:
                overstretched_start = index
                break

    safe_zone = valid[safe_start:safe_end + 1] if safe_end >= safe_start else []
    sweet_zone = valid[sweet_start:sweet_end + 1]
    transition_zone = valid[sweet_end + 1:overstretched_start] if overstretched_start is not None else valid[sweet_end + 1:]
    overstretched_zone = valid[overstretched_start:] if overstretched_start is not None else []

    for index, bucket in enumerate(valid):
        bucket["ratio"] = None
        if sweet_start <= index <= sweet_end:
            bucket["zone"] = "sweet_spot"
            bucket["zone_label"] = "Sweet spot"
            bucket["zone_tone"] = "safe"
        elif safe_zone and safe_start <= index <= safe_end:
            bucket["zone"] = "safe"
            bucket["zone_label"] = "Safe"
            bucket["zone_tone"] = "safe"
        elif overstretched_start is not None and index >= overstretched_start:
            bucket["zone"] = "overstretched"
            bucket["zone_label"] = "Overstretched"
            bucket["zone_tone"] = "danger"
        else:
            bucket["zone"] = "transition"
            bucket["zone_label"] = "Transition"
            bucket["zone_tone"] = "warning"

    sweet_range_label = _format_bucket_zone_range(sweet_zone)
    safe_range_label = _format_bucket_zone_range(safe_zone) if safe_zone else None
    transition_range_label = _format_bucket_zone_range(transition_zone) if transition_zone else None
    overstretched_range_label = _format_bucket_zone_range(overstretched_zone) if overstretched_zone else None

    if overstretched_zone:
        headline = (
            f"Sweet spot sits around APS {sweet_range_label}; overstretch begins around {overstretched_zone[0]['label']}."
        )
        verdict = "danger"
    else:
        headline = f"Sweet spot sits around APS {sweet_range_label}; no persistent overstretched zone yet."
        verdict = "stable"

    findings = [
        {
            "title": "Sweet spot",
            "detail": (
                f"APS {sweet_range_label} combines the strongest revenue-per-1k signal with manageable D3 churn."
            ),
        }
    ]
    if safe_range_label:
        findings.append({
            "title": "Safe runway",
            "detail": f"APS {safe_range_label} still monetizes well before churn meaningfully accelerates.",
        })
    if transition_range_label:
        findings.append({
            "title": "Riskier runway",
            "detail": f"APS {transition_range_label} can still monetize, but churn is climbing faster than in the sweet spot.",
        })
    if overstretched_range_label:
        findings.append({
            "title": "Overstretched zone",
            "detail": (
                f"APS {overstretched_range_label} keeps difficulty rising after the sweet spot while revenue density flattens and churn stays higher."
            ),
        })
    else:
        findings.append({
            "title": "No persistent overstretch",
            "detail": "Higher APS buckets do not yet show a sustained post-peak decline in revenue-adjusted efficiency.",
        })

    high_aps_survivor = next(
        (
            bucket for bucket in valid
            if bucket["low_aps"] >= 7.0
            and bucket["revenue_per_k_users"] >= _percentile([b["revenue_per_k_users"] for b in valid], 0.75)
            and bucket.get("avg_users", 0.0) <= _percentile(user_values, 0.30)
        ),
        None,
    )
    if high_aps_survivor:
        findings.append({
            "title": "Survivor-heavy monetization",
            "detail": (
                f"APS {high_aps_survivor['label']} still spends well, but mostly through a much smaller surviving audience."
            ),
        })

    return {
        "available": True,
        "headline": headline,
        "verdict": verdict,
        "buckets": valid,
        "findings": findings,
        "zones": {
            "safe": safe_range_label,
            "sweet_spot": sweet_range_label,
            "transition": transition_range_label,
            "overstretched": overstretched_range_label,
        },
        "metric_note": "Using smoothed revenue per 1k users, payer rate, and D3 churn to find a sweet spot before overstretch.",
        "metric_tag": "Revenue/churn sweet spot",
    }


def _bucket_level_windows(df, start_level, end_level, window_size=WINDOW_SIZE):
    buckets = []
    playtime_col = _playtime_col(df)

    for bucket_start in range(start_level, end_level + 1, window_size):
        bucket_end = min(end_level, bucket_start + window_size - 1)
        subset = df[(df["level"] >= bucket_start) & (df["level"] <= bucket_end)].copy()
        if len(subset) == 0:
            continue

        bucket = {
            "range_label": f"L{bucket_start}\u2013L{bucket_end}",
            "start_level": int(bucket_start),
            "end_level": int(bucket_end),
            "count": int(len(subset)),
            "avg_aps": round(float(subset["aps"].mean()), 3) if "aps" in subset.columns else 0.0,
            "avg_users": round(float(subset["users"].mean()), 2) if "users" in subset.columns else 0.0,
            "avg_funnel_pct": round(float(subset["funnel_pct"].mean()) * 100, 2) if "funnel_pct" in subset.columns else 0.0,
            "avg_d3_churn_pct": round(float(subset["churn_3d"].mean()) * 100, 2) if "churn_3d" in subset.columns else 0.0,
            "avg_playtime_sec": round(float(subset[playtime_col].mean()), 2) if playtime_col in subset.columns else 0.0,
            "avg_iap_users_pct": round(float(subset["iap_users_pct"].mean()) * 100, 3) if "iap_users_pct" in subset.columns else 0.0,
            "avg_iap_revenue": round(float(subset["iap_revenue"].mean()), 3) if "iap_revenue" in subset.columns else 0.0,
            "avg_iap_transactions": round(float(subset["iap_transactions"].mean()), 3) if "iap_transactions" in subset.columns else 0.0,
        }
        buckets.append(bucket)

    _attach_iap_composite(buckets)
    return buckets


def _build_aps_buckets(df):
    buckets = []
    for low, high in APS_BUCKETS:
        if high is None:
            subset = df[df["aps"] >= low].copy()
            label = f"{int(low)}+"
        else:
            subset = df[(df["aps"] >= low) & (df["aps"] < high)].copy()
            label = f"{low:.1f}\u2013{high:.1f}"

        if len(subset) == 0:
            continue

        buckets.append({
            "label": label,
            "low_aps": float(low),
            "high_aps": None if high is None else float(high),
            "count": int(len(subset)),
            "avg_users": round(float(subset["users"].mean()), 2) if "users" in subset.columns else 0.0,
            "avg_d3_churn_pct": round(float(subset["churn_3d"].mean()) * 100, 3) if "churn_3d" in subset.columns else 0.0,
            "avg_iap_users_pct": round(float(subset["iap_users_pct"].mean()) * 100, 3) if "iap_users_pct" in subset.columns else 0.0,
            "avg_iap_revenue": round(float(subset["iap_revenue"].mean()), 3) if "iap_revenue" in subset.columns else 0.0,
            "avg_iap_transactions": round(float(subset["iap_transactions"].mean()), 3) if "iap_transactions" in subset.columns else 0.0,
            "avg_sink_pct": round(float(subset["sink_users_pct"].mean()) * 100, 3) if "sink_users_pct" in subset.columns else 0.0,
        })

    return buckets


def _attach_iap_composite(buckets):
    if not buckets:
        return buckets

    max_iap_users = max(bucket.get("avg_iap_users_pct", 0) for bucket in buckets) or 1.0
    max_iap_revenue = max(bucket.get("avg_iap_revenue", 0) for bucket in buckets) or 1.0
    max_iap_transactions = max(bucket.get("avg_iap_transactions", 0) for bucket in buckets) or 1.0

    for bucket in buckets:
        norm_iap_users = bucket.get("avg_iap_users_pct", 0) / max_iap_users if max_iap_users else 0.0
        norm_iap_revenue = bucket.get("avg_iap_revenue", 0) / max_iap_revenue if max_iap_revenue else 0.0
        norm_iap_transactions = bucket.get("avg_iap_transactions", 0) / max_iap_transactions if max_iap_transactions else 0.0
        bucket["iap_composite"] = round((norm_iap_users + norm_iap_revenue + norm_iap_transactions) / 3.0, 4)
        bucket["efficiency_score"] = bucket["iap_composite"] / max(bucket.get("avg_d3_churn_pct", 0), 0.05)

    return buckets


def _derive_optimal_aps_band(buckets, window_size):
    eligible = [bucket.copy() for bucket in buckets if bucket["count"] >= max(5, math.ceil(window_size * 0.7))]
    if len(eligible) < 2:
        return {
            "min": DEFAULT_LATE_APS_TARGET_MIN,
            "max": DEFAULT_LATE_APS_TARGET_MAX,
            "source": "fallback",
            "window_size": window_size,
        }

    for bucket in eligible:
        bucket["revenue_per_k_users"] = (
            bucket.get("avg_iap_revenue", 0.0) / max(bucket.get("avg_users", 0.0), 1.0) * 1000.0
        )

    revenue_values = [bucket["revenue_per_k_users"] for bucket in eligible]
    payer_values = [bucket.get("avg_iap_users_pct", 0.0) for bucket in eligible]
    user_values = [bucket.get("avg_users", 0.0) for bucket in eligible]
    churn_values = [bucket.get("avg_d3_churn_pct", 0.0) for bucket in eligible]

    revenue_low, revenue_high = _percentile(revenue_values, 0.10), _percentile(revenue_values, 0.90)
    payer_low, payer_high = _percentile(payer_values, 0.10), _percentile(payer_values, 0.90)
    users_low, users_high = _percentile(user_values, 0.25), _percentile(user_values, 0.90)
    churn_low, churn_high = _percentile(churn_values, 0.10), _percentile(churn_values, 0.85)

    for bucket in eligible:
        revenue_strength = _scale_to_unit(bucket["revenue_per_k_users"], revenue_low, revenue_high)
        payer_strength = _scale_to_unit(bucket.get("avg_iap_users_pct", 0.0), payer_low, payer_high)
        volume_strength = _scale_to_unit(bucket.get("avg_users", 0.0), users_low, users_high)
        churn_penalty = _scale_to_unit(bucket.get("avg_d3_churn_pct", 0.0), churn_low, churn_high)
        churn_efficiency = 1.0 - churn_penalty

        bucket["optimization_score"] = (
            (0.75 * revenue_strength + 0.25 * payer_strength)
            * (0.35 + 0.65 * churn_efficiency)
            * (0.55 + 0.45 * volume_strength)
        )

    weighted_aps = [
        (bucket["avg_aps"], max(bucket.get("optimization_score", 0.0), 0.01) ** 3)
        for bucket in eligible
    ]
    target_min = round(max(_weighted_percentile(weighted_aps, 0.30) - 0.05, 0.5), 2)
    target_max = round(_weighted_percentile(weighted_aps, 0.70) + 0.05, 2)

    if target_min >= target_max:
        aps_values = [bucket["avg_aps"] for bucket in eligible]
        center = round(statistics.mean(aps_values), 2)
        target_min = max(round(center - 0.15, 2), 0.5)
        target_max = round(center + 0.15, 2)

    return {
        "min": target_min,
        "max": target_max,
        "source": "optimized",
        "window_count": len(eligible),
        "window_size": window_size,
        "method": "weighted_revenue_churn",
    }


def _playtime_col(df):
    if "real_playtime" in df.columns and df["real_playtime"].notna().any():
        return "real_playtime"
    return "playtime"


def _scale_to_unit(value, low, high):
    if high <= low:
        return 0.5
    return max(0.0, min(1.0, (value - low) / (high - low)))


def _percentile(values, quantile):
    ordered = sorted(values)
    if not ordered:
        return 0.0

    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = math.ceil(index)
    if lower == upper:
        return float(ordered[lower])

    fraction = index - lower
    return float(ordered[lower] * (1.0 - fraction) + ordered[upper] * fraction)


def _weighted_percentile(weighted_values, quantile):
    ordered = sorted(weighted_values, key=lambda item: item[0])
    total_weight = sum(weight for _, weight in ordered)
    if total_weight <= 0:
        return float(ordered[-1][0]) if ordered else 0.0

    threshold = total_weight * quantile
    cumulative_weight = 0.0
    for value, weight in ordered:
        cumulative_weight += weight
        if cumulative_weight >= threshold:
            return float(value)

    return float(ordered[-1][0])


def _neighbor_average(buckets, index, key):
    values = []
    for neighbor_index in range(max(0, index - 1), min(len(buckets), index + 2)):
        values.append(float(buckets[neighbor_index].get(key, 0.0)))
    return sum(values) / max(len(values), 1)


def _format_bucket_zone_range(buckets):
    if not buckets:
        return None

    low = buckets[0]["low_aps"]
    high = buckets[-1]["high_aps"]
    if high is None:
        return f"{low:.1f}+"
    return f"{low:.1f}\u2013{high:.1f}"
