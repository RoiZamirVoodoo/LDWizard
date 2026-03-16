# LD Wizard — Product Requirements Document (v1.0)

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

The application takes **two files** as input:

### 4.1 Level Data File (Excel - .xlsx)
- Standardized format across all games, provided by the internal data analytics team
- Contains per-level performance metrics: users, funnel %, APS, IAP, churn, win rate, playtime, boosters, revenue, and more
- Includes target vs. achieved difficulty classification per level
- Number of levels varies per game
- See Data Dictionary for full column reference

### 4.2 Level Parameters File (CSV)
- Contains level design properties: colors used, features, spline type, tile counts, difficulty setting, etc.
- Format may vary between games (no unified export standard yet)
- Card Factory format serves as the baseline for MVP development
- See Data Dictionary for full column reference

## 5. MVP Scope — Analysis Features

Development will proceed in phases. Each phase is verified before moving to the next.

### Phase 1 — Funnel Pacing Analysis
- Visualize the full level funnel (progression curve across all levels)
- Identify pacing deficiencies: where does the difficulty curve behave unexpectedly? (sudden jumps, flat zones, inconsistent ramp)
- Highlight areas where pacing deviates from a smooth/expected curve

### Phase 2 — Level Performance Ranking
- Identify best and worst performing levels based on key metrics (win rate, attempts, churn, etc.)
- Sortable/filterable ranking view
- Visual indicators for outliers (levels that stand out significantly from the average)

### Phase 3 — Drop-off Analysis
- Detect drop-off spikes across the funnel
- Identify drop-off zones (clusters of consecutive levels with elevated churn)
- Visualize drop-off rate per level with clear spike markers

### Phase 4 — Difficulty / Revenue / Churn Correlation
- Correlate difficulty metrics with revenue and churn data
- Identify optimal difficulty values per level bracket
- Flag outlier levels where difficulty deviates from what appears optimal for monetization and retention
- Trend visualization showing how these three dimensions interact

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

## 9. Development Rules

- No command is executed without user verification
- Questions about prompts or ambiguity are raised before execution
- All work adheres strictly to this PRD
- Features are built and verified one phase at a time
- Suggestions for deeper level design understanding will be raised during each phase if relevant
