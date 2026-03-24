"""
LD Wizard — AB test workbook parser
Normalizes side-by-side Control / Variant experiment exports into one row per level.
"""

import pandas as pd

from engine.parser import DIFFICULTY_CODE_MAP
from engine.parser import _read_csv_smart


AB_METRIC_MAP = {
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
    "Objectives Left": "objectives_left",
    "Objectives Left ": "objectives_left",
    "% Objectives Left": "objectives_left_pct",
}

SUM_METRICS = {
    "users",
    "iap_revenue",
    "iap_transactions",
    "soft_currency_used",
    "boosters_used",
    "egps_used",
}


def process_ab_file(filepath):
    errors = []
    warnings = []

    try:
        if filepath.endswith(".csv"):
            raw = _read_csv_smart(filepath)
        else:
            raw = pd.read_excel(filepath, sheet_name=0, header=None)
    except Exception as exc:
        errors.append(f"Could not read AB test file: {exc}")
        return None, errors, warnings, None

    if raw.shape[0] < 4:
        errors.append("AB test file has too few rows. Expected at least 4.")
        return None, errors, warnings, None

    metric_row = raw.iloc[1].ffill().fillna("")
    cohort_row = raw.iloc[2].fillna("")

    control_label = None
    variant_label = None
    column_specs = []

    for col_index in range(4, raw.shape[1]):
        metric_name = str(metric_row.iloc[col_index]).strip()
        cohort_name = str(cohort_row.iloc[col_index]).strip()
        if not metric_name or not cohort_name:
            continue
        if cohort_name.startswith("Unnamed"):
            continue
        internal_name = AB_METRIC_MAP.get(metric_name)
        if not internal_name:
            continue

        if control_label is None and cohort_name.lower() == "control":
            control_label = cohort_name
        elif cohort_name.lower() != "control" and variant_label is None:
            variant_label = cohort_name

        column_specs.append({
            "column_index": col_index,
            "metric_name": internal_name,
            "cohort_label": cohort_name,
        })

    if control_label is None or variant_label is None:
        errors.append("Could not find both Control and Variant cohort columns in the AB test file.")
        return None, errors, warnings, None

    data = raw.iloc[3:].copy().reset_index(drop=True)
    data = data.rename(columns={
        0: "level",
        1: "control_target_code",
        2: "achieved_code",
        3: "variant_target_code",
    })
    data["level"] = pd.to_numeric(data["level"], errors="coerce").ffill()
    data = data[data["level"].notna()].copy()
    if data.empty:
        errors.append("No level rows were found in the AB test file.")
        return None, errors, warnings, None

    data["level"] = data["level"].astype(int)
    for col in ("control_target_code", "achieved_code", "variant_target_code"):
        data[col] = data[col].ffill().astype(str).str.strip()

    records = []
    for level, level_rows in data.groupby("level", sort=True):
        record = {
            "level": int(level),
            "target_code": _dominant_code(level_rows["control_target_code"], level_rows["variant_target_code"]),
            "achieved_code": _dominant_code(level_rows["achieved_code"]),
        }

        for cohort_key, cohort_label in (("control", control_label), ("variant", variant_label)):
            user_series = _numeric_series(level_rows, column_specs, cohort_label, "users")
            total_users = float(user_series.fillna(0).sum())
            record[f"{cohort_key}_users"] = round(total_users, 3)

            for metric_name in {spec["metric_name"] for spec in column_specs if spec["cohort_label"] == cohort_label}:
                values = _numeric_series(level_rows, column_specs, cohort_label, metric_name)
                record[f"{cohort_key}_{metric_name}"] = _aggregate_metric(values, user_series, metric_name)

        records.append(record)

    df = pd.DataFrame(records).sort_values("level").reset_index(drop=True)
    df["target_bracket"] = df["target_code"].map(DIFFICULTY_CODE_MAP)
    if df["target_bracket"].isna().all():
        warnings.append("Could not derive difficulty brackets from the AB workbook. Bracket breakdown will be unavailable.")

    meta = {
        "control_label": control_label,
        "variant_label": variant_label,
        "level_count": int(df["level"].nunique()),
    }
    return df, errors, warnings, meta


def _dominant_code(*series_list):
    candidates = []
    for series in series_list:
        for value in series:
            if pd.isna(value):
                continue
            text = str(value).strip()
            if text and text.lower() != "nan":
                candidates.append(text)
    if not candidates:
        return None
    return pd.Series(candidates).mode().iloc[0]


def _numeric_series(rows, column_specs, cohort_label, metric_name):
    matching_indices = [
        spec["column_index"]
        for spec in column_specs
        if spec["cohort_label"] == cohort_label and spec["metric_name"] == metric_name
    ]
    if not matching_indices:
        return pd.Series(dtype=float)

    series = rows[matching_indices[0]].astype(str).str.strip()
    series = series.str.replace(",", "", regex=False)
    percent_mask = series.str.endswith("%")
    series = series.str.rstrip("%")
    numeric = pd.to_numeric(series, errors="coerce")
    if percent_mask.any():
        numeric = numeric.where(~percent_mask, numeric / 100.0)
    return numeric


def _aggregate_metric(values, user_series, metric_name):
    clean_values = values.dropna()
    if clean_values.empty:
        return None

    if metric_name in SUM_METRICS:
        return round(float(clean_values.sum()), 6)

    clean_weights = user_series.loc[clean_values.index].fillna(0)
    if clean_weights.sum() > 0:
        return round(float((clean_values * clean_weights).sum() / clean_weights.sum()), 6)
    return round(float(clean_values.mean()), 6)
