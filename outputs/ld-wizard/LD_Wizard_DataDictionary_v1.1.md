# LD Wizard — Data Dictionary & Base Assumptions (v1.1)

## Changelog

- **v1.1** — Real Playtime column moved from IGNORED to active use (primary playtime source for Playtime Economics). Added `real_playtime` mapped column. Updated A11. Added Part 4: Playtime Economics Output Schema — full description of `playtime_economics` computation output including onboarding/core loop split, IAP-only monetization definition, score thresholds, derived calculations, and revenue derivation.
- **v1.0** — Initial Data Dictionary

---

## Part 1: Data Dictionary

### File 1 — Level Data (Excel .xlsx)

This file contains per-level performance metrics from the analytics team. One row per level. Standardized format across all games.

#### Identity & Classification Columns

| Column | Name | Type | Description | Notes |
|--------|------|------|-------------|-------|
| A | Level | Integer | Level number (sequential position in the funnel) | Primary key for joining with Level Parameters |
| B | Target | Category | Prescribed difficulty bracket for funnel pacing | Values: E, M, H, SH, W. Defines the intended player experience cadence. |
| C | Achieved | Category | ~~Measured difficulty from player data~~ | **IGNORED — Do not use in analysis** |
| D | Target (duplicate) | Category | Duplicate of column B | **IGNORED — Do not use in analysis** |

#### Difficulty Bracket Codes

| Code | Full Name | In-Game Label | Purpose |
|------|-----------|---------------|---------|
| E | Easy | Easy | Engage players, fast-paced, interesting splines, minimize friction |
| M | Medium | Medium | Create sink moments, drive booster usage without forcing EGP |
| H | Hard | Hard | Balance sink & conversion, meaningful difficulty driving coin spend and IAP |
| SH | Super Hard | VeryHard | Maximize conversion, premium monetization moments |
| W | Wall (Paywall) | VeryHard | Highest monetization pressure, harder than SH, maximum revenue with churn mitigation |

#### Player Funnel Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| E | Users | Integer | Count | Number of unique users who reached this level |
| F | % Level Funnel | Float | Ratio (0–1) | Retention percentage relative to level 1. Starts at 1.0 for level 1 and declines. Represents what fraction of the original player base reached this level. |

#### Difficulty & Attempt Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| G | APS | Float | Ratio | Attempts Per Success — average number of attempts needed to beat the level (includes booster/EGP-assisted attempts) |
| N | Pure APS | Float | Ratio | Attempts Per Success without booster or EGP usage — clean attempts only. Reflects the raw difficulty of the level without monetization aid. |
| L | Completion Rate | Float | Ratio (0–1) | Percentage of users who started the level and eventually passed it (per-user metric) |
| M | Win Rate | Float | Ratio (0–1) | Percentage of attempts won out of total finished attempts (per-attempt metric) |
| Z | Objectives Left | Float | Count | Average number of objectives remaining when a player loses |
| AA | % Objectives Left | Float | Ratio (0–1) | Percentage of total objectives remaining when a player loses |

#### Churn Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| I | Churn | Float | Ratio (0–1) | Session quit rate — percentage of users who quit the session at this level (not necessarily permanent) |
| J | 3-D Churn | Float | Ratio (0–1) | 3-day churn — users who left at this level and did not return within 3 days |
| Q | 7-D Churn | Float | Ratio (0–1) | 7-day churn — users who left at this level and did not return within 7 days |

#### Monetization Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| H | % IAP Users | Float | Ratio (0–1) | Percentage of users who made an in-app purchase on this level. **Primary monetization signal used in Playtime Economics scoring.** |
| O | % FTD | Float | Ratio (0–1) | Percentage of first-time depositors — users making their very first IAP at this level |
| P | % Repeaters | Float | Ratio (0–1) | Percentage of users who are repeat purchasers at this level |
| R | IAP Revenue | Float | Currency ($) | Revenue generated from in-app purchases at this level |
| S | IAP Transactions | Float | Count | Number of IAP transactions at this level |

#### Economy & Sink Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| K | Coin Balance | Float | Currency (soft) | Average soft currency balance of users at this level |
| T | % Sink Users | Float | Ratio (0–1) | Percentage of users who spent soft currency at this level. **Context-only in Playtime Economics — not used in scoring.** |
| U | Soft Currency Used | Float | Currency (soft) | Average amount of soft currency spent at this level |

#### Booster & EGP Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| V | Boosters Used | Float | Count | Average number of boosters used at this level |
| W | % Booster Users | Float | Ratio (0–1) | Percentage of users who used at least one booster. **Context-only in Playtime Economics — not used in scoring.** |
| X | EGPs Used | Float | Count | Average number of End Game Purchases used (e.g., +5 moves after losing). This is typically the most expensive single purchase in the game. |
| Y | % EGP Users | Float | Ratio (0–1) | Percentage of users who used at least one EGP. **Context-only in Playtime Economics — not used in scoring.** |

#### Playtime Metrics

| Column | Name | Internal Field | Type | Unit | Description |
|--------|------|----------------|------|------|-------------|
| Z_ | Playtime | `playtime` | Float | Seconds | Average per-attempt playtime on this level. Used as fallback if Real Playtime is unavailable. |
| AA_ | Win Playtime | `win_playtime` | Float | Seconds | Average playtime on winning attempts |
| AB | Lose Playtime | `lose_playtime` | Float | Seconds | Average playtime on losing attempts |
| AC | Real Playtime | `real_playtime` | Float | Seconds | **Primary playtime source for Playtime Economics.** Total cumulative time investment per user per level, including all retry attempts. Approximately equal to `playtime / completion_rate` in structure; consistently 1.5–2.0× larger than per-attempt playtime for difficult levels. Represents the true time cost a player pays to complete a level. |

> Note: Column letters above are approximate due to merged header rows in the source Excel. The system should parse by header name, not column position.

---

### File 2 — Level Parameters (CSV)

This file contains level design properties exported from the game. One row per level. Format may vary between games; Card Factory format is the MVP baseline.

| Column | Name | Type | Values | Description |
|--------|------|------|--------|-------------|
| 1 | Level Name | String | e.g., "HitFunnel_V2_Level 1" | Internal level identifier. Used for display, not for joining (use level number extracted from name or row position). |
| 2–10 | Color columns (Red, Blue, Green, Yellow, Orange, Pink, Turquoise, Brown, Purple) | Category | ✓ or - | Whether each tile color is active in this level |
| 11 | Blocker | Category | ✓ or - | Whether blocker elements are present |
| 12–15 | Feature 0, Feature 1, Feature 2, Feature 3 | String | Feature name or - | Up to 4 game mechanics active in the level |
| 16 | Spline 1 | String | Spline identifier | The track/path shape that tiles follow in the level |
| 17 | Deposit Point Count | Integer | 1–5+ | Number of deposit point locations |
| 18 | Deposit Box Count | Integer | 2–30+ | Number of deposit boxes |
| 19 | Queue Count | Integer | 1–3+ | Number of tile queues feeding the level |
| 20 | Color Count | Integer | 2–8 | Total distinct colors used in this level |
| 21 | Total Tile Count | Integer | 12–306 | Total number of tiles in the level |
| 22 | Difficulty | Category | Easy, Medium, Hard, VeryHard | Designer-assigned difficulty label |

#### Known Features (Card Factory)

BlockerTiles, BoxConnector, CardPacks, ColoredLockedDepositPoints, DeckLocks, HiddenBoxes, HiddenTileGroups, HiddenTiles, IceBox, IceQueue, LockAndKey, LockedDepositPoints, OpaqueBox, Teleport, TileChain, TileWall

---

## Part 2: Base Assumptions (Set in Stone)

These assumptions govern how the system interprets and processes data. They are fixed unless explicitly revised.

### A1 — Difficulty Bracket Mapping

The system recognizes 5 internal difficulty brackets mapped to in-game labels:

| Internal Code | In-Game Label | Analysis Group |
|---------------|---------------|----------------|
| E | Easy | Easy |
| M | Medium | Medium |
| H | Hard | Hard |
| SH | VeryHard | Super Hard |
| W | VeryHard | Wall |

**SH and W share the same in-game label (VeryHard) but are always analyzed separately.** W levels represent paywall moments and are expected to be harder than SH with higher monetization metrics.

### A2 — Difficulty Bracket Goals

Each bracket serves a distinct business purpose. These goals drive the adaptive APS range system and all analysis insights.

| Bracket | Primary Goals | Priority Order |
|---------|--------------|----------------|
| **Easy** | Minimize churn, maximize completion rate | 1. Churn 2. Completion Rate |
| **Medium** | Minimize churn, maximize completion rate, begin monetization | 1. Churn 2. Completion Rate 3. Monetization (boosters, soft currency sink) |
| **Hard** | Minimize churn, maximize completion rate, maximize revenue | 1. Churn = Completion Rate = Revenue (equal weight) |
| **Super Hard (SH)** | Minimize churn, maximize completion rate, revenue must be high | 1. Churn 2. Completion Rate 3. Revenue (must be high) |
| **Wall (W)** | Maximum monetization pressure, mitigate churn | 1. Revenue (highest priority) 2. Churn mitigation 3. Completion Rate |

### A3 — Adaptive APS Range System

- The system determines APS ranges **per difficulty bracket, per game** — not hardcoded globally.
- Ranges are optimized against the bracket goals defined in A2.
- Each difficulty bracket must occupy a progressively higher APS range (Easy < Medium < Hard < SH < W).
- **APS ranges must not overlap** between brackets.
- **Gaps between ranges are permitted** and expected (varying sizes as needed).
- The system must flag when:
  - A level's APS falls outside its bracket's expected range
  - A bracket's APS range is too wide or too narrow
  - Goals for a bracket appear unbalanced (e.g., Hard levels have high revenue but unacceptable churn)
  - The overall APS progression is unhealthy (e.g., Medium levels harder than Hard levels)

### A4 — Funnel Direction

- Level 1 is always the start of the funnel.
- The funnel is read left-to-right (level 1 → level N).
- % Level Funnel is always relative to level 1 users (1.0 = 100% of the starting cohort).
- The funnel is expected to decline monotonically, but the rate of decline is what matters for analysis.

### A5 — Churn Definition & Combined Churn Score

The system uses a **Combined Churn Score** as the primary churn metric, weighting all three churn windows:

| Metric | Weight | Reasoning |
|--------|--------|-----------|
| Session Churn | 0.2 (20%) | Weakest signal — players often quit sessions and come back |
| 3-D Churn | 0.5 (50%) | Strongest actionable signal — 3 days without return is the key intervention window |
| 7-D Churn | 0.3 (30%) | Strong signal but partially a subset of 3-D; higher weight would double-count |

**Formula:** `combined_churn = 0.2 × session_churn + 0.5 × churn_3d + 0.3 × churn_7d`

The Combined Churn Score is the **default churn metric used in all analysis, bracket goal evaluation, and flagging**. Individual churn metrics remain available for drill-down.

Additionally, the system computes a **Predicted D14 Churn** by extrapolating the return-rate pattern observed between D3 and D7:
- `daily_factor = (churn_7d / churn_3d) ^ (1/4)` — daily churn retention rate in the D3→D7 window
- `predicted_d14 = churn_7d × daily_factor ^ 7` — project 7 more days from D7 to D14

This provides a forward-looking estimate of long-term player loss per level.

### A6 — Completion Rate vs. Win Rate

- **Completion Rate** = per-user metric: what % of users who started a level eventually passed it.
- **Win Rate** = per-attempt metric: what % of finished attempts were wins.
- Both are important but measure different things. A level with 95% completion rate but 30% win rate means almost everyone beats it eventually, but it takes many tries.

### A7 — APS vs. Pure APS

- **APS** includes all attempts (with boosters, with EGP, clean).
- **Pure APS** includes only clean attempts (no boosters, no EGP).
- The delta between APS and Pure APS indicates how much monetization tools are aiding player progression on a level.

### A8 — EGP Context

- EGP (End Game Purchase) is the most expensive per-use purchase in the game.
- It is triggered after a lost attempt (e.g., "+5 moves" or "add space").
- High EGP usage on a level indicates the level is a significant monetization pressure point.
- EGP usage is expected to correlate with higher difficulty brackets.

### A9 — Level Parameters Variability

- The Level Parameters file format is **game-specific** and may change between games.
- The Card Factory format is the MVP baseline.
- The system should gracefully handle different column structures in future versions.
- The Level Data (Excel) format is **standardized** across all games.

### A10 — Two-File Input Model

- The system always receives exactly two files: Level Data (.xlsx) and Level Parameters (.csv).
- Both files must cover the same set of levels, matched by level number.
- The level count may vary per game (Card Factory demo: 500 levels).

### A11 — Ignored Columns

The following columns are present in the data but excluded from all analysis:

| File | Column | Reason |
|------|--------|--------|
| Level Data | Achieved (col C) | Not used |
| Level Data | Target duplicate (col D) | Duplicate of col B |

> Note: **Real Playtime is no longer ignored** (changed in v1.1). It is now the primary playtime source for the Playtime Economics module. See Part 1 Playtime Metrics table and Part 4 for full details.

---

## Part 3: Derived Metrics (Calculated by the System)

These metrics are not present in the raw data but will be computed during analysis.

| Metric | Formula | Purpose |
|--------|---------|---------|
| Combined Churn | `0.2 × session + 0.5 × D3 + 0.3 × D7` | **Primary churn metric** — weighted score across all churn windows |
| Predicted D14 Churn | `churn_7d × (churn_7d / churn_3d) ^ (7/4)` | Forward-looking churn estimate extrapolated from D3→D7 return rate |
| Drop-off Rate | `(Users[n] - Users[n+1]) / Users[n]` | Level-to-level player loss |
| Funnel Decline Rate | Delta of % Level Funnel between consecutive levels | Speed of funnel decay |
| APS Delta (Booster Impact) | `Pure APS - APS` | How much monetization tools reduce difficulty |
| Difficulty Delta | `APS[n+1] - APS[n]` | Level-to-level difficulty change (pacing signal) |
| Revenue per User (derived) | `IAP Revenue / Users` (per level, when explicit column absent) | Normalized revenue for cross-level comparison |
| EGP per User | `EGPs Used / Users` | Normalized EGP usage |
| Booster per User | `Boosters Used / Users` | Normalized booster usage |
| Churn CV (Onboarding) | `std(per_level_churn) / mean(per_level_churn)` | Onboarding smoothness — lower = smoother ramp |

> Additional derived metrics will be added as analysis phases are developed.

---

## Part 4: Playtime Economics Output Schema

The `playtime_economics` computation (from `_compute_playtime_economics` in `engine/analysis/recommendations.py`) returns a structured object. This schema is authoritative for both backend computation and frontend rendering.

### Top-Level Structure

```
playtime_economics = {
  "available": bool,              # False if insufficient data
  "onboarding_cutoff": int,       # Level number of last onboarding level (default 20)
  "playtime_source": str,         # "real_playtime" or "playtime" (fallback)
  "funnel": { ... },              # Overall funnel summary
  "onboarding": { ... },          # Onboarding phase (L1 to onboarding_cutoff)
  "core_loop": { ... }            # Core loop phase (L(cutoff+1) onward, 2-hr window)
}
```

### `funnel` Block

| Field | Type | Description |
|-------|------|-------------|
| `total_levels` | int | Total levels in the dataset |
| `total_playtime_sec` | float | Sum of real_playtime across all levels |
| `total_playtime_min` | float | Same in minutes |
| `avg_sec_per_level` | float | Mean real_playtime across all levels |

### `onboarding` Block

| Field | Type | Description |
|-------|------|-------------|
| `levels` | int | Number of onboarding levels |
| `last_level` | int | Level number of final onboarding level |
| `survival_pct` | float | % of players who reach the end of onboarding |
| `churn_pct` | float | % of players lost during onboarding |
| `total_sec` | float | Total real_playtime across onboarding levels (sum) |
| `total_min` | float | Same in minutes |
| `avg_sec_per_level` | float | Mean real_playtime per onboarding level |
| `cv_churn` | float | Coefficient of variation of per-level churn rates |
| `mean_churn_pct` | float | Average per-level churn % across onboarding |
| `worst_wall_level` | int | Level number with highest single-level churn |
| `worst_wall_pct` | float | Churn % at that level |
| `spike_count` | int | Number of levels with churn > 2× mean |
| `first_monet_level` | int or null | First level with any IAP activity (null if none) |
| `per_level_churn` | list[float] | Churn % at each individual level (for sparkline) |
| `level_labels` | list[int] | Corresponding level numbers |
| `survival_score` | int | Score 20–95 based on survival % thresholds |
| `smoothness_score` | int | Score 20–95 based on CV thresholds |

### `core_loop` Block

```
core_loop = {
  "available": bool,       # False if not enough levels beyond onboarding
  "reason": str,           # Explanation if unavailable
  "funnel": { ... },
  "churn": { ... },
  "monetization": { ... },
  "revenue": { ... },
  "efficiency": { ... }
}
```

#### `core_loop.funnel`

| Field | Type | Description |
|-------|------|-------------|
| `total_levels` | int | Levels available beyond onboarding |
| `window_levels` | int | Levels within the 2-hour observation window |
| `window_start_level` | int | First level of the core loop (onboarding_cutoff + 1) |
| `total_playtime_min` | float | Total real_playtime across all post-onboarding levels |
| `window_min` | float | Total real_playtime within the 2-hour window |
| `avg_min_per_level` | float | Mean real_playtime (minutes) per level in the window |

#### `core_loop.churn`

| Field | Type | Description |
|-------|------|-------------|
| `churn_per_min` | float | Average churn % per real-playtime minute in the window |
| `survival_pct` | float | % of players surviving to end of window |
| `total_churn_pct` | float | % of players lost across the window |
| `window_min` | float | Duration of the window in minutes |
| `window_level` | int | Level at which the 2-hour window ends |
| `avg_churn_per_level_pct` | float | Average churn % per level within the window |
| `score` | int | Score 20–95 based on churn/min thresholds |

#### `core_loop.monetization`

**Scoring metric:** IAP users %/min only (real-money conversion rate). Booster and EGP are context-only.

| Field | Type | Description |
|-------|------|-------------|
| `iap_users_pct` | float | Playtime-weighted average IAP users % across the window |
| `monet_per_min` | float | IAP users %/min — formula: `(iap_users_pct / avg_level_min_w) × 100` |
| `score` | int | Score 20–95 based on IAP monet/min thresholds |
| `booster_users_pct` | float | Playtime-weighted average % Booster Users — **context display only** |
| `egp_users_pct` | float | Playtime-weighted average % EGP Users — **context display only** |
| `sink_users_pct` | float | Playtime-weighted average % Sink Users — **context display only** |

**Why IAP-only:** Booster and EGP activity are driven by soft-currency economy mechanics (give-aways, discounts) and do not reliably signal real-money conversion intent. IAP users % is the cleanest signal that a player is actively spending real money at a given level.

#### `core_loop.revenue`

| Field | Type | Description |
|-------|------|-------------|
| `rev_per_min` | float | Playtime-weighted average revenue per user per minute across the window. Derived as `(iap_revenue / users) / playtime_min` per level. |
| `total_rev_per_user` | float | Total IAP revenue across the window ÷ users at start of window |
| `total_iap_revenue` | float | Sum of IAP Revenue across the window |
| `score` | int | Score 20–95 based on $/user/min thresholds |

**Revenue derivation note:** If the source data does not include an explicit `revenue_per_user` column, the system derives it as `IAP Revenue / Users` per level at computation time.

#### `core_loop.efficiency`

| Field | Type | Description |
|-------|------|-------------|
| `monet_per_churn` | float | IAP monet/min ÷ churn/min — monetization efficiency per unit of churn |
| `rev_per_churn` | float | Rev/min ÷ churn/min — revenue earned per unit of churn |
| `churn_monet_score` | int or null | Score 20–95 based on monet/churn ratio thresholds |
| `churn_rev_score` | int or null | Score 20–95 based on rev/churn ratio thresholds |

### Score Threshold Reference (All Metrics)

| Metric | 95 | 80 | 65 | 50 | 35 | 20 |
|--------|----|----|----|----|----|----|
| Churn/min (%/min) | ≤0.20 | ≤0.40 | ≤0.65 | ≤0.80 | ≤1.00 | >1.00 |
| IAP Monet/min (%/min) | ≥0.30 | ≥0.15 | ≥0.08 | ≥0.03 | ≥0.01 | <0.01 |
| Revenue ($/user/min) | ≥0.030 | ≥0.010 | ≥0.003 | ≥0.001 | ≥0.0003 | <0.0003 |
| Monet/Churn efficiency | ≥0.80 | ≥0.40 | ≥0.20 | ≥0.10 | ≥0.05 | <0.05 |
| Rev/Churn efficiency | ≥3.0 | ≥1.0 | ≥0.3 | ≥0.1 | ≥0.03 | <0.03 |
| Onboarding Survival % | ≥80% | ≥65% | ≥50% | ≥35% | ≥20% | <20% |
| Smoothness CV | ≤0.30 | ≤0.60 | ≤1.00 | ≤1.50 | ≤2.00 | >2.00 |

### Retention Prediction Mapping

Validated against real D1–D30 day-over-day retention data across multiple games:

| Playtime Economics Metric | Predicts Retention Period |
|---------------------------|--------------------------|
| Onboarding Survival % | D1 retention |
| Onboarding Smoothness (low CV) | D1/D3 retention stability |
| Core Loop Churn/min | D3 → D14 retention slope |
| IAP Monet/min | D14 → D30 retention (monetized players are retained players) |
| Rev/cohort user | D30 lifetime value |
