# LD Wizard — Project Handoff & Context

## What is LD Wizard?

A local Flask web app that automates level design analysis for puzzle games (built for Voodoo). Upload a CSV of level metrics, optionally a level parameters CSV, and get a full dashboard with health scoring, funnel analysis, difficulty curves, and actionable recommendations.

**Tech stack:** Python Flask (port 5050), HTML/CSS/JS frontend (Bootstrap 5, Chart.js), pandas for data processing. Everything runs locally — no cloud dependencies.

---

## Project Location

```
/sessions/gifted-magical-brown/mnt/outputs/ld-wizard/
```

### Key Files

| File | Purpose |
|------|---------|
| `app.py` | Flask routes, API endpoints, session management |
| `config.py` | Port config |
| `engine/parser.py` | Core data pipeline — loads CSVs, joins, enriches, assigns brackets/phases |
| `engine/aps_engine.py` | APS range analysis, bracket health scoring |
| `engine/analysis/ranking.py` | Performance scoring (bracket-relative), outlier detection |
| `engine/analysis/funnel.py` | Player funnel curve, pacing score, steep drops |
| `engine/analysis/dropoff.py` | Phase-aware drop-off analysis, spike detection, zone identification |
| `engine/analysis/correlation.py` | APS vs churn/revenue correlations, diminishing returns, bracket metrics |
| `engine/analysis/recommendations.py` | Fix/replicate, smoothing, reorder, difficulty curve, best mechanics |
| `templates/dashboard.html` | Main dashboard — 3 tabs (Exec Summary, Deep Dive, Recommendations) |
| `templates/upload.html` | File upload page |
| `templates/base.html` | Base template |
| `static/css/style.css` | All styles |

### Test Data

| File | Description |
|------|-------------|
| `Metrics.csv` | Card Factory — 500 levels, mature data (session + D3 + D7 churn) |
| `LevelProperties_Funnel_16.02_HitFunnel_V4_2026-03-15_23-29-50.csv` | Card Factory level parameters (colors, features, APS settings) |
| `MS_FH_v1.1.7_03_15.csv` | Immature data — 300 levels, session churn only |

### Reference Documents

| File | Description |
|------|-------------|
| `LD_Wizard_PRD_v1.1.md` | Product Requirements Document |
| `LD_Wizard_DataDictionary_v1.md` | Data dictionary for input/output fields |
| `LD_Wizard_UserManual_v1.0.docx` | User manual (created with docx-js) |
| `ld-wizard-v1.0.zip` | Bundled app (69KB, 25 files) — needs re-bundling after recent changes |

---

## Architecture & Key Concepts

### Dashboard Structure (3 Tabs)

**Tab 1 — Executive Summary (5 views):**
- Health Gauge (letter grade A-F, score 0-100)
- Health Breakdown Bars (Retention, Pacing, Drop-off, Bracket Balance, Monetization)
- KPI Stack (Levels, Avg APS, Avg Churn, Completion)
- Bracket Distribution + APS Ranges + Top Priority Actions
- Bracket Metrics table + Data Context (Maturity + Content Runway)

**Tab 2 — Deep Dive (3 accordion sections):**
- Funnel & Retention: Funnel curve, drop-off vs expected baseline, phase summary, steep drops, problem areas
- Level Performance: Score distribution scatter, outliers, full ranking table (collapsed)
- Difficulty & Monetization: 3 scatter plots (APS vs Churn, APS vs Revenue, Churn vs Revenue), optimal APS ranges, diminishing returns

**Tab 3 — Recommendations (3 panels):**
- Fix vs Replicate Levels
- **Difficulty & Progression Fixes** (unified panel — see "Latest Changes" below)
- Best Mechanics & Parameters (requires level params file)

### Funnel Phases

Tutorial = first 30 levels (flat constant `TUTORIAL_LEVEL_COUNT = 30`), then post-tutorial levels split proportionally:
- Early: 0-30% of post-tutorial range (expected churn mult: 1.6x)
- Mid: 30-70% (expected churn mult: 1.0x)
- Late: 70-100% (expected churn mult: 0.6x)
- Tutorial expected churn mult: 2.5x

### Bracket System

5 difficulty brackets: Easy, Medium, Hard, Super Hard, Wall — assigned by APS ranges in `aps_engine.py`.

### Bracket-Relative Performance Scoring

Raw composite score per level (using bracket-specific goal weights) is normalized within each bracket using percentile rank. This ensures all bracket averages converge to ~0.50, so Hard/Wall levels can compete fairly with Easy levels.

Key function: `_normalize_scores_by_bracket()` in `ranking.py`.

### Phase-Adjusted Drop-off

Drop-off deviation is divided by the phase's expected churn multiplier, so Tutorial/Early drops are de-weighted relative to Mid/Late.

### Spike Detection

Sigma-based: warning at 1.8σ, critical at 3.0σ.

---

## Latest Changes (This Session)

### 1. Unified "Difficulty & Progression Fixes" Panel

**What changed:** Merged 3 separate recommendation panels (Smoothing, Difficulty Curve, Optimal Level Reordering) into a single unified panel.

**The new panel has:**
- **APS Curve Chart** — actual APS (purple line) vs ideal logarithmic curve (dashed gray), rendered with Chart.js. Problem zones highlighted as colored bands (annotation plugin — note: the annotation plugin may not be loaded; if bands don't render, that's fine, the chart still works).
- **Bracket APS Targets** — collapsible compact card row showing current vs sweet-spot APS for each bracket.
- **Unified Priority Action List** — all issues from smoothing (drop-offs), reorder (spikes), and difficulty curve (zone deviations) merged into one numbered list sorted by impact. Each item shows a step number, zone/level range, type pill (Drop-off / Reorder / Curve), severity badge, action headline, detail line, and sub-items.
- **"Show all" toggle** — top 15 items shown initially, rest behind a button.

**Backend change:** Added `curve_points` to `_recommend_difficulty_curve()` output in `recommendations.py` — sampled actual vs ideal APS values (max ~80 points) for the chart.

**Frontend change:** Replaced the 3 separate rendering functions (`smoothingContainer`, `reorderContainer`, `difficultyCurveContainer`) with a single `renderDifficultyProgressionFixes(data)` function.

### 2. Dashboard Consolidation (Previous in This Session)

Audited all 32 views, cut to 22:
- KPI Stack: 7→4 metrics (cut Session/D3/D7 churn)
- Funnel Preview: cut from Exec Summary
- Data Maturity + Content Runway: merged into "Data Context" panel
- Bracket Metrics table: moved to Exec Summary
- Pacing Zones table: cut
- Drop-off Zones + Spikes: merged into "Problem Areas"
- Best/Worst per Bracket tables: cut
- Full Level Ranking: collapsed by default with toggle
- APS vs Completion scatter, APS Binned chart, Revenue by Churn Range, Churn-Revenue Efficiency table: all cut
- Smoothing + Difficulty Curve: merged into "Difficulty & Pacing Fixes" (now further merged with Reorder)

### 3. Bracket-Relative Scoring (Previous in This Session)

Added `_normalize_scores_by_bracket()` to `ranking.py`. Changed `perf_score` to use percentile rank within each bracket.

### 4. Tutorial Phase Change (Previous in This Session)

Changed from percentage-based (first 10%) to flat 30 levels.

---

## Development Rules

These are rules Roi established across sessions — follow them:

1. **Ask for verification before executing any command** (especially destructive ones)
2. **Ask questions about prompts before executing** — clarify requirements first
3. **Stick to the PRD** created together
4. **Features built and verified one phase at a time**

---

## How to Run

```bash
cd /path/to/ld-wizard
pip install flask pandas numpy
python app.py
# Opens on http://127.0.0.1:5050
```

Or use the bundled scripts:
- macOS/Linux: `./run.sh`
- Windows: `run.bat`

---

## How to Test

```bash
# Start server
cd ld-wizard && python app.py &

# Upload test data
curl -s -X POST \
  -F "level_data=@Metrics.csv" \
  -F "level_params=@LevelProperties_Funnel_16.02_HitFunnel_V4_2026-03-15_23-29-50.csv" \
  -c cookies.txt \
  http://127.0.0.1:5050/upload

# Check API endpoints
curl -s -b cookies.txt http://127.0.0.1:5050/api/data/overview | python3 -m json.tool | head -20
curl -s -b cookies.txt http://127.0.0.1:5050/api/data/recommendations | python3 -m json.tool | head -20
curl -s -b cookies.txt http://127.0.0.1:5050/api/data/funnel | python3 -m json.tool | head -20
curl -s -b cookies.txt http://127.0.0.1:5050/api/data/ranking | python3 -m json.tool | head -20
curl -s -b cookies.txt http://127.0.0.1:5050/api/data/correlation | python3 -m json.tool | head -20
curl -s -b cookies.txt http://127.0.0.1:5050/api/data/dropoff | python3 -m json.tool | head -20
```

---

## Known Issues / Technical Debt

1. **ZIP bundle is outdated** — `ld-wizard-v1.0.zip` was created before the dashboard consolidation and unified progression panel. Needs re-bundling.
2. **User manual is outdated** — `LD_Wizard_UserManual_v1.0.docx` doesn't reflect the new unified Difficulty & Progression panel or the dashboard consolidation.
3. **Chart.js annotation plugin** — The APS curve chart uses annotation config for problem zone highlighting bands, but the annotation plugin may not be loaded (it's a separate Chart.js plugin). The chart renders fine without it — you just don't get the colored background bands. Could add the plugin CDN if desired.
4. **48 action items in unified list for Card Factory data** — the list caps at 15 initially with a "show all" toggle, but the raw count is high. Could consider being more selective in what gets surfaced (e.g., only top N reorder spikes, only actionable curve deviations).
5. **npm dependency for docx creation** — The user manual was built with `npm install docx` (docx-js). If re-creating the manual, need to `npm install docx` first.

---

## What Roi Might Want Next

Based on the project trajectory, likely next steps:
- Re-bundle the app as v1.1 zip
- Update the user manual
- Further UI polish or new features
- Test with additional game datasets
- Any bug fixes from user testing
