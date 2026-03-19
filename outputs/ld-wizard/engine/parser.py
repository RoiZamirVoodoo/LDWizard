"""
LD Wizard — Data Ingestion & Validation (Step 2)
Parses Level Data (.xlsx) and Level Parameters (.csv), validates, joins, and computes derived metrics.
"""

import re
import pandas as pd
import numpy as np


# ---------------------------------------------------------------------------
# Constants — Column mappings per Data Dictionary v1
# ---------------------------------------------------------------------------

# Expected headers in the Level Data Excel (row 2 of the file)
# Maps: display name -> standardized internal name
LEVEL_DATA_COLUMNS = {
    "Users": "users",
    "% Level Funnel along Level, Target": "funnel_pct",
    "APS": "aps",
    "% IAP Users": "iap_users_pct",
    "Churn": "churn",
    "3-D Churn": "churn_3d",
    "Coin Balance": "coin_balance",
    "Completion Rate": "completion_rate",
    "Win Rate": "win_rate",
    "Pure APS": "pure_aps",
    "% FTD": "ftd_pct",
    "% Repeaters": "repeaters_pct",
    "7-D Churn": "churn_7d",
    "IAP revenue": "iap_revenue",
    "IAP Transactions": "iap_transactions",
    "% Sink Users": "sink_users_pct",
    "Soft Currency used": "soft_currency_used",
    "Boosters Used": "boosters_used",
    "% Booster Users": "booster_users_pct",
    "EGPs used": "egps_used",
    "% EGP Users": "egp_users_pct",
    "Playtime": "playtime",
    "Win Playtime": "win_playtime",
    "Lose Playtime": "lose_playtime",
    "Real Playtime": "real_playtime",
    "Objectives Left ": "objectives_left",
    "% Objectives Left": "objectives_left_pct",
}

# Ignored columns (documented in Data Dictionary)
IGNORED_COLUMNS = ["Achieved"]

# Difficulty bracket mapping
DIFFICULTY_CODE_MAP = {
    "E": "Easy",
    "M": "Medium",
    "H": "Hard",
    "SH": "Super Hard",
    "W": "Wall",
}

DIFFICULTY_ORDER = ["Easy", "Medium", "Hard", "Super Hard", "Wall"]

# Combined Churn Score weights
CHURN_WEIGHT_SESSION = 0.2
CHURN_WEIGHT_3D = 0.5
CHURN_WEIGHT_7D = 0.3

# Funnel phase definitions
# Tutorial = first N levels (flat number, not percentage).
# Early/Mid/Late split the *remaining* levels by percentage of the post-tutorial range.
TUTORIAL_LEVEL_COUNT = 30  # first 30 levels of every game are Tutorial

FUNNEL_PHASES_POST_TUTORIAL = [
    # Percentages are relative to the post-tutorial levels only
    {"name": "Early", "start_pct": 0.00, "end_pct": 0.30, "expected_churn_mult": 1.6},
    {"name": "Mid",   "start_pct": 0.30, "end_pct": 0.70, "expected_churn_mult": 1.0},
    {"name": "Late",  "start_pct": 0.70, "end_pct": 1.00, "expected_churn_mult": 0.6},
]

# Full list (used by downstream code that iterates all phases)
FUNNEL_PHASES = [
    {"name": "Tutorial", "expected_churn_mult": 2.5},
    {"name": "Early",    "expected_churn_mult": 1.6},
    {"name": "Mid",      "expected_churn_mult": 1.0},
    {"name": "Late",     "expected_churn_mult": 0.6},
]

# Revenue Score component weights — reflect actual revenue impact
# IAP (direct cash) > EGP (premium purchase) > Boosters (moderate) > Sink (soft currency)
REVENUE_WEIGHTS = {
    "iap_users_pct": 0.35,
    "egp_users_pct": 0.30,
    "booster_users_pct": 0.20,
    "sink_users_pct": 0.15,
}

# Level Parameters — expected columns (Card Factory baseline)
LEVEL_PARAMS_COLOR_COLS = [
    "Red", "Blue", "Green", "Yellow", "Orange", "Pink", "Turqoise", "Brown", "Purple"
]

LEVEL_PARAMS_FEATURE_COLS = ["Feature 0", "Feature 1", "Feature 2", "Feature 3"]


# ---------------------------------------------------------------------------
# Smart CSV reader — handles UTF-8, UTF-16, tab/comma separated
# ---------------------------------------------------------------------------

def _read_csv_smart(filepath):
    """
    Attempt to read a CSV with automatic encoding and separator detection.
    Handles UTF-8, UTF-16 (LE/BE), tab-separated, and comma-separated files.
    """
    # Try common encodings and separators
    attempts = [
        {"encoding": "utf-8", "sep": ","},
        {"encoding": "utf-8", "sep": "\t"},
        {"encoding": "utf-16", "sep": "\t"},
        {"encoding": "utf-16", "sep": ","},
        {"encoding": "latin-1", "sep": ","},
        {"encoding": "latin-1", "sep": "\t"},
    ]

    last_error = None
    for params in attempts:
        try:
            df = pd.read_csv(filepath, header=None, **params)
            # Sanity check: should have at least 2 columns and some data
            if df.shape[1] >= 2 and df.shape[0] >= 2:
                return df
        except Exception as e:
            last_error = e
            continue

    raise last_error or ValueError("Could not read CSV file with any encoding/separator combination")


# ---------------------------------------------------------------------------
# Parse Level Data (Excel)
# ---------------------------------------------------------------------------

def parse_level_data(filepath):
    """
    Parse the Level Data Excel file.

    Returns:
        (DataFrame, errors: list[str], warnings: list[str])
        DataFrame is None if critical errors occurred.
    """
    errors = []
    warnings = []

    try:
        # Read raw — headers are in row 2 (0-indexed: row index 1)
        if filepath.endswith(".csv"):
            df_raw = _read_csv_smart(filepath)
        else:
            df_raw = pd.read_excel(filepath, sheet_name=0, header=None)
    except Exception as e:
        errors.append(f"Could not read Level Data file: {str(e)}")
        return None, errors, warnings

    # --- Locate header row ---
    # Row 2 (index 1) contains the metric headers, Row 3 (index 2) has sub-headers
    # Data starts at row 4 (index 3)
    if df_raw.shape[0] < 4:
        errors.append("Level Data file has too few rows. Expected at least 4 (headers + data).")
        return None, errors, warnings

    header_row = df_raw.iloc[1].fillna("").astype(str).tolist()
    sub_header_row = df_raw.iloc[2].fillna("").astype(str).tolist()

    # Build column name list: first 4 cols use sub-header (Level, Target, Achieved, Target)
    # Deduplicate: rename duplicate columns by appending _N
    col_names = []
    seen = {}
    for i in range(len(header_row)):
        if i < 4:
            name = sub_header_row[i].strip()
        else:
            name = header_row[i].strip()

        if name in seen:
            seen[name] += 1
            name = f"{name}_{seen[name]}"
        else:
            seen[name] = 0
        col_names.append(name)

    # Extract data rows
    df = df_raw.iloc[3:].copy()
    df.columns = col_names[:df.shape[1]]
    df = df.reset_index(drop=True)

    # --- Validate required columns ---
    # Check for Level column
    if "Level" not in df.columns:
        errors.append("'Level' column not found in Level Data file.")
        return None, errors, warnings

    # Check for Target column (first occurrence, before dedup renamed it)
    target_col = "Target" if "Target" in df.columns else None
    if target_col is None:
        errors.append("'Target' (difficulty bracket) column not found in Level Data file.")
        return None, errors, warnings

    # Check for metric columns
    missing_metrics = []
    found_metrics = {}
    for display_name, internal_name in LEVEL_DATA_COLUMNS.items():
        if display_name in df.columns:
            found_metrics[display_name] = internal_name
        else:
            missing_metrics.append(display_name)

    if len(missing_metrics) > 5:
        errors.append(
            f"Too many missing columns ({len(missing_metrics)}). "
            f"First few: {', '.join(missing_metrics[:5])}. "
            f"Please check the file format matches the expected standard."
        )
        return None, errors, warnings
    elif missing_metrics:
        warnings.append(
            f"Missing columns (will be treated as null): {', '.join(missing_metrics)}"
        )

    # --- Build clean DataFrame ---
    clean = pd.DataFrame()

    # Level number
    clean["level"] = pd.to_numeric(df["Level"], errors="coerce").astype("Int64")

    # Target difficulty bracket
    clean["target_code"] = df[target_col].astype(str).str.strip()
    clean["target_bracket"] = clean["target_code"].map(DIFFICULTY_CODE_MAP)

    # Check for unknown difficulty codes
    unknown_codes = clean[clean["target_bracket"].isna() & clean["target_code"].notna()]["target_code"].unique()
    if len(unknown_codes) > 0:
        warnings.append(f"Unknown difficulty codes found: {', '.join(unknown_codes)}. These rows will have null bracket.")

    # Metric columns — clean formatted values first (commas, percentages)
    for display_name, internal_name in found_metrics.items():
        raw = df[display_name].astype(str).str.strip()
        # Remove commas from numbers like "1,046,999"
        raw = raw.str.replace(",", "", regex=False)
        # Convert percentages like "96.57%" to decimal (0.9657)
        is_pct = raw.str.endswith("%")
        raw = raw.str.rstrip("%")
        numeric = pd.to_numeric(raw, errors="coerce")
        # Divide percentage values by 100 to get decimal form
        if is_pct.any():
            numeric = numeric.where(~is_pct, numeric / 100.0)
        clean[internal_name] = numeric

    # Drop rows where level number is null (empty rows)
    null_levels = clean["level"].isna().sum()
    if null_levels > 0:
        warnings.append(f"{null_levels} rows with missing level numbers were removed.")
        clean = clean.dropna(subset=["level"]).reset_index(drop=True)

    # Sort by level
    clean = clean.sort_values("level").reset_index(drop=True)

    # Check for duplicate levels
    dupes = clean[clean["level"].duplicated(keep=False)]
    if len(dupes) > 0:
        errors.append(f"Duplicate level numbers found: {sorted(dupes['level'].unique().tolist())}")
        return None, errors, warnings

    # Check for null values in critical columns
    for col in ["users", "funnel_pct", "aps", "churn", "completion_rate", "win_rate"]:
        if col in clean.columns:
            null_count = clean[col].isna().sum()
            if null_count > 0:
                warnings.append(f"'{col}' has {null_count} missing values.")

    return clean, errors, warnings


# ---------------------------------------------------------------------------
# Parse Level Parameters (CSV)
# ---------------------------------------------------------------------------

def parse_level_params(filepath):
    """
    Parse the Level Parameters CSV file.

    Returns:
        (DataFrame, errors: list[str], warnings: list[str])
        DataFrame is None if critical errors occurred.
    """
    errors = []
    warnings = []

    try:
        if filepath.endswith((".xlsx", ".xls")):
            df = pd.read_excel(filepath)
        else:
            df = pd.read_csv(filepath)
    except Exception as e:
        errors.append(f"Could not read Level Parameters file: {str(e)}")
        return None, errors, warnings

    if df.shape[0] == 0:
        errors.append("Level Parameters file is empty.")
        return None, errors, warnings

    # --- Validate required columns ---
    if "Level Name" not in df.columns:
        errors.append("'Level Name' column not found in Level Parameters file.")
        return None, errors, warnings

    if "Difficulty" not in df.columns:
        errors.append("'Difficulty' column not found in Level Parameters file.")
        return None, errors, warnings

    # --- Build clean DataFrame ---
    clean = pd.DataFrame()

    # Level name and number
    clean["level_name"] = df["Level Name"].astype(str)

    # Use row position as level number (1-indexed) since level names aren't always sequential
    clean["level"] = range(1, len(df) + 1)

    # Color columns — convert checkmark/dash to boolean
    for col in LEVEL_PARAMS_COLOR_COLS:
        if col in df.columns:
            clean[f"color_{col.lower()}"] = df[col].astype(str).str.strip() == "\u2713"
        else:
            warnings.append(f"Color column '{col}' not found — set to False.")
            clean[f"color_{col.lower()}"] = False

    # Blocker
    if "Blocker" in df.columns:
        clean["has_blocker"] = df["Blocker"].astype(str).str.strip() == "\u2713"
    else:
        warnings.append("'Blocker' column not found — set to False.")
        clean["has_blocker"] = False

    # Features — collect active features into a list
    feature_lists = []
    for _, row in df.iterrows():
        features = []
        for col in LEVEL_PARAMS_FEATURE_COLS:
            if col in df.columns:
                val = str(row[col]).strip()
                if val != "-" and val != "nan" and val != "":
                    features.append(val)
        feature_lists.append(features)
    clean["features"] = feature_lists
    clean["feature_count"] = clean["features"].apply(len)

    # Spline
    if "Spline 1" in df.columns:
        clean["spline"] = df["Spline 1"].astype(str).str.strip()
    else:
        warnings.append("'Spline 1' column not found.")
        clean["spline"] = None

    # Numeric properties
    for col, internal in [
        ("Deposit Point Count", "deposit_points"),
        ("Deposit Box Count", "deposit_boxes"),
        ("Queue Count", "queue_count"),
        ("Color Count", "color_count"),
        ("Total Tile Count", "total_tiles"),
    ]:
        if col in df.columns:
            clean[internal] = pd.to_numeric(df[col], errors="coerce").astype("Int64")
        else:
            warnings.append(f"'{col}' column not found — set to null.")
            clean[internal] = pd.NA

    # Difficulty label
    clean["params_difficulty"] = df["Difficulty"].astype(str).str.strip()

    return clean, errors, warnings


# ---------------------------------------------------------------------------
# Join & Enrich
# ---------------------------------------------------------------------------

def join_and_enrich(level_data_df, level_params_df):
    """
    Join Level Data with Level Parameters on level number and compute derived metrics.
    level_params_df can be None if no params file was provided.

    Returns:
        (DataFrame, errors: list[str], warnings: list[str])
    """
    errors = []
    warnings = []

    if level_params_df is not None:
        # --- Join on level number ---
        merged = pd.merge(
            level_data_df,
            level_params_df,
            on="level",
            how="left",
        )

        # Check join quality
        unmatched = merged["level_name"].isna().sum()
        if unmatched > 0:
            warnings.append(
                f"{unmatched} levels in Level Data have no matching Level Parameters. "
                f"These levels will have null design properties."
            )
    else:
        # No params file — use level data only
        merged = level_data_df.copy()

    total_levels = len(merged)
    if total_levels == 0:
        errors.append("No data after processing files. Please check that the level data file has valid rows.")
        return None, errors, warnings

    # --- Compute derived metrics ---

    # Drop-off Rate: (Users[n] - Users[n+1]) / Users[n]
    if "users" in merged.columns:
        merged["dropoff_rate"] = (
            (merged["users"] - merged["users"].shift(-1)) / merged["users"]
        )
        merged.loc[merged.index[-1], "dropoff_rate"] = np.nan

    # Funnel Decline Rate: delta of funnel_pct between consecutive levels
    if "funnel_pct" in merged.columns:
        merged["funnel_decline_rate"] = merged["funnel_pct"].diff()

    # APS Delta (Booster Impact): Pure APS - APS
    if "pure_aps" in merged.columns and "aps" in merged.columns:
        merged["aps_delta_booster"] = merged["pure_aps"] - merged["aps"]

    # Difficulty Delta: APS[n+1] - APS[n]
    if "aps" in merged.columns:
        merged["difficulty_delta"] = merged["aps"].diff()

    # Revenue per User
    if "iap_revenue" in merged.columns and "users" in merged.columns:
        merged["revenue_per_user"] = merged["iap_revenue"] / merged["users"].replace(0, np.nan)

    # EGP per User
    if "egps_used" in merged.columns and "users" in merged.columns:
        merged["egp_per_user"] = merged["egps_used"] / merged["users"].replace(0, np.nan)

    # Booster per User
    if "boosters_used" in merged.columns and "users" in merged.columns:
        merged["booster_per_user"] = merged["boosters_used"] / merged["users"].replace(0, np.nan)

    # --- Combined Churn Score ---
    # Weighted: 0.2 * session + 0.5 * 3D + 0.3 * 7D
    # Graceful degradation: if a churn window is NaN for a given row,
    # use only the available windows and re-normalize weights.
    # This handles immature data (e.g., D7 not yet available for recent levels).
    has_churn = "churn" in merged.columns
    has_3d = "churn_3d" in merged.columns
    has_7d = "churn_7d" in merged.columns

    if has_churn:
        # Build per-row combined churn using available windows
        churn_components = []
        weight_components = []

        # Session churn — always available if column exists
        churn_components.append(("churn", CHURN_WEIGHT_SESSION))
        # D3 churn — may have NaN per row
        if has_3d:
            churn_components.append(("churn_3d", CHURN_WEIGHT_3D))
        # D7 churn — may have NaN per row
        if has_7d:
            churn_components.append(("churn_7d", CHURN_WEIGHT_7D))

        # Compute per-row: sum(weight_i * churn_i) / sum(weight_i) for non-NaN values
        numerator = pd.Series(0.0, index=merged.index)
        denominator = pd.Series(0.0, index=merged.index)
        for col, w in churn_components:
            valid_mask = merged[col].notna()
            numerator += merged[col].fillna(0) * w * valid_mask.astype(float)
            denominator += w * valid_mask.astype(float)

        # Where denominator > 0, compute weighted churn; otherwise NaN
        merged["combined_churn"] = np.where(denominator > 0, numerator / denominator, np.nan)

        # Track data maturity per row:
        # 3 = full (session + D3 + D7), 2 = partial (session + D3), 1 = minimal (session only)
        maturity = pd.Series(1, index=merged.index)  # at least session
        if has_3d:
            maturity += merged["churn_3d"].notna().astype(int)
        if has_7d:
            maturity += merged["churn_7d"].notna().astype(int)
        merged["_churn_maturity"] = maturity

        # Detect and warn about immature data
        n_total = len(merged)
        n_full = int((maturity == 3).sum()) if has_3d and has_7d else 0
        n_partial = int((maturity == 2).sum()) if has_3d else 0
        n_minimal = int((maturity == 1).sum())

        if has_7d and n_full < n_total:
            immature_count = n_total - n_full
            pct = immature_count / n_total * 100
            if n_full == 0:
                warnings.append(
                    f"⚠ Data maturity: 7-D churn is not available for any level. "
                    f"Combined churn is computed from session churn"
                    f"{' and D3 churn' if has_3d else ''} only. "
                    f"Results will be more accurate once the data matures past 7 days."
                )
            else:
                warnings.append(
                    f"⚠ Data maturity: {immature_count} of {n_total} levels ({pct:.0f}%) "
                    f"are missing 7-D churn data (data not yet mature). "
                    f"Combined churn for those levels uses available windows only. "
                    f"Full D7 data available for levels 1–{n_full}."
                )
        elif not has_3d:
            warnings.append("3-D churn column not available. Combined churn uses session churn only.")

    # --- Predicted D14 Churn ---
    # Extrapolates from the return-rate pattern observed between D3 and D7.
    # Only computed where both D3 and D7 are non-NaN.
    if has_3d and has_7d:
        safe_3d = merged["churn_3d"].replace(0, np.nan)
        ratio = merged["churn_7d"] / safe_3d
        ratio = ratio.clip(lower=0.001, upper=1.0)
        daily_factor = ratio ** (1.0 / 4.0)
        merged["predicted_d14_churn"] = merged["churn_7d"] * (daily_factor ** 7)
    else:
        warnings.append("Cannot compute predicted D14 churn: 3-D and 7-D churn data required.")

    # --- Funnel Position Weight ---
    # Early levels have naturally higher churn (uncommitted players), so we discount it.
    # Late levels losing players is more alarming (committed players), so we amplify it.
    # Weight ramps from 0.6 at level 1 to 1.4 at the last level (linear ramp).
    if "level" in merged.columns and len(merged) > 1:
        level_min = merged["level"].min()
        level_max = merged["level"].max()
        level_span = max(level_max - level_min, 1)
        # Normalized position: 0 at start, 1 at end
        position_norm = (merged["level"] - level_min) / level_span
        # Weight ramps from 0.6 (early) to 1.4 (late)
        merged["_funnel_position_weight"] = 0.6 + 0.8 * position_norm
    else:
        merged["_funnel_position_weight"] = 1.0

    # --- Funnel Phase Assignment ---
    # Tutorial = first TUTORIAL_LEVEL_COUNT levels (flat).
    # Early/Mid/Late split the remaining levels by percentage.
    if "level" in merged.columns and len(merged) > 1:
        levels = merged["level"].values
        # Pre-compute post-tutorial range once
        post_tutorial_mask = levels > TUTORIAL_LEVEL_COUNT
        pt_levels = levels[post_tutorial_mask]
        pt_min = pt_levels.min() if len(pt_levels) > 0 else 0
        pt_max = pt_levels.max() if len(pt_levels) > 0 else 0
        pt_span = max(pt_max - pt_min, 1)

        phases = []
        for lvl in levels:
            if lvl <= TUTORIAL_LEVEL_COUNT:
                phases.append("Tutorial")
            elif len(pt_levels) <= 1:
                phases.append("Mid")  # fallback if almost no post-tutorial levels
            else:
                pct = (lvl - pt_min) / pt_span
                assigned = "Mid"
                for phase_def in FUNNEL_PHASES_POST_TUTORIAL:
                    if phase_def["start_pct"] <= pct < phase_def["end_pct"]:
                        assigned = phase_def["name"]
                        break
                if pct >= 1.0:
                    assigned = FUNNEL_PHASES_POST_TUTORIAL[-1]["name"]
                phases.append(assigned)
        merged["_funnel_phase"] = phases

        # Phase-aware expected churn multiplier (how much churn is "expected" at this position)
        phase_mult_map = {p["name"]: p["expected_churn_mult"] for p in FUNNEL_PHASES}
        merged["_phase_churn_mult"] = merged["_funnel_phase"].map(phase_mult_map).fillna(1.0)
    else:
        merged["_funnel_phase"] = "Mid"
        merged["_phase_churn_mult"] = 1.0

    # --- Expected Drop-off Baseline ---
    # Fit an exponential decay to the drop-off data: expected(i) = a * exp(-b * i) + c
    # This models the natural decline in drop-off rate as you move through the funnel.
    # Levels that deviate *above* this baseline are genuinely problematic.
    if "dropoff_rate" in merged.columns and len(merged) > 10:
        dropoff_vals = merged["dropoff_rate"].fillna(0).values
        n_levels = len(dropoff_vals)

        # Robust baseline: use a wide rolling median (less sensitive to spikes)
        # Then smooth it with a second pass
        window = max(15, n_levels // 10)
        rolling_median = pd.Series(dropoff_vals).rolling(
            window=window, center=True, min_periods=3
        ).median()
        # Fill edges with nearest values
        rolling_median = rolling_median.bfill().ffill()

        # Second smoothing pass for a cleaner curve
        expected_baseline = rolling_median.rolling(
            window=max(7, window // 2), center=True, min_periods=3
        ).mean()
        expected_baseline = expected_baseline.bfill().ffill()

        merged["_expected_dropoff"] = expected_baseline.values

        # Deviation from expected: positive = worse than expected
        merged["_dropoff_deviation"] = merged["dropoff_rate"] - merged["_expected_dropoff"]

        # Phase-adjusted deviation: scale by the phase multiplier
        # In Tutorial phase (mult=2.5), a deviation is divided by 2.5 → less alarming
        # In Late phase (mult=0.6), a deviation is divided by 0.6 → more alarming
        merged["_dropoff_deviation_adj"] = merged["_dropoff_deviation"] / merged["_phase_churn_mult"]
    else:
        merged["_expected_dropoff"] = 0.0
        merged["_dropoff_deviation"] = 0.0
        merged["_dropoff_deviation_adj"] = 0.0

    # --- Revenue Score (weighted composite monetization metric) ---
    # Weighted by actual revenue impact: IAP > EGP > Boosters > Sink
    rev_numerator = pd.Series(0.0, index=merged.index)
    rev_total_weight = 0.0
    for col, weight in REVENUE_WEIGHTS.items():
        if col in merged.columns:
            rev_numerator += merged[col].fillna(0) * weight
            rev_total_weight += weight
    if rev_total_weight > 0:
        merged["_revenue_score"] = rev_numerator / rev_total_weight
    else:
        merged["_revenue_score"] = 0.0

    return merged, errors, warnings


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def process_files(level_data_path, level_params_path=None):
    """
    Full parsing pipeline: parse both files, join, enrich.
    Level params file is optional — if not provided, analysis runs
    without level design properties (mechanics, colors, etc.).

    Returns:
        (DataFrame or None, errors: list[str], warnings: list[str], summary: dict)
    """
    all_errors = []
    all_warnings = []

    # Parse level data
    ld_df, ld_errors, ld_warnings = parse_level_data(level_data_path)
    all_errors.extend(ld_errors)
    all_warnings.extend(ld_warnings)

    if ld_df is None:
        return None, all_errors, all_warnings, {}

    # Parse level params (optional)
    if level_params_path:
        lp_df, lp_errors, lp_warnings = parse_level_params(level_params_path)
        all_errors.extend(lp_errors)
        all_warnings.extend(lp_warnings)

        if lp_df is None:
            return None, all_errors, all_warnings, {}
    else:
        lp_df = None
        all_warnings.append("No Level Parameters file provided. Mechanics and design property analysis will be unavailable.")

    # Join and enrich
    merged_df, join_errors, join_warnings = join_and_enrich(ld_df, lp_df)
    all_errors.extend(join_errors)
    all_warnings.extend(join_warnings)

    if merged_df is None:
        return None, all_errors, all_warnings, {}

    summary = compute_summary(merged_df)

    return merged_df, all_errors, all_warnings, summary


def compute_summary(df):
    """Compute summary statistics for a DataFrame. Can be called on filtered data."""
    # --- Data maturity info ---
    maturity_info = _compute_maturity_info(df)

    summary = {
        "total_levels": len(df),
        "level_range": f"{int(df['level'].min())} \u2013 {int(df['level'].max())}",
        "bracket_counts": df["target_bracket"].value_counts().to_dict(),
        "bracket_order": [b for b in DIFFICULTY_ORDER if b in df["target_bracket"].values],
        "has_params": int(df["level_name"].notna().sum()) if "level_name" in df.columns else 0,
        "missing_params": int(df["level_name"].isna().sum()) if "level_name" in df.columns else len(df),
        "has_params_file": "level_name" in df.columns,
        "avg_aps": round(float(df["aps"].mean()), 3) if "aps" in df.columns else None,
        "avg_combined_churn": round(float(df["combined_churn"].mean()), 4) if "combined_churn" in df.columns and df["combined_churn"].notna().any() else None,
        "avg_session_churn": round(float(df["churn"].mean()), 4) if "churn" in df.columns and df["churn"].notna().any() else None,
        "avg_3d_churn": round(float(df["churn_3d"].mean()), 4) if "churn_3d" in df.columns and df["churn_3d"].notna().any() else None,
        "avg_7d_churn": round(float(df["churn_7d"].mean()), 4) if "churn_7d" in df.columns and df["churn_7d"].notna().any() else None,
        "avg_predicted_d14_churn": round(float(df["predicted_d14_churn"].mean()), 4) if "predicted_d14_churn" in df.columns and df["predicted_d14_churn"].notna().any() else None,
        "avg_completion": round(float(df["completion_rate"].mean()), 4) if "completion_rate" in df.columns else None,
    }
    summary.update(maturity_info)
    return summary


def _compute_maturity_info(df):
    """
    Compute data maturity information for the summary.
    Returns a dict with maturity metrics that get merged into the summary.
    """
    info = {
        "has_immature_data": False,
        "churn_maturity_label": "full",       # "full", "partial", "minimal"
        "churn_maturity_detail": "",           # human-readable detail
        "churn_windows_available": [],         # e.g. ["session", "D3", "D7"]
        "pct_full_maturity": 100.0,            # % of levels with all churn windows
        "pct_partial_maturity": 0.0,
        "pct_minimal_maturity": 0.0,
    }

    if "_churn_maturity" not in df.columns:
        return info

    maturity = df["_churn_maturity"]
    n = len(df)
    if n == 0:
        return info

    n_full = int((maturity >= 3).sum())
    n_partial = int((maturity == 2).sum())
    n_minimal = int((maturity <= 1).sum())

    info["pct_full_maturity"] = round(n_full / n * 100, 1)
    info["pct_partial_maturity"] = round(n_partial / n * 100, 1)
    info["pct_minimal_maturity"] = round(n_minimal / n * 100, 1)

    # Determine available windows
    windows = ["session"]
    if "churn_3d" in df.columns and df["churn_3d"].notna().any():
        windows.append("D3")
    if "churn_7d" in df.columns and df["churn_7d"].notna().any():
        windows.append("D7")
    info["churn_windows_available"] = windows

    # Classify overall maturity
    if n_full == n:
        info["churn_maturity_label"] = "full"
        info["churn_maturity_detail"] = "All churn windows (session, D3, D7) available for all levels."
    elif n_full > 0:
        info["has_immature_data"] = True
        info["churn_maturity_label"] = "partial"
        info["churn_maturity_detail"] = (
            f"{n_full} of {n} levels ({info['pct_full_maturity']}%) have full churn data. "
            f"{n - n_full} levels use degraded churn (fewer windows)."
        )
    elif n_partial > 0:
        info["has_immature_data"] = True
        info["churn_maturity_label"] = "partial"
        available = " + ".join(windows)
        info["churn_maturity_detail"] = (
            f"7-D churn data is not available. Combined churn is computed from {available} only. "
            f"Results will improve once data matures past 7 days."
        )
    else:
        info["has_immature_data"] = True
        info["churn_maturity_label"] = "minimal"
        info["churn_maturity_detail"] = (
            f"Only session churn is available. D3 and D7 churn data is missing. "
            f"Combined churn accuracy is limited."
        )

    return info
