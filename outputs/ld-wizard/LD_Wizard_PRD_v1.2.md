# LD Wizard — Product Requirements Document (v1.2)

## Changelog

- **v1.2** — Added Playtime Economics module (Section 5.5): Onboarding / Core Loop split, Real Playtime column, IAP-only monetization definition, revenue derivation, onboarding smoothness metrics, score thresholds, and retention prediction mapping. Updated A11 (Real Playtime no longer ignored). Updated data dictionary reference.
- **v1.1** — Added Adaptive APS Range System (Section 5.0), Difficulty Bracket Goals (Section 5.0), W (Wall) as distinct analysis category, system insight/flagging responsibilities, corrected Section 4.1 (removed reference to Achieved column), added reference to Data Dictionary document.
- **v1.0** — Initial PRD

---

## 1. Product Overview

**LD Wizard** (Level Design Wizard) is a local web application that automates level design analysis for puzzle games. It receives a standardized level funnel data file and a level parameters file, processes the data, and outputs visual analysis with actionable insights — replacing the manual process of combing through funnel data to identify issues and opportunities.

## 2. Target Users

Level designers, business analysts, game managers, heads of departments, VP Gaming, and CEO. All users are tech-savvy, but the UI must remain clean, simple, and highly readable. The app must serve both deep analytical use (designers tweaking levels) and high-level overview use (executives checking game health).

## 3. Tech Stack

- **Backend:** Python (Flask or FastAPI)
- **Frontend:** HTML/CSS/JS served locally (clean dashboard UI)
- **Data processing:** pandas
- **Visualization:** Chart.js or Plotly.js (browser-side)
- **Distribution:** Zip folder with a run script; future option to package as EXE
- **Runs on:** localhost in the user's browser

## 4. Data Input

The application takes **two files** as input. Full column definitions, data types, and units are documented in the **Data Dictionary & Base Assumptions** document (LD_Wizard_DataDictionary_v1.md).

### 4.1 Level Data File (Excel - .xlsx)

- Standardized format across all games, provided by the internal data analytics team
- Contains per-level performance metrics: users, funnel %, APS, IAP, churn, win rate, playtime, real playtime, boosters, revenue, and more
- Includes a Target difficulty bracket per level that defines the intended pacing cadence
- Number of levels varies per game

### 4.2 Level Parameters File (CSV)

- Contains level design properties: colors used, features, spline type, tile counts, difficulty setting, etc.
- Format may vary between games (no unified export standard yet)
- Card Factory format serves as the baseline for MVP development

## 5. Core Analysis Framework

### 5.0 — Difficulty Bracket System & Adaptive APS Ranges

This is the analytical foundation that underpins all analysis phases. It must be established before any phase-specific analysis is meaningful.

#### Difficulty Brackets

The system recognizes 5 difficulty brackets, each serving a distinct business purpose:

| Bracket | Code | In-Game Label | Core Purpose |
|---------|------|---------------|-------------|
| Easy | E | Easy | Engage players, minimize friction |
| Medium | M | Medium | Create sink moments, drive booster usage |
| Hard | H | Hard | Balance sink & conversion equally |
| Super Hard | SH | VeryHard | Maximize conversion, premium monetization |
| Wall | W | VeryHard | Highest monetization pressure, harder than SH |

SH and W share the same in-game label (VeryHard) but are **always analyzed separately**. W levels represent deliberate paywall moments and carry distinct performance expectations.

#### Bracket Goal Priorities

| Bracket | Priority Order |
|---------|---------------|
| **Easy** | 1. Minimize churn  2. Maximize completion rate |
| **Medium** | 1. Minimize churn  2. Maximize completion rate  3. Begin monetization (boosters, soft currency) |
| **Hard** | Churn, completion rate, and revenue weighted equally |
| **Super Hard** | 1. Minimize churn  2. Maximize completion rate  3. Revenue must be high |
| **Wall** | 1. Maximize revenue  2. Mitigate churn  3. Completion rate |

#### Adaptive APS Range System

The system determines optimal APS ranges per difficulty bracket, per game. This is not hardcoded — it is computed from the data by optimizing against each bracket's goal priorities.

Rules:
- Each bracket occupies a progressively higher APS range (E < M < H < SH < W)
- Ranges must not overlap between brackets
- Gaps between ranges are permitted (varying sizes)
- Ranges are recalculated per game based on that game's data

#### System Insight & Flagging Responsibilities

Beyond setting ranges, the system must actively flag issues:
- Levels whose APS falls outside their bracket's expected range
- Brackets with APS ranges that are too wide or too narrow
- Unbalanced bracket goals (e.g., Hard levels generating revenue but with unacceptable churn)
- Unhealthy APS progression (e.g., Medium levels harder than Hard levels)
- APS climbing too high overall or within a bracket
- Bracket tags that don't match the level's actual performance profile

### 5.1 — Phase 1: Funnel Pacing Analysis

- Visualize the full level funnel (progression curve across all levels)
- Identify pacing deficiencies: where does the difficulty curve behave unexpectedly? (sudden jumps, flat zones, inconsistent ramp)
- Highlight areas where pacing deviates from a smooth/expected curve
- Overlay the Target bracket sequence to show intended cadence vs. actual player experience

### 5.2 — Phase 2: Level Performance Ranking

- Identify best and worst performing levels based on key metrics (win rate, attempts, churn, etc.)
- Sortable/filterable ranking view
- Visual indicators for outliers (levels that stand out significantly from the average)
- Performance evaluated relative to bracket expectations (a "bad" Easy level is different from a "bad" Hard level)

### 5.3 — Phase 3: Drop-off Analysis

- Detect drop-off spikes across the funnel
- Identify drop-off zones (clusters of consecutive levels with elevated churn)
- Visualize drop-off rate per level with clear spike markers
- Correlate drop-offs with difficulty brackets to distinguish expected vs. problematic churn

### 5.4 — Phase 4: Difficulty / Revenue / Churn Correlation

- Correlate difficulty metrics with revenue and churn data
- Identify optimal difficulty values per level bracket
- Flag outlier levels where difficulty deviates from what appears optimal for monetization and retention
- Trend visualization showing how these three dimensions interact
- Leverage the adaptive APS ranges to contextualize whether a level's monetization performance matches its bracket's goals

### 5.5 — Phase 5: Playtime Economics (Onboarding + Core Loop)

This module provides a time-rate view of game health, split into two distinct analysis phases that correspond to different retention periods.

#### Overview

Rather than aggregate stats, this module measures how efficiently the game converts player time into retention and revenue — and separates the onboarding experience from the ongoing core loop. This split is validated against real day-over-day retention data: onboarding metrics predict D1/D3 retention, while core loop metrics predict D14/D30 retention.

#### Playtime Source: Real Playtime

All per-minute calculations use the **Real Playtime** column (`real_playtime`) from the Level Data file. This column represents the total time investment per user per level — including all retry attempts — not just a single-attempt average. It is consistently 1.5–2.0× larger than the per-attempt `playtime` column for difficult levels.

If `real_playtime` is unavailable or empty, the system falls back to `playtime`.

#### Onboarding Phase: L1–L20

The onboarding phase is defined as the first 20 levels. If a `tutorial_max_level` value is detected in the data (explicit tutorial boundary), the cutoff is extended to whichever is larger.

The onboarding phase measures **smoothness**, not per-minute rates. The key question is: does the difficulty ramp up in a controlled, predictable way, or does it spike and scare players off early?

**Onboarding metrics computed:**

| Metric | Description |
|--------|-------------|
| Survival % | Percentage of players who reach the end of the onboarding phase |
| Churn % | Total churn lost during onboarding |
| CV (Coefficient of Variation) | Standard deviation / mean of per-level churn rates — measures how spiky vs. smooth the ramp is |
| Mean churn %/level | Average per-level churn across onboarding levels |
| Worst wall | The single highest-churn level — its level number and churn % |
| Spike count | Number of levels with churn > 2× the mean (abnormal difficulty spikes) |
| First monetization touch | Level number of the first level with any IAP activity |
| Avg sec/level | Average time per onboarding level |
| Per-level churn array | Churn % at each individual level for the sparkline chart |

**Onboarding scores:**

| Score | Metric | Thresholds |
|-------|--------|-----------|
| Survival Score | Onboarding survival % | ≥80% → 95, ≥65% → 80, ≥50% → 65, ≥35% → 50, ≥20% → 35, else → 20 |
| Smoothness Score | CV of per-level churn | ≤0.30 → 95, ≤0.60 → 80, ≤1.00 → 65, ≤1.50 → 50, ≤2.00 → 35, else → 20 |

#### Core Loop Phase: L21+ (2-Hour Observation Window)

The core loop phase begins at L21 (or the level after the onboarding cutoff). Analysis uses a **2-hour / 7,200-second observation window** of cumulative Real Playtime — taking only as many levels as fit within that window. This ensures a consistent time-normalized comparison across games with different level lengths.

Per-minute rates are calculated from this window, enabling direct comparison between games regardless of level count or structure.

**Core loop metrics computed:**

| Metric | Description |
|--------|-------------|
| Churn/min | Average churn % per real-playtime minute within the window |
| Survival % | Players surviving to end of window |
| IAP users %/min | Weighted-average IAP user percentage per level, divided by avg level time in minutes — the primary monetization signal |
| Booster users % | Context-only display field (not used in scoring) |
| EGP users % | Context-only display field (not used in scoring) |
| Rev/min | Weighted-average revenue per user per minute within the window |
| Total rev/cohort user | Total IAP revenue across the window divided by starting user count |
| Total IAP pool | Sum of IAP revenue across the window |
| Monet/churn ratio | IAP %/min ÷ churn %/min — monetization efficiency relative to churn |
| Rev/churn ratio | $/min ÷ churn %/min — revenue efficiency relative to churn |

**Why IAP-only monetization:** Booster and EGP engagement are derivatives of the game economy (soft currency give-aways, temporary difficulty aids) and do not represent direct real-money conversion signals. IAP users % is the clean signal for how many players are spending real money at each level.

**Core loop score thresholds (calibrated for IAP-only values):**

| Metric | Score thresholds |
|--------|-----------------|
| Churn/min (%/min) | ≤0.20→95, ≤0.40→80, ≤0.65→65, ≤0.80→50, ≤1.00→35, else→20 |
| IAP Monet/min (%/min) | ≥0.30→95, ≥0.15→80, ≥0.08→65, ≥0.03→50, ≥0.01→35, else→20 |
| Revenue ($/user/min) | ≥0.030→95, ≥0.010→80, ≥0.003→65, ≥0.001→50, ≥0.0003→35, else→20 |
| Monet/Churn efficiency | ≥0.80→95, ≥0.40→80, ≥0.20→65, ≥0.10→50, ≥0.05→35, else→20 |
| Rev/Churn efficiency | ≥3.0→95, ≥1.0→80, ≥0.3→65, ≥0.1→50, ≥0.03→35, else→20 |

#### Retention Prediction Mapping

Validated against real D1–D30 retention data:

| Playtime Economics Metric | Predicts |
|---------------------------|----------|
| Onboarding survival % | D1 retention |
| Onboarding smoothness (CV) | D1/D3 retention stability |
| Core loop churn/min | D3 → D14 retention slope |
| IAP monet/min | D14 → D30 retention (monetized players are retained players) |
| Rev/cohort user | D30 lifetime value |

#### UI Layout (Dashboard)

The Playtime Economics panel renders as two visual sections:

**Section 1 — Onboarding (blue left border):** Survival score bar, Smoothness score bar, worst wall callout (red if >15% single-level churn, orange if >8%), first monetization touch indicator, per-level churn bar chart (red = spike >2× avg, orange = elevated >1.3× avg, blue = normal).

**Section 2 — Core Loop (purple left border):** Churn/min score bar, IAP Monetization score bar (shows IAP %/min with Booster and EGP % as context), Revenue score bar, Churn/Monet Efficiency ratio bar, Churn/Rev Efficiency ratio bar, radar chart of all core loop scores.

## 6. Output & UI

- All analysis displayed in-app via dashboard panels
- Each analysis phase gets its own view/tab
- Charts selected for maximum readability per data type (line charts for funnels, bar charts for rankings, scatter plots for correlations, etc.)
- Layout: analysis visuals first, then insights/flags below each chart
- No export in MVP — future feature

## 7. Recommendations (Post-MVP, after analysis is verified)

Will be implemented in this order after all analysis phases are functional:

1. **Funnel recommendations** — Optimal level reordering for pacing
2. **Funnel recommendations** — Drop-off zone smoothing suggestions
3. **Funnel recommendations** — Difficulty curve adjustments (slower/faster rise, average difficulty targets)
4. **Level recommendations** — Which levels to fix, which to replicate/modify
5. **Level recommendations** — Best performing mechanics and parameters per element
6. **General recommendations** — Cross-game performance comparison and overall game/funnel health

## 8. Future Features (Not in MVP, infrastructure not ready)

1. **Level Quality Framework (LQF)** — Flag system based on 4 key gameplay metrics (positive/negative flags per level)
2. **Mechanics & properties analysis** — Find best combinations and designs for levels
3. **Image recognition analysis** — Correlate level images on best/worst levels to identify visual patterns
4. **Cross-game intelligence** — Compare games against each other, build knowledge base, assess overall game health
5. **AB Test Analysis** — Decide AB test winners, perform level-based AB test analysis, compare test variants on key metrics

## 9. Reference Documents

- **Data Dictionary & Base Assumptions** — LD_Wizard_DataDictionary_v1.md (column definitions, data types, units, base assumptions, derived metrics)

## 10. Development Rules

- No command is executed without user verification
- Questions about prompts or ambiguity are raised before execution
- All work adheres strictly to this PRD
- Features are built and verified one phase at a time
- Suggestions for deeper level design understanding will be raised during each phase if relevant
