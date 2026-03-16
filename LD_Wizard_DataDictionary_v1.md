# LD Wizard — Data Dictionary & Base Assumptions (v1.0)

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
| H | % IAP Users | Float | Ratio (0–1) | Percentage of users who made an in-app purchase on this level |
| O | % FTD | Float | Ratio (0–1) | Percentage of first-time depositors — users making their very first IAP at this level |
| P | % Repeaters | Float | Ratio (0–1) | Percentage of users who are repeat purchasers at this level |
| R | IAP Revenue | Float | Currency | Revenue generated from in-app purchases at this level |
| S | IAP Transactions | Float | Count | Number of IAP transactions at this level |

#### Economy & Sink Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| K | Coin Balance | Float | Currency (soft) | Average soft currency balance of users at this level |
| T | % Sink Users | Float | Ratio (0–1) | Percentage of users who spent soft currency at this level |
| U | Soft Currency Used | Float | Currency (soft) | Average amount of soft currency spent at this level |

#### Booster & EGP Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| V | Boosters Used | Float | Count | Average number of boosters used at this level |
| W | % Booster Users | Float | Ratio (0–1) | Percentage of users who used at least one booster |
| X | EGPs Used | Float | Count | Average number of End Game Purchases used (e.g., +5 moves after losing). This is typically the most expensive single purchase in the game. |
| Y | % EGP Users | Float | Ratio (0–1) | Percentage of users who used at least one EGP |

#### Playtime Metrics

| Column | Name | Type | Unit | Description |
|--------|------|------|------|-------------|
| Z_ | Playtime | Float | Seconds | Average total playtime spent on this level across all attempts |
| AA_ | Win Playtime | Float | Seconds | Average playtime on winning attempts |
| AB | Lose Playtime | Float | Seconds | Average playtime on losing attempts |
| AC | Real Playtime | — | — | **IGNORED — Do not use in analysis** |

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
| Level Data | Real Playtime | Superseded by Playtime, Win Playtime, Lose Playtime |

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
| Revenue per User | `IAP Revenue / Users` | Normalized revenue for cross-level comparison |
| EGP per User | `EGPs Used / Users` | Normalized EGP usage |
| Booster per User | `Boosters Used / Users` | Normalized booster usage |

> Additional derived metrics will be added as analysis phases are developed.
