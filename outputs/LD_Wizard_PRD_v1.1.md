# LD Wizard — Product Requirements Document (v1.1)

## Changelog

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
- Contains per-level performance metrics: users, funnel %, APS, IAP, churn, win rate, playtime, boosters, revenue, and more
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
