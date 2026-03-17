"""
LD Wizard — Phase 2: Level Performance Ranking
Ranks levels by a composite performance score that respects bracket-specific goals.
Identifies best/worst performers and outlier levels.
"""

import pandas as pd
import numpy as np
from engine.parser import DIFFICULTY_ORDER, REVENUE_WEIGHTS
from engine.aps_engine import BRACKET_GOALS


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Number of best/worst levels to highlight per bracket
TOP_N = 5
BOTTOM_N = 5

# Outlier detection: Z-score threshold
OUTLIER_Z = 2.0


def compute_ranking(df):
    """
    Rank all levels by a bracket-aware composite performance score.

    The performance score uses the same goal weights from the APS engine
    (churn, completion, revenue) so that "good" means different things
    for Easy vs. Wall levels.

    Args:
        df: Enriched DataFrame from parser

    Returns:
        dict with keys:
            - rankings: list of all levels sorted by score (best first), each with level, bracket, score, metrics
            - best_per_bracket: dict[bracket -> list of top N levels]
            - worst_per_bracket: dict[bracket -> list of bottom N levels]
            - outliers: list of levels that are statistical outliers within their bracket
            - insights: list of string insights
    """
    required = ["level", "target_bracket", "combined_churn", "completion_rate", "aps"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "rankings": [], "best_per_bracket": {}, "worst_per_bracket": {},
            "outliers": [], "insights": [f"Missing columns: {', '.join(missing)}"],
        }

    df = df.copy().sort_values("level").reset_index(drop=True)

    # --- Compute weighted revenue score (reuse weights from parser) ---
    if "_revenue_score" not in df.columns:
        num = pd.Series(0.0, index=df.index)
        tw = 0.0
        for col, w in REVENUE_WEIGHTS.items():
            if col in df.columns:
                num += df[col].fillna(0) * w
                tw += w
        df["_revenue_score"] = (num / tw) if tw > 0 else 0.0

    # Fill NaN
    for col in ["combined_churn", "completion_rate", "_revenue_score"]:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    # --- Compute composite performance score per level ---
    # Uses funnel position weight: early churn is discounted (uncommitted players),
    # late churn is amplified (losing engaged players is costlier).
    has_position_weight = "_funnel_position_weight" in df.columns
    scores = []
    for _, row in df.iterrows():
        bracket = row["target_bracket"]
        goals = BRACKET_GOALS.get(bracket, BRACKET_GOALS.get("Hard", {}))

        # Churn: lower is better → invert
        raw_churn = min(max(row["combined_churn"], 0), 1)
        # Apply funnel position weight to churn penalty:
        # Higher weight at late levels means churn hurts score MORE there.
        # Lower weight at early levels means churn is partially forgiven.
        pos_w = row["_funnel_position_weight"] if has_position_weight else 1.0
        adjusted_churn = min(raw_churn * pos_w, 1.0)
        churn_score = 1.0 - adjusted_churn

        # Completion: higher is better
        completion_score = min(max(row["completion_rate"], 0), 1)
        # Revenue
        revenue_score = min(max(row["_revenue_score"], 0), 1)

        composite = (
            goals.get("combined_churn", 0.33) * churn_score
            + goals.get("completion_rate", 0.33) * completion_score
            + goals.get("revenue_score", 0.34) * revenue_score
        )
        scores.append(round(composite, 4))

    df["perf_score"] = scores

    # --- Build ranking list ---
    rankings = []
    for _, row in df.iterrows():
        entry = {
            "level": int(row["level"]),
            "bracket": row["target_bracket"],
            "perf_score": row["perf_score"],
            "aps": round(float(row["aps"]), 3) if pd.notna(row.get("aps")) else None,
            "combined_churn": round(float(row["combined_churn"]), 4),
            "completion_rate": round(float(row["completion_rate"]), 4),
            "revenue_score": round(float(row["_revenue_score"]), 4),
            "win_rate": round(float(row["win_rate"]), 4) if "win_rate" in df.columns and pd.notna(row.get("win_rate")) else None,
            "users": int(row["users"]) if "users" in df.columns and pd.notna(row.get("users")) else None,
            "dropoff_rate": round(float(row["dropoff_rate"]), 5) if "dropoff_rate" in df.columns and pd.notna(row.get("dropoff_rate")) else None,
        }
        rankings.append(entry)

    # Sort by score descending
    rankings.sort(key=lambda x: x["perf_score"], reverse=True)

    # Add rank
    for i, r in enumerate(rankings):
        r["rank"] = i + 1

    # --- Best / Worst per bracket ---
    best_per_bracket = {}
    worst_per_bracket = {}
    for bracket in DIFFICULTY_ORDER:
        bracket_levels = [r for r in rankings if r["bracket"] == bracket]
        if bracket_levels:
            best_per_bracket[bracket] = bracket_levels[:TOP_N]
            worst_per_bracket[bracket] = bracket_levels[-BOTTOM_N:][::-1]  # worst first

    # --- Outlier detection ---
    outliers = _detect_outliers(df)

    # --- Insights ---
    insights = _generate_ranking_insights(df, rankings, best_per_bracket, worst_per_bracket, outliers)

    return {
        "rankings": rankings,
        "best_per_bracket": best_per_bracket,
        "worst_per_bracket": worst_per_bracket,
        "outliers": outliers,
        "insights": insights,
    }


def _detect_outliers(df):
    """
    Detect levels whose composite score is an outlier within their bracket
    (Z-score based).
    """
    outliers = []
    for bracket in DIFFICULTY_ORDER:
        subset = df[df["target_bracket"] == bracket]
        if len(subset) < 5:
            continue

        scores = subset["perf_score"]
        mean = scores.mean()
        std = scores.std()
        if std < 0.001:
            continue

        for _, row in subset.iterrows():
            z = (row["perf_score"] - mean) / std
            if abs(z) >= OUTLIER_Z:
                outliers.append({
                    "level": int(row["level"]),
                    "bracket": bracket,
                    "perf_score": round(float(row["perf_score"]), 4),
                    "z_score": round(float(z), 2),
                    "direction": "overperforming" if z > 0 else "underperforming",
                    "aps": round(float(row["aps"]), 3) if pd.notna(row.get("aps")) else None,
                    "combined_churn": round(float(row["combined_churn"]), 4),
                    "completion_rate": round(float(row["completion_rate"]), 4),
                })

    outliers.sort(key=lambda x: abs(x["z_score"]), reverse=True)
    return outliers


def _generate_ranking_insights(df, rankings, best, worst, outliers):
    """Generate human-readable insights about level performance."""
    insights = []

    # Overall score distribution
    scores = [r["perf_score"] for r in rankings]
    if scores:
        avg = sum(scores) / len(scores)
        insights.append(f"Average performance score: {avg:.3f}. Scores range from {min(scores):.3f} to {max(scores):.3f}.")

    # Best overall level
    if rankings:
        top = rankings[0]
        insights.append(
            f"Best performing level: L{top['level']} ({top['bracket']}) — "
            f"score {top['perf_score']:.3f}, churn {top['combined_churn']*100:.2f}%, "
            f"completion {top['completion_rate']*100:.1f}%."
        )

    # Worst overall level
    if len(rankings) > 1:
        bottom = rankings[-1]
        insights.append(
            f"Worst performing level: L{bottom['level']} ({bottom['bracket']}) — "
            f"score {bottom['perf_score']:.3f}, churn {bottom['combined_churn']*100:.2f}%, "
            f"completion {bottom['completion_rate']*100:.1f}%."
        )

    # Bracket score comparison
    bracket_avgs = {}
    for bracket in DIFFICULTY_ORDER:
        bracket_scores = [r["perf_score"] for r in rankings if r["bracket"] == bracket]
        if bracket_scores:
            bracket_avgs[bracket] = sum(bracket_scores) / len(bracket_scores)

    if bracket_avgs:
        best_bracket = max(bracket_avgs, key=bracket_avgs.get)
        worst_bracket = min(bracket_avgs, key=bracket_avgs.get)
        if best_bracket != worst_bracket:
            insights.append(
                f"Highest avg score bracket: {best_bracket} ({bracket_avgs[best_bracket]:.3f}). "
                f"Lowest: {worst_bracket} ({bracket_avgs[worst_bracket]:.3f})."
            )

    # Outlier count
    overperf = [o for o in outliers if o["direction"] == "overperforming"]
    underperf = [o for o in outliers if o["direction"] == "underperforming"]
    if overperf:
        insights.append(f"{len(overperf)} level(s) are statistical overperformers within their bracket — study these for best practices.")
    if underperf:
        insights.append(f"{len(underperf)} level(s) are statistical underperformers within their bracket — these need redesign attention.")

    return insights
