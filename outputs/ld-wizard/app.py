import os
import json
from flask import Flask, render_template, request, redirect, url_for, flash, session
from config import UPLOAD_FOLDER, ALLOWED_EXTENSIONS_LEVEL_DATA, ALLOWED_EXTENSIONS_LEVEL_PARAMS, MAX_CONTENT_LENGTH, SECRET_KEY
from engine.parser import process_files
from engine.aps_engine import compute_aps_ranges
from engine.analysis.funnel import compute_funnel_analysis
from engine.analysis.ranking import compute_ranking
from engine.analysis.dropoff import compute_dropoff_analysis
from engine.analysis.correlation import compute_correlation_analysis
from engine.analysis.recommendations import compute_recommendations

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
    "level_range": None,  # Current filter: {"min": int, "max": int} or None
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


def allowed_file(filename, allowed_extensions):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in allowed_extensions


@app.route("/", methods=["GET"])
def index():
    return render_template("upload.html")


@app.route("/upload", methods=["POST"])
def upload_files():
    # Validate level data file (required)
    if "level_data" not in request.files or request.files["level_data"].filename == "":
        flash("Please select a Level Data file (.xlsx)", "error")
        return redirect(url_for("index"))

    level_data_file = request.files["level_data"]

    if not allowed_file(level_data_file.filename, ALLOWED_EXTENSIONS_LEVEL_DATA):
        flash("Level Data file must be .xlsx, .xls, or .csv", "error")
        return redirect(url_for("index"))

    # Level params file (optional)
    level_params_file = None
    if "level_params" in request.files and request.files["level_params"].filename != "":
        level_params_file = request.files["level_params"]
        if not allowed_file(level_params_file.filename, ALLOWED_EXTENSIONS_LEVEL_PARAMS):
            flash("Level Parameters file must be .xlsx, .xls, or .csv", "error")
            return redirect(url_for("index"))

    # Save files — preserve original extensions
    data_ext = level_data_file.filename.rsplit(".", 1)[1].lower()
    level_data_path = os.path.join(app.config["UPLOAD_FOLDER"], f"level_data.{data_ext}")
    level_data_file.save(level_data_path)

    level_params_path = None
    if level_params_file:
        params_ext = level_params_file.filename.rsplit(".", 1)[1].lower()
        level_params_path = os.path.join(app.config["UPLOAD_FOLDER"], f"level_params.{params_ext}")
        level_params_file.save(level_params_path)

    # --- Parse and validate ---
    df, errors, warnings, summary = process_files(level_data_path, level_params_path)

    # Show warnings
    for w in warnings:
        flash(w, "warning")

    # If critical errors, go back to upload
    if errors:
        for e in errors:
            flash(e, "error")
        return redirect(url_for("index"))

    # Store full DataFrame and run all analyses
    _app_data["df_full"] = df
    _app_data["level_range"] = None
    _run_all_analyses(df)

    # Store metadata in session
    session["level_data_path"] = level_data_path
    session["level_params_path"] = level_params_path  # May be None
    session["level_data_name"] = level_data_file.filename
    session["level_params_name"] = level_params_file.filename if level_params_file else ""
    session["data_loaded"] = True

    flash("Files parsed and validated successfully!", "success")
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


@app.route("/api/reanalyze", methods=["POST"])
def api_reanalyze():
    """Re-run all analyses on a filtered level range."""
    if _app_data["df_full"] is None:
        return json.dumps({"error": "No data loaded"}), 400

    payload = request.get_json(silent=True) or {}
    level_min = payload.get("level_min")
    level_max = payload.get("level_max")

    df_full = _app_data["df_full"]
    full_min = int(df_full["level"].min())
    full_max = int(df_full["level"].max())

    # Validate and apply filter
    if level_min is not None and level_max is not None:
        level_min = int(level_min)
        level_max = int(level_max)
        if level_min < full_min:
            level_min = full_min
        if level_max > full_max:
            level_max = full_max
        if level_min > level_max:
            return json.dumps({"error": "Min level must be ≤ max level"}), 400

        df_filtered = df_full[(df_full["level"] >= level_min) & (df_full["level"] <= level_max)].copy()
        if len(df_filtered) < 2:
            return json.dumps({"error": "Selected range has fewer than 2 levels"}), 400

        _app_data["level_range"] = {"min": level_min, "max": level_max}
    else:
        # Reset to full range
        df_filtered = df_full
        _app_data["level_range"] = None

    _run_all_analyses(df_filtered)

    return json.dumps({
        "success": True,
        "total_levels": len(df_filtered),
        "level_range": _app_data["level_range"],
        "full_range": {"min": full_min, "max": full_max},
        "summary": _app_data["summary"],
    })


@app.route("/api/data/level-range")
def api_level_range():
    """Return the full level range available and current filter."""
    if _app_data["df_full"] is None:
        return json.dumps({"error": "No data loaded"}), 400
    df_full = _app_data["df_full"]
    return json.dumps({
        "full_min": int(df_full["level"].min()),
        "full_max": int(df_full["level"].max()),
        "current_filter": _app_data["level_range"],
    })


@app.route("/reset")
def reset():
    # Clear uploaded files (any extension)
    import glob
    for pattern in ["level_data.*", "level_params.*"]:
        for path in glob.glob(os.path.join(app.config["UPLOAD_FOLDER"], pattern)):
            os.remove(path)
    # Clear in-memory data
    _app_data["df"] = None
    _app_data["df_full"] = None
    _app_data["summary"] = None
    _app_data["aps_results"] = None
    _app_data["funnel_results"] = None
    _app_data["ranking_results"] = None
    _app_data["dropoff_results"] = None
    _app_data["correlation_results"] = None
    _app_data["recommendations"] = None
    _app_data["level_range"] = None
    session.clear()
    flash("Session reset. Upload new files to begin.", "info")
    return redirect(url_for("index"))


if __name__ == "__main__":
    print("\n  LD Wizard is running at: http://127.0.0.1:5050\n")
    app.run(debug=True, host="127.0.0.1", port=5050)
