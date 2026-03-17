"""
LD Wizard — Phase 3: Drop-off Analysis
Identifies drop-off spikes, classifies drop-off zones, correlates drop-offs
with difficulty and churn, and provides actionable level-specific insights.
"""

import pandas as pd
import numpy as np
from engine.parser import DIFFICULTY_ORDER


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Rolling window for smoothing and spike detection
ROLLING_WINDOW = 15

# Spike thresholds (relative to rolling average)
SPIKE_WARNING = 2.0
SPIKE_CRITICAL = 3.5

# Zone classification thresholds (cumulative user loss within a zone)
ZONE_LOSS_WARNING = 0.05   # 5% funnel loss in a single zone
ZONE_LOSS_CRITICAL = 0.10  # 10% funnel loss


def compute_dropoff_analysis(df):
    """
    Full drop-off analysis.

    Args:
        df: Enriched DataFrame from parser

    Returns:
        dict with keys:
            - dropoff_by_level: list per level with drop-off metrics
            - spikes: list of detected drop-off spikes
            - zones: list of drop-off concentration zones
            - churn_correlation: correlation between drop-off and churn metrics
            - bracket_dropoff: average drop-off by bracket
            - insights: list of string insights
    """
    required = ["level", "users", "target_bracket"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "dropoff_by_level": [], "spikes": [], "zones": [],
            "churn_correlation": {}, "bracket_dropoff": [],
            "insights": [f"Missing columns: {', '.join(missing)}"],
        }

    df = df.copy().sort_values("level").reset_index(drop=True)

    # Ensure dropoff_rate exists
    if "dropoff_rate" not in df.columns:
        df["dropoff_rate"] = (df["users"] - df["users"].shift(-1)) / df["users"]
        df.loc[df.index[-1], "dropoff_rate"] = 0

    # Absolute user loss per level
    df["user_loss"] = df["users"] - df["users"].shift(-1)
    df.loc[df.index[-1], "user_loss"] = 0

    # Rolling average for comparison
    df["dropoff_rolling_avg"] = df["dropoff_rate"].rolling(
        window=ROLLING_WINDOW, center=True, min_periods=3
    ).mean()
    df["dropoff_rolling_avg"] = df["dropoff_rolling_avg"].fillna(df["dropoff_rate"].mean())

    # --- 1. Per-level drop-off data ---
    dropoff_by_level = []
    for _, row in df.iterrows():
        entry = {
            "level": int(row["level"]),
            "bracket": row["target_bracket"] if pd.notna(row.get("target_bracket")) else None,
            "users": int(row["users"]) if pd.notna(row.get("users")) else None,
            "user_loss": int(row["user_loss"]) if pd.notna(row.get("user_loss")) else 0,
            "dropoff_rate": round(float(row["dropoff_rate"]), 5) if pd.notna(row.get("dropoff_rate")) else 0,
            "rolling_avg": round(float(row["dropoff_rolling_avg"]), 5),
            "aps": round(float(row["aps"]), 3) if "aps" in df.columns and pd.notna(row.get("aps")) else None,
            "combined_churn": round(float(row["combined_churn"]), 4) if "combined_churn" in df.columns and pd.notna(row.get("combined_churn")) else None,
            "completion_rate": round(float(row["completion_rate"]), 4) if "completion_rate" in df.columns and pd.notna(row.get("completion_rate")) else None,
        }
        dropoff_by_level.append(entry)

    # --- 2. Spike detection ---
    spikes = _detect_spikes(df)

    # --- 3. Drop-off concentration zones ---
    zones = _find_dropoff_zones(df)

    # --- 4. Churn correlation ---
    churn_corr = _compute_churn_correlation(df)

    # --- 5. Bracket-level drop-off ---
    bracket_dropoff = _bracket_dropoff_summary(df)

    # --- 6. Insights ---
    insights = _generate_dropoff_insights(df, spikes, zones, churn_corr, bracket_dropoff)

    return {
        "dropoff_by_level": dropoff_by_level,
        "spikes": spikes,
        "zones": zones,
        "churn_correlation": churn_corr,
        "bracket_dropoff": bracket_dropoff,
        "insights": insights,
    }


def _detect_spikes(df):
    """Detect levels where drop-off significantly exceeds the local rolling average."""
    spikes = []
    for _, row in df.iterrows():
        dr = row["dropoff_rate"]
        avg = row["dropoff_rolling_avg"]
        if dr < 0.003 or avg < 0.001:
            continue

        ratio = dr / avg
        if ratio >= SPIKE_WARNING:
            severity = "critical" if ratio >= SPIKE_CRITICAL else "warning"
            spikes.append({
                "level": int(row["level"]),
                "bracket": row["target_bracket"] if pd.notna(row.get("target_bracket")) else None,
                "dropoff_rate": round(float(dr), 5),
                "rolling_avg": round(float(avg), 5),
                "ratio": round(float(ratio), 2),
                "user_loss": int(row["user_loss"]) if pd.notna(row.get("user_loss")) else 0,
                "severity": severity,
                "aps": round(float(row["aps"]), 3) if "aps" in df.columns and pd.notna(row.get("aps")) else None,
                "combined_churn": round(float(row["combined_churn"]), 4) if "combined_churn" in df.columns and pd.notna(row.get("combined_churn")) else None,
            })

    spikes.sort(key=lambda x: (0 if x["severity"] == "critical" else 1, -x["ratio"]))
    return spikes


def _find_dropoff_zones(df):
    """
    Find contiguous zones where cumulative user loss is concentrated.
    Uses a sliding window approach to find the worst zones.
    """
    zones = []
    n = len(df)
    if n < 5:
        return zones

    total_users_start = float(df["users"].iloc[0])
    if total_users_start == 0:
        return zones

    window_sizes = [5, 10, 15]
    for w in window_sizes:
        for start in range(0, n - w + 1, max(1, w // 2)):
            end = start + w
            chunk = df.iloc[start:end]
            users_start = float(chunk["users"].iloc[0])
            users_end = float(chunk["users"].iloc[-1])
            if users_start == 0:
                continue

            zone_loss = (users_start - users_end) / total_users_start
            zone_dropoff = (users_start - users_end) / users_start

            if zone_loss >= ZONE_LOSS_WARNING:
                severity = "critical" if zone_loss >= ZONE_LOSS_CRITICAL else "warning"
                dominant = chunk["target_bracket"].mode().iloc[0] if len(chunk["target_bracket"].mode()) > 0 else None
                zones.append({
                    "start_level": int(chunk["level"].iloc[0]),
                    "end_level": int(chunk["level"].iloc[-1]),
                    "window": w,
                    "funnel_loss_pct": round(float(zone_loss), 4),
                    "zone_dropoff_pct": round(float(zone_dropoff), 4),
                    "user_loss": int(users_start - users_end),
                    "severity": severity,
                    "dominant_bracket": dominant,
                    "avg_aps": round(float(chunk["aps"].mean()), 3) if "aps" in chunk.columns else None,
                })

    # Deduplicate overlapping zones: keep the highest-loss zone for each start level
    zones.sort(key=lambda z: (-z["funnel_loss_pct"], z["start_level"]))
    seen_levels = set()
    deduped = []
    for z in zones:
        key = z["start_level"]
        if key not in seen_levels:
            deduped.append(z)
            seen_levels.add(key)
        if len(deduped) >= 20:
            break

    return deduped


def _compute_churn_correlation(df):
    """Compute correlation between drop-off rate and churn metrics."""
    corr = {}
    churn_cols = [
        ("combined_churn", "Combined Churn"),
        ("churn", "Session Churn"),
        ("churn_3d", "D3 Churn"),
        ("churn_7d", "D7 Churn"),
    ]

    for col, label in churn_cols:
        if col in df.columns and "dropoff_rate" in df.columns:
            valid = df[[col, "dropoff_rate"]].dropna()
            if len(valid) > 5:
                r = float(valid[col].corr(valid["dropoff_rate"]))
                corr[label] = round(r, 3) if not np.isnan(r) else None

    # Also correlate with APS and completion
    if "aps" in df.columns and "dropoff_rate" in df.columns:
        valid = df[["aps", "dropoff_rate"]].dropna()
        if len(valid) > 5:
            r = float(valid["aps"].corr(valid["dropoff_rate"]))
            corr["APS (Difficulty)"] = round(r, 3) if not np.isnan(r) else None

    if "completion_rate" in df.columns and "dropoff_rate" in df.columns:
        valid = df[["completion_rate", "dropoff_rate"]].dropna()
        if len(valid) > 5:
            r = float(valid["completion_rate"].corr(valid["dropoff_rate"]))
            corr["Completion Rate"] = round(r, 3) if not np.isnan(r) else None

    return corr


def _bracket_dropoff_summary(df):
    """Average drop-off metrics by bracket."""
    result = []
    for bracket in DIFFICULTY_ORDER:
        subset = df[df["target_bracket"] == bracket]
        if len(subset) == 0:
            continue
        result.append({
            "bracket": bracket,
            "count": int(len(subset)),
            "avg_dropoff": round(float(subset["dropoff_rate"].mean()), 5),
            "max_dropoff": round(float(subset["dropoff_rate"].max()), 5),
            "total_user_loss": int(subset["user_loss"].sum()),
            "avg_combined_churn": round(float(subset["combined_churn"].mean()), 4) if "combined_churn" in subset.columns else None,
            "avg_aps": round(float(subset["aps"].mean()), 3) if "aps" in subset.columns else None,
        })
    return result


def _generate_dropoff_insights(df, spikes, zones, churn_corr, bracket_dropoff):
    """Generate human-readable insights about drop-offs."""
    insights = []

    # Total user loss
    if "users" in df.columns and len(df) > 1:
        start_users = int(df["users"].iloc[0])
        end_users = int(df["users"].iloc[-1])
        total_loss = start_users - end_users
        loss_pct = total_loss / start_users * 100 if start_users > 0 else 0
        insights.append(
            f"Total funnel loss: {total_loss:,} users ({loss_pct:.1f}%) across {len(df)} levels."
        )

    # Spike summary
    crit_spikes = [s for s in spikes if s["severity"] == "critical"]
    if crit_spikes:
        levels = ", ".join([f"L{s['level']}" for s in crit_spikes[:5]])
        insights.append(f"{len(crit_spikes)} critical drop-off spike(s): {levels}. These levels lose players at 3.5×+ the local average.")

    # Worst zone
    if zones:
        worst = zones[0]
        insights.append(
            f"Worst drop-off zone: L{worst['start_level']}–L{worst['end_level']} "
            f"({worst['funnel_loss_pct']*100:.1f}% of total funnel lost, dominant: {worst['dominant_bracket']})."
        )

    # Churn correlation insights
    if "Combined Churn" in churn_corr and churn_corr["Combined Churn"] is not None:
        r = churn_corr["Combined Churn"]
        if r > 0.5:
            insights.append(f"Strong positive correlation (r={r}) between combined churn and drop-off — high-churn levels are where players leave.")
        elif r > 0.3:
            insights.append(f"Moderate correlation (r={r}) between combined churn and drop-off rate.")

    if "APS (Difficulty)" in churn_corr and churn_corr["APS (Difficulty)"] is not None:
        r = churn_corr["APS (Difficulty)"]
        if r > 0.4:
            insights.append(f"Positive correlation (r={r}) between APS and drop-off — harder levels drive more player loss.")
        elif r < -0.2:
            insights.append(f"Negative correlation (r={r}) between APS and drop-off — easier levels may bore players, causing exits.")

    # Bracket with highest drop-off
    if bracket_dropoff:
        worst_bracket = max(bracket_dropoff, key=lambda b: b["avg_dropoff"])
        insights.append(
            f"Highest avg drop-off bracket: {worst_bracket['bracket']} "
            f"({worst_bracket['avg_dropoff']*100:.2f}% per level, {worst_bracket['total_user_loss']:,} users lost total)."
        )

    return insights
