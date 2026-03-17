"""
LD Wizard — Phase 4: Difficulty / Revenue / Churn Correlation
Analyzes relationships between difficulty (APS), monetization metrics,
and churn to identify optimal difficulty ranges for revenue and retention.
"""

import pandas as pd
import numpy as np
from engine.parser import DIFFICULTY_ORDER, REVENUE_WEIGHTS


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Number of APS bins for binned analysis
APS_BINS = 10

# Correlation strength labels
def _corr_label(r):
    ar = abs(r)
    if ar >= 0.7: return "strong"
    if ar >= 0.4: return "moderate"
    if ar >= 0.2: return "weak"
    return "negligible"


def compute_correlation_analysis(df):
    """
    Full difficulty-revenue-churn correlation analysis.

    Args:
        df: Enriched DataFrame from parser

    Returns:
        dict with keys:
            - correlation_matrix: pairwise correlations between key metrics
            - aps_binned: binned APS analysis (avg metrics per APS bucket)
            - bracket_metrics: comprehensive metrics per bracket
            - optimal_ranges: identified sweet spots for different objectives
            - scatter_data: data points for scatter plots (APS vs churn, APS vs revenue)
            - insights: list of string insights
    """
    required = ["level", "target_bracket", "aps"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        return {
            "correlation_matrix": {}, "aps_binned": [], "bracket_metrics": [],
            "optimal_ranges": {}, "scatter_data": {}, "insights": [f"Missing columns: {', '.join(missing)}"],
        }

    df = df.copy().sort_values("level").reset_index(drop=True)

    # Fill NaN
    for col in ["combined_churn", "completion_rate", "churn", "churn_3d", "churn_7d"]:
        if col in df.columns:
            df[col] = df[col].fillna(0)

    # Weighted revenue score
    if "_revenue_score" not in df.columns:
        num = pd.Series(0.0, index=df.index)
        tw = 0.0
        for col, w in REVENUE_WEIGHTS.items():
            if col in df.columns:
                num += df[col].fillna(0) * w
                tw += w
        df["_revenue_score"] = (num / tw) if tw > 0 else 0.0

    # --- 1. Correlation Matrix ---
    corr_matrix = _compute_correlation_matrix(df)

    # --- 2. Binned APS Analysis ---
    aps_binned = _compute_aps_binned(df)

    # --- 3. Bracket Metrics ---
    bracket_metrics = _compute_bracket_metrics(df)

    # --- 4. Optimal Ranges ---
    optimal_ranges = _find_optimal_ranges(df, aps_binned)

    # --- 5. Scatter Data ---
    scatter_data = _build_scatter_data(df)

    # --- 6. Churn over Revenue Analysis ---
    churn_revenue = _compute_churn_revenue_analysis(df)

    # --- 7. Diminishing Returns / Monetization Inflection ---
    diminishing_returns = _compute_diminishing_returns(df, aps_binned)

    # --- 8. Insights ---
    insights = _generate_correlation_insights(corr_matrix, aps_binned, bracket_metrics,
                                              optimal_ranges, churn_revenue, diminishing_returns)

    return {
        "correlation_matrix": corr_matrix,
        "aps_binned": aps_binned,
        "bracket_metrics": bracket_metrics,
        "optimal_ranges": optimal_ranges,
        "scatter_data": scatter_data,
        "churn_revenue": churn_revenue,
        "diminishing_returns": diminishing_returns,
        "insights": insights,
    }


def _compute_correlation_matrix(df):
    """Compute pairwise correlation between key metrics."""
    metrics = {
        "aps": "APS",
        "combined_churn": "Combined Churn",
        "completion_rate": "Completion Rate",
        "_revenue_score": "Revenue Score",
        "churn": "Session Churn",
        "churn_3d": "D3 Churn",
        "churn_7d": "D7 Churn",
    }

    available = {k: v for k, v in metrics.items() if k in df.columns}
    cols = list(available.keys())

    matrix = {}
    for i, col_a in enumerate(cols):
        row = {}
        for j, col_b in enumerate(cols):
            valid = df[[col_a, col_b]].dropna()
            if len(valid) > 5:
                r = float(valid.iloc[:, 0].corr(valid.iloc[:, 1]))
                row[available[col_b]] = round(r, 3) if not np.isnan(r) else None
            else:
                row[available[col_b]] = None
        matrix[available[col_a]] = row

    return matrix


def _compute_aps_binned(df):
    """Bin levels by APS and compute average metrics per bin."""
    if "aps" not in df.columns or len(df) == 0:
        return []

    aps_min = float(df["aps"].min())
    aps_max = float(df["aps"].max())
    if aps_max <= aps_min:
        return []

    bin_edges = np.linspace(aps_min, aps_max, APS_BINS + 1)
    bins = []

    for i in range(APS_BINS):
        low, high = bin_edges[i], bin_edges[i + 1]
        if i == APS_BINS - 1:
            subset = df[(df["aps"] >= low) & (df["aps"] <= high)]
        else:
            subset = df[(df["aps"] >= low) & (df["aps"] < high)]

        if len(subset) == 0:
            continue

        entry = {
            "bin_label": f"{low:.2f}–{high:.2f}",
            "bin_low": round(float(low), 3),
            "bin_high": round(float(high), 3),
            "count": int(len(subset)),
            "avg_aps": round(float(subset["aps"].mean()), 3),
        }

        for col, label in [
            ("combined_churn", "avg_churn"),
            ("completion_rate", "avg_completion"),
            ("_revenue_score", "avg_revenue"),
            ("churn", "avg_session_churn"),
            ("churn_3d", "avg_d3_churn"),
            ("churn_7d", "avg_d7_churn"),
        ]:
            if col in subset.columns:
                entry[label] = round(float(subset[col].mean()), 4)

        # Bracket distribution within bin
        bracket_counts = subset["target_bracket"].value_counts().to_dict()
        entry["bracket_mix"] = {k: int(v) for k, v in bracket_counts.items()}

        bins.append(entry)

    return bins


def _compute_bracket_metrics(df):
    """Comprehensive metrics per bracket."""
    result = []
    for bracket in DIFFICULTY_ORDER:
        subset = df[df["target_bracket"] == bracket]
        if len(subset) == 0:
            continue

        entry = {
            "bracket": bracket,
            "count": int(len(subset)),
            "avg_aps": round(float(subset["aps"].mean()), 3),
            "median_aps": round(float(subset["aps"].median()), 3),
        }

        for col, label in [
            ("combined_churn", "avg_churn"),
            ("completion_rate", "avg_completion"),
            ("_revenue_score", "avg_revenue"),
            ("churn", "avg_session_churn"),
            ("churn_3d", "avg_d3_churn"),
            ("churn_7d", "avg_d7_churn"),
            ("win_rate", "avg_win_rate"),
        ]:
            if col in subset.columns:
                val = subset[col].mean()
                entry[label] = round(float(val), 4) if not np.isnan(val) else None

        # Revenue breakdown
        for col, label in [
            ("iap_users_pct", "avg_iap_pct"),
            ("egp_users_pct", "avg_egp_pct"),
            ("booster_users_pct", "avg_booster_pct"),
            ("sink_users_pct", "avg_sink_pct"),
        ]:
            if col in subset.columns:
                val = subset[col].mean()
                entry[label] = round(float(val), 4) if not np.isnan(val) else None

        result.append(entry)

    return result


def _find_optimal_ranges(df, aps_binned):
    """
    Find optimal APS ranges for different objectives:
    - Lowest churn
    - Highest completion
    - Highest revenue
    - Best balanced (composite)
    """
    if not aps_binned:
        return {}

    optimal = {}

    # Lowest churn bin
    churn_bins = [b for b in aps_binned if "avg_churn" in b and b["count"] >= 3]
    if churn_bins:
        best = min(churn_bins, key=lambda b: b["avg_churn"])
        optimal["lowest_churn"] = {
            "range": best["bin_label"],
            "avg_churn": best["avg_churn"],
            "count": best["count"],
        }

    # Highest completion bin
    comp_bins = [b for b in aps_binned if "avg_completion" in b and b["count"] >= 3]
    if comp_bins:
        best = max(comp_bins, key=lambda b: b["avg_completion"])
        optimal["highest_completion"] = {
            "range": best["bin_label"],
            "avg_completion": best["avg_completion"],
            "count": best["count"],
        }

    # Highest revenue bin
    rev_bins = [b for b in aps_binned if "avg_revenue" in b and b["count"] >= 3]
    if rev_bins:
        best = max(rev_bins, key=lambda b: b["avg_revenue"])
        optimal["highest_revenue"] = {
            "range": best["bin_label"],
            "avg_revenue": best["avg_revenue"],
            "count": best["count"],
        }

    # Best balanced: lowest churn × highest completion × highest revenue
    balanced_bins = [b for b in aps_binned if "avg_churn" in b and "avg_completion" in b and b["count"] >= 3]
    if balanced_bins:
        for b in balanced_bins:
            churn_inv = 1.0 - b.get("avg_churn", 0)
            comp = b.get("avg_completion", 0)
            rev = b.get("avg_revenue", 0)
            b["_balanced"] = churn_inv * 0.4 + comp * 0.3 + rev * 0.3

        best = max(balanced_bins, key=lambda b: b["_balanced"])
        optimal["best_balanced"] = {
            "range": best["bin_label"],
            "score": round(best["_balanced"], 3),
            "count": best["count"],
        }

    return optimal


def _build_scatter_data(df):
    """Build scatter plot data for APS vs key metrics."""
    scatter = {}

    # APS vs Combined Churn
    if "aps" in df.columns and "combined_churn" in df.columns:
        valid = df[["level", "aps", "combined_churn", "target_bracket"]].dropna()
        scatter["aps_vs_churn"] = [
            {
                "level": int(row["level"]),
                "x": round(float(row["aps"]), 3),
                "y": round(float(row["combined_churn"]), 4),
                "bracket": row["target_bracket"],
            }
            for _, row in valid.iterrows()
        ]

    # APS vs Revenue Score
    if "aps" in df.columns and "_revenue_score" in df.columns:
        valid = df[["level", "aps", "_revenue_score", "target_bracket"]].dropna()
        scatter["aps_vs_revenue"] = [
            {
                "level": int(row["level"]),
                "x": round(float(row["aps"]), 3),
                "y": round(float(row["_revenue_score"]), 4),
                "bracket": row["target_bracket"],
            }
            for _, row in valid.iterrows()
        ]

    # APS vs Completion Rate
    if "aps" in df.columns and "completion_rate" in df.columns:
        valid = df[["level", "aps", "completion_rate", "target_bracket"]].dropna()
        scatter["aps_vs_completion"] = [
            {
                "level": int(row["level"]),
                "x": round(float(row["aps"]), 3),
                "y": round(float(row["completion_rate"]), 4),
                "bracket": row["target_bracket"],
            }
            for _, row in valid.iterrows()
        ]

    return scatter


def _compute_churn_revenue_analysis(df):
    """
    Analyze the churn-to-revenue tradeoff:
    - Per-bracket churn vs revenue
    - Churn-revenue efficiency (revenue gained per unit of churn)
    - Scatter data for churn vs revenue
    - Identification of "worth it" and "not worth it" levels
    """
    result = {
        "bracket_tradeoff": [],
        "scatter": [],
        "efficiency_zones": [],
    }

    if "combined_churn" not in df.columns or "_revenue_score" not in df.columns:
        return result

    # --- Per-bracket churn vs revenue tradeoff ---
    for bracket in DIFFICULTY_ORDER:
        subset = df[df["target_bracket"] == bracket]
        if len(subset) == 0:
            continue

        avg_churn = float(subset["combined_churn"].mean())
        avg_rev = float(subset["_revenue_score"].mean())
        # Efficiency: revenue per unit of churn (higher = better tradeoff)
        efficiency = avg_rev / max(avg_churn, 0.001)

        result["bracket_tradeoff"].append({
            "bracket": bracket,
            "count": int(len(subset)),
            "avg_churn": round(avg_churn, 4),
            "avg_revenue": round(avg_rev, 4),
            "efficiency": round(efficiency, 3),
        })

    # --- Scatter: churn vs revenue per level ---
    valid = df[["level", "combined_churn", "_revenue_score", "target_bracket", "aps"]].dropna()
    result["scatter"] = [
        {
            "level": int(row["level"]),
            "churn": round(float(row["combined_churn"]), 4),
            "revenue": round(float(row["_revenue_score"]), 4),
            "bracket": row["target_bracket"],
            "aps": round(float(row["aps"]), 3),
        }
        for _, row in valid.iterrows()
    ]

    # --- Efficiency zones: bin by churn and see avg revenue ---
    churn_min = float(df["combined_churn"].min())
    churn_max = float(df["combined_churn"].max())
    if churn_max > churn_min:
        n_bins = 8
        edges = np.linspace(churn_min, churn_max, n_bins + 1)
        for i in range(n_bins):
            low, high = edges[i], edges[i + 1]
            if i == n_bins - 1:
                subset = df[(df["combined_churn"] >= low) & (df["combined_churn"] <= high)]
            else:
                subset = df[(df["combined_churn"] >= low) & (df["combined_churn"] < high)]

            if len(subset) == 0:
                continue

            avg_rev = float(subset["_revenue_score"].mean())
            avg_aps = float(subset["aps"].mean()) if "aps" in subset.columns else None
            result["efficiency_zones"].append({
                "churn_range": f"{low*100:.2f}%–{high*100:.2f}%",
                "churn_mid": round((low + high) / 2, 4),
                "count": int(len(subset)),
                "avg_revenue": round(avg_rev, 4),
                "avg_aps": round(avg_aps, 3) if avg_aps is not None else None,
            })

    return result


def _compute_diminishing_returns(df, aps_binned):
    """
    Detect the monetization inflection point — the APS level beyond which
    increasing difficulty no longer generates proportionally more revenue
    but churn continues to climb (diminishing returns).

    Method: Walk through APS bins sorted by difficulty. At each bin,
    compute the marginal revenue gain vs. marginal churn cost.
    The inflection point is where marginal churn overtakes marginal revenue.
    """
    result = {
        "inflection_aps": None,
        "inflection_bin": None,
        "marginal_analysis": [],
        "summary": "",
        "content_runway": None,
    }

    # Need at least 4 bins with both churn and revenue data
    valid_bins = [b for b in aps_binned
                  if "avg_churn" in b and "avg_revenue" in b and b["count"] >= 3]
    if len(valid_bins) < 4:
        result["summary"] = "Insufficient data for diminishing returns analysis."
        return result

    # Sort bins by APS (ascending difficulty)
    valid_bins.sort(key=lambda b: b["avg_aps"])

    # Compute marginal revenue and marginal churn between consecutive bins
    inflection_found = False
    peak_efficiency_bin = None
    peak_efficiency = -float("inf")

    for i in range(1, len(valid_bins)):
        prev = valid_bins[i - 1]
        curr = valid_bins[i]

        delta_aps = curr["avg_aps"] - prev["avg_aps"]
        delta_rev = curr["avg_revenue"] - prev["avg_revenue"]
        delta_churn = curr["avg_churn"] - prev["avg_churn"]

        # Marginal efficiency: how much revenue gained per unit churn added
        marginal_eff = delta_rev / max(delta_churn, 0.0001) if delta_churn > 0 else (
            float("inf") if delta_rev > 0 else 0
        )

        entry = {
            "from_bin": prev["bin_label"],
            "to_bin": curr["bin_label"],
            "from_aps": prev["avg_aps"],
            "to_aps": curr["avg_aps"],
            "delta_revenue": round(delta_rev, 4),
            "delta_churn": round(delta_churn, 4),
            "marginal_efficiency": round(marginal_eff, 3) if abs(marginal_eff) < 1000 else None,
            "verdict": "",
        }

        # Track peak efficiency
        if marginal_eff != float("inf") and marginal_eff > peak_efficiency:
            peak_efficiency = marginal_eff
            peak_efficiency_bin = curr

        # Classify: is this step worth it?
        if delta_rev <= 0 and delta_churn > 0:
            entry["verdict"] = "diminishing"  # More churn, no more revenue
            if not inflection_found:
                inflection_found = True
                result["inflection_aps"] = round(prev["avg_aps"], 3)
                result["inflection_bin"] = prev["bin_label"]
        elif delta_rev > 0 and delta_churn > 0:
            if delta_churn > delta_rev * 3:
                entry["verdict"] = "costly"  # Revenue grows but churn grows faster
            else:
                entry["verdict"] = "worthwhile"
        elif delta_rev > 0 and delta_churn <= 0:
            entry["verdict"] = "ideal"  # More revenue, less churn
        else:
            entry["verdict"] = "neutral"

        result["marginal_analysis"].append(entry)

    # If no clear inflection, check for the point where efficiency drops below 1.0
    if not inflection_found:
        for entry in result["marginal_analysis"]:
            if entry["marginal_efficiency"] is not None and entry["marginal_efficiency"] < 0:
                result["inflection_aps"] = round(entry["from_aps"], 3)
                result["inflection_bin"] = entry["from_bin"]
                inflection_found = True
                break

    # --- Content Runway Estimation ---
    # How many more 50-level zones before retention drops below viability?
    if "funnel_pct" in df.columns and len(df) >= 50:
        sorted_df = df.sort_values("level")
        n_levels = len(sorted_df)
        # Average funnel loss per 50 levels (last half of the funnel to avoid early-game skew)
        mid = n_levels // 2
        if mid >= 25 and n_levels - mid >= 25:
            mid_pct = float(sorted_df.iloc[mid]["funnel_pct"])
            end_pct = float(sorted_df.iloc[-1]["funnel_pct"])
            levels_in_second_half = n_levels - mid
            if mid_pct > end_pct and mid_pct > 0:
                loss_per_level = (mid_pct - end_pct) / levels_in_second_half
                # How many levels until we hit 1% retention?
                remaining_pct = end_pct - 0.01
                if remaining_pct > 0 and loss_per_level > 0:
                    levels_remaining = int(remaining_pct / loss_per_level)
                    zones_remaining = levels_remaining // 50
                    result["content_runway"] = {
                        "current_retention": round(end_pct * 100, 2),
                        "loss_per_50_levels": round(loss_per_level * 50 * 100, 2),
                        "levels_to_1pct": levels_remaining,
                        "zones_of_50_to_1pct": zones_remaining,
                    }

    # Summary
    if inflection_found:
        result["summary"] = (f"Monetization inflection detected at APS ~{result['inflection_aps']:.2f} "
                             f"({result['inflection_bin']}). Beyond this point, increasing difficulty "
                             f"yields diminishing or negative returns relative to churn cost.")
    else:
        result["summary"] = ("No clear monetization inflection detected — revenue continues to scale "
                             "with difficulty across the current APS range.")

    if result["content_runway"]:
        cr = result["content_runway"]
        result["summary"] += (f" Content runway: ~{cr['levels_to_1pct']} levels ({cr['zones_of_50_to_1pct']} zones of 50) "
                              f"remaining before retention drops below 1% (currently {cr['current_retention']:.1f}%, "
                              f"losing ~{cr['loss_per_50_levels']:.1f}pp per 50 levels).")

    return result


def _generate_correlation_insights(corr_matrix, aps_binned, bracket_metrics, optimal_ranges, churn_revenue=None, diminishing_returns=None):
    """Generate human-readable insights about correlations."""
    insights = []

    # Key correlations from the matrix
    if "APS" in corr_matrix:
        aps_row = corr_matrix["APS"]

        if "Combined Churn" in aps_row and aps_row["Combined Churn"] is not None:
            r = aps_row["Combined Churn"]
            label = _corr_label(r)
            direction = "positive" if r > 0 else "negative"
            insights.append(f"APS ↔ Combined Churn: {label} {direction} correlation (r={r}). {'Harder levels drive more churn.' if r > 0.3 else ''}")

        if "Completion Rate" in aps_row and aps_row["Completion Rate"] is not None:
            r = aps_row["Completion Rate"]
            label = _corr_label(r)
            insights.append(f"APS ↔ Completion Rate: {label} correlation (r={r}). {'Harder levels have lower completion as expected.' if r < -0.3 else ''}")

        if "Revenue Score" in aps_row and aps_row["Revenue Score"] is not None:
            r = aps_row["Revenue Score"]
            label = _corr_label(r)
            insights.append(f"APS ↔ Revenue: {label} correlation (r={r}). {'Higher difficulty drives monetization.' if r > 0.3 else ''}")

    # Churn progression across brackets
    if len(bracket_metrics) >= 2:
        churn_values = [(b["bracket"], b.get("avg_churn", 0)) for b in bracket_metrics if b.get("avg_churn") is not None]
        if len(churn_values) >= 2:
            first_churn = churn_values[0][1]
            last_churn = churn_values[-1][1]
            if last_churn > first_churn * 1.5:
                insights.append(
                    f"Churn escalates from {churn_values[0][0]} ({first_churn*100:.2f}%) to "
                    f"{churn_values[-1][0]} ({last_churn*100:.2f}%) — a {(last_churn/first_churn):.1f}× increase."
                )

    # Revenue progression
    if len(bracket_metrics) >= 2:
        rev_values = [(b["bracket"], b.get("avg_revenue", 0)) for b in bracket_metrics if b.get("avg_revenue") is not None]
        if len(rev_values) >= 2:
            first_rev = rev_values[0][1]
            last_rev = rev_values[-1][1]
            if last_rev > first_rev * 1.5 and last_rev > 0.01:
                insights.append(
                    f"Revenue increases from {rev_values[0][0]} to {rev_values[-1][0]} — "
                    f"harder brackets drive {(last_rev/max(first_rev, 0.001)):.1f}× more monetization."
                )

    # Optimal ranges
    if "lowest_churn" in optimal_ranges:
        r = optimal_ranges["lowest_churn"]
        insights.append(f"Lowest churn APS range: {r['range']} (avg churn: {r['avg_churn']*100:.2f}%).")
    if "highest_revenue" in optimal_ranges:
        r = optimal_ranges["highest_revenue"]
        insights.append(f"Highest revenue APS range: {r['range']} (avg revenue score: {r['avg_revenue']:.3f}).")
    if "best_balanced" in optimal_ranges:
        r = optimal_ranges["best_balanced"]
        insights.append(f"Best balanced APS range: {r['range']} (composite score: {r['score']}).")

    # Churn-revenue tradeoff insights
    if churn_revenue and churn_revenue.get("bracket_tradeoff"):
        tradeoffs = churn_revenue["bracket_tradeoff"]
        best_eff = max(tradeoffs, key=lambda t: t["efficiency"])
        worst_eff = min(tradeoffs, key=lambda t: t["efficiency"])
        if best_eff["bracket"] != worst_eff["bracket"]:
            insights.append(
                f"Best churn-to-revenue efficiency: {best_eff['bracket']} "
                f"(efficiency {best_eff['efficiency']:.2f} — revenue per unit churn). "
                f"Worst: {worst_eff['bracket']} ({worst_eff['efficiency']:.2f})."
            )

    # Diminishing returns insights
    if diminishing_returns:
        if diminishing_returns.get("inflection_aps") is not None:
            insights.append(
                f"⚠ Monetization inflection at APS ~{diminishing_returns['inflection_aps']:.2f}: "
                f"beyond this point, harder levels yield diminishing revenue returns while churn keeps climbing."
            )
        ma = diminishing_returns.get("marginal_analysis", [])
        costly_steps = [m for m in ma if m["verdict"] == "diminishing"]
        if costly_steps:
            insights.append(
                f"{len(costly_steps)} APS range(s) show negative returns — churn increases "
                f"with no revenue gain. Consider capping difficulty in these ranges."
            )
        runway = diminishing_returns.get("content_runway")
        if runway:
            insights.append(
                f"Content runway: ~{runway['levels_to_1pct']} more levels "
                f"({runway['zones_of_50_to_1pct']} zones of 50) before retention drops below 1%. "
                f"Current end retention: {runway['current_retention']:.1f}%, "
                f"losing ~{runway['loss_per_50_levels']:.1f}pp per 50 levels."
            )

    return insights
