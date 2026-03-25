import os
import json
import math
from collections import Counter
from flask import Flask, render_template, request, redirect, url_for, flash, session
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS_LEVEL_DATA, ALLOWED_EXTENSIONS_LEVEL_PARAMS, MAX_CONTENT_LENGTH, SECRET_KEY
from engine.parser import process_files, DIFFICULTY_ORDER
from engine.parser_ab import process_ab_file
from engine.aps_engine import compute_aps_ranges
from engine.analysis.funnel import compute_funnel_analysis
from engine.analysis.ranking import compute_ranking
from engine.analysis.dropoff import compute_dropoff_analysis
from engine.analysis.correlation import compute_correlation_analysis
from engine.analysis.recommendations import compute_recommendations
from engine.analysis.main_breakdown import compute_main_breakdown
from engine.analysis.strategic import compute_strategic_views
from engine.analysis.ab_test import compute_ab_test_analysis
from engine.analysis.difficulty_bands import build_aps_adaptive_bands, classify_aps_bracket, format_band_label

app = Flask(__name__)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
app.config["MAX_CONTENT_LENGTH"] = MAX_CONTENT_LENGTH
app.secret_key = SECRET_KEY

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# In-memory store for parsed data (per-process, fine for local single-user app)
_app_data = {
    "df": None,           # Currently active (possibly filtered) DataFrame
    "df_full": None,      # Full unfiltered DataFrame (always kept)
    "summary": None,
    "aps_results": None,
    "funnel_results": None,
    "ranking_results": None,
    "dropoff_results": None,
    "correlation_results": None,
    "recommendations": None,
    "main_breakdown": None,
    "strategic_views": None,
    "ab_test_df": None,
    "ab_test_meta": None,
    "ab_test_results": None,
    "level_range": None,  # Current filter: {"min": int, "max": int} or None
    "analysis_scope": None,  # Current scope: {"start": int, "end": int, "loop_start": int|None}
}


def _run_all_analyses(df):
    """Run all analysis engines on a DataFrame and update _app_data."""
    from engine.parser import compute_summary
    _app_data["df"] = df
    _app_data["summary"] = compute_summary(df)
    _app_data["aps_results"] = compute_aps_ranges(df)
    _app_data["funnel_results"] = compute_funnel_analysis(df)
    _app_data["ranking_results"] = compute_ranking(df)
    _app_data["dropoff_results"] = compute_dropoff_analysis(df)
    _app_data["correlation_results"] = compute_correlation_analysis(df)
    _app_data["recommendations"] = compute_recommendations(
        df, _app_data["aps_results"], _app_data["funnel_results"],
        _app_data["ranking_results"], _app_data["dropoff_results"],
        _app_data["correlation_results"]
    )
    _app_data["main_breakdown"] = compute_main_breakdown(df)
    tutorial_max_level = (_app_data["recommendations"] or {}).get("tutorial_max_level", 0)
    _app_data["strategic_views"] = compute_strategic_views(
        df,
        _app_data.get("analysis_scope"),
        tutorial_max_level=tutorial_max_level,
    )
    _app_data["ab_test_results"] = compute_ab_test_analysis(
        _app_data.get("ab_test_df"),
        _app_data.get("ab_test_meta"),
    )


def _clear_primary_analysis_data():
    _app_data["df"] = None
    _app_data["df_full"] = None
    _app_data["summary"] = None
    _app_data["aps_results"] = None
    _app_data["funnel_results"] = None
    _app_data["ranking_results"] = None
    _app_data["dropoff_results"] = None
    _app_data["correlation_results"] = None
    _app_data["recommendations"] = None
    _app_data["main_breakdown"] = None
    _app_data["strategic_views"] = None
    _app_data["level_range"] = None
    _app_data["analysis_scope"] = None


def _run_ab_only_analyses():
    _clear_primary_analysis_data()
    _app_data["ab_test_results"] = compute_ab_test_analysis(
        _app_data.get("ab_test_df"),
        _app_data.get("ab_test_meta"),
    )


def _coerce_pct(value, digits=1):
    if value is None:
        return None
    return round(float(value) * 100, digits)


def _get_full_level_bounds(df):
    return int(df["level"].min()), int(df["level"].max())


def _default_analysis_scope(df):
    full_min, full_max = _get_full_level_bounds(df)
    return {"start": full_min, "end": full_max, "loop_start": None}


def _scope_labels(df_full, scope):
    full_min, full_max = _get_full_level_bounds(df_full)
    current_scope = scope or _default_analysis_scope(df_full)
    loop_start = current_scope.get("loop_start")

    return {
        "full_min": full_min,
        "full_max": full_max,
        "full_range_label": f"L{full_min}\u2013L{full_max}",
        "analysis_range_label": f"L{current_scope['start']}\u2013L{current_scope['end']}",
        "loop_start_label": f"L{loop_start}" if loop_start is not None else "Not set",
    }


def _normalize_analysis_scope(payload, df_full):
    full_min, full_max = _get_full_level_bounds(df_full)

    start = payload.get("start", payload.get("level_min"))
    end = payload.get("end", payload.get("level_max"))
    loop_start = payload.get("loop_start", payload.get("loop_start_level"))

    if start is None and end is None and loop_start in (None, ""):
        return _default_analysis_scope(df_full), df_full.copy()

    if start is None or end is None:
        raise ValueError("Start and end levels must both be provided.")

    start = max(full_min, int(start))
    end = min(full_max, int(end))
    if start > end:
        raise ValueError("Start level must be \u2264 end level.")

    if loop_start in (None, ""):
        loop_start = None
    else:
        loop_start = int(loop_start)
        if loop_start < start or loop_start > end:
            raise ValueError("Loop start level must fall within the selected analysis range.")

    df_filtered = df_full[(df_full["level"] >= start) & (df_full["level"] <= end)].copy()
    if len(df_filtered) < 2:
        raise ValueError("Selected range has fewer than 2 levels.")

    return {"start": start, "end": end, "loop_start": loop_start}, df_filtered


def _build_focus_dashboard_payload():
    summary = _app_data.get("summary") or {}
    df_full = _app_data.get("df_full")
    scope = _app_data.get("analysis_scope")
    strategic_views = _app_data.get("strategic_views") or {}
    if _app_data.get("df") is None or df_full is None:
        return {
            "available": False,
            "summary": {
                "total_levels": 0,
                "level_range": None,
                "avg_aps": None,
                "avg_completion_pct": None,
                "avg_combined_churn_pct": None,
            },
            "scope": None,
            "data_quality": {
                "has_immature_data": False,
                "maturity_label": None,
                "maturity_detail": "No level-data workbook is loaded.",
                "has_params_file": False,
                "params_note": "Upload a Level Data file to unlock the core dashboard analyses.",
                "loop_scope_note": "AB-only mode is active.",
            },
            "strategic_views": {
                "late_aps_trend": {"available": False, "reason": "No level-data workbook is loaded."},
                "end_game_loop": {"available": False, "reason": "No level-data workbook is loaded."},
                "diminishing_returns": {"available": False, "reason": "No level-data workbook is loaded."},
            },
        }

    return {
        "available": True,
        "summary": {
            "total_levels": int(summary.get("total_levels", 0)),
            "level_range": summary.get("level_range"),
            "avg_aps": round(float(summary.get("avg_aps", 0)), 3) if summary.get("avg_aps") is not None else None,
            "avg_completion_pct": _coerce_pct(summary.get("avg_completion")),
            "avg_combined_churn_pct": _coerce_pct(summary.get("avg_combined_churn"), digits=2),
        },
        "scope": _scope_labels(df_full, scope) if df_full is not None else None,
        "data_quality": {
            "has_immature_data": bool(summary.get("has_immature_data")),
            "maturity_label": summary.get("churn_maturity_label"),
            "maturity_detail": summary.get("churn_maturity_detail", ""),
            "has_params_file": bool(summary.get("has_params_file")),
            "params_note": (
                "Mechanics analysis is enabled."
                if summary.get("has_params_file")
                else "No Level Parameters file loaded. Recommendations are performance-based only."
            ),
            "loop_scope_note": (
                f"End-game loop analyses will anchor from L{scope['loop_start']}."
                if scope and scope.get("loop_start") is not None
                else "Loop start is not set yet."
            ),
        },
        "strategic_views": {
            "late_aps_trend": strategic_views.get("late_aps_trend", {}),
            "end_game_loop": strategic_views.get("end_game_loop", {}),
            "diminishing_returns": strategic_views.get("diminishing_returns", {}),
        },
    }


def _build_ab_test_payload(bucket_size=10):
    results = _app_data.get("ab_test_results") or {}
    meta = _app_data.get("ab_test_meta") or {}
    if _app_data.get("ab_test_df") is None:
        return {"available": False, "reason": "No AB test workbook loaded."}

    payload = dict(compute_ab_test_analysis(
        _app_data.get("ab_test_df"),
        meta,
        level_bucket_size=bucket_size,
    ))
    payload["meta"] = meta
    return payload


def _build_bracket_performance_payload():
    ranking_results = _app_data.get("ranking_results") or {}
    rankings = ranking_results.get("rankings") or []
    tag_accuracy = _build_difficulty_tag_accuracy_payload(_app_data.get("df"))
    if not rankings and not tag_accuracy.get("available"):
        return {
            "available": False,
            "reason": "No bracket data is available for the current scope.",
        }

    best_per_bracket = ranking_results.get("best_per_bracket") or {}
    worst_per_bracket = ranking_results.get("worst_per_bracket") or {}
    outliers = ranking_results.get("outliers") or []

    bracket_stats = {}
    for entry in rankings:
        bracket = entry.get("bracket")
        if not bracket:
            continue
        stats = bracket_stats.setdefault(bracket, {
            "scores": [],
            "raw_scores": [],
            "aps": [],
            "combined_churn": [],
            "completion_rate": [],
            "revenue_score": [],
            "revenue_per_k_users": [],
            "iap_users_pct": [],
            "count": 0,
        })
        stats["count"] += 1
        for key in ("perf_score", "perf_score_raw", "aps", "combined_churn", "completion_rate", "revenue_score", "revenue_per_k_users", "iap_users_pct"):
            value = entry.get(key)
            if value is not None:
                target_key = "scores" if key == "perf_score" else "raw_scores" if key == "perf_score_raw" else key
                stats[target_key].append(float(value))

    bracket_cards = []
    for bracket, stats in bracket_stats.items():
        card = {
            "bracket": bracket,
            "level_count": stats["count"],
            "avg_score": round(sum(stats["scores"]) / max(len(stats["scores"]), 1), 3) if stats["scores"] else None,
            "avg_business_score": round(sum(stats["raw_scores"]) / max(len(stats["raw_scores"]), 1), 3) if stats["raw_scores"] else None,
            "avg_aps": round(sum(stats["aps"]) / max(len(stats["aps"]), 1), 3) if stats["aps"] else None,
            "avg_combined_churn_pct": round(sum(stats["combined_churn"]) / max(len(stats["combined_churn"]), 1) * 100, 2) if stats["combined_churn"] else None,
            "avg_completion_pct": round(sum(stats["completion_rate"]) / max(len(stats["completion_rate"]), 1) * 100, 1) if stats["completion_rate"] else None,
            "avg_revenue_score": round(sum(stats["revenue_score"]) / max(len(stats["revenue_score"]), 1), 3) if stats["revenue_score"] else None,
            "avg_revenue_per_k_users": round(sum(stats["revenue_per_k_users"]) / max(len(stats["revenue_per_k_users"]), 1), 1) if stats["revenue_per_k_users"] else None,
            "avg_iap_users_pct": round(sum(stats["iap_users_pct"]) / max(len(stats["iap_users_pct"]), 1), 2) if stats["iap_users_pct"] else None,
            "top_levels": [],
            "bottom_levels": [],
            "outlier_count": sum(1 for item in outliers if item.get("bracket") == bracket),
        }

        for level_data in best_per_bracket.get(bracket, [])[:3]:
            card["top_levels"].append(_shape_bracket_level(level_data, card, "top"))
        for level_data in worst_per_bracket.get(bracket, [])[:3]:
            card["bottom_levels"].append(_shape_bracket_level(level_data, card, "bottom"))

        bracket_cards.append(card)

    strongest = max(
        bracket_cards,
        key=lambda item: item["avg_business_score"] if item["avg_business_score"] is not None else -1,
        default=None,
    )
    weakest = min(
        bracket_cards,
        key=lambda item: item["avg_business_score"] if item["avg_business_score"] is not None else 999,
        default=strongest,
    )
    bracket_cards.sort(
        key=lambda item: DIFFICULTY_ORDER.index(item["bracket"]) if item["bracket"] in DIFFICULTY_ORDER else 999
    )
    overperformers = sum(1 for item in outliers if item.get("direction") == "overperforming")
    underperformers = sum(1 for item in outliers if item.get("direction") == "underperforming")

    return {
        "available": True,
        "headline": "Bracket performance now uses APS-derived peer bands for apples-to-apples ranking, while tag accuracy checks whether the intended difficulty labels still match reality.",
        "overview": {
            "strongest_bracket": strongest.get("bracket") if strongest else None,
            "strongest_score": strongest.get("avg_business_score") if strongest else None,
            "weakest_bracket": weakest.get("bracket") if weakest else None,
            "weakest_score": weakest.get("avg_business_score") if weakest else None,
            "outlier_count": len(outliers),
            "overperformer_count": overperformers,
            "underperformer_count": underperformers,
            "tag_accuracy_pct": tag_accuracy.get("overall_accuracy_pct"),
            "aligned_level_count": tag_accuracy.get("aligned_level_count"),
            "scored_level_count": tag_accuracy.get("scored_level_count"),
            "worst_target_bracket": tag_accuracy.get("worst_target_bracket"),
            "worst_target_accuracy_pct": tag_accuracy.get("worst_target_accuracy_pct"),
        },
        "brackets": bracket_cards,
        "insights": ranking_results.get("insights", [])[:4],
        "tag_accuracy": tag_accuracy,
    }


def _build_difficulty_tag_accuracy_payload(df):
    if df is None or len(df) == 0:
        return {
            "available": False,
            "reason": "No scoped level data is available.",
        }
    if "aps" not in df.columns or "target_bracket" not in df.columns:
        return {
            "available": False,
            "reason": "APS or target bracket data is missing.",
        }

    scored_rows = []
    for row in df[["level", "aps", "target_bracket"]].to_dict("records"):
        target_bracket = row.get("target_bracket")
        if target_bracket not in DIFFICULTY_ORDER:
            continue
        aps_value = _safe_float(row.get("aps"))
        if aps_value is None:
            continue
        scored_rows.append({
            "level": int(row["level"]),
            "aps": aps_value,
            "target_bracket": target_bracket,
        })

    if not scored_rows:
        return {
            "available": False,
            "reason": "No levels in the current scope have both APS and a target difficulty tag.",
        }

    aps_values = [row["aps"] for row in scored_rows]
    aps_min = min(aps_values)
    aps_max = max(aps_values)
    band_edges = build_aps_adaptive_bands(aps_values)

    for row in scored_rows:
        actual_bracket = classify_aps_bracket(row["aps"], band_edges)
        row["actual_bracket"] = actual_bracket
        row["matches"] = actual_bracket == row["target_bracket"]

    tag_cards = []
    weakest_card = None
    total_aligned = sum(1 for row in scored_rows if row["matches"])
    total_scored = len(scored_rows)

    for bracket in DIFFICULTY_ORDER:
        target_rows = [row for row in scored_rows if row["target_bracket"] == bracket]
        if not target_rows:
            continue

        match_count = sum(1 for row in target_rows if row["matches"])
        mismatch_rows = [row for row in target_rows if not row["matches"]]
        mismatch_rows.sort(
            key=lambda row: (
                abs(DIFFICULTY_ORDER.index(row["actual_bracket"]) - DIFFICULTY_ORDER.index(row["target_bracket"])),
                row["aps"],
            ),
            reverse=True,
        )
        actual_counter = Counter(row["actual_bracket"] for row in target_rows)
        dominant_actual = actual_counter.most_common(1)[0][0] if actual_counter else None
        match_pct = round(match_count / len(target_rows) * 100, 1)
        target_band = band_edges.get(bracket, {})

        card = {
            "target_bracket": bracket,
            "total_count": len(target_rows),
            "match_count": match_count,
            "mismatch_count": len(mismatch_rows),
            "match_pct": match_pct,
            "target_band_min": target_band.get("min"),
            "target_band_max": target_band.get("max"),
            "target_band_label": format_band_label(
                target_band.get("min"),
                target_band.get("max"),
                open_ended=bracket == DIFFICULTY_ORDER[-1],
            ),
            "dominant_actual_bracket": dominant_actual,
            "distribution": [
                {
                    "bracket": actual_bracket,
                    "count": actual_counter.get(actual_bracket, 0),
                }
                for actual_bracket in DIFFICULTY_ORDER
                if actual_counter.get(actual_bracket, 0) > 0
            ],
            "mismatch_examples": [
                {
                    "level": row["level"],
                    "aps": round(row["aps"], 3),
                    "actual_bracket": row["actual_bracket"],
                    "actual_band_label": format_band_label(
                        band_edges.get(row["actual_bracket"], {}).get("min"),
                        band_edges.get(row["actual_bracket"], {}).get("max"),
                        open_ended=row["actual_bracket"] == DIFFICULTY_ORDER[-1],
                    ),
                    "distance": abs(DIFFICULTY_ORDER.index(row["actual_bracket"]) - DIFFICULTY_ORDER.index(row["target_bracket"])),
                    "direction": "harder" if DIFFICULTY_ORDER.index(row["actual_bracket"]) > DIFFICULTY_ORDER.index(row["target_bracket"]) else "softer",
                }
                for row in mismatch_rows[:3]
            ],
        }
        tag_cards.append(card)

        if weakest_card is None or card["match_pct"] < weakest_card["match_pct"]:
            weakest_card = card

    return {
        "available": True,
        "headline": "Target tags are checked against an adaptive APS ladder that spreads bands in log space and trims the extreme top tail, so the easier brackets do not collapse while Wall stays reserved for genuinely high APS content.",
        "overall_accuracy_pct": round(total_aligned / total_scored * 100, 1),
        "aligned_level_count": total_aligned,
        "scored_level_count": total_scored,
        "worst_target_bracket": weakest_card.get("target_bracket") if weakest_card else None,
        "worst_target_accuracy_pct": weakest_card.get("match_pct") if weakest_card else None,
        "aps_range_min": round(aps_min, 3),
        "aps_range_max": round(aps_max, 3),
        "aps_range_label": format_band_label(aps_min, aps_max),
        "band_method": "adaptive_log",
        "bands": [
            {
                "bracket": bracket,
                "min": round(edges["min"], 3),
                "max": round(edges["max"], 3),
                "label": format_band_label(
                    edges["min"],
                    edges["max"],
                    open_ended=bracket == DIFFICULTY_ORDER[-1],
                ),
            }
            for bracket, edges in band_edges.items()
        ],
        "targets": tag_cards,
    }


def _safe_float(value):
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(numeric):
        return None
    return numeric


def _shape_bracket_level(level_data, bracket_card, direction):
    level = int(level_data.get("level"))
    aps = level_data.get("aps")
    combined_churn = level_data.get("combined_churn")
    completion = level_data.get("completion_rate")
    revenue_score = level_data.get("revenue_score")
    revenue_per_k_users = level_data.get("revenue_per_k_users")
    iap_users_pct = level_data.get("iap_users_pct")
    target_bracket = level_data.get("target_bracket")

    notes = []
    avg_churn = bracket_card.get("avg_combined_churn_pct")
    if combined_churn is not None and avg_churn is not None:
        churn_pct = float(combined_churn) * 100
        if direction == "top" and churn_pct <= avg_churn - 0.25:
            notes.append("lower churn than bracket average")
        if direction == "bottom" and churn_pct >= avg_churn + 0.25:
            notes.append("higher churn than bracket average")

    avg_completion = bracket_card.get("avg_completion_pct")
    if completion is not None and avg_completion is not None:
        completion_pct = float(completion) * 100
        if direction == "top" and completion_pct >= avg_completion + 2:
            notes.append("better completion than peers")
        if direction == "bottom" and completion_pct <= avg_completion - 2:
            notes.append("weaker completion than peers")

    avg_revenue = bracket_card.get("avg_revenue_score")
    if revenue_score is not None and avg_revenue is not None:
        if direction == "top" and float(revenue_score) >= avg_revenue + 0.03:
            notes.append("stronger monetization for the same APS band")
        if direction == "bottom" and float(revenue_score) <= avg_revenue - 0.03:
            notes.append("weaker monetization for the same APS band")

    if target_bracket and target_bracket != bracket_card.get("bracket"):
        notes.append(f"tagged {target_bracket} but behaves closer to {bracket_card.get('bracket')}")

    if not notes:
        notes.append("balanced peer-relative performance" if direction == "top" else "lagging peer-relative performance")

    return {
        "level": level,
        "perf_score": round(float(level_data.get("perf_score", 0)), 3),
        "aps": round(float(aps), 3) if aps is not None else None,
        "combined_churn_pct": round(float(combined_churn) * 100, 2) if combined_churn is not None else None,
        "completion_pct": round(float(completion) * 100, 1) if completion is not None else None,
        "revenue_score": round(float(revenue_score), 3) if revenue_score is not None else None,
        "revenue_per_k_users": round(float(revenue_per_k_users), 1) if revenue_per_k_users is not None else None,
        "iap_users_pct": round(float(iap_users_pct), 2) if iap_users_pct is not None else None,
        "target_bracket": target_bracket,
        "reason": notes[0],
    }


def allowed_file(filename, allowed_extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload_files():
    level_data_file = request.files.get("level_data")
    has_level_data = bool(level_data_file and level_data_file.filename)
    if has_level_data and not allowed_file(level_data_file.filename, ALLOWED_EXTENSIONS_LEVEL_DATA):
        flash("Level Data file must be .xlsx, .xls, or .csv", "error")
        return redirect(url_for("index"))

    # Level params file (optional)
    level_params_file = None
    if "level_params" in request.files and request.files["level_params"].filename != "":
        level_params_file = request.files["level_params"]
        if not allowed_file(level_params_file.filename, ALLOWED_EXTENSIONS_LEVEL_PARAMS):
            flash("Level Parameters file must be .xlsx, .xls, or .csv", "error")
            return redirect(url_for("index"))

    ab_test_file = None
    if "ab_test_file" in request.files and request.files["ab_test_file"].filename != "":
        ab_test_file = request.files["ab_test_file"]
        if not allowed_file(ab_test_file.filename, ALLOWED_EXTENSIONS_LEVEL_DATA):
            flash("AB Test workbook must be .xlsx, .xls, or .csv", "error")
            return redirect(url_for("index"))

    if not has_level_data and ab_test_file is None:
        flash("Please upload either a Level Data file or an AB Test workbook.", "error")
        return redirect(url_for("index"))

    if not has_level_data and level_params_file is not None:
        flash("Level Parameters can only be used together with a Level Data file.", "error")
        return redirect(url_for("index"))

    # Save files — preserve original extensions
    level_data_path = None
    if has_level_data:
        data_ext = level_data_file.filename.rsplit(".", 1)[1].lower()
        level_data_path = os.path.join(app.config["UPLOAD_FOLDER"], f"level_data.{data_ext}")
        level_data_file.save(level_data_path)

    level_params_path = None
    if level_params_file:
        params_ext = level_params_file.filename.rsplit(".", 1)[1].lower()
        level_params_path = os.path.join(app.config["UPLOAD_FOLDER"], f"level_params.{params_ext}")
        level_params_file.save(level_params_path)

    ab_test_path = None
    if ab_test_file:
        ab_ext = ab_test_file.filename.rsplit(".", 1)[1].lower()
        ab_test_path = os.path.join(app.config["UPLOAD_FOLDER"], f"ab_test.{ab_ext}")
        ab_test_file.save(ab_test_path)

    _app_data["ab_test_df"] = None
    _app_data["ab_test_meta"] = None
    if ab_test_path:
        ab_df, ab_errors, ab_warnings, ab_meta = process_ab_file(ab_test_path)
        for warning in ab_warnings:
            flash(warning, "warning")
        if ab_errors:
            for error in ab_errors:
                flash(error, "error")
            return redirect(url_for("index"))
        _app_data["ab_test_df"] = ab_df
        _app_data["ab_test_meta"] = ab_meta

    if has_level_data:
        df, errors, warnings, summary = process_files(level_data_path, level_params_path)

        for w in warnings:
            flash(w, "warning")

        if errors:
            for e in errors:
                flash(e, "error")
            return redirect(url_for("index"))

        _app_data["df_full"] = df
        _app_data["analysis_scope"] = _default_analysis_scope(df)
        _app_data["level_range"] = None
        _run_all_analyses(df)
    else:
        _run_ab_only_analyses()

    # Store metadata in session
    session["level_data_path"] = level_data_path
    session["level_params_path"] = level_params_path  # May be None
    session["level_data_name"] = level_data_file.filename if has_level_data else ""
    session["level_params_name"] = level_params_file.filename if level_params_file else ""
    session["ab_test_name"] = ab_test_file.filename if ab_test_file else ""
    session["data_loaded"] = True

    if has_level_data:
        flash("Files parsed and validated successfully!", "success")
    else:
        flash("AB test workbook parsed and loaded successfully!", "success")
    return redirect(url_for("dashboard"))


@app.route("/dashboard")
def dashboard():
    if not session.get("data_loaded"):
        flash("Please upload your files first.", "error")
        return redirect(url_for("index"))

    return render_template(
        "dashboard.html",
        level_data_name=session.get("level_data_name", ""),
        level_params_name=session.get("level_params_name", ""),
        ab_test_name=session.get("ab_test_name", ""),
        summary=_app_data.get("summary", {}),
    )


@app.route("/api/data/overview")
def api_overview():
    """API endpoint returning overview data as JSON for frontend charts."""
    if _app_data["df"] is None:
        return json.dumps({"error": "No data loaded"}), 400

    df = _app_data["df"]
    summary = _app_data["summary"]

    # Bracket distribution for chart
    bracket_dist = []
    for bracket in ["Easy", "Medium", "Hard", "Super Hard", "Wall"]:
        count = int((df["target_bracket"] == bracket).sum())
        if count > 0:
            bracket_dist.append({"bracket": bracket, "count": count})

    # APS by bracket for chart
    aps_by_bracket = []
    for bracket in ["Easy", "Medium", "Hard", "Super Hard", "Wall"]:
        subset = df[df["target_bracket"] == bracket]
        if len(subset) > 0 and "aps" in df.columns:
            aps_by_bracket.append({
                "bracket": bracket,
                "mean_aps": round(float(subset["aps"].mean()), 3),
                "min_aps": round(float(subset["aps"].min()), 3),
                "max_aps": round(float(subset["aps"].max()), 3),
                "median_aps": round(float(subset["aps"].median()), 3),
            })

    return json.dumps({
        "summary": summary,
        "bracket_distribution": bracket_dist,
        "aps_by_bracket": aps_by_bracket,
    })


@app.route("/api/data/aps-ranges")
def api_aps_ranges():
    """API endpoint returning APS range analysis as JSON."""
    if _app_data["aps_results"] is None:
        return json.dumps({"error": "No data loaded"}), 400
    return json.dumps(_app_data["aps_results"])


@app.route("/api/data/ranking")
def api_ranking():
    """API endpoint returning level performance ranking as JSON."""
    if _app_data["ranking_results"] is None:
        return json.dumps({"error": "No data loaded"}), 400
    return json.dumps(_app_data["ranking_results"])


@app.route("/api/data/dropoff")
def api_dropoff():
    """API endpoint returning drop-off analysis as JSON."""
    if _app_data["dropoff_results"] is None:
        return json.dumps({"error": "No data loaded"}), 400
    return json.dumps(_app_data["dropoff_results"])


@app.route("/api/data/correlation")
def api_correlation():
    """API endpoint returning correlation analysis as JSON."""
    if _app_data["correlation_results"] is None:
        return json.dumps({"error": "No data loaded"}), 400
    return json.dumps(_app_data["correlation_results"])


@app.route("/api/data/funnel")
def api_funnel():
    """API endpoint returning funnel pacing analysis as JSON."""
    if _app_data["funnel_results"] is None:
        return json.dumps({"error": "No data loaded"}), 400
    return json.dumps(_app_data["funnel_results"])


@app.route("/api/data/recommendations")
def api_recommendations():
    """API endpoint returning all recommendations as JSON."""
    if _app_data["recommendations"] is None:
        return json.dumps({"error": "No data loaded"}), 400
    return json.dumps(_app_data["recommendations"])


@app.route("/api/data/focus-dashboard")
def api_focus_dashboard():
    """Focused dashboard payload with the smallest high-signal analysis surface."""
    return json.dumps(_build_focus_dashboard_payload())


@app.route("/api/data/bracket-performance")
def api_bracket_performance():
    """Bracket-first ranking payload for a dedicated performance tab."""
    return json.dumps(_build_bracket_performance_payload())


@app.route("/api/data/ab-test")
def api_ab_test():
    """AB test comparison payload, if an experiment workbook was uploaded."""
    try:
        bucket_size = int(request.args.get("bucket_size", 10))
    except (TypeError, ValueError):
        bucket_size = 10
    return json.dumps(_build_ab_test_payload(bucket_size=bucket_size))


@app.route("/api/data/main-breakdown")
def api_main_breakdown():
    """API endpoint returning main breakdown analysis as JSON."""
    if _app_data["main_breakdown"] is None:
        return json.dumps({"error": "No data loaded"}), 400
    return json.dumps(_app_data["main_breakdown"])


@app.route("/api/reanalyze", methods=["POST"])
def api_reanalyze():
    """Re-run all analyses on an explicit analysis scope."""
    if _app_data["df_full"] is None:
        return json.dumps({"error": "No data loaded"}), 400

    payload = request.get_json(silent=True) or {}
    df_full = _app_data["df_full"]
    full_min, full_max = _get_full_level_bounds(df_full)

    try:
        scope, df_filtered = _normalize_analysis_scope(payload, df_full)
    except ValueError as exc:
        return json.dumps({"error": str(exc)}), 400

    _app_data["analysis_scope"] = scope
    _app_data["level_range"] = (
        None
        if (scope["start"] == full_min and scope["end"] == full_max)
        else {"min": scope["start"], "max": scope["end"]}
    )

    _run_all_analyses(df_filtered)

    return json.dumps({
        "success": True,
        "total_levels": len(df_filtered),
        "analysis_scope": scope,
        "level_range": _app_data["level_range"],
        "full_range": {"min": full_min, "max": full_max},
        "summary": _app_data["summary"],
    })


@app.route("/api/data/level-range")
def api_level_range():
    """Return the full level range available and current analysis scope."""
    if _app_data["df_full"] is None:
        return json.dumps({
            "available": False,
            "full_min": None,
            "full_max": None,
            "current_filter": None,
            "analysis_scope": None,
        })
    df_full = _app_data["df_full"]
    scope = _app_data["analysis_scope"] or _default_analysis_scope(df_full)
    return json.dumps({
        "available": True,
        "full_min": int(df_full["level"].min()),
        "full_max": int(df_full["level"].max()),
        "current_filter": _app_data["level_range"],
        "analysis_scope": scope,
    })


@app.route("/reset")
def reset():
    # Clear uploaded files (any extension)
    import glob
    for pattern in ["level_data.*", "level_params.*", "ab_test.*"]:
        for path in glob.glob(os.path.join(app.config["UPLOAD_FOLDER"], pattern)):
            os.remove(path)
    # Clear in-memory data
    _clear_primary_analysis_data()
    _app_data["ab_test_df"] = None
    _app_data["ab_test_meta"] = None
    _app_data["ab_test_results"] = None
    session.clear()
    flash("Session reset. Upload new files to begin.", "info")
    return redirect(url_for("index"))


if __name__ == "__main__":
    print("\n  LD Wizard is running at: http://127.0.0.1:5050\n")
    app.run(debug=True, host="127.0.0.1", port=5050)
