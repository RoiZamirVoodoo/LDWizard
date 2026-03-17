"""
LD Wizard — Phase 1: Funnel Pacing Analysis
Analyzes the player funnel progression, detects pacing deficiencies,
identifies steep drop-off zones, and overlays difficulty cadence.
"""

import pandas as pd
import numpy as np
from engine.parser import DIFFICULTY_ORDER, REVENUE_WEIGHTS, FUNNEL_PHASES


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# How many consecutive levels define a "zone" for smoothing
ZONE_WINDOW = 10

# Thresholds for flagging steep drops (relative to zone average)
STEEP_DROP_MULTIPLIER = 2.5   # Drop > 2.5× zone average = steep
CRITICAL_DROP_MULTIPLIER = 4.0  # Drop > 4× zone average = critical

# Expected retention curve shape: exponential decay
# We fit an ideal curve and compare actual pacing against it
IDEAL_CURVE_MIN_RETENTION = 0.02  # Expect at least 2% at end of funnel


def compute_funnel_analysis(df):
    """
    Full funnel pacing analysis.

    Args:
        df: Enriched DataFrame from parser (must contain level, users, funnel_pct,
            target_bracket, combined_churn, aps, dropoff_rate)

    Returns:
        dict with keys:
            - funnel_curve: list of dicts per level (level, users, funnel_pct, bracket, aps)
            - zones: list of dicts per zone (zone_start, zone_end, avg_dropoff, zone_type, bracket_mix)
            - steep_drops: list of dicts for levels with abnormally steep drop-offs
            - pacing_score: overall pacing health score (0-100)
            - cadence: difficulty cadence analysis
            - insights: list of string insights
    """
    required = ["level", "users", "funnel_pct", "target_bracket"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "funnel_curve": [], "zones": [], "steep_drops": [],
            "pacing_score": None, "cadence": {}, "insights": [f"Missing columns: {', '.join(missing)}"],
        }

    df = df.copy().sort_values("level").reset_index(drop=True)

    # Ensure dropoff_rate exists
    if "dropoff_rate" not in df.columns and "users" in df.columns:
        df["dropoff_rate"] = (df["users"] - df["users"].shift(-1)) / df["users"]
        df.loc[df.index[-1], "dropoff_rate"] = 0

    # Compute weighted revenue_score if not present
    if "_revenue_score" not in df.columns:
        num = pd.Series(0.0, index=df.index)
        tw = 0.0
        for col, w in REVENUE_WEIGHTS.items():
            if col in df.columns:
                num += df[col].fillna(0) * w
                tw += w
        df["_revenue_score"] = (num / tw) if tw > 0 else 0.0

    # --- 1. Funnel Curve ---
    funnel_curve = []
    for _, row in df.iterrows():
        entry = {
            "level": int(row["level"]),
            "users": int(row["users"]) if pd.notna(row.get("users")) else None,
            "funnel_pct": round(float(row["funnel_pct"]), 4) if pd.notna(row.get("funnel_pct")) else None,
            "bracket": row["target_bracket"] if pd.notna(row.get("target_bracket")) else None,
            "aps": round(float(row["aps"]), 3) if pd.notna(row.get("aps")) else None,
            "dropoff_rate": round(float(row["dropoff_rate"]), 4) if pd.notna(row.get("dropoff_rate")) else None,
            "combined_churn": round(float(row["combined_churn"]), 4) if "combined_churn" in df.columns and pd.notna(row.get("combined_churn")) else None,
            "completion_rate": round(float(row["completion_rate"]), 4) if "completion_rate" in df.columns and pd.notna(row.get("completion_rate")) else None,
            "revenue_score": round(float(row["_revenue_score"]), 4) if pd.notna(row.get("_revenue_score")) else None,
            "phase": row["_funnel_phase"] if "_funnel_phase" in df.columns else None,
            "expected_dropoff": round(float(row["_expected_dropoff"]), 5) if "_expected_dropoff" in df.columns and pd.notna(row.get("_expected_dropoff")) else None,
        }
        funnel_curve.append(entry)

    # --- 2. Pacing Zones ---
    zones = _compute_pacing_zones(df)

    # --- 3. Steep Drop Detection ---
    steep_drops = _detect_steep_drops(df)

    # --- 4. Difficulty Cadence Analysis ---
    cadence = _analyze_cadence(df)

    # --- 5. Pacing Score ---
    pacing_score = _compute_pacing_score(df, steep_drops, cadence)

    # --- 6. Difficulty Trend (APS vs Churn & Revenue) ---
    difficulty_trend = _compute_difficulty_trend(df)

    # --- 7. Insights ---
    insights = _generate_funnel_insights(df, zones, steep_drops, cadence, pacing_score)

    return {
        "funnel_curve": funnel_curve,
        "zones": zones,
        "steep_drops": steep_drops,
        "pacing_score": pacing_score,
        "cadence": cadence,
        "difficulty_trend": difficulty_trend,
        "insights": insights,
    }


# ---------------------------------------------------------------------------
# Difficulty Trend — APS vs Churn & Revenue
# ---------------------------------------------------------------------------

def _compute_difficulty_trend(df):
    """
    Bin levels by APS and compute average churn and revenue per bin.
    Shows how difficulty correlates with churn and monetization across the funnel.
    """
    if "aps" not in df.columns:
        return []

    # Use 12 bins for a smooth trend
    n_bins = 12
    aps_min = float(df["aps"].min())
    aps_max = float(df["aps"].max())
    if aps_max <= aps_min:
        return []

    bin_edges = np.linspace(aps_min, aps_max, n_bins + 1)
    trend = []

    for i in range(n_bins):
        low, high = bin_edges[i], bin_edges[i + 1]
        if i == n_bins - 1:
            subset = df[(df["aps"] >= low) & (df["aps"] <= high)]
        else:
            subset = df[(df["aps"] >= low) & (df["aps"] < high)]

        if len(subset) == 0:
            continue

        entry = {
            "aps_range": f"{low:.2f}–{high:.2f}",
            "aps_mid": round((low + high) / 2, 3),
            "count": int(len(subset)),
        }

        if "combined_churn" in subset.columns:
            entry["avg_churn"] = round(float(subset["combined_churn"].mean()), 4)
        if "_revenue_score" in subset.columns:
            entry["avg_revenue"] = round(float(subset["_revenue_score"].mean()), 4)
        if "completion_rate" in subset.columns:
            entry["avg_completion"] = round(float(subset["completion_rate"].mean()), 4)

        # Bracket distribution
        bracket_counts = subset["target_bracket"].value_counts().to_dict()
        entry["bracket_mix"] = {k: int(v) for k, v in bracket_counts.items()}

        trend.append(entry)

    return trend


# ---------------------------------------------------------------------------
# Pacing Zones
# ---------------------------------------------------------------------------

def _compute_pacing_zones(df):
    """
    Divide the funnel into zones of ZONE_WINDOW levels each.
    Compute average drop-off, bracket mix, and classify zone health.
    """
    zones = []
    n = len(df)
    for start_idx in range(0, n, ZONE_WINDOW):
        end_idx = min(start_idx + ZONE_WINDOW, n)
        chunk = df.iloc[start_idx:end_idx]

        if len(chunk) == 0:
            continue

        start_level = int(chunk["level"].iloc[0])
        end_level = int(chunk["level"].iloc[-1])

        avg_dropoff = float(chunk["dropoff_rate"].mean()) if "dropoff_rate" in chunk.columns else 0
        avg_churn = float(chunk["combined_churn"].mean()) if "combined_churn" in chunk.columns else 0
        avg_aps = float(chunk["aps"].mean()) if "aps" in chunk.columns else 0

        # Bracket mix in this zone
        bracket_counts = chunk["target_bracket"].value_counts().to_dict()
        dominant_bracket = chunk["target_bracket"].mode().iloc[0] if len(chunk["target_bracket"].mode()) > 0 else None

        # Funnel retention across the zone
        if "funnel_pct" in chunk.columns and len(chunk) > 1:
            zone_start_pct = float(chunk["funnel_pct"].iloc[0])
            zone_end_pct = float(chunk["funnel_pct"].iloc[-1])
            zone_retention = zone_end_pct / zone_start_pct if zone_start_pct > 0 else 1
        else:
            zone_start_pct = zone_end_pct = zone_retention = None

        # Classify zone
        if avg_dropoff > 0.03:
            zone_type = "critical"
        elif avg_dropoff > 0.015:
            zone_type = "steep"
        elif avg_dropoff > 0.005:
            zone_type = "moderate"
        else:
            zone_type = "healthy"

        zones.append({
            "zone_start": start_level,
            "zone_end": end_level,
            "level_count": len(chunk),
            "avg_dropoff": round(avg_dropoff, 5),
            "avg_churn": round(avg_churn, 4),
            "avg_aps": round(avg_aps, 3),
            "zone_retention": round(zone_retention, 4) if zone_retention is not None else None,
            "zone_type": zone_type,
            "dominant_bracket": dominant_bracket,
            "bracket_mix": {k: int(v) for k, v in bracket_counts.items()},
            "funnel_start_pct": round(zone_start_pct, 4) if zone_start_pct is not None else None,
            "funnel_end_pct": round(zone_end_pct, 4) if zone_end_pct is not None else None,
        })

    return zones


# ---------------------------------------------------------------------------
# Steep Drop Detection
# ---------------------------------------------------------------------------

def _detect_steep_drops(df):
    """
    Detect individual levels where drop-off is abnormally steep,
    using phase-adjusted deviation from expected baseline.
    Early-game drops are de-emphasized; late-game drops are amplified.
    """
    if "dropoff_rate" not in df.columns:
        return []

    has_deviation = "_dropoff_deviation_adj" in df.columns
    drops = df["dropoff_rate"].fillna(0).values
    n = len(drops)

    steep = []
    window = 20

    for i in range(n):
        current = drops[i]
        row = df.iloc[i]

        # Skip negligible drops
        if current < 0.005:
            continue

        if has_deviation:
            # Phase-aware detection using adjusted deviation
            dev_adj = row.get("_dropoff_deviation_adj", 0)
            if pd.isna(dev_adj) or dev_adj <= 0:
                continue

            # Local context for sigma computation
            start = max(0, i - window // 2)
            end = min(n, i + window // 2 + 1)
            local_devs = df["_dropoff_deviation_adj"].iloc[start:end].dropna()
            local_std = max(float(local_devs.std()), 0.001) if len(local_devs) >= 3 else 0.01
            sigma = dev_adj / local_std

            # Phase-aware thresholds: use the same multipliers as the config
            if sigma < STEEP_DROP_MULTIPLIER:
                continue

            severity = "critical" if sigma >= CRITICAL_DROP_MULTIPLIER else "warning"
            expected = row.get("_expected_dropoff", 0)

            steep.append({
                "level": int(row["level"]),
                "bracket": row["target_bracket"] if pd.notna(row.get("target_bracket")) else None,
                "dropoff_rate": round(current, 5),
                "expected_dropoff": round(float(expected), 5) if pd.notna(expected) else None,
                "local_avg_dropoff": round(float(expected), 5) if pd.notna(expected) else None,
                "ratio": round(float(sigma), 2),
                "severity": severity,
                "phase": row.get("_funnel_phase", "Mid") if "_funnel_phase" in df.columns else None,
                "aps": round(float(row["aps"]), 3) if pd.notna(row.get("aps")) else None,
                "combined_churn": round(float(row["combined_churn"]), 4) if "combined_churn" in df.columns and pd.notna(row.get("combined_churn")) else None,
                "completion_rate": round(float(row["completion_rate"]), 4) if "completion_rate" in df.columns and pd.notna(row.get("completion_rate")) else None,
                "users": int(row["users"]) if pd.notna(row.get("users")) else None,
            })
        else:
            # Legacy: ratio-based detection
            start = max(0, i - window // 2)
            end = min(n, i + window // 2 + 1)
            neighbors = np.concatenate([drops[start:i], drops[i + 1:end]])
            if len(neighbors) == 0:
                continue
            local_avg = float(np.mean(neighbors))
            if local_avg < 0.001:
                continue
            ratio = current / local_avg
            if ratio < STEEP_DROP_MULTIPLIER:
                continue

            severity = "critical" if ratio >= CRITICAL_DROP_MULTIPLIER else "warning"
            steep.append({
                "level": int(row["level"]),
                "bracket": row["target_bracket"] if pd.notna(row.get("target_bracket")) else None,
                "dropoff_rate": round(current, 5),
                "local_avg_dropoff": round(local_avg, 5),
                "ratio": round(ratio, 2),
                "severity": severity,
                "phase": row.get("_funnel_phase") if "_funnel_phase" in df.columns else None,
                "aps": round(float(row["aps"]), 3) if pd.notna(row.get("aps")) else None,
                "combined_churn": round(float(row["combined_churn"]), 4) if "combined_churn" in df.columns and pd.notna(row.get("combined_churn")) else None,
                "completion_rate": round(float(row["completion_rate"]), 4) if "completion_rate" in df.columns and pd.notna(row.get("completion_rate")) else None,
                "users": int(row["users"]) if pd.notna(row.get("users")) else None,
            })

    # Sort by severity then level
    steep.sort(key=lambda x: (0 if x["severity"] == "critical" else 1, x["level"]))
    return steep


# ---------------------------------------------------------------------------
# Difficulty Cadence Analysis
# ---------------------------------------------------------------------------

def _analyze_cadence(df):
    """
    Analyze the difficulty cadence — how brackets alternate through the funnel,
    whether there are long stretches of hard content, and whether easy levels
    provide sufficient recovery.
    """
    cadence = {
        "bracket_sequences": [],
        "long_hard_stretches": [],
        "recovery_gaps": [],
        "transitions": [],
    }

    if "target_bracket" not in df.columns:
        return cadence

    brackets = df["target_bracket"].tolist()
    levels = df["level"].astype(int).tolist()

    # Build bracket sequence runs
    sequences = []
    current_bracket = brackets[0]
    run_start = levels[0]
    run_length = 1

    for i in range(1, len(brackets)):
        if brackets[i] == current_bracket:
            run_length += 1
        else:
            sequences.append({
                "bracket": current_bracket,
                "start_level": run_start,
                "end_level": levels[i - 1],
                "length": run_length,
            })
            current_bracket = brackets[i]
            run_start = levels[i]
            run_length = 1

    # Last run
    sequences.append({
        "bracket": current_bracket,
        "start_level": run_start,
        "end_level": levels[-1],
        "length": run_length,
    })
    cadence["bracket_sequences"] = sequences

    # Detect long hard stretches (Hard/Super Hard/Wall runs > 5 levels)
    hard_brackets = {"Hard", "Super Hard", "Wall"}
    for seq in sequences:
        if seq["bracket"] in hard_brackets and seq["length"] > 5:
            cadence["long_hard_stretches"].append(seq)

    # Also detect consecutive hard brackets (even if mixed between H/SH/W)
    consecutive_hard = 0
    hard_start = None
    for i, b in enumerate(brackets):
        if b in hard_brackets:
            if consecutive_hard == 0:
                hard_start = levels[i]
            consecutive_hard += 1
        else:
            if consecutive_hard > 8:
                cadence["long_hard_stretches"].append({
                    "bracket": "Mixed Hard",
                    "start_level": hard_start,
                    "end_level": levels[i - 1],
                    "length": consecutive_hard,
                })
            consecutive_hard = 0

    # Final check
    if consecutive_hard > 8:
        cadence["long_hard_stretches"].append({
            "bracket": "Mixed Hard",
            "start_level": hard_start,
            "end_level": levels[-1],
            "length": consecutive_hard,
        })

    # Transitions between brackets
    for i in range(1, len(brackets)):
        if brackets[i] != brackets[i - 1]:
            cadence["transitions"].append({
                "level": levels[i],
                "from_bracket": brackets[i - 1],
                "to_bracket": brackets[i],
            })

    # Recovery gaps: distance between Easy/Medium levels
    easy_medium_indices = [i for i, b in enumerate(brackets) if b in ("Easy", "Medium")]
    for i in range(1, len(easy_medium_indices)):
        gap = easy_medium_indices[i] - easy_medium_indices[i - 1]
        if gap > 10:
            cadence["recovery_gaps"].append({
                "from_level": levels[easy_medium_indices[i - 1]],
                "to_level": levels[easy_medium_indices[i]],
                "gap_levels": gap,
            })

    return cadence


# ---------------------------------------------------------------------------
# Pacing Score (0–100)
# ---------------------------------------------------------------------------

def _compute_pacing_score(df, steep_drops, cadence):
    """
    Compute an overall funnel pacing health score from 0 to 100.
    Higher = smoother, healthier funnel.
    Penalties are scaled relative to the number of levels so that
    a 500-level game isn't automatically penalized to zero.
    """
    score = 100.0
    n = len(df)
    if n == 0:
        return 0

    # Penalty: steep drops as a percentage of total levels
    critical_count = sum(1 for d in steep_drops if d["severity"] == "critical")
    warning_count = sum(1 for d in steep_drops if d["severity"] == "warning")
    critical_pct = critical_count / n
    warning_pct = warning_count / n
    score -= min(30, critical_pct * 200)   # e.g., 10% critical = -20
    score -= min(15, warning_pct * 100)    # e.g., 10% warning = -10

    # Penalty: long hard stretches (proportional)
    hard_levels = sum(s["length"] for s in cadence.get("long_hard_stretches", []))
    hard_pct = hard_levels / n
    score -= min(15, hard_pct * 60)

    # Penalty: recovery gaps
    for gap in cadence.get("recovery_gaps", []):
        if gap["gap_levels"] > 20:
            score -= 3
        elif gap["gap_levels"] > 10:
            score -= 1
    # Cap recovery gap penalties at 15 points total
    score = max(score, 0)

    # Penalty: high variance in drop-off rates
    if "dropoff_rate" in df.columns:
        dropoff_cv = df["dropoff_rate"].std() / max(df["dropoff_rate"].mean(), 0.0001)
        if dropoff_cv > 2.0:
            score -= 10
        elif dropoff_cv > 1.5:
            score -= 5

    # Penalty: total funnel loss (end retention)
    if "funnel_pct" in df.columns and len(df) > 0:
        end_retention = float(df["funnel_pct"].iloc[-1])
        if end_retention < 0.02:
            score -= 8
        elif end_retention < 0.05:
            score -= 4
        elif end_retention < 0.10:
            score -= 2

    return max(0, min(100, round(score)))


# ---------------------------------------------------------------------------
# Insight Generation
# ---------------------------------------------------------------------------

def _generate_funnel_insights(df, zones, steep_drops, cadence, pacing_score):
    """Generate human-readable insights about funnel pacing."""
    insights = []
    n = len(df)

    # Overall pacing assessment
    if pacing_score is not None:
        if pacing_score >= 80:
            insights.append(f"Funnel pacing score: {pacing_score}/100 — Overall pacing is healthy with smooth progression.")
        elif pacing_score >= 60:
            insights.append(f"Funnel pacing score: {pacing_score}/100 — Pacing has some issues that should be addressed.")
        elif pacing_score >= 40:
            insights.append(f"Funnel pacing score: {pacing_score}/100 — Significant pacing problems detected. Multiple levels need attention.")
        else:
            insights.append(f"Funnel pacing score: {pacing_score}/100 — Critical pacing issues. The funnel has severe retention problems.")

    # Funnel start/end
    if "funnel_pct" in df.columns and n > 0:
        start_pct = float(df["funnel_pct"].iloc[0])
        end_pct = float(df["funnel_pct"].iloc[-1])
        total_loss = start_pct - end_pct
        insights.append(
            f"Funnel spans {n} levels: {start_pct*100:.1f}% → {end_pct*100:.1f}% "
            f"(total loss: {total_loss*100:.1f} percentage points)."
        )

    # Steep drops summary — phase-aware
    critical_drops = [d for d in steep_drops if d["severity"] == "critical"]
    if critical_drops:
        # Separate by game phase for more targeted insight
        mid_late_drops = [d for d in critical_drops if d.get("phase") in ("Mid", "Late")]
        early_drops = [d for d in critical_drops if d.get("phase") in ("Tutorial", "Early")]
        if mid_late_drops:
            level_list = ", ".join([f"L{d['level']}" for d in mid_late_drops[:5]])
            suffix = f" and {len(mid_late_drops) - 5} more" if len(mid_late_drops) > 5 else ""
            insights.append(f"{len(mid_late_drops)} critical drop-off spike(s) in core/late game: {level_list}{suffix}. High priority.")
        if early_drops:
            insights.append(f"{len(early_drops)} early-game spike(s) noted (de-weighted — early churn is partially expected).")

    # Worst zone
    critical_zones = [z for z in zones if z["zone_type"] in ("critical", "steep")]
    if critical_zones:
        worst = max(critical_zones, key=lambda z: z["avg_dropoff"])
        insights.append(
            f"Worst pacing zone: levels {worst['zone_start']}–{worst['zone_end']} "
            f"(avg drop-off: {worst['avg_dropoff']*100:.2f}%, dominant bracket: {worst['dominant_bracket']})."
        )

    # Long hard stretches
    for stretch in cadence.get("long_hard_stretches", []):
        insights.append(
            f"Long hard stretch: {stretch['length']} consecutive {stretch['bracket']} levels "
            f"({stretch['start_level']}–{stretch['end_level']}). Players may fatigue without recovery."
        )

    # Recovery gaps
    for gap in cadence.get("recovery_gaps", []):
        if gap["gap_levels"] > 15:
            insights.append(
                f"No Easy/Medium recovery levels for {gap['gap_levels']} levels "
                f"(L{gap['from_level']} to L{gap['to_level']}). Consider inserting breather levels."
            )

    # Bracket transition frequency
    transitions = cadence.get("transitions", [])
    if n > 0 and len(transitions) > 0:
        transition_rate = len(transitions) / n
        if transition_rate > 0.3:
            insights.append(
                f"High bracket transition frequency ({len(transitions)} transitions in {n} levels). "
                f"The difficulty may feel erratic to players."
            )
        elif transition_rate < 0.05:
            insights.append(
                f"Low bracket transition frequency ({len(transitions)} transitions in {n} levels). "
                f"Difficulty may feel monotonous within long stretches."
            )

    return insights
