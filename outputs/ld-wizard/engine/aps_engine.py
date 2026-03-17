"""
LD Wizard — Adaptive APS Range System (Step 3)
Computes optimal APS ranges per difficulty bracket, flags anomalous levels,
and assesses bracket health — all driven by bracket-specific goal priorities.
"""

import pandas as pd
import numpy as np
from engine.parser import DIFFICULTY_ORDER, REVENUE_WEIGHTS


# ---------------------------------------------------------------------------
# Bracket goal weights — how much each metric matters per bracket
# Keys: combined_churn (lower is better), completion_rate (higher is better),
#        revenue_score (higher is better — composite of IAP + EGP + sink)
# Values are relative weights that sum to 1.0 per bracket.
# ---------------------------------------------------------------------------

BRACKET_GOALS = {
    "Easy": {
        "combined_churn": 0.55,      # Primary: minimize churn
        "completion_rate": 0.40,     # Primary: maximize completion
        "revenue_score": 0.05,       # Not a goal — near-zero weight
    },
    "Medium": {
        "combined_churn": 0.40,      # Still primary
        "completion_rate": 0.35,     # Still primary
        "revenue_score": 0.25,       # Starting to matter (boosters, soft currency)
    },
    "Hard": {
        "combined_churn": 0.33,      # Equal weight
        "completion_rate": 0.33,     # Equal weight
        "revenue_score": 0.34,       # Equal weight
    },
    "Super Hard": {
        "combined_churn": 0.35,      # Losing committed players here is expensive
        "completion_rate": 0.20,     # Less critical — these are challenge levels
        "revenue_score": 0.45,       # Revenue must be high
    },
    "Wall": {
        "combined_churn": 0.25,      # Mitigate but not primary
        "completion_rate": 0.15,     # Least priority
        "revenue_score": 0.60,       # Highest monetization pressure
    },
}


def _compute_revenue_score(df):
    """
    Compute a weighted revenue score per level from available monetization metrics.
    Weights reflect actual revenue impact: IAP > EGP > Boosters > Sink.
    """
    numerator = pd.Series(0.0, index=df.index)
    total_weight = 0.0
    for col, weight in REVENUE_WEIGHTS.items():
        if col in df.columns:
            numerator += df[col].fillna(0) * weight
            total_weight += weight
    if total_weight > 0:
        return numerator / total_weight
    return pd.Series(0.0, index=df.index)


def _compute_bracket_score(subset, goals):
    """
    Compute a goal-weighted health score for a bracket's levels.
    Higher score = better alignment with bracket goals.
    Returns a score per level (Series).
    """
    # Churn component: lower is better → invert
    churn_score = 1.0 - subset["combined_churn"].clip(0, 1)

    # Completion: higher is better (already 0-1)
    completion_score = subset["completion_rate"].clip(0, 1)

    # Revenue score
    revenue_score = subset["_revenue_score"].clip(0, 1)

    weighted = (
        goals["combined_churn"] * churn_score
        + goals["completion_rate"] * completion_score
        + goals["revenue_score"] * revenue_score
    )
    return weighted


# ---------------------------------------------------------------------------
# Main APS Range computation
# ---------------------------------------------------------------------------

def compute_aps_ranges(df):
    """
    Compute adaptive APS ranges per bracket, flag anomalous levels,
    and assess bracket health.

    Args:
        df: Enriched DataFrame from parser (must contain target_bracket, aps, combined_churn, etc.)

    Returns:
        dict with keys:
            - ranges: list of dicts per bracket with min/max/recommended APS
            - flags: list of dicts for flagged levels
            - health: list of dicts with bracket health assessments
            - insights: list of string insights
    """
    if "aps" not in df.columns or "target_bracket" not in df.columns:
        return {"ranges": [], "flags": [], "health": [], "insights": ["Missing required columns for APS analysis."]}

    # Add revenue score column
    df = df.copy()
    df["_revenue_score"] = _compute_revenue_score(df)

    # Fill NaN in key columns for computation
    for col in ["combined_churn", "completion_rate", "aps", "_revenue_score"]:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    # --- Step 1: Compute per-bracket statistics ---
    bracket_stats = []
    for bracket in DIFFICULTY_ORDER:
        subset = df[df["target_bracket"] == bracket]
        if len(subset) == 0:
            continue

        goals = BRACKET_GOALS[bracket]
        scores = _compute_bracket_score(subset, goals)

        # Use percentile-based range to exclude extreme outliers
        aps_values = subset["aps"]
        p10 = float(np.percentile(aps_values, 10))
        p90 = float(np.percentile(aps_values, 90))
        p25 = float(np.percentile(aps_values, 25))
        p75 = float(np.percentile(aps_values, 75))

        # "Sweet spot" — APS range of top-performing levels (top 30% by goal score)
        score_threshold = scores.quantile(0.70)
        top_levels = subset[scores >= score_threshold]
        if len(top_levels) > 0:
            sweet_min = float(top_levels["aps"].quantile(0.15))
            sweet_max = float(top_levels["aps"].quantile(0.85))
        else:
            sweet_min = p25
            sweet_max = p75

        bracket_stats.append({
            "bracket": bracket,
            "count": int(len(subset)),
            "aps_min": round(float(aps_values.min()), 3),
            "aps_max": round(float(aps_values.max()), 3),
            "aps_mean": round(float(aps_values.mean()), 3),
            "aps_median": round(float(aps_values.median()), 3),
            "aps_p10": round(p10, 3),
            "aps_p90": round(p90, 3),
            "aps_p25": round(p25, 3),
            "aps_p75": round(p75, 3),
            "recommended_min": round(sweet_min, 3),
            "recommended_max": round(sweet_max, 3),
            "avg_combined_churn": round(float(subset["combined_churn"].mean()), 4),
            "avg_completion": round(float(subset["completion_rate"].mean()), 4),
            "avg_revenue_score": round(float(subset["_revenue_score"].mean()), 4),
            "avg_goal_score": round(float(scores.mean()), 4),
        })

    # --- Step 2: Enforce non-overlapping ranges ---
    # Adjust recommended ranges so they don't overlap and maintain progressive order
    for i in range(1, len(bracket_stats)):
        prev = bracket_stats[i - 1]
        curr = bracket_stats[i]
        if curr["recommended_min"] <= prev["recommended_max"]:
            # Set gap midpoint as boundary
            midpoint = (prev["recommended_max"] + curr["recommended_min"]) / 2
            # Nudge slightly to create a gap
            prev["recommended_max"] = round(midpoint - 0.005, 3)
            curr["recommended_min"] = round(midpoint + 0.005, 3)
            # Ensure min < max for each bracket
            if curr["recommended_min"] >= curr["recommended_max"]:
                curr["recommended_min"] = round(curr["recommended_max"] - 0.01, 3)
            if prev["recommended_min"] >= prev["recommended_max"]:
                prev["recommended_max"] = round(prev["recommended_min"] + 0.01, 3)

    # Build a lookup for quick range access
    range_lookup = {s["bracket"]: s for s in bracket_stats}

    # --- Step 3: Flag anomalous levels ---
    flags = []
    for _, row in df.iterrows():
        bracket = row["target_bracket"]
        if bracket not in range_lookup:
            continue

        stats = range_lookup[bracket]
        level = int(row["level"])
        aps = row["aps"]
        level_flags = []

        # Flag: APS outside recommended range
        if aps < stats["recommended_min"]:
            level_flags.append({
                "type": "aps_too_low",
                "severity": "warning",
                "message": f"APS ({aps:.3f}) is below {bracket} range ({stats['recommended_min']:.3f}–{stats['recommended_max']:.3f}). Level may be too easy for its bracket.",
            })
        elif aps > stats["recommended_max"]:
            severity = "critical" if aps > stats["aps_p90"] else "warning"
            level_flags.append({
                "type": "aps_too_high",
                "severity": severity,
                "message": f"APS ({aps:.3f}) exceeds {bracket} range ({stats['recommended_min']:.3f}–{stats['recommended_max']:.3f}). Level may be too hard for its bracket.",
            })

        # Flag: High churn for bracket
        churn_threshold = stats["avg_combined_churn"] * 1.8
        if row["combined_churn"] > churn_threshold and row["combined_churn"] > 0.02:
            level_flags.append({
                "type": "high_churn",
                "severity": "critical" if row["combined_churn"] > churn_threshold * 1.3 else "warning",
                "message": f"Combined churn ({row['combined_churn']*100:.2f}%) is significantly above {bracket} average ({stats['avg_combined_churn']*100:.2f}%).",
            })

        # Flag: Low completion for bracket
        completion_threshold = stats["avg_completion"] * 0.85
        if row["completion_rate"] < completion_threshold and row["completion_rate"] < 0.95:
            level_flags.append({
                "type": "low_completion",
                "severity": "warning",
                "message": f"Completion rate ({row['completion_rate']*100:.1f}%) is below {bracket} average ({stats['avg_completion']*100:.1f}%).",
            })

        # Flag: Revenue underperforming on monetization brackets
        if bracket in ("Hard", "Super Hard", "Wall"):
            if row["_revenue_score"] < stats["avg_revenue_score"] * 0.5 and stats["avg_revenue_score"] > 0.01:
                level_flags.append({
                    "type": "low_revenue",
                    "severity": "warning",
                    "message": f"Revenue metrics are significantly below {bracket} average. This level may not be fulfilling its monetization role.",
                })

        if level_flags:
            flags.append({
                "level": level,
                "bracket": bracket,
                "aps": round(aps, 3),
                "flags": level_flags,
            })

    # --- Step 4: Bracket health assessment ---
    health = []
    insights = []

    for i, stats in enumerate(bracket_stats):
        bracket = stats["bracket"]
        goals = BRACKET_GOALS[bracket]
        issues = []

        # Check APS range width
        aps_range_width = stats["recommended_max"] - stats["recommended_min"]
        if aps_range_width > 1.5:
            issues.append({
                "type": "wide_range",
                "message": f"APS range is very wide ({aps_range_width:.2f}). Difficulty within {bracket} levels is inconsistent.",
            })
        elif aps_range_width < 0.05 and stats["count"] > 5:
            issues.append({
                "type": "narrow_range",
                "message": f"APS range is very narrow ({aps_range_width:.3f}). {bracket} levels may lack variety.",
            })

        # Check goal balance
        if bracket in ("Hard", "Super Hard", "Wall"):
            if stats["avg_revenue_score"] < 0.01 and goals["revenue_score"] > 0.3:
                issues.append({
                    "type": "revenue_underperforming",
                    "message": f"{bracket} should drive monetization but revenue metrics are near zero.",
                })
            if stats["avg_combined_churn"] > 0.08:
                issues.append({
                    "type": "high_bracket_churn",
                    "message": f"Average combined churn ({stats['avg_combined_churn']*100:.1f}%) is high for {bracket}. Players may be leaving at these levels.",
                })

        if bracket in ("Easy", "Medium"):
            if stats["avg_completion"] < 0.90:
                issues.append({
                    "type": "low_bracket_completion",
                    "message": f"Average completion ({stats['avg_completion']*100:.1f}%) is low for {bracket}. These levels should be more accessible.",
                })

        # Check APS progression vs previous bracket
        if i > 0:
            prev = bracket_stats[i - 1]
            if stats["aps_mean"] < prev["aps_mean"]:
                issue_msg = f"{bracket} has lower average APS ({stats['aps_mean']:.3f}) than {prev['bracket']} ({prev['aps_mean']:.3f}). Difficulty progression is inverted."
                issues.append({"type": "inverted_progression", "message": issue_msg})
                insights.append(issue_msg)

        health.append({
            "bracket": bracket,
            "status": "healthy" if not issues else ("warning" if len(issues) <= 1 else "critical"),
            "goal_score": stats["avg_goal_score"],
            "issues": issues,
        })

    # --- Step 5: Global insights ---
    # Overall APS trend
    if len(bracket_stats) >= 2:
        first_aps = bracket_stats[0]["aps_mean"]
        last_aps = bracket_stats[-1]["aps_mean"]
        spread = last_aps - first_aps
        if spread < 0.3:
            insights.append(f"Overall APS spread is narrow ({spread:.2f}). There may not be enough difficulty differentiation between brackets.")
        elif spread > 5.0:
            insights.append(f"Overall APS spread is very wide ({spread:.2f}). The difficulty jump between easiest and hardest levels is extreme.")

    # Count flagged levels
    critical_flags = sum(1 for f in flags for fl in f["flags"] if fl["severity"] == "critical")
    warning_flags = sum(1 for f in flags for fl in f["flags"] if fl["severity"] == "warning")
    if critical_flags > 0:
        insights.append(f"{critical_flags} critical flag(s) detected across levels — these need immediate attention.")
    if warning_flags > 10:
        insights.append(f"{warning_flags} warning flags detected — consider reviewing bracket assignments and level tuning.")

    # Check for significant overlap in raw APS between adjacent brackets
    for i in range(1, len(bracket_stats)):
        prev = bracket_stats[i - 1]
        curr = bracket_stats[i]
        if prev["aps_p75"] > curr["aps_p25"]:
            insights.append(
                f"APS overlap between {prev['bracket']} (P75: {prev['aps_p75']:.3f}) and "
                f"{curr['bracket']} (P25: {curr['aps_p25']:.3f}). "
                f"Some {prev['bracket']} levels are harder than some {curr['bracket']} levels."
            )

    return {
        "ranges": bracket_stats,
        "flags": flags,
        "health": health,
        "insights": insights,
    }
