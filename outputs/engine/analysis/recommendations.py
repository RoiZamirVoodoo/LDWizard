"""
LD Wizard — Recommendations Engine (Post-MVP)
Generates actionable recommendations from all analysis results.
Each recommendation produces structured data ready for dashboard display.
"""

import pandas as pd
import numpy as np
from engine.parser import DIFFICULTY_ORDER, REVENUE_WEIGHTS
from engine.aps_engine import BRACKET_GOALS


# ---------------------------------------------------------------------------
# Master function
# ---------------------------------------------------------------------------

def compute_recommendations(df, aps_results, funnel_results, ranking_results,
                            dropoff_results, correlation_results):
    """
    Generate all 6 recommendation categories.

    Args:
        df: Enriched DataFrame
        *_results: Output dicts from each analysis engine

    Returns:
        dict with keys matching the 6 recommendation categories
    """
    df = df.copy().sort_values("level").reset_index(drop=True)

    # Ensure weighted revenue score exists
    if "_revenue_score" not in df.columns:
        num = pd.Series(0.0, index=df.index)
        tw = 0.0
        for col, w in REVENUE_WEIGHTS.items():
            if col in df.columns:
                num += df[col].fillna(0) * w
                tw += w
        df["_revenue_score"] = (num / tw) if tw > 0 else 0.0

    return {
        "reorder": _recommend_reordering(df, funnel_results),
        "smoothing": _recommend_smoothing(df, dropoff_results, funnel_results),
        "difficulty_curve": _recommend_difficulty_curve(df, aps_results, funnel_results),
        "fix_replicate": _recommend_fix_replicate(df, ranking_results, dropoff_results),
        "best_mechanics": _recommend_best_mechanics(df, ranking_results),
        "game_health": _compute_game_health(df, aps_results, funnel_results, ranking_results,
                                             dropoff_results, correlation_results),
    }


# ---------------------------------------------------------------------------
# 1. Optimal Level Reordering
# ---------------------------------------------------------------------------

def _recommend_reordering(df, funnel_results):
    """
    Identify where the difficulty curve jumps too steeply and suggest
    which levels to swap or move for smoother progression.
    """
    recs = []

    if "aps" not in df.columns or len(df) < 5:
        return {"recommendations": recs, "summary": "Insufficient data for reordering analysis."}

    levels = df["level"].values
    aps_vals = df["aps"].values
    brackets = df["target_bracket"].values
    n = len(df)

    # Compute APS deltas
    aps_deltas = np.diff(aps_vals)
    mean_delta = float(np.mean(np.abs(aps_deltas)))
    std_delta = float(np.std(np.abs(aps_deltas)))

    # Find spike jumps: APS increase > mean + 2*std
    spike_threshold = mean_delta + 2.0 * std_delta
    jump_count = 0

    for i in range(len(aps_deltas)):
        delta = aps_deltas[i]
        if abs(delta) > spike_threshold and abs(delta) > 0.2:
            direction = "harder" if delta > 0 else "easier"
            from_level = int(levels[i])
            to_level = int(levels[i + 1])

            # Find a nearby level that could be swapped in to smooth the transition
            swap_candidate = _find_swap_candidate(df, i, delta)

            rec = {
                "type": "spike_jump",
                "priority": "high" if abs(delta) > spike_threshold * 1.5 else "medium",
                "from_level": from_level,
                "to_level": to_level,
                "from_aps": round(float(aps_vals[i]), 3),
                "to_aps": round(float(aps_vals[i + 1]), 3),
                "delta": round(float(delta), 3),
                "direction": direction,
                "action": f"Difficulty jumps {abs(delta):.2f} APS between L{from_level} and L{to_level} ({direction}). "
                          f"This is {abs(delta)/max(mean_delta, 0.001):.1f}× the average step.",
            }
            if swap_candidate:
                rec["suggestion"] = swap_candidate
            recs.append(rec)
            jump_count += 1

    # Check for bracket ordering violations (Easy after Hard, etc.)
    bracket_rank = {b: i for i, b in enumerate(DIFFICULTY_ORDER)}
    for i in range(1, n):
        curr_rank = bracket_rank.get(brackets[i], 2)
        prev_rank = bracket_rank.get(brackets[i - 1], 2)
        # Flag big jumps (e.g., Easy → Wall or Wall → Easy)
        if abs(curr_rank - prev_rank) >= 3:
            recs.append({
                "type": "bracket_jump",
                "priority": "medium",
                "from_level": int(levels[i - 1]),
                "to_level": int(levels[i]),
                "action": f"Sharp bracket transition: L{int(levels[i-1])} ({brackets[i-1]}) → L{int(levels[i])} ({brackets[i]}). "
                          f"Consider inserting a transitional level between them.",
                "suggestion": f"Add a {DIFFICULTY_ORDER[min(curr_rank, prev_rank) + 1]} level between L{int(levels[i-1])} and L{int(levels[i])} to ease the transition.",
            })

    # Limit to top 20 most impactful
    recs.sort(key=lambda r: (0 if r["priority"] == "high" else 1, -abs(r.get("delta", 0))))
    recs = recs[:20]

    summary = (f"Found {jump_count} difficulty spike(s) that exceed normal step size. "
               f"Average APS step: {mean_delta:.3f}, threshold: {spike_threshold:.3f}.")

    return {"recommendations": recs, "summary": summary}


def _find_swap_candidate(df, jump_idx, delta):
    """Find a level that could be moved to smooth a spike."""
    target_aps = df["aps"].iloc[jump_idx] + delta * 0.5  # Ideal midpoint
    levels = df["level"].values
    aps_vals = df["aps"].values

    # Search within ±30 levels for a level close to the target APS
    search_range = range(max(0, jump_idx - 30), min(len(df), jump_idx + 30))
    best = None
    best_dist = float("inf")

    for j in search_range:
        if abs(j - jump_idx) < 2:
            continue  # Skip the levels involved in the jump
        dist = abs(aps_vals[j] - target_aps)
        if dist < best_dist:
            best_dist = dist
            best = j

    if best is not None and best_dist < abs(delta) * 0.6:
        return (f"Consider moving L{int(levels[best])} (APS {aps_vals[best]:.3f}) "
                f"to position between L{int(levels[jump_idx])} and L{int(levels[jump_idx + 1])} "
                f"to create a smoother APS ramp.")
    return None


# ---------------------------------------------------------------------------
# 2. Drop-off Zone Smoothing
# ---------------------------------------------------------------------------

def _recommend_smoothing(df, dropoff_results, funnel_results):
    """
    For each high-loss zone, recommend specific levels to ease
    or where to insert breather levels.
    """
    recs = []

    if not dropoff_results:
        return {"recommendations": recs, "summary": "No drop-off data available."}

    zones = dropoff_results.get("zones", [])
    spikes = dropoff_results.get("spikes", [])

    # Get bracket averages for context
    bracket_avg_churn = {}
    for bd in dropoff_results.get("bracket_dropoff", []):
        bracket_avg_churn[bd["bracket"]] = bd.get("avg_combined_churn", 0)

    # Recommend for each critical/warning zone
    for zone in zones[:10]:
        zone_df = df[(df["level"] >= zone["start_level"]) & (df["level"] <= zone["end_level"])]
        if len(zone_df) == 0:
            continue

        # Find the worst levels in this zone
        worst_levels = zone_df.nlargest(3, "dropoff_rate") if "dropoff_rate" in zone_df.columns else zone_df.head(3)

        level_details = []
        for _, row in worst_levels.iterrows():
            bracket = row.get("target_bracket", "—")
            avg_churn = bracket_avg_churn.get(bracket, 0)
            is_high_churn = row.get("combined_churn", 0) > avg_churn * 1.5 if avg_churn > 0 else False

            detail = {
                "level": int(row["level"]),
                "bracket": bracket,
                "dropoff_rate": round(float(row.get("dropoff_rate", 0)), 4),
                "aps": round(float(row.get("aps", 0)), 3),
                "churn": round(float(row.get("combined_churn", 0)), 4),
            }

            # Generate specific action
            if is_high_churn and bracket in ("Hard", "Super Hard", "Wall"):
                detail["action"] = f"Reduce APS by 10–15% (target ~{row['aps'] * 0.88:.2f}). High churn for {bracket}."
            elif is_high_churn:
                detail["action"] = f"Reduce difficulty. Churn is {row.get('combined_churn', 0) * 100:.1f}% vs bracket avg {avg_churn * 100:.1f}%."
            else:
                detail["action"] = f"Review level design — drop-off is {row.get('dropoff_rate', 0) * 100:.2f}% but churn seems normal. May be a progression issue."

            level_details.append(detail)

        rec = {
            "zone": f"L{zone['start_level']}–L{zone['end_level']}",
            "severity": zone["severity"],
            "funnel_loss": round(zone["funnel_loss_pct"] * 100, 1),
            "user_loss": zone["user_loss"],
            "dominant_bracket": zone.get("dominant_bracket", "—"),
            "worst_levels": level_details,
        }

        # Zone-level suggestion
        if zone.get("dominant_bracket") in ("Hard", "Super Hard", "Wall"):
            rec["zone_action"] = f"This zone is dominated by {zone['dominant_bracket']} levels. Insert 1–2 Easy/Medium breather levels to let players recover."
        else:
            rec["zone_action"] = f"Reduce overall difficulty in this zone. Consider lowering APS targets by 10–20%."

        recs.append(rec)

    # Also flag individual spikes not covered by zones
    zone_levels = set()
    for z in zones:
        zone_levels.update(range(z["start_level"], z["end_level"] + 1))

    isolated_spikes = [s for s in spikes if s["level"] not in zone_levels and s["severity"] == "critical"]
    for spike in isolated_spikes[:5]:
        recs.append({
            "zone": f"L{spike['level']} (isolated spike)",
            "severity": "critical",
            "funnel_loss": None,
            "user_loss": spike.get("user_loss", 0),
            "dominant_bracket": spike.get("bracket", "—"),
            "worst_levels": [{
                "level": spike["level"],
                "bracket": spike.get("bracket", "—"),
                "dropoff_rate": spike["dropoff_rate"],
                "aps": spike.get("aps"),
                "churn": spike.get("combined_churn"),
                "action": f"Critical isolated spike at {spike['ratio']}× local average. Reduce difficulty or redesign this level.",
            }],
            "zone_action": "This is an isolated spike — the single level causes abnormal player loss. Priority fix.",
        })

    summary = f"{len(zones)} high-loss zones detected. {len(isolated_spikes)} isolated critical spikes outside zones."
    return {"recommendations": recs, "summary": summary}


# ---------------------------------------------------------------------------
# 3. Difficulty Curve Adjustments
# ---------------------------------------------------------------------------

def _recommend_difficulty_curve(df, aps_results, funnel_results):
    """
    Recommend target APS averages per zone, flag where the curve
    rises too fast/slow, and suggest ideal ramp rate.

    Uses a logarithmic ideal curve instead of linear:
    ideal(i) = aps_start + (aps_end - aps_start) * log(1 + i) / log(1 + n-1)
    This models real puzzle games where difficulty ramps steeply early
    (to introduce mechanics) then flattens in the late game.
    """
    recs = []

    if "aps" not in df.columns or len(df) < 10:
        return {"recommendations": recs, "ideal_ramp": None, "curve_model": "log", "summary": "Insufficient data."}

    n = len(df)
    levels = df["level"].values
    aps_vals = df["aps"].values

    # Logarithmic ideal curve: gentle start, steepens mid-game, plateaus late
    aps_start = float(aps_vals[0])
    aps_end = float(aps_vals[-1])
    aps_range = aps_end - aps_start
    log_denom = np.log(1 + n - 1)  # log(n)

    def ideal_aps_at(idx):
        """Logarithmic ideal APS for a given index position."""
        if log_denom == 0:
            return aps_start
        return aps_start + aps_range * np.log(1 + idx) / log_denom

    # Average ramp rate (for summary — the log curve doesn't have a constant rate)
    avg_ramp_per_level = aps_range / max(n - 1, 1)

    # Compute actual ramp in 20-level windows
    window = 20
    zone_analysis = []
    for start_idx in range(0, n, window):
        end_idx = min(start_idx + window, n)
        chunk = df.iloc[start_idx:end_idx]
        if len(chunk) < 3:
            continue

        zone_start = int(chunk["level"].iloc[0])
        zone_end = int(chunk["level"].iloc[-1])
        zone_aps_start = float(chunk["aps"].iloc[0])
        zone_aps_end = float(chunk["aps"].iloc[-1])
        zone_ramp = (zone_aps_end - zone_aps_start) / max(len(chunk) - 1, 1)
        zone_avg_aps = float(chunk["aps"].mean())

        # Ideal APS for this zone (log curve)
        ideal_start_val = ideal_aps_at(start_idx)
        ideal_end_val = ideal_aps_at(end_idx - 1)
        ideal_avg = (ideal_start_val + ideal_end_val) / 2
        ideal_zone_ramp = (ideal_end_val - ideal_start_val) / max(len(chunk) - 1, 1)

        deviation = zone_avg_aps - ideal_avg
        ramp_ratio = zone_ramp / ideal_zone_ramp if ideal_zone_ramp != 0 else 1.0

        zone_entry = {
            "zone": f"L{zone_start}–L{zone_end}",
            "zone_start": zone_start,
            "zone_end": zone_end,
            "actual_avg_aps": round(zone_avg_aps, 3),
            "ideal_avg_aps": round(ideal_avg, 3),
            "deviation": round(deviation, 3),
            "ramp_rate": round(zone_ramp, 4),
            "ideal_ramp_rate": round(ideal_zone_ramp, 4),
            "ramp_ratio": round(ramp_ratio, 2),
        }

        # Classify and recommend — tolerance scales with zone position
        # (early zones are expected to ramp faster under log model)
        deviation_threshold = 0.5 + 0.3 * (start_idx / max(n - 1, 1))  # 0.5 early → 0.8 late
        if abs(deviation) > deviation_threshold:
            if deviation > 0:
                zone_entry["status"] = "too_hard"
                zone_entry["action"] = f"Zone is {deviation:.2f} APS above ideal curve. Lower average APS to ~{ideal_avg:.2f}."
                zone_entry["priority"] = "high" if deviation > deviation_threshold * 2 else "medium"
            else:
                zone_entry["status"] = "too_easy"
                zone_entry["action"] = f"Zone is {abs(deviation):.2f} APS below ideal curve. Could increase difficulty to ~{ideal_avg:.2f}."
                zone_entry["priority"] = "low"
        elif ramp_ratio > 2.5:
            zone_entry["status"] = "steep_ramp"
            zone_entry["action"] = f"Difficulty climbs {ramp_ratio:.1f}× faster than ideal. Slow down the ramp in this zone."
            zone_entry["priority"] = "high"
        elif ramp_ratio < 0 and abs(zone_ramp) > abs(ideal_zone_ramp) * 0.5:
            zone_entry["status"] = "reverse_ramp"
            zone_entry["action"] = f"Difficulty decreases in this zone (ramp: {zone_ramp:.4f}/level). Ensure this is intentional."
            zone_entry["priority"] = "medium"
        else:
            zone_entry["status"] = "on_track"
            zone_entry["action"] = "Difficulty progression is within expected range."
            zone_entry["priority"] = "none"

        zone_analysis.append(zone_entry)

    # Filter to only actionable zones
    actionable = [z for z in zone_analysis if z["priority"] != "none"]

    # Bracket-level APS targets
    bracket_targets = []
    ranges = aps_results.get("ranges", []) if aps_results else []
    for r in ranges:
        bracket_targets.append({
            "bracket": r["bracket"],
            "current_avg": r["aps_mean"],
            "recommended_min": r["recommended_min"],
            "recommended_max": r["recommended_max"],
            "sweet_spot": round((r["recommended_min"] + r["recommended_max"]) / 2, 3),
        })

    summary = (f"Ideal difficulty curve: logarithmic ramp from {aps_start:.2f} to {aps_end:.2f} "
               f"over {n} levels (avg {avg_ramp_per_level:.4f} APS/level). "
               f"{len(actionable)} zone(s) deviate significantly from ideal.")

    return {
        "recommendations": actionable,
        "all_zones": zone_analysis,
        "bracket_targets": bracket_targets,
        "ideal_ramp": round(avg_ramp_per_level, 5),
        "curve_model": "logarithmic",
        "summary": summary,
    }


# ---------------------------------------------------------------------------
# 4. Fix vs. Replicate Levels
# ---------------------------------------------------------------------------

def _recommend_fix_replicate(df, ranking_results, dropoff_results):
    """
    Combine ranking + outlier + dropoff data to create actionable
    'fix these' and 'clone these' lists.
    """
    fix_list = []
    replicate_list = []

    if not ranking_results:
        return {"fix": fix_list, "replicate": replicate_list, "summary": "No ranking data."}

    rankings = ranking_results.get("rankings", [])
    outliers = ranking_results.get("outliers", [])
    spikes = dropoff_results.get("spikes", []) if dropoff_results else []

    # Build spike lookup
    spike_levels = {s["level"]: s for s in spikes}

    # Build outlier lookup
    outlier_lookup = {o["level"]: o for o in outliers}

    # --- Fix list: underperformers + spike levels ---
    # Bottom 5% by performance score
    n = len(rankings)
    bottom_cutoff = max(1, int(n * 0.05))
    bottom_levels = rankings[-bottom_cutoff:] if n > 0 else []

    seen_fix = set()
    for level_data in bottom_levels:
        lvl = level_data["level"]
        if lvl in seen_fix:
            continue
        seen_fix.add(lvl)

        reasons = []
        reasons.append(f"Bottom {((n - rankings.index(level_data)) / n * 100):.0f}% performance score ({level_data['perf_score']:.3f})")

        if lvl in spike_levels:
            reasons.append(f"Drop-off spike ({spike_levels[lvl]['ratio']}× local avg)")
        if lvl in outlier_lookup and outlier_lookup[lvl]["direction"] == "underperforming":
            reasons.append(f"Statistical outlier (Z={outlier_lookup[lvl]['z_score']:.1f})")

        fix_list.append({
            "level": lvl,
            "bracket": level_data["bracket"],
            "score": level_data["perf_score"],
            "churn": level_data["combined_churn"],
            "completion": level_data["completion_rate"],
            "revenue": level_data.get("revenue_score", 0),
            "reasons": reasons,
            "action": _suggest_fix_action(level_data, spike_levels.get(lvl)),
        })

    # Add spike levels not already in the fix list
    for spike in spikes:
        if spike["level"] not in seen_fix and spike["severity"] == "critical":
            seen_fix.add(spike["level"])
            # Find ranking data
            rank_data = next((r for r in rankings if r["level"] == spike["level"]), None)
            fix_list.append({
                "level": spike["level"],
                "bracket": spike.get("bracket", "—"),
                "score": rank_data["perf_score"] if rank_data else None,
                "churn": spike.get("combined_churn"),
                "completion": None,
                "revenue": None,
                "reasons": [f"Critical drop-off spike ({spike['ratio']}× local avg)"],
                "action": f"Critical player loss at this level. Reduce difficulty (current APS: {spike.get('aps', '—')}).",
            })

    # Sort fix list by score ascending (worst first)
    fix_list.sort(key=lambda x: x["score"] if x["score"] is not None else 0)
    fix_list = fix_list[:25]  # Cap at 25

    # --- Replicate list: top performers + overperformers ---
    top_cutoff = max(1, int(n * 0.05))
    top_levels = rankings[:top_cutoff] if n > 0 else []

    seen_rep = set()
    for level_data in top_levels:
        lvl = level_data["level"]
        if lvl in seen_rep:
            continue
        seen_rep.add(lvl)

        reasons = []
        reasons.append(f"Top {((rankings.index(level_data) + 1) / n * 100):.0f}% performance score ({level_data['perf_score']:.3f})")

        if lvl in outlier_lookup and outlier_lookup[lvl]["direction"] == "overperforming":
            reasons.append(f"Statistical overperformer (Z=+{outlier_lookup[lvl]['z_score']:.1f})")

        replicate_list.append({
            "level": lvl,
            "bracket": level_data["bracket"],
            "score": level_data["perf_score"],
            "churn": level_data["combined_churn"],
            "completion": level_data["completion_rate"],
            "revenue": level_data.get("revenue_score", 0),
            "reasons": reasons,
            "action": f"Study and replicate this level's design. Excellent {level_data['bracket']} performance.",
        })

    # Add overperformer outliers not already in the list
    for outlier in outliers:
        if outlier["direction"] == "overperforming" and outlier["level"] not in seen_rep:
            seen_rep.add(outlier["level"])
            rank_data = next((r for r in rankings if r["level"] == outlier["level"]), None)
            replicate_list.append({
                "level": outlier["level"],
                "bracket": outlier["bracket"],
                "score": outlier["perf_score"],
                "churn": outlier.get("combined_churn"),
                "completion": outlier.get("completion_rate"),
                "revenue": rank_data.get("revenue_score") if rank_data else None,
                "reasons": [f"Statistical overperformer in {outlier['bracket']} (Z=+{outlier['z_score']:.1f})"],
                "action": f"Outlier-level performance. Analyze what makes this {outlier['bracket']} level exceptional.",
            })

    replicate_list.sort(key=lambda x: x["score"] if x["score"] is not None else 0, reverse=True)
    replicate_list = replicate_list[:25]

    summary = f"{len(fix_list)} level(s) flagged for fixing. {len(replicate_list)} level(s) identified as models to replicate."
    return {"fix": fix_list, "replicate": replicate_list, "summary": summary}


def _suggest_fix_action(level_data, spike_data=None):
    """Generate a specific fix suggestion for an underperforming level."""
    parts = []
    bracket = level_data["bracket"]

    if level_data["combined_churn"] > 0.05:
        parts.append("High churn — reduce difficulty or add engagement hooks")
    if level_data["completion_rate"] < 0.85 and bracket in ("Easy", "Medium"):
        parts.append(f"Low completion ({level_data['completion_rate']*100:.0f}%) for {bracket} — simplify level design")
    if level_data.get("revenue_score", 0) < 0.01 and bracket in ("Hard", "Super Hard", "Wall"):
        parts.append(f"Low monetization for {bracket} — review sink/booster placement")
    if spike_data:
        parts.append(f"Drop-off spike — players exit at {spike_data['ratio']}× normal rate")

    return ". ".join(parts) if parts else f"Underperforming for {bracket} bracket — review level design."


# ---------------------------------------------------------------------------
# 5. Best Mechanics & Parameters
# ---------------------------------------------------------------------------

def _recommend_best_mechanics(df, ranking_results):
    """
    Correlate level properties (colors, features, tiles, blockers)
    with performance scores to find winning formulas.
    """
    results = {
        "color_analysis": [],
        "feature_analysis": [],
        "property_correlations": [],
        "best_combos": [],
        "summary": "",
    }

    if not ranking_results or "rankings" not in ranking_results:
        results["summary"] = "No ranking data available for mechanics analysis."
        return results

    # Build a score lookup
    score_lookup = {r["level"]: r["perf_score"] for r in ranking_results["rankings"]}
    df = df.copy()
    df["perf_score"] = df["level"].map(score_lookup)

    if df["perf_score"].isna().all():
        results["summary"] = "Could not match scores to levels."
        return results

    # --- Color analysis ---
    color_cols = [c for c in df.columns if c.startswith("color_")]
    if color_cols:
        for col in color_cols:
            if col not in df.columns or df[col].dtype != bool:
                continue
            color_name = col.replace("color_", "").title()
            with_color = df[df[col] == True]["perf_score"].dropna()
            without_color = df[df[col] == False]["perf_score"].dropna()

            if len(with_color) >= 3 and len(without_color) >= 3:
                diff = float(with_color.mean() - without_color.mean())
                results["color_analysis"].append({
                    "color": color_name,
                    "levels_with": int(len(with_color)),
                    "avg_score_with": round(float(with_color.mean()), 4),
                    "avg_score_without": round(float(without_color.mean()), 4),
                    "score_diff": round(diff, 4),
                    "impact": "positive" if diff > 0.005 else ("negative" if diff < -0.005 else "neutral"),
                })

        results["color_analysis"].sort(key=lambda x: x["score_diff"], reverse=True)

    # --- Feature analysis ---
    if "features" in df.columns:
        # Explode features and analyze each
        all_features = {}
        for _, row in df.iterrows():
            if pd.isna(row.get("perf_score")):
                continue
            feats = row.get("features", [])
            if isinstance(feats, list):
                for f in feats:
                    if f not in all_features:
                        all_features[f] = []
                    all_features[f].append(row["perf_score"])

        for feat, scores in all_features.items():
            if len(scores) >= 3:
                avg_with = float(np.mean(scores))
                overall_avg = float(df["perf_score"].dropna().mean())
                diff = avg_with - overall_avg
                results["feature_analysis"].append({
                    "feature": feat,
                    "count": len(scores),
                    "avg_score": round(avg_with, 4),
                    "vs_average": round(diff, 4),
                    "impact": "positive" if diff > 0.005 else ("negative" if diff < -0.005 else "neutral"),
                })

        results["feature_analysis"].sort(key=lambda x: x["vs_average"], reverse=True)

    # --- Numeric property correlations ---
    numeric_props = ["color_count", "total_tiles", "deposit_points", "deposit_boxes",
                     "queue_count", "feature_count"]
    for prop in numeric_props:
        if prop in df.columns:
            valid = df[[prop, "perf_score"]].dropna()
            if len(valid) >= 10:
                r = float(valid[prop].corr(valid["perf_score"]))
                if not np.isnan(r):
                    results["property_correlations"].append({
                        "property": prop.replace("_", " ").title(),
                        "correlation": round(r, 3),
                        "strength": "strong" if abs(r) >= 0.4 else ("moderate" if abs(r) >= 0.2 else "weak"),
                        "direction": "More → Better" if r > 0.1 else ("More → Worse" if r < -0.1 else "No clear effect"),
                    })

    results["property_correlations"].sort(key=lambda x: abs(x["correlation"]), reverse=True)

    # --- Best combinations (feature_count + color_count + blocker) ---
    if "feature_count" in df.columns and "color_count" in df.columns and "has_blocker" in df.columns:
        combo_groups = df.groupby(["feature_count", "color_count", "has_blocker"]).agg(
            avg_score=("perf_score", "mean"),
            count=("perf_score", "count"),
        ).reset_index()
        combo_groups = combo_groups[combo_groups["count"] >= 3].sort_values("avg_score", ascending=False)

        for _, row in combo_groups.head(10).iterrows():
            results["best_combos"].append({
                "features": int(row["feature_count"]),
                "colors": int(row["color_count"]),
                "blocker": bool(row["has_blocker"]),
                "avg_score": round(float(row["avg_score"]), 4),
                "level_count": int(row["count"]),
            })

    n_props = len(results["property_correlations"])
    n_feats = len(results["feature_analysis"])
    n_colors = len(results["color_analysis"])
    results["summary"] = (f"Analyzed {n_colors} colors, {n_feats} features, "
                          f"and {n_props} numeric properties against performance scores.")

    return results


# ---------------------------------------------------------------------------
# 6. Game Health Summary
# ---------------------------------------------------------------------------

def _compute_game_health(df, aps_results, funnel_results, ranking_results,
                         dropoff_results, correlation_results):
    """
    Overall game health grade combining all analysis dimensions.
    """
    scores = {}
    details = {}

    n = len(df)
    if n == 0:
        return {"grade": "N/A", "score": 0, "breakdown": {}, "details": {}, "key_actions": []}

    # --- 1. Pacing Health (from funnel) ---
    pacing_score = funnel_results.get("pacing_score", 50) if funnel_results else 50
    scores["pacing"] = pacing_score
    details["pacing"] = f"Funnel pacing score: {pacing_score}/100"

    # --- 2. Retention Health ---
    retention_score = 70  # default
    if "funnel_pct" in df.columns and len(df) > 1:
        end_retention = float(df["funnel_pct"].iloc[-1])
        if end_retention >= 0.10:
            retention_score = 90
        elif end_retention >= 0.05:
            retention_score = 75
        elif end_retention >= 0.02:
            retention_score = 55
        elif end_retention >= 0.01:
            retention_score = 35
        else:
            retention_score = 15
        details["retention"] = f"End-of-funnel retention: {end_retention*100:.2f}% → score {retention_score}/100"
    scores["retention"] = retention_score

    # --- 3. Bracket Balance (includes distribution health) ---
    bracket_score = 80
    bracket_dist_info = ""
    if aps_results:
        health = aps_results.get("health", [])
        critical_brackets = sum(1 for h in health if h["status"] == "critical")
        warning_brackets = sum(1 for h in health if h["status"] == "warning")
        bracket_score = max(0, 100 - critical_brackets * 25 - warning_brackets * 10)

    # Bracket distribution check: is the mix of E/M/H/SH/W healthy?
    if "target_bracket" in df.columns and n > 0:
        counts = df["target_bracket"].value_counts()
        total = counts.sum()
        easy_medium_pct = sum(counts.get(b, 0) for b in ("Easy", "Medium")) / total
        hard_plus_pct = sum(counts.get(b, 0) for b in ("Hard", "Super Hard", "Wall")) / total

        # Penalty for extreme skew
        if hard_plus_pct > 0.65:
            penalty = min(15, int((hard_plus_pct - 0.65) * 100))
            bracket_score = max(0, bracket_score - penalty)
            bracket_dist_info = f" | Distribution skewed hard ({hard_plus_pct*100:.0f}% H/SH/W) — may be too aggressive"
        elif easy_medium_pct > 0.70:
            penalty = min(10, int((easy_medium_pct - 0.70) * 80))
            bracket_score = max(0, bracket_score - penalty)
            bracket_dist_info = f" | Distribution skewed easy ({easy_medium_pct*100:.0f}% E/M) — may undermonetize"

        # Also check if any bracket is missing entirely
        missing_brackets = [b for b in DIFFICULTY_ORDER if counts.get(b, 0) == 0]
        if missing_brackets:
            bracket_score = max(0, bracket_score - len(missing_brackets) * 5)
            bracket_dist_info += f" | Missing bracket(s): {', '.join(missing_brackets)}"

    if aps_results:
        details["bracket_balance"] = (f"{critical_brackets} critical, {warning_brackets} warning bracket(s)"
                                       f"{bracket_dist_info} → score {bracket_score}/100")
    elif bracket_dist_info:
        details["bracket_balance"] = f"Distribution check{bracket_dist_info} → score {bracket_score}/100"
    scores["bracket_balance"] = bracket_score

    # --- 4. Monetization Efficiency ---
    monetization_score = 60
    if correlation_results and correlation_results.get("churn_revenue"):
        tradeoffs = correlation_results["churn_revenue"].get("bracket_tradeoff", [])
        if tradeoffs:
            efficiencies = [t["efficiency"] for t in tradeoffs]
            avg_eff = float(np.mean(efficiencies))
            if avg_eff >= 2.0:
                monetization_score = 90
            elif avg_eff >= 1.0:
                monetization_score = 70
            elif avg_eff >= 0.5:
                monetization_score = 50
            else:
                monetization_score = 30
            details["monetization"] = f"Avg churn-revenue efficiency: {avg_eff:.2f} → score {monetization_score}/100"
    scores["monetization"] = monetization_score

    # --- 5. Drop-off Severity ---
    # Proportional to game size: a 500-level game with 20 spikes is very different
    # from a 50-level game with 20 spikes.
    dropoff_score = 80
    if dropoff_results:
        spikes = dropoff_results.get("spikes", [])
        critical_spikes = sum(1 for s in spikes if s["severity"] == "critical")
        zones = dropoff_results.get("zones", [])
        critical_zones = sum(1 for z in zones if z["severity"] == "critical")
        # Scale penalties by proportion of total levels affected
        spike_pct = critical_spikes / max(n, 1)
        zone_pct = critical_zones / max(n / 20, 1)  # ~1 zone per 20 levels
        dropoff_score = max(0, 100 - min(40, spike_pct * 250) - min(30, zone_pct * 60))
        dropoff_score = min(100, round(dropoff_score))
        details["dropoff"] = f"{critical_spikes} critical spike(s) ({spike_pct*100:.0f}% of levels), {critical_zones} critical zone(s) → score {dropoff_score}/100"
    scores["dropoff"] = dropoff_score

    # --- Overall ---
    # Retention is the foundation — a game that retains can always optimize monetization.
    # Dropoff is more directly actionable than bracket balance.
    # Monetization follows from having enough players in later brackets.
    weights = {"pacing": 0.25, "retention": 0.30, "bracket_balance": 0.15,
               "monetization": 0.10, "dropoff": 0.20}
    overall = sum(scores[k] * weights[k] for k in weights)
    overall = round(overall)

    # Grade
    if overall >= 85:
        grade = "A"
    elif overall >= 70:
        grade = "B"
    elif overall >= 55:
        grade = "C"
    elif overall >= 40:
        grade = "D"
    else:
        grade = "F"

    # Key actions (top 3 things to improve)
    key_actions = []
    sorted_scores = sorted(scores.items(), key=lambda x: x[1])
    for dimension, score in sorted_scores[:3]:
        if score < 70:
            action_map = {
                "pacing": "Improve funnel pacing — smooth out difficulty spikes and add recovery levels",
                "retention": "Address end-of-funnel retention — too many players lost before reaching late game",
                "bracket_balance": "Fix bracket health issues — some brackets have misaligned APS ranges or goals",
                "monetization": "Optimize monetization efficiency — improve revenue per unit of churn in key brackets",
                "dropoff": "Reduce critical drop-off points — several levels cause abnormal player loss",
            }
            key_actions.append({
                "dimension": dimension.replace("_", " ").title(),
                "score": score,
                "action": action_map.get(dimension, "Review and improve this dimension"),
            })

    # --- Bracket Distribution Data ---
    bracket_distribution = {}
    if "target_bracket" in df.columns:
        counts = df["target_bracket"].value_counts()
        for bracket in DIFFICULTY_ORDER:
            cnt = int(counts.get(bracket, 0))
            bracket_distribution[bracket] = {
                "count": cnt,
                "pct": round(cnt / n * 100, 1) if n > 0 else 0,
            }

    return {
        "grade": grade,
        "score": overall,
        "breakdown": {k: v for k, v in scores.items()},
        "weights": weights,
        "details": details,
        "key_actions": key_actions,
        "bracket_distribution": bracket_distribution,
    }
