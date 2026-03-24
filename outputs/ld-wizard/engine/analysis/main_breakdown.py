"""Main Breakdown analysis — Pacing Formula Compliance & Difficulty Mismatch Detection."""

import numpy as np

# ── Voodoo Puzzle Hit Formula — target difficulty pattern ────────────────
# Extracted from the official template. 300 levels. Levels beyond 300 cycle
# the core-loop episode pattern (indices 20..299 repeat every 280 levels).
_FORMULA_RAW = (
    # L1-20: Onboarding
    "E E E E E E E M M E E E E E E E H SH E E"
    # L21-30: first core episodes
    " E E M E H E M E M SH"
    # L31-40
    " E E M E H E M E M SH"
    # L41-50
    " E E M E H E M E M SH"
    # L51-60
    " E M M H M M H E M SH"
    # L61-70
    " E M M H M M H E M SH"
    # L71-80
    " E M M H M M H E M W"
    # L81-90
    " E M M H M M H E M SH"
    # L91-100
    " E M M H M M H E M W"
    # L101-110
    " E M M H M M H E M SH"
    # L111-120
    " E M M H M M H E M W"
    # L121-130
    " E M M H M M H E M SH"
    # L131-140
    " E M M H M M H E M W"
    # L141-150
    " E M M H M M H E M SH"
    # L151-160
    " E M M H M M H E M W"
    # L161-170
    " E M M H M M H E M SH"
    # L171-180
    " E M M H M M H E M W"
    # L181-190
    " E M M H M M H E M SH"
    # L191-200
    " E M M H M M H E M W"
    # L201-210
    " E M M H M M H E M SH"
    # L211-220
    " E M M H M M H E M W"
    # L221-230
    " E M M H M M H E M SH"
    # L231-240
    " E M M H M M H E M W"
    # L241-250
    " E M M H M M H E M SH"
    # L251-260
    " E M M H M M H E M W"
    # L261-270
    " E M M H M M H E M SH"
    # L271-280
    " E M M H M M H E M W"
    # L281-290
    " E M M H M M H E M SH"
    # L291-300
    " E M M H M M H E M W"
)

_CODE_MAP = {"E": "Easy", "M": "Medium", "H": "Hard", "SH": "Super Hard", "W": "Wall"}
_CODE_REVERSE = {v: k for k, v in _CODE_MAP.items()}
_BRACKET_RANK = {"Easy": 0, "Medium": 1, "Hard": 2, "Super Hard": 3, "Wall": 4}

FORMULA_PATTERN = [_CODE_MAP[c] for c in _FORMULA_RAW.split()]

# Core-loop episode (L81+ in the template) is a stable 20-level cycle:
# [E M M H M M H E M SH] [E M M H M M H E M W]
_CORE_CYCLE = FORMULA_PATTERN[80:100]  # 20-level repeating unit


def _get_formula_bracket(level_num):
    """Return the expected bracket for any level number (1-indexed)."""
    idx = level_num - 1
    if idx < len(FORMULA_PATTERN):
        return FORMULA_PATTERN[idx]
    # Beyond 300: repeat the 20-level core cycle
    overflow = (idx - 80) % 20
    return _CORE_CYCLE[overflow]


def _aps_bracket(aps_val, max_aps):
    """Assign difficulty bracket based on APS percentile of max APS."""
    if max_aps <= 0 or not np.isfinite(aps_val):
        return "Easy"
    pct = aps_val / max_aps
    if pct <= 0.20:
        return "Easy"
    elif pct <= 0.40:
        return "Medium"
    elif pct <= 0.60:
        return "Hard"
    elif pct <= 0.80:
        return "Super Hard"
    else:
        return "Wall"


def compute_main_breakdown(df):
    """Compute the Main Breakdown analysis.

    Returns a dict with two sections:
    1. pacing_compliance — Does the difficulty curve follow the formula?
    2. difficulty_mismatches — Which levels don't fit their target bracket (APS-based)?
    """
    result = {"available": False}

    if df is None or len(df) < 2:
        return result
    if "level" not in df.columns or "aps" not in df.columns:
        return result
    if "target_bracket" not in df.columns:
        return result

    levels = df["level"].values
    aps_vals = df["aps"].fillna(0).values
    target_brackets = df["target_bracket"].fillna("").values
    max_aps = float(np.nanmax(aps_vals)) if len(aps_vals) > 0 else 1.0
    if max_aps <= 0:
        max_aps = 1.0

    n = len(df)

    # ── 1. PACING COMPLIANCE ─────────────────────────────────────────────
    # Compare the game's Target column against the Voodoo formula
    pacing_levels = []
    match_count = 0
    total_compared = 0
    deviations = []  # levels where target ≠ formula

    for i in range(n):
        lv = int(levels[i])
        target_b = target_brackets[i]
        formula_b = _get_formula_bracket(lv)

        matches = (target_b == formula_b)
        if target_b:  # skip if target is empty
            total_compared += 1
            if matches:
                match_count += 1
            else:
                dev_dir = "harder" if _BRACKET_RANK.get(target_b, 0) > _BRACKET_RANK.get(formula_b, 0) else "easier"
                deviations.append({
                    "level": lv,
                    "target": target_b,
                    "formula": formula_b,
                    "direction": dev_dir,
                })

        pacing_levels.append({
            "level": lv,
            "target": target_b,
            "formula": formula_b,
            "match": matches,
            "aps": round(float(aps_vals[i]), 3),
        })

    compliance_pct = round(match_count / total_compared * 100, 1) if total_compared > 0 else 0

    # Streak analysis: longest matching streak, longest deviation streak
    match_flags = [p["match"] for p in pacing_levels if p["target"]]
    longest_match = _longest_streak(match_flags, True)
    longest_dev = _longest_streak(match_flags, False)

    # Group deviations by severity
    harder_count = sum(1 for d in deviations if d["direction"] == "harder")
    easier_count = sum(1 for d in deviations if d["direction"] == "easier")

    # Build the formula pattern sequence for the chart (full dataset range)
    formula_sequence = []
    for i in range(n):
        lv = int(levels[i])
        formula_sequence.append({
            "level": lv,
            "bracket": _get_formula_bracket(lv),
            "rank": _BRACKET_RANK.get(_get_formula_bracket(lv), 0),
        })

    target_sequence = []
    for i in range(n):
        lv = int(levels[i])
        tb = target_brackets[i] if target_brackets[i] else None
        target_sequence.append({
            "level": lv,
            "bracket": tb,
            "rank": _BRACKET_RANK.get(tb, -1) if tb else -1,
        })

    pacing = {
        "total_levels": total_compared,
        "match_count": match_count,
        "compliance_pct": compliance_pct,
        "deviation_count": len(deviations),
        "harder_count": harder_count,
        "easier_count": easier_count,
        "longest_match_streak": longest_match,
        "longest_deviation_streak": longest_dev,
        "deviations": deviations[:50],  # cap for payload size
        "total_deviations": len(deviations),
        "formula_sequence": formula_sequence,
        "target_sequence": target_sequence,
    }

    # ── 2. DIFFICULTY MISMATCHES (APS-based brackets) ────────────────────
    mismatch_levels = []
    aps_match_count = 0

    per_level_aps_brackets = []
    for i in range(n):
        lv = int(levels[i])
        target_b = target_brackets[i]
        aps_b = _aps_bracket(aps_vals[i], max_aps)
        aps_match = (target_b == aps_b)

        if target_b:
            if aps_match:
                aps_match_count += 1
            else:
                rank_diff = _BRACKET_RANK.get(aps_b, 0) - _BRACKET_RANK.get(target_b, 0)
                mismatch_levels.append({
                    "level": lv,
                    "target": target_b,
                    "aps_bracket": aps_b,
                    "aps": round(float(aps_vals[i]), 3),
                    "aps_pct": round(float(aps_vals[i]) / max_aps * 100, 1),
                    "direction": "harder" if rank_diff > 0 else "easier",
                    "severity": abs(rank_diff),
                })

        per_level_aps_brackets.append({
            "level": lv,
            "target": target_b,
            "aps_bracket": aps_b,
            "aps": round(float(aps_vals[i]), 3),
            "aps_pct": round(float(aps_vals[i]) / max_aps * 100, 1),
            "match": aps_match if target_b else None,
        })

    aps_compliance_pct = round(aps_match_count / total_compared * 100, 1) if total_compared > 0 else 0

    # Sort mismatches by severity desc, then level asc
    mismatch_levels.sort(key=lambda x: (-x["severity"], x["level"]))

    # Severity breakdown
    sev_counts = {}
    for m in mismatch_levels:
        s = m["severity"]
        sev_counts[s] = sev_counts.get(s, 0) + 1

    # Per-bracket mismatch rates
    bracket_mismatch_rates = {}
    for b in ["Easy", "Medium", "Hard", "Super Hard", "Wall"]:
        total_b = sum(1 for p in per_level_aps_brackets if p["target"] == b)
        mismatch_b = sum(1 for p in per_level_aps_brackets if p["target"] == b and p["match"] is False)
        if total_b > 0:
            bracket_mismatch_rates[b] = {
                "total": total_b,
                "mismatched": mismatch_b,
                "rate": round(mismatch_b / total_b * 100, 1),
            }

    # Harder vs easier
    harder_aps = sum(1 for m in mismatch_levels if m["direction"] == "harder")
    easier_aps = sum(1 for m in mismatch_levels if m["direction"] == "easier")

    mismatches = {
        "max_aps": round(max_aps, 3),
        "total_levels": total_compared,
        "match_count": aps_match_count,
        "compliance_pct": aps_compliance_pct,
        "mismatch_count": len(mismatch_levels),
        "harder_count": harder_aps,
        "easier_count": easier_aps,
        "severity_counts": sev_counts,
        "bracket_mismatch_rates": bracket_mismatch_rates,
        "mismatches": mismatch_levels[:80],  # cap for payload
        "total_mismatches": len(mismatch_levels),
        "per_level": per_level_aps_brackets,
        "bracket_thresholds": {
            "Easy": f"0–{round(max_aps * 0.20, 2)}",
            "Medium": f"{round(max_aps * 0.20, 2)}–{round(max_aps * 0.40, 2)}",
            "Hard": f"{round(max_aps * 0.40, 2)}–{round(max_aps * 0.60, 2)}",
            "Super Hard": f"{round(max_aps * 0.60, 2)}–{round(max_aps * 0.80, 2)}",
            "Wall": f"{round(max_aps * 0.80, 2)}–{round(max_aps, 2)}",
        },
    }

    result = {
        "available": True,
        "pacing_compliance": pacing,
        "difficulty_mismatches": mismatches,
    }
    return result


def _longest_streak(flags, target_value):
    """Find length of longest consecutive run of target_value in a list of bools."""
    longest = 0
    current = 0
    for f in flags:
        if f == target_value:
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return longest
