"""
LD Wizard — AB test analysis
Compares control vs variant cohorts across the level funnel.
"""

import math
import pandas as pd

from engine.parser import DIFFICULTY_ORDER


def compute_ab_test_analysis(df, meta):
    if df is None or len(df) == 0:
        return {"available": False, "reason": "No AB test workbook loaded."}

    control_label = (meta or {}).get("control_label", "Control")
    variant_label = (meta or {}).get("variant_label", "Variant")
    working = df.copy().sort_values("level").reset_index(drop=True)

    summary = _cohort_summary(working)
    if summary is None:
        return {"available": False, "reason": "The AB workbook is missing required cohort metrics."}

    funnel_curve = []
    for _, row in working.iterrows():
        funnel_curve.append({
            "level": int(row["level"]),
            "control_funnel_pct": _pct_value(row.get("control_funnel_pct")),
            "variant_funnel_pct": _pct_value(row.get("variant_funnel_pct")),
            "control_d3_churn_pct": _pct_value(row.get("control_churn_3d")),
            "variant_d3_churn_pct": _pct_value(row.get("variant_churn_3d")),
        })

    level_swings = []
    for _, row in working.iterrows():
        control_users = float(row.get("control_users") or 0)
        variant_users = float(row.get("variant_users") or 0)
        control_rev_per_k = _revenue_per_k(row.get("control_iap_revenue"), control_users)
        variant_rev_per_k = _revenue_per_k(row.get("variant_iap_revenue"), variant_users)
        control_churn_pct = _pct_value(row.get("control_churn_3d"))
        variant_churn_pct = _pct_value(row.get("variant_churn_3d"))
        control_completion_pct = _pct_value(row.get("control_completion_rate"))
        variant_completion_pct = _pct_value(row.get("variant_completion_rate"))
        control_funnel_pct = _pct_value(row.get("control_funnel_pct"))
        variant_funnel_pct = _pct_value(row.get("variant_funnel_pct"))

        revenue_delta_pct = _relative_lift(control_rev_per_k, variant_rev_per_k)
        revenue_delta_per_k = round(variant_rev_per_k - control_rev_per_k, 2)
        churn_delta_pp = None if control_churn_pct is None or variant_churn_pct is None else round(variant_churn_pct - control_churn_pct, 3)
        completion_delta_pp = None if control_completion_pct is None or variant_completion_pct is None else round(variant_completion_pct - control_completion_pct, 3)
        funnel_delta_pp = None if control_funnel_pct is None or variant_funnel_pct is None else round(variant_funnel_pct - control_funnel_pct, 3)
        revenue_signal = math.copysign(math.log1p(abs(revenue_delta_per_k)) * 12.0, revenue_delta_per_k)

        balanced_delta = (
            revenue_signal
            + (completion_delta_pp or 0) * 4.0
            + (funnel_delta_pp or 0) * 6.0
            - (churn_delta_pp or 0) * 8.0
        )

        level_swings.append({
            "level": int(row["level"]),
            "bracket": row.get("target_bracket"),
            "balanced_delta": round(balanced_delta, 3),
            "revenue_delta_per_k_users": revenue_delta_per_k,
            "revenue_delta_pct": round(revenue_delta_pct, 2) if revenue_delta_pct is not None else None,
            "churn_delta_pp": churn_delta_pp,
            "completion_delta_pp": completion_delta_pp,
            "funnel_delta_pp": funnel_delta_pp,
            "winner": _swing_winner(balanced_delta),
        })

    positive_swings = sorted([item for item in level_swings if item["balanced_delta"] > 0], key=lambda item: item["balanced_delta"], reverse=True)[:6]
    negative_swings = sorted([item for item in level_swings if item["balanced_delta"] < 0], key=lambda item: item["balanced_delta"])[:6]

    bracket_breakdown = []
    if "target_bracket" in working.columns and working["target_bracket"].notna().any():
        for bracket in DIFFICULTY_ORDER:
            subset = working[working["target_bracket"] == bracket]
            if subset.empty:
                continue
            bracket_breakdown.append(_bracket_result(subset, bracket, control_label, variant_label))

    headline, verdict, recommendation = _headline(summary, control_label, variant_label)
    findings = _build_findings(summary, bracket_breakdown, control_label, variant_label)

    return {
        "available": True,
        "headline": headline,
        "verdict": verdict,
        "recommendation": recommendation,
        "control_label": control_label,
        "variant_label": variant_label,
        "summary": summary,
        "findings": findings,
        "funnel_curve": funnel_curve,
        "bracket_breakdown": bracket_breakdown,
        "top_positive_levels": positive_swings,
        "top_negative_levels": negative_swings,
    }


def _cohort_summary(df):
    if "control_users" not in df.columns or "variant_users" not in df.columns:
        return None

    first_level = df.iloc[0]
    control_start_users = float(first_level.get("control_users") or 0)
    variant_start_users = float(first_level.get("variant_users") or 0)
    if control_start_users <= 0 or variant_start_users <= 0:
        return None

    control_total_revenue = float(df.get("control_iap_revenue", pd.Series(dtype=float)).fillna(0).sum())
    variant_total_revenue = float(df.get("variant_iap_revenue", pd.Series(dtype=float)).fillna(0).sum())

    control_revenue_per_k_starters = round(control_total_revenue / control_start_users * 1000, 2)
    variant_revenue_per_k_starters = round(variant_total_revenue / variant_start_users * 1000, 2)

    control_weighted_d3 = _weighted_average(df.get("control_churn_3d"), df.get("control_users"))
    variant_weighted_d3 = _weighted_average(df.get("variant_churn_3d"), df.get("variant_users"))
    control_weighted_completion = _weighted_average(df.get("control_completion_rate"), df.get("control_users"))
    variant_weighted_completion = _weighted_average(df.get("variant_completion_rate"), df.get("variant_users"))

    control_end_funnel = _last_non_null(df.get("control_funnel_pct"))
    variant_end_funnel = _last_non_null(df.get("variant_funnel_pct"))

    control_score = _cohort_value_score(control_revenue_per_k_starters, control_weighted_d3, control_end_funnel, control_weighted_completion)
    variant_score = _cohort_value_score(variant_revenue_per_k_starters, variant_weighted_d3, variant_end_funnel, variant_weighted_completion)

    control_rev_per_level_k = round(control_total_revenue / max(float(df.get("control_users", pd.Series(dtype=float)).fillna(0).sum()), 1.0) * 1000, 2)
    variant_rev_per_level_k = round(variant_total_revenue / max(float(df.get("variant_users", pd.Series(dtype=float)).fillna(0).sum()), 1.0) * 1000, 2)

    winner = "mixed"
    if variant_score >= control_score * 1.03:
        winner = "variant"
    elif control_score >= variant_score * 1.03:
        winner = "control"

    return {
        "winner": winner,
        "control": {
            "starting_users": int(round(control_start_users)),
            "total_iap_revenue": round(control_total_revenue, 2),
            "revenue_per_k_starters": control_revenue_per_k_starters,
            "revenue_per_k_level_users": control_rev_per_level_k,
            "avg_d3_churn_pct": _pct_value(control_weighted_d3),
            "avg_completion_pct": _pct_value(control_weighted_completion),
            "end_funnel_pct": _pct_value(control_end_funnel),
            "value_score": round(control_score, 3),
        },
        "variant": {
            "starting_users": int(round(variant_start_users)),
            "total_iap_revenue": round(variant_total_revenue, 2),
            "revenue_per_k_starters": variant_revenue_per_k_starters,
            "revenue_per_k_level_users": variant_rev_per_level_k,
            "avg_d3_churn_pct": _pct_value(variant_weighted_d3),
            "avg_completion_pct": _pct_value(variant_weighted_completion),
            "end_funnel_pct": _pct_value(variant_end_funnel),
            "value_score": round(variant_score, 3),
        },
        "deltas": {
            "revenue_per_k_starters_pct": round(_relative_lift(control_revenue_per_k_starters, variant_revenue_per_k_starters), 2),
            "revenue_per_k_level_users_pct": round(_relative_lift(control_rev_per_level_k, variant_rev_per_level_k), 2),
            "d3_churn_pp": round((_pct_value(variant_weighted_d3) or 0) - (_pct_value(control_weighted_d3) or 0), 3),
            "completion_pp": round((_pct_value(variant_weighted_completion) or 0) - (_pct_value(control_weighted_completion) or 0), 3),
            "end_funnel_pp": round((_pct_value(variant_end_funnel) or 0) - (_pct_value(control_end_funnel) or 0), 3),
            "value_score_pct": round(_relative_lift(control_score, variant_score), 2),
        },
    }


def _bracket_result(subset, bracket, control_label, variant_label):
    control_users = subset.get("control_users", pd.Series(dtype=float)).fillna(0)
    variant_users = subset.get("variant_users", pd.Series(dtype=float)).fillna(0)
    control_revenue = float(subset.get("control_iap_revenue", pd.Series(dtype=float)).fillna(0).sum())
    variant_revenue = float(subset.get("variant_iap_revenue", pd.Series(dtype=float)).fillna(0).sum())

    control_rev_per_k = round(control_revenue / max(float(control_users.sum()), 1.0) * 1000, 2)
    variant_rev_per_k = round(variant_revenue / max(float(variant_users.sum()), 1.0) * 1000, 2)
    control_d3 = _pct_value(_weighted_average(subset.get("control_churn_3d"), control_users))
    variant_d3 = _pct_value(_weighted_average(subset.get("variant_churn_3d"), variant_users))
    control_completion = _pct_value(_weighted_average(subset.get("control_completion_rate"), control_users))
    variant_completion = _pct_value(_weighted_average(subset.get("variant_completion_rate"), variant_users))

    control_score = _cohort_value_score(control_rev_per_k, _decimal_from_pct(control_d3), _decimal_from_pct(control_completion), _decimal_from_pct(control_completion))
    variant_score = _cohort_value_score(variant_rev_per_k, _decimal_from_pct(variant_d3), _decimal_from_pct(variant_completion), _decimal_from_pct(variant_completion))

    winner = "mixed"
    if variant_score >= control_score * 1.04:
        winner = "variant"
    elif control_score >= variant_score * 1.04:
        winner = "control"

    return {
        "bracket": bracket,
        "level_count": int(len(subset)),
        "winner": winner,
        "winner_label": variant_label if winner == "variant" else control_label if winner == "control" else "Mixed",
        "control_revenue_per_k_users": control_rev_per_k,
        "variant_revenue_per_k_users": variant_rev_per_k,
        "control_d3_churn_pct": control_d3,
        "variant_d3_churn_pct": variant_d3,
        "control_completion_pct": control_completion,
        "variant_completion_pct": variant_completion,
        "delta_revenue_pct": round(_relative_lift(control_rev_per_k, variant_rev_per_k), 2),
        "delta_d3_churn_pp": round((variant_d3 or 0) - (control_d3 or 0), 3),
    }


def _headline(summary, control_label, variant_label):
    deltas = summary["deltas"]
    winner = summary["winner"]
    if winner == "variant":
        if deltas["d3_churn_pp"] <= 0.15 and deltas["end_funnel_pp"] >= -0.2:
            return (
                f"{variant_label} wins on value without meaningfully hurting retention.",
                "success",
                "Ship candidate",
            )
        return (
            f"{variant_label} monetizes better, but the retention cost needs review.",
            "warning",
            "Mixed result",
        )
    if winner == "control":
        return (
            f"{control_label} stays healthier once churn and funnel depth are priced into the comparison.",
            "danger",
            "Keep control",
        )
    return (
        "Neither cohort is a clean winner yet; the experiment is mixed across monetization and retention.",
        "warning",
        "Mixed result",
    )


def _build_findings(summary, bracket_breakdown, control_label, variant_label):
    deltas = summary["deltas"]
    findings = [
        {
            "title": "Revenue per 1k starters",
            "detail": f"{variant_label} is {signed_pct(deltas['revenue_per_k_starters_pct'])} vs {control_label}.",
        },
        {
            "title": "3-day churn",
            "detail": f"{variant_label} changes D3 churn by {signed_pp(deltas['d3_churn_pp'])} vs {control_label}.",
        },
        {
            "title": "End funnel reach",
            "detail": f"{variant_label} changes end-of-funnel reach by {signed_pp(deltas['end_funnel_pp'])}.",
        },
    ]

    strong_variant = next((item for item in bracket_breakdown if item["winner"] == "variant"), None)
    strong_control = next((item for item in bracket_breakdown if item["winner"] == "control"), None)
    if strong_variant:
        findings.append({
            "title": "Variant pocket",
            "detail": f"{variant_label} looks strongest in {strong_variant['bracket']} levels.",
        })
    if strong_control:
        findings.append({
            "title": "Control pocket",
            "detail": f"{control_label} still looks stronger in {strong_control['bracket']} levels.",
        })
    return findings[:5]


def _cohort_value_score(revenue_per_k, d3_churn, end_funnel, completion):
    churn_pct = _pct_value(d3_churn)
    end_funnel_pct = _pct_value(end_funnel)
    completion_pct = _pct_value(completion)
    churn_gate = 1.0 / (1.0 + math.exp(((churn_pct or 0) - 2.2) / 0.45))
    return revenue_per_k * churn_gate * (0.55 + 0.45 * ((end_funnel_pct or 0) / 100.0)) * (0.65 + 0.35 * ((completion_pct or 0) / 100.0))


def _weighted_average(values, weights):
    if values is None or weights is None:
        return None
    values = pd.to_numeric(values, errors="coerce")
    weights = pd.to_numeric(weights, errors="coerce").fillna(0)
    mask = values.notna()
    if not mask.any():
        return None
    values = values[mask]
    weights = weights[mask]
    if weights.sum() <= 0:
        return float(values.mean())
    return float((values * weights).sum() / weights.sum())


def _last_non_null(series):
    if series is None:
        return None
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if clean.empty:
        return None
    return float(clean.iloc[-1])


def _revenue_per_k(revenue, users):
    if revenue is None or users is None or users <= 0:
        return 0.0
    return float(revenue) / float(users) * 1000.0


def _relative_lift(control_value, variant_value):
    if control_value in (None, 0):
        return None
    return (float(variant_value) - float(control_value)) / float(control_value) * 100.0


def _pct_value(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    return round(float(value) * 100, 3)


def _decimal_from_pct(value):
    if value is None:
        return None
    return float(value) / 100.0


def _swing_winner(balanced_delta):
    if balanced_delta >= 0.2:
        return "variant"
    if balanced_delta <= -0.2:
        return "control"
    return "mixed"


def signed_pct(value):
    if value is None:
        return "n/a"
    return f"{value:+.1f}%"


def signed_pp(value):
    if value is None:
        return "n/a"
    return f"{value:+.2f} pp"
