"""
LD Wizard — Phase 2: Level Performance Ranking
Ranks levels by a composite performance score that respects bracket-specific goals.
Identifies best/worst performers and outlier levels.
"""

import pandas as pd
import numpy as np
from engine.parser import DIFFICULTY_ORDER
from engine.analysis.difficulty_bands import build_aps_quantile_bands, classify_aps_bracket, format_band_label


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
    required = ["level", "combined_churn", "completion_rate", "aps"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "rankings": [], "best_per_bracket": {}, "worst_per_bracket": {},
            "outliers": [], "insights": [f"Missing columns: {', '.join(missing)}"],
        }

    df = df.copy().sort_values("level").reset_index(drop=True)
    aps_bands = build_aps_quantile_bands(df["aps"].tolist())
    if not aps_bands:
        return {
            "rankings": [], "best_per_bracket": {}, "worst_per_bracket": {},
            "outliers": [], "insights": ["Unable to derive APS peer brackets from the current scope."],
        }
    df["peer_bracket"] = df["aps"].apply(lambda value: classify_aps_bracket(value, aps_bands))
    df["peer_band_label"] = df["peer_bracket"].map(
        lambda bracket: format_band_label(
            aps_bands.get(bracket, {}).get("min"),
            aps_bands.get(bracket, {}).get("max"),
            open_ended=bracket == DIFFICULTY_ORDER[-1],
        )
    )

    users = df["users"].replace(0, np.nan) if "users" in df.columns else pd.Series(np.nan, index=df.index)
    df["revenue_per_k_users"] = (
        df.get("iap_revenue", pd.Series(0.0, index=df.index)).fillna(0) / users
    ).replace([np.inf, -np.inf], np.nan).fillna(0) * 1000.0
    df["transactions_per_k_users"] = (
        df.get("iap_transactions", pd.Series(0.0, index=df.index)).fillna(0) / users
    ).replace([np.inf, -np.inf], np.nan).fillna(0) * 1000.0
    df["payer_rate"] = df.get("iap_users_pct", pd.Series(0.0, index=df.index)).fillna(0).clip(lower=0, upper=1)
    df["volume_strength"] = 1.0 if "users" not in df.columns else _scale_series(df["users"].fillna(0), 0.25, 0.90)
    df["revenue_strength"] = _scale_series(df["revenue_per_k_users"], 0.10, 0.90)
    df["payer_strength"] = _scale_series(df["payer_rate"], 0.10, 0.90)
    df["transaction_strength"] = _scale_series(df["transactions_per_k_users"], 0.10, 0.90)
    df["completion_strength"] = df["completion_rate"].fillna(0).clip(lower=0, upper=1)
    df["churn_penalty"] = _scale_series(df["combined_churn"].fillna(0).clip(lower=0, upper=1), 0.10, 0.85)
    df["churn_efficiency"] = 1.0 - df["churn_penalty"]
    df["monetization_strength"] = (
        0.60 * df["revenue_strength"]
        + 0.25 * df["payer_strength"]
        + 0.15 * df["transaction_strength"]
    ).clip(lower=0, upper=1)

    # Fill NaN
    for col in ["combined_churn", "completion_rate", "monetization_strength", "revenue_per_k_users", "transactions_per_k_users", "payer_rate"]:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    # Monetization leads; churn acts like a tax; completion and volume stop
    # tiny low-friction levels from dominating without revenue.
    df["perf_score_raw"] = (
        (0.72 * df["monetization_strength"] + 0.28 * df["completion_strength"])
        * (0.30 + 0.70 * df["churn_efficiency"])
        * (0.55 + 0.45 * df["volume_strength"])
    ).round(4)

    # --- APS-peer-relative normalization ---
    df["perf_score"] = _normalize_scores_by_bracket(df, bracket_col="peer_bracket")

    # --- Build ranking list ---
    rankings = []
    for _, row in df.iterrows():
        entry = {
            "level": int(row["level"]),
            "bracket": row["peer_bracket"],
            "peer_band_label": row["peer_band_label"],
            "target_bracket": row["target_bracket"] if "target_bracket" in df.columns else None,
            "perf_score": row["perf_score"],
            "perf_score_raw": round(float(row["perf_score_raw"]), 4),
            "aps": round(float(row["aps"]), 3) if pd.notna(row.get("aps")) else None,
            "combined_churn": round(float(row["combined_churn"]), 4),
            "completion_rate": round(float(row["completion_rate"]), 4),
            "revenue_score": round(float(row["monetization_strength"]), 4),
            "revenue_per_k_users": round(float(row["revenue_per_k_users"]), 2),
            "transactions_per_k_users": round(float(row["transactions_per_k_users"]), 2),
            "iap_users_pct": round(float(row["payer_rate"]) * 100, 3),
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
    outliers = _detect_outliers(df, bracket_col="peer_bracket")

    # --- Insights ---
    insights = _generate_ranking_insights(df, rankings, best_per_bracket, worst_per_bracket, outliers)

    return {
        "rankings": rankings,
        "best_per_bracket": best_per_bracket,
        "worst_per_bracket": worst_per_bracket,
        "outliers": outliers,
        "insights": insights,
        "band_method": "quantile",
        "bands": [
            {
                "bracket": bracket,
                "min": round(band["min"], 3),
                "max": round(band["max"], 3),
                "label": format_band_label(band["min"], band["max"], open_ended=bracket == DIFFICULTY_ORDER[-1]),
            }
            for bracket, band in aps_bands.items()
        ],
    }


def _normalize_scores_by_bracket(df, bracket_col="target_bracket", min_bracket_size=5):
    """
    Normalize perf_score_raw within each difficulty bracket so that levels
    compete against peers of similar difficulty.

    For each bracket with enough levels (>= min_bracket_size):
      1. Compute z-score: (raw - bracket_mean) / bracket_std
      2. Convert to percentile rank within the bracket (0.0 – 1.0)

    Brackets with fewer than min_bracket_size levels use the global
    percentile as a fallback.

    Returns a Series aligned with df.index.
    """
    result = pd.Series(0.5, index=df.index)  # default mid-range
    global_scores = df["perf_score_raw"]

    for bracket in df[bracket_col].dropna().unique():
        mask = df[bracket_col] == bracket
        subset = df.loc[mask, "perf_score_raw"]

        if len(subset) < min_bracket_size:
            # Fallback: percentile rank within global scores
            result.loc[mask] = global_scores.rank(pct=True).loc[mask]
        else:
            # Percentile rank within this bracket (handles ties gracefully)
            result.loc[mask] = subset.rank(pct=True)

    return result.round(4)


def _detect_outliers(df, bracket_col="peer_bracket"):
    """
    Detect levels whose composite score is an outlier within their bracket
    (Z-score based).
    """
    outliers = []
    raw_col = "perf_score_raw" if "perf_score_raw" in df.columns else "perf_score"
    for bracket in DIFFICULTY_ORDER:
        subset = df[df[bracket_col] == bracket]
        if len(subset) < 5:
            continue

        scores = subset[raw_col]
        mean = scores.mean()
        std = scores.std()
        if std < 0.001:
            continue

        for _, row in subset.iterrows():
            z = (row[raw_col] - mean) / std
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


def _scale_series(series, low_quantile, high_quantile):
    values = series.fillna(0).astype(float).to_numpy()
    if len(values) == 0:
        return pd.Series(0.5, index=series.index)

    low = float(np.quantile(values, low_quantile))
    high = float(np.quantile(values, high_quantile))
    if high <= low:
        return pd.Series(0.5, index=series.index)

    scaled = (series.astype(float) - low) / (high - low)
    return scaled.clip(lower=0.0, upper=1.0).fillna(0.0)


def _generate_ranking_insights(df, rankings, best, worst, outliers):
    """Generate human-readable insights about level performance."""
    insights = []

    # Overall score distribution
    scores = [r["perf_score"] for r in rankings]
    if scores:
        avg = sum(scores) / len(scores)
        insights.append(
            f"Performance scores are APS-peer-relative: levels compete inside adaptive APS quintiles, not by target tag. "
            f"Average: {avg:.3f}, range: {min(scores):.3f} – {max(scores):.3f}."
        )

    # Best overall level
    if rankings:
        top = rankings[0]
        insights.append(
            f"Best performing level: L{top['level']} ({top['bracket']}) — "
            f"score {top['perf_score']:.3f}, revenue/1k {top['revenue_per_k_users']:.1f}, "
            f"churn {top['combined_churn']*100:.2f}%."
        )

    # Worst overall level
    if len(rankings) > 1:
        bottom = rankings[-1]
        insights.append(
            f"Worst performing level: L{bottom['level']} ({bottom['bracket']}) — "
            f"score {bottom['perf_score']:.3f}, revenue/1k {bottom['revenue_per_k_users']:.1f}, "
            f"churn {bottom['combined_churn']*100:.2f}%."
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
