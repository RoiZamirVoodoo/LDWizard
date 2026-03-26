const dashboardState = {
    lateTrendChart: null,
    loopChart: null,
    drChart: null,
    abFunnelChart: null,
    abBucketSize: 10,
    lateTrendBucketSize: 50,
    drChurnMetric: "d3",
    apsTargetMode: "adaptive",
    manualApsTargets: defaultManualApsTargets(),
};

const MANUAL_APS_FIELD_MAP = {
    easy_min: "easyMin",
    easy_max: "easyMax",
    medium_min: "mediumMin",
    medium_max: "mediumMax",
    hard_min: "hardMin",
    hard_max: "hardMax",
    super_hard_min: "superHardMin",
    super_hard_max: "superHardMax",
    wall_min: "wallMin",
    wall_max: "wallMax",
};

document.addEventListener("DOMContentLoaded", () => {
    if (!document.getElementById("focusDashboard")) {
        return;
    }

    bindDashboardTabs();
    bindRangeControls();
    bindFocusViewControls();
    bindABControls();
    bindExportControls();
    initializeDashboard();
});


function bindRangeControls() {
    const applyBtn = document.getElementById("applyRangeBtn");
    const resetBtn = document.getElementById("resetRangeBtn");
    const startInput = document.getElementById("levelStart");
    const endInput = document.getElementById("levelEnd");
    const loopStartInput = document.getElementById("loopStart");
    const apsTargetMode = document.getElementById("apsTargetMode");
    const trendBucketInput = document.getElementById("lateTrendBucketSizeTop");

    applyBtn?.addEventListener("click", applyLevelRange);
    resetBtn?.addEventListener("click", resetLevelRange);
    apsTargetMode?.addEventListener("change", syncApsTargetModeUI);

    [startInput, endInput, loopStartInput, trendBucketInput].forEach((input) => {
        input?.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                applyLevelRange();
            }
        });
    });

    Object.values(MANUAL_APS_FIELD_MAP).forEach((id) => {
        const input = document.getElementById(id);
        input?.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                applyLevelRange();
            }
        });
    });
}


async function initializeDashboard() {
    setActiveDashboardTab("focus");
    await refreshDashboardData();
}


async function fetchJSON(url, options) {
    const response = await fetch(url, options);
    const payload = await response.json();

    if (!response.ok) {
        throw new Error(payload.error || "Request failed");
    }

    return payload;
}


function setLoading(isLoading) {
    const loadingEl = document.getElementById("dashboardLoading");
    const dashboardEl = document.getElementById("dashboardViews");
    const spinner = document.getElementById("rangeSpinner");

    if (loadingEl) {
        loadingEl.style.display = isLoading ? "flex" : "none";
    }
    if (dashboardEl) {
        dashboardEl.hidden = isLoading;
    }
    if (spinner) {
        spinner.style.display = isLoading ? "inline-flex" : "none";
    }
}


function showError(message) {
    const errorEl = document.getElementById("dashboardError");
    if (!errorEl) {
        return;
    }

    if (!message) {
        errorEl.style.display = "none";
        errorEl.textContent = "";
        return;
    }

    errorEl.textContent = message;
    errorEl.style.display = "block";
}


async function refreshDashboardData() {
    setLoading(true);
    showError("");

    try {
        const sharedParams = buildSharedAnalysisParams();
        const [rangeData, focusData, bracketData, qqfData, abData] = await Promise.all([
            fetchJSON("/api/data/level-range"),
            fetchJSON(`/api/data/focus-dashboard?${sharedParams.toString()}`),
            fetchJSON(`/api/data/bracket-performance?${sharedParams.toString()}`),
            fetchJSON(`/api/data/qqf?${buildQqfParams().toString()}`),
            fetchJSON(`/api/data/ab-test?bucket_size=${dashboardState.abBucketSize}`),
        ]);
        updateRangeUI(rangeData);
        renderFocusDashboard(focusData);
        renderBracketPerformance(bracketData);
        renderQQF(qqfData);
        renderABTest(abData);
        if (focusData.available === false && abData.available) {
            setActiveDashboardTab("ab");
        }
    } catch (error) {
        showError(error.message || "Unable to load dashboard");
    } finally {
        setLoading(false);
    }
}


function bindFocusViewControls() {
    const lateTrendInput = document.getElementById("lateTrendBucketSizeTop");
    const drSelect = document.getElementById("drChurnType");
    const apsTargetMode = document.getElementById("apsTargetMode");

    if (lateTrendInput) {
        lateTrendInput.value = String(dashboardState.lateTrendBucketSize);
        lateTrendInput.addEventListener("keydown", (event) => {
            if (event.key === "Enter") {
                event.preventDefault();
                applyLevelRange();
            }
        });
    }

    if (drSelect) {
        drSelect.value = dashboardState.drChurnMetric;
    }

    if (apsTargetMode) {
        apsTargetMode.value = dashboardState.apsTargetMode;
        syncApsTargetModeUI();
    }
}


function buildSharedAnalysisParams() {
    const params = new URLSearchParams();
    params.set("late_trend_bucket_size", String(dashboardState.lateTrendBucketSize));
    params.set("dr_churn_metric", dashboardState.drChurnMetric);
    params.set("aps_target_mode", dashboardState.apsTargetMode);
    for (const [key, value] of Object.entries(dashboardState.manualApsTargets || {})) {
        if (value !== "" && value != null) {
            params.set(key, String(value));
        }
    }
    return params;
}


function buildQqfParams() {
    const params = buildSharedAnalysisParams();
    params.set("churn_metric", dashboardState.drChurnMetric);
    return params;
}


function defaultManualApsTargets() {
    return {
        easy_min: "",
        easy_max: "",
        medium_min: "",
        medium_max: "",
        hard_min: "",
        hard_max: "",
        super_hard_min: "",
        super_hard_max: "",
        wall_min: "",
        wall_max: "",
    };
}


function readManualApsTargetsFromUI() {
    const next = defaultManualApsTargets();
    Object.entries(MANUAL_APS_FIELD_MAP).forEach(([key, id]) => {
        const input = document.getElementById(id);
        next[key] = input?.value?.trim() || "";
    });
    return next;
}


function writeManualApsTargetsToUI(targets) {
    const values = targets || defaultManualApsTargets();
    Object.entries(MANUAL_APS_FIELD_MAP).forEach(([key, id]) => {
        const input = document.getElementById(id);
        if (input) {
            input.value = values[key] ?? "";
        }
    });
}


function syncApsTargetModeUI() {
    const select = document.getElementById("apsTargetMode");
    const panel = document.getElementById("manualApsTargetsPanel");
    const mode = select?.value || dashboardState.apsTargetMode;
    dashboardState.apsTargetMode = mode;
    if (panel) {
        panel.hidden = mode !== "manual";
    }
}


function bindABControls() {
    const bucketInput = document.getElementById("abBucketSize");
    const applyBtn = document.getElementById("applyAbBucketBtn");
    if (!bucketInput || !applyBtn) {
        return;
    }

    bucketInput.value = String(dashboardState.abBucketSize);
    applyBtn.addEventListener("click", applyABBucketSize);
    bucketInput.addEventListener("keydown", (event) => {
        if (event.key === "Enter") {
            event.preventDefault();
            applyABBucketSize();
        }
    });
}


function bindExportControls() {
    document.getElementById("fullReportBtn")?.addEventListener("click", openFullReport);
    document.getElementById("exportFocusBtn")?.addEventListener("click", () => exportReport("focus"));
    document.getElementById("exportBracketBtn")?.addEventListener("click", () => exportReport("brackets"));
    document.getElementById("exportQqfBtn")?.addEventListener("click", () => exportReport("qqf"));
    document.getElementById("exportAbBtn")?.addEventListener("click", () => exportReport("ab"));
    document.getElementById("visualFocusBtn")?.addEventListener("click", () => openVisualReport("focus"));
    document.getElementById("visualBracketBtn")?.addEventListener("click", () => openVisualReport("brackets"));
    document.getElementById("visualQqfBtn")?.addEventListener("click", () => openVisualReport("qqf"));
    document.getElementById("visualAbBtn")?.addEventListener("click", () => openVisualReport("ab"));
}


async function exportReport(tabName) {
    showError("");
    try {
        const params = new URLSearchParams({ tab: tabName });
        if (tabName === "focus" || tabName === "brackets" || tabName === "qqf") {
            buildSharedAnalysisParams().forEach((value, key) => params.set(key, value));
        }
        if (tabName === "ab") {
            params.set("ab_bucket_size", String(dashboardState.abBucketSize));
        }

        const response = await fetch(`/api/export-report?${params.toString()}`);
        const payload = await response.json();
        if (!response.ok) {
            throw new Error(payload.error || "Unable to export report");
        }

        const blob = new Blob([payload.content || ""], { type: "text/markdown;charset=utf-8" });
        const url = URL.createObjectURL(blob);
        const anchor = document.createElement("a");
        anchor.href = url;
        anchor.download = payload.filename || `ld-wizard-${tabName}-report.md`;
        document.body.appendChild(anchor);
        anchor.click();
        anchor.remove();
        URL.revokeObjectURL(url);
    } catch (error) {
        showError(error.message || "Unable to export report");
    }
}


function openVisualReport(tabName) {
    const params = new URLSearchParams({ tab: tabName });
    if (tabName === "focus" || tabName === "brackets" || tabName === "qqf") {
        buildSharedAnalysisParams().forEach((value, key) => params.set(key, value));
    }
    if (tabName === "ab") {
        params.set("ab_bucket_size", String(dashboardState.abBucketSize));
    }
    window.open(`/report/view?${params.toString()}`, "_blank", "noopener");
}


function openFullReport() {
    const params = buildSharedAnalysisParams();
    window.open(`/report/full?${params.toString()}`, "_blank", "noopener");
}


function applyABBucketSize() {
    const input = document.getElementById("abBucketSize");
    if (!input) {
        return;
    }
    const nextValue = Math.max(1, Math.min(50, Number.parseInt(input.value || "10", 10) || 10));
    dashboardState.abBucketSize = nextValue;
    input.value = String(nextValue);
    refreshDashboardData();
}


function updateRangeUI(data) {
    const startInput = document.getElementById("levelStart");
    const endInput = document.getElementById("levelEnd");
    const loopStartInput = document.getElementById("loopStart");
    const resetBtn = document.getElementById("resetRangeBtn");
    const rangeInfo = document.getElementById("rangeInfo");
    const apsTargetMode = document.getElementById("apsTargetMode");
    const churnSelect = document.getElementById("drChurnType");
    const trendBucketInput = document.getElementById("lateTrendBucketSizeTop");

    if (!startInput || !endInput || !loopStartInput || !resetBtn || !rangeInfo) {
        return;
    }

    const applyBtn = document.getElementById("applyRangeBtn");
    if (!data || data.available === false || data.full_min == null || data.full_max == null) {
        startInput.value = "";
        endInput.value = "";
        loopStartInput.value = "";
        startInput.disabled = true;
        endInput.disabled = true;
        loopStartInput.disabled = true;
        if (applyBtn) {
            applyBtn.disabled = true;
        }
        if (churnSelect) {
            churnSelect.disabled = true;
        }
        if (apsTargetMode) {
            apsTargetMode.disabled = true;
        }
        if (trendBucketInput) {
            trendBucketInput.disabled = true;
        }
        Object.values(MANUAL_APS_FIELD_MAP).forEach((id) => {
            const input = document.getElementById(id);
            if (input) {
                input.disabled = true;
            }
        });
        resetBtn.style.display = "none";
        rangeInfo.textContent = "AB-only mode: upload a Level Data file to use analysis scope controls.";
        return;
    }

    startInput.disabled = false;
    endInput.disabled = false;
    loopStartInput.disabled = false;
    if (applyBtn) {
        applyBtn.disabled = false;
    }
    if (churnSelect) {
        churnSelect.disabled = false;
    }
    if (apsTargetMode) {
        apsTargetMode.disabled = false;
    }
    if (trendBucketInput) {
        trendBucketInput.disabled = false;
    }
    Object.values(MANUAL_APS_FIELD_MAP).forEach((id) => {
        const input = document.getElementById(id);
        if (input) {
            input.disabled = false;
        }
    });

    const fullMin = data.full_min;
    const fullMax = data.full_max;
    const scope = data.analysis_scope || { start: fullMin, end: fullMax, loop_start: null };
    const config = data.analysis_config || {};
    const isCustomScope = scope.start !== fullMin || scope.end !== fullMax || scope.loop_start != null;

    startInput.value = scope.start;
    endInput.value = scope.end;
    loopStartInput.value = scope.loop_start ?? "";
    if (apsTargetMode) {
        apsTargetMode.value = config.aps_target_mode || dashboardState.apsTargetMode;
    }
    dashboardState.apsTargetMode = config.aps_target_mode || dashboardState.apsTargetMode;
    dashboardState.drChurnMetric = config.churn_metric || dashboardState.drChurnMetric;
    dashboardState.lateTrendBucketSize = Number(config.late_trend_bucket_size || dashboardState.lateTrendBucketSize);
    dashboardState.manualApsTargets = { ...defaultManualApsTargets(), ...(config.manual_aps_targets || {}) };
    if (trendBucketInput) {
        trendBucketInput.value = String(dashboardState.lateTrendBucketSize);
    }
    writeManualApsTargetsToUI(dashboardState.manualApsTargets);
    syncApsTargetModeUI();
    resetBtn.style.display = isCustomScope ? "inline-block" : "none";
    rangeInfo.textContent = isCustomScope
        ? `Full data L${fullMin}–L${fullMax}. Analyzing L${scope.start}–L${scope.end}${scope.loop_start != null ? ` · Loop starts L${scope.loop_start}` : ""}`
        : `Full data L${fullMin}–L${fullMax}. Loop start not set.`;
}


async function applyLevelRange() {
    const startInput = document.getElementById("levelStart");
    const endInput = document.getElementById("levelEnd");
    const loopStartInput = document.getElementById("loopStart");
    const trendBucketInput = document.getElementById("lateTrendBucketSizeTop");
    const start = Number(startInput?.value);
    const end = Number(endInput?.value);
    const loopStartRaw = loopStartInput?.value?.trim();
    const loopStart = loopStartRaw ? Number(loopStartRaw) : null;
    const trendBucketSize = Math.max(
        10,
        Math.min(
            100,
            Number.parseInt(trendBucketInput?.value || String(dashboardState.lateTrendBucketSize), 10) || dashboardState.lateTrendBucketSize
        )
    );

    if (Number.isNaN(start) || Number.isNaN(end)) {
        showError("Please enter both a start and end level.");
        return;
    }
    if (start > end) {
        showError("Start level must be less than or equal to end level.");
        return;
    }
    if (loopStartRaw && Number.isNaN(loopStart)) {
        showError("Loop start must be a valid level number.");
        return;
    }

    const churnSelect = document.getElementById("drChurnType");
    const apsTargetMode = document.getElementById("apsTargetMode");
    dashboardState.drChurnMetric = churnSelect?.value || dashboardState.drChurnMetric;
    dashboardState.apsTargetMode = apsTargetMode?.value || dashboardState.apsTargetMode;
    dashboardState.lateTrendBucketSize = trendBucketSize;
    dashboardState.manualApsTargets = readManualApsTargetsFromUI();
    if (trendBucketInput) {
        trendBucketInput.value = String(trendBucketSize);
    }

    setLoading(true);
    showError("");

    try {
        await fetchJSON("/api/reanalyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                start,
                end,
                loop_start: loopStart,
                churn_metric: dashboardState.drChurnMetric,
                late_trend_bucket_size: dashboardState.lateTrendBucketSize,
                aps_target_mode: dashboardState.apsTargetMode,
                manual_aps_targets: dashboardState.manualApsTargets,
            }),
        });

        await refreshDashboardData();
    } catch (error) {
        showError(error.message || "Unable to apply scope");
        setLoading(false);
    }
}


async function applyConfigUpdate(configPayload) {
    const startInput = document.getElementById("levelStart");
    const endInput = document.getElementById("levelEnd");
    const loopStartInput = document.getElementById("loopStart");
    const churnSelect = document.getElementById("drChurnType");
    const apsTargetMode = document.getElementById("apsTargetMode");
    const loopStartRaw = loopStartInput?.value?.trim();
    dashboardState.drChurnMetric = churnSelect?.value || dashboardState.drChurnMetric;
    dashboardState.apsTargetMode = apsTargetMode?.value || dashboardState.apsTargetMode;
    dashboardState.manualApsTargets = readManualApsTargetsFromUI();
    const payload = {
        start: Number(startInput?.value),
        end: Number(endInput?.value),
        loop_start: loopStartRaw ? Number(loopStartRaw) : null,
        churn_metric: dashboardState.drChurnMetric,
        late_trend_bucket_size: dashboardState.lateTrendBucketSize,
        aps_target_mode: dashboardState.apsTargetMode,
        manual_aps_targets: dashboardState.manualApsTargets,
        ...configPayload,
    };

    setLoading(true);
    showError("");
    try {
        await fetchJSON("/api/reanalyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
        });
        await refreshDashboardData();
    } catch (error) {
        showError(error.message || "Unable to apply settings");
        setLoading(false);
    }
}


async function resetLevelRange() {
    setLoading(true);
    showError("");

    try {
        await fetchJSON("/api/reanalyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({}),
        });

        await refreshDashboardData();
    } catch (error) {
        showError(error.message || "Unable to reset scope");
        setLoading(false);
    }
}


function bindDashboardTabs() {
    document.querySelectorAll("[data-dashboard-tab]").forEach((button) => {
        button.addEventListener("click", () => {
            setActiveDashboardTab(button.dataset.dashboardTab);
        });
    });
}


function setActiveDashboardTab(tabName) {
    const focusPanel = document.getElementById("focusDashboard");
    const bracketPanel = document.getElementById("bracketPerformancePanel");
    const qqfPanel = document.getElementById("qqfPanel");
    const abPanel = document.getElementById("abTestPanel");

    document.querySelectorAll("[data-dashboard-tab]").forEach((button) => {
        button.classList.toggle("active", button.dataset.dashboardTab === tabName);
    });

    if (focusPanel) {
        focusPanel.hidden = tabName !== "focus";
    }
    if (bracketPanel) {
        bracketPanel.hidden = tabName !== "brackets";
    }
    if (qqfPanel) {
        qqfPanel.hidden = tabName !== "qqf";
    }
    if (abPanel) {
        abPanel.hidden = tabName !== "ab";
    }
}


function renderFocusDashboard(data) {
    const strategic = data.strategic_views || {};
    const lateTrend = strategic.late_aps_trend || {};
    const diminishingReturns = strategic.diminishing_returns || {};
    const analysisConfig = data.analysis_config || {};

    renderScopeCard(data.scope, data.summary || {}, data.data_quality || {});
    renderTopCard("lateTrend", lateTrend, {
        stable: "Trend stable",
        upward: "Trend rising",
        downward: "Trend falling",
    });
    renderTopCard("loop", strategic.end_game_loop, {
        stable: "Loop stable",
        hardening: "Loop hardening",
        softening: "Loop softening",
    });
    renderTopCard("dr", diminishingReturns, {
        stable: "No sharp break",
        danger: "Returns fading",
    });

    const lateTrendInput = document.getElementById("lateTrendBucketSizeTop");
    if (lateTrendInput && lateTrend.bucket_size) {
        lateTrendInput.value = String(lateTrend.bucket_size);
        dashboardState.lateTrendBucketSize = lateTrend.bucket_size;
    }
    setText("lateTrendBucketNote", lateTrend.bucket_size ? `${lateTrend.bucket_size}-level windows` : "Trend unavailable");

    const churnSelect = document.getElementById("drChurnType");
    const availableChurnMetrics = lateTrend.available_churn_metrics?.length
        ? lateTrend.available_churn_metrics
        : diminishingReturns.available_churn_metrics;
    const selectedChurnMetric = lateTrend.churn_metric || diminishingReturns.churn_metric || dashboardState.drChurnMetric;
    const selectedChurnLabel = lateTrend.churn_label || diminishingReturns.churn_label || "Churn unavailable";
    if (churnSelect && availableChurnMetrics?.length) {
        churnSelect.innerHTML = availableChurnMetrics.map((item) => `
            <option value="${escapeHtml(item.key)}"${item.key === selectedChurnMetric ? " selected" : ""}>${escapeHtml(item.label)}</option>
        `).join("");
        dashboardState.drChurnMetric = selectedChurnMetric;
    }
    setText("drChurnNote", selectedChurnLabel);
    dashboardState.apsTargetMode = analysisConfig.aps_target_mode || dashboardState.apsTargetMode;
    dashboardState.manualApsTargets = { ...defaultManualApsTargets(), ...(analysisConfig.manual_aps_targets || {}) };
    writeManualApsTargetsToUI(dashboardState.manualApsTargets);
    const apsModeSelect = document.getElementById("apsTargetMode");
    if (apsModeSelect) {
        apsModeSelect.value = dashboardState.apsTargetMode;
    }
    syncApsTargetModeUI();
    setText(
        "apsTargetNote",
        dashboardState.apsTargetMode === "manual" ? "Manual APS targets" : "Adaptive APS targets"
    );

    renderLateTrend(lateTrend);
    renderEndGameLoop(strategic.end_game_loop || {});
    renderDiminishingReturns(diminishingReturns);
}


function renderBracketPerformance(data) {
    if (!data || !data.available) {
        setText("strongestBracketValue", "--");
        setText("strongestBracketCopy", data?.reason || "Bracket performance is unavailable.");
        setText("weakestBracketValue", "--");
        setText("weakestBracketCopy", "");
        setText("bracketOutlierValue", "--");
        setText("bracketOutlierCopy", "");
        setText("tagAccuracyValue", "--");
        setText("tagAccuracyCopy", "");
        setHTML("bracketInsights", emptyState(data?.reason || "Bracket performance is unavailable."));
        setHTML("difficultyTagBands", "");
        setHTML("difficultyTagAccuracy", "");
        setHTML("bracketCards", "");
        return;
    }

    const overview = data.overview || {};
    const tagAccuracy = data.tag_accuracy || {};
    setText("strongestBracketValue", overview.strongest_bracket || "--");
    setText(
        "strongestBracketCopy",
        overview.strongest_score != null
            ? `Average business score ${overview.strongest_score.toFixed(3)}`
            : "No ranking data"
    );
    setText("weakestBracketValue", overview.weakest_bracket || "--");
    setText(
        "weakestBracketCopy",
        overview.weakest_score != null
            ? `Average business score ${overview.weakest_score.toFixed(3)}`
            : "No ranking data"
    );
    setText("bracketOutlierValue", String(overview.outlier_count ?? "--"));
    setText(
        "bracketOutlierCopy",
        `${overview.overperformer_count || 0} overperformers · ${overview.underperformer_count || 0} underperformers`
    );
    setText(
        "tagAccuracyValue",
        overview.tag_accuracy_pct != null ? `${overview.tag_accuracy_pct.toFixed(1)}%` : "--"
    );
    setText(
        "tagAccuracyCopy",
        overview.tag_accuracy_pct != null
            ? `${overview.aligned_level_count || 0}/${overview.scored_level_count || 0} levels match their APS band${overview.worst_target_bracket ? ` · weakest tag ${overview.worst_target_bracket}${overview.worst_target_accuracy_pct != null ? ` (${overview.worst_target_accuracy_pct.toFixed(1)}%)` : ""}` : ""}`
            : tagAccuracy.reason || "No tag accuracy data"
    );

    setHTML(
        "bracketInsights",
        data.insights?.length
            ? data.insights.map((item) => itemCard("Insight", item, [], false)).join("")
            : emptyState("No bracket-level insights were generated.")
    );
    setHTML(
        "difficultyTagBands",
        tagAccuracy.available && tagAccuracy.bands?.length
            ? [
                pill(`Scoped APS ${tagAccuracy.aps_range_label || "unknown"}`),
                pill(tagAccuracy.band_method === "manual" ? "Manual APS targets" : tagAccuracy.band_method === "adaptive_log" ? "Adaptive log APS bands" : "APS bands"),
                ...tagAccuracy.bands.map((band) => pill(`${band.bracket} ${band.label}`)),
            ].join("")
            : ""
    );
    setHTML(
        "difficultyTagAccuracy",
        tagAccuracy.available && tagAccuracy.targets?.length
            ? tagAccuracy.targets.map((target) => renderTagAccuracyCard(target)).join("")
            : emptyState(tagAccuracy.reason || "No difficulty tag accuracy data was generated.")
    );

    setHTML(
        "bracketCards",
        data.brackets?.length
            ? data.brackets.map((bracket) => renderBracketCard(bracket)).join("")
            : emptyState("Peer ranking data is unavailable for the current scope.")
    );
}


function renderQQF(data) {
    if (!data || !data.available) {
        setText("qqfStarsValue", "--");
        setText("qqfStarsCopy", data?.reason || "QQF is unavailable.");
        setText("qqfStableValue", "--");
        setText("qqfStableCopy", "");
        setText("qqfWatchValue", "--");
        setText("qqfWatchCopy", "");
        setText("qqfKillzoneValue", "--");
        setText("qqfKillzoneCopy", "");
        setText("qqfHeadline", data?.reason || "QQF is unavailable.");
        setHTML("qqfMeta", "");
        setHTML("qqfTierCards", emptyState(data?.reason || "QQF is unavailable."));
        setHTML("qqfTopStars", "");
        setHTML("qqfTopKillzones", "");
        setHTML("qqfWatchlist", "");
        return;
    }

    const overview = data.overview || {};
    setText("qqfStarsValue", String(overview.star_count ?? "--"));
    setText("qqfStarsCopy", "Best study levels inside their target tags.");
    setText("qqfStableValue", String(overview.stable_count ?? "--"));
    setText("qqfStableCopy", "Healthy levels without major correction signals.");
    setText("qqfWatchValue", String(overview.watch_count ?? "--"));
    setText("qqfWatchCopy", "Needs attention before it drifts into killzone.");
    setText("qqfKillzoneValue", String(overview.killzone_count ?? "--"));
    setText("qqfKillzoneCopy", "Highest-priority fix candidates.");
    setText("qqfHeadline", data.headline || "QQF ready.");
    setHTML(
        "qqfMeta",
        [
            pill(data.churn_label || "Churn n/a"),
            pill(data.aps_target_mode === "manual" ? "Manual APS targets" : "Adaptive APS targets"),
            pill(`APS aligned ${overview.aps_alignment_pct != null ? `${overview.aps_alignment_pct.toFixed(1)}%` : "n/a"}`),
            ...(data.bands || []).map((band) => pill(`${band.bracket} ${band.label}`)),
        ].join("")
    );
    setHTML(
        "qqfTierCards",
        data.tiers?.length
            ? data.tiers.map((tier) => renderQqfTierCard(tier)).join("")
            : emptyState("No QQF tier summaries are available.")
    );
    setHTML(
        "qqfTopStars",
        data.top_stars?.length
            ? data.top_stars.map((item) => renderQqfLevel(item, "success")).join("")
            : emptyState("No star levels were identified in the current scope.")
    );
    setHTML(
        "qqfTopKillzones",
        data.top_killzones?.length
            ? data.top_killzones.map((item) => renderQqfLevel(item, "danger")).join("")
            : emptyState("No killzone levels were identified in the current scope.")
    );
    setHTML(
        "qqfWatchlist",
        data.watchlist?.length
            ? data.watchlist.map((item) => renderQqfLevel(item, item.qqf_status === "Killzone" ? "danger" : "warning")).join("")
            : emptyState("No watchlist levels were identified in the current scope.")
    );
}


function renderABTest(data) {
    if (!data || !data.available) {
        setText("abWinnerValue", "--");
        setText("abWinnerCopy", data?.reason || "No AB workbook loaded.");
        setText("abRecommendationValue", "--");
        setText("abRecommendationCopy", "Upload an AB workbook to compare cohorts.");
        setText("abRevenueDeltaValue", "--");
        setText("abRevenueDeltaCopy", "");
        setText("abChurnDeltaValue", "--");
        setText("abChurnDeltaCopy", "");
        setText("abBucketScopeNote", "No AB workbook loaded");
        setHTML("abFindings", emptyState(data?.reason || "No AB workbook loaded."));
        setHTML("abMetricSummary", "");
        setHTML("abBucketMetrics", "");
        setHTML("abBracketCards", "");
        setHTML("abPositiveLevels", "");
        setHTML("abNegativeLevels", "");
        destroyChart("abFunnelChart");
        return;
    }

    const summary = data.summary || {};
    const deltas = summary.deltas || {};
    const winnerLabel = summary.winner === "variant" ? data.variant_label : summary.winner === "control" ? data.control_label : "Mixed";

    setText("abWinnerValue", winnerLabel || "--");
    setText("abWinnerCopy", data.headline || "AB result ready.");
    setText("abRecommendationValue", data.recommendation || "--");
    setText("abRecommendationCopy", `${data.control_label || "Control"} vs ${data.variant_label || "Variant"}`);
    setText("abRevenueDeltaValue", deltas.revenue_per_k_starters_pct != null ? `${deltas.revenue_per_k_starters_pct >= 0 ? "+" : ""}${deltas.revenue_per_k_starters_pct.toFixed(1)}%` : "--");
    setText("abRevenueDeltaCopy", `${data.variant_label} vs ${data.control_label} on revenue per 1k starters`);
    setText("abChurnDeltaValue", deltas.d3_churn_pp != null ? `${deltas.d3_churn_pp >= 0 ? "+" : ""}${deltas.d3_churn_pp.toFixed(2)} pp` : "--");
    setText("abChurnDeltaCopy", `${data.variant_label} vs ${data.control_label} on weighted D3 churn`);
    setText("abBucketScopeNote", `${data.bucket_size || dashboardState.abBucketSize}-level buckets`);
    const bucketInput = document.getElementById("abBucketSize");
    if (bucketInput && data.bucket_size) {
        bucketInput.value = String(data.bucket_size);
    }

    setHTML(
        "abFindings",
        data.findings?.length
            ? data.findings.map((item) => itemCard(item.title, item.detail, [], false)).join("")
            : emptyState("No AB findings were generated.")
    );
    setHTML("abMetricSummary", renderABMetricSummary(data));
    setHTML("abBucketMetrics", renderABBucketMetrics(data));

    setHTML(
        "abBracketCards",
        data.bracket_breakdown?.length
            ? data.bracket_breakdown.map((item) => renderABBracketCard(item)).join("")
            : emptyState("No bracket breakdown is available for this experiment workbook.")
    );

    setHTML(
        "abPositiveLevels",
        data.top_positive_levels?.length
            ? data.top_positive_levels.map((item) => renderABLevelSwing(item, data.variant_label, "success")).join("")
            : emptyState("No strong positive variant levels were detected.")
    );
    setHTML(
        "abNegativeLevels",
        data.top_negative_levels?.length
            ? data.top_negative_levels.map((item) => renderABLevelSwing(item, data.variant_label, "danger")).join("")
            : emptyState("No strong negative variant levels were detected.")
    );

    renderABFunnelChart(data);
}


function renderABBracketCard(item) {
    return `
        <article class="focus-panel focus-bracket-card">
            <div class="focus-item-header">
                <div>
                    <h3>${escapeHtml(item.bracket)}</h3>
                    <p class="focus-item-copy">Revenue / 1k users ${formatMaybe(item.control_revenue_per_k_users, 1)} vs ${formatMaybe(item.variant_revenue_per_k_users, 1)} · D3 churn ${formatMaybe(item.control_d3_churn_pct, 2, "%")} vs ${formatMaybe(item.variant_d3_churn_pct, 2, "%")}</p>
                </div>
                <div class="focus-pill-row">
                    ${pill(item.winner_label || "Mixed", item.winner === "variant" ? "success" : item.winner === "control" ? "danger" : "warning")}
                    ${pill(`${item.level_count} levels`)}
                </div>
            </div>
            <div class="focus-list focus-list-compact">
                ${itemCard("Revenue delta", `${item.delta_revenue_pct >= 0 ? "+" : ""}${item.delta_revenue_pct.toFixed(1)}% variant lift vs control`, [], true)}
                ${itemCard("D3 churn delta", `${item.delta_d3_churn_pp >= 0 ? "+" : ""}${item.delta_d3_churn_pp.toFixed(2)} pp`, [], true)}
            </div>
        </article>
    `;
}


function renderABMetricSummary(data) {
    if (!data.metric_summary?.length) {
        return emptyState("No key metric summary is available for this experiment workbook.");
    }

    return `
        <div class="focus-table-wrap">
            <table class="table focus-table">
                <thead>
                    <tr>
                        <th>Metric</th>
                        <th>${escapeHtml(data.control_label)} Avg</th>
                        <th>${escapeHtml(data.control_label)} Median</th>
                        <th>${escapeHtml(data.variant_label)} Avg</th>
                        <th>${escapeHtml(data.variant_label)} Median</th>
                        <th>Avg Delta</th>
                        <th>Median Delta</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.metric_summary.map((row) => `
                        <tr>
                            <td>${escapeHtml(row.label)}</td>
                            <td>${formatABMetric(row.control_avg, row.type)}</td>
                            <td>${formatABMetric(row.control_median, row.type)}</td>
                            <td>${formatABMetric(row.variant_avg, row.type)}</td>
                            <td>${formatABMetric(row.variant_median, row.type)}</td>
                            <td>${formatABDelta(row.avg_delta, row.type)}</td>
                            <td>${formatABDelta(row.median_delta, row.type)}</td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
}


function renderABBucketMetrics(data) {
    if (!data.bucket_metrics?.length) {
        return emptyState("No bucketed AB metrics are available.");
    }

    return `
        <div class="focus-table-wrap">
            <table class="table focus-table">
                <thead>
                    <tr>
                        <th>Range</th>
                        <th>Levels</th>
                        <th>D3 Churn</th>
                        <th>% IAP Users</th>
                        <th>IAP Revenue</th>
                        <th>FTD</th>
                    </tr>
                </thead>
                <tbody>
                    ${data.bucket_metrics.map((row) => `
                        <tr>
                            <td>${escapeHtml(row.label)}</td>
                            <td>${row.level_count}</td>
                            <td>${formatABPair(row.churn_3d, data.control_label, data.variant_label)}</td>
                            <td>${formatABPair(row.iap_users_pct, data.control_label, data.variant_label)}</td>
                            <td>${formatABPair(row.iap_revenue, data.control_label, data.variant_label)}</td>
                            <td>${formatABPair(row.ftd_pct, data.control_label, data.variant_label)}</td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
}


function renderABLevelSwing(item, variantLabel, tone) {
    const details = [
        item.revenue_delta_per_k_users != null ? `Rev / 1k ${item.revenue_delta_per_k_users >= 0 ? "+" : ""}${item.revenue_delta_per_k_users.toFixed(1)}` : null,
        item.revenue_delta_pct != null ? `(${item.revenue_delta_pct >= 0 ? "+" : ""}${item.revenue_delta_pct.toFixed(1)}%)` : null,
        item.churn_delta_pp != null ? `D3 ${item.churn_delta_pp >= 0 ? "+" : ""}${item.churn_delta_pp.toFixed(2)} pp` : null,
        item.funnel_delta_pp != null ? `Funnel ${item.funnel_delta_pp >= 0 ? "+" : ""}${item.funnel_delta_pp.toFixed(2)} pp` : null,
    ].filter(Boolean).join(" · ");

    return itemCard(
        `L${item.level}${item.bracket ? ` · ${item.bracket}` : ""}`,
        `${details}${details ? " · " : ""}${variantLabel} ${item.balanced_delta >= 0 ? "helps" : "hurts"} here on a balanced score.`,
        [
            pill(item.balanced_delta >= 0 ? "Variant up" : "Variant down", tone),
            pill(`Score ${item.balanced_delta.toFixed(2)}`),
        ],
        true
    );
}


function formatABMetric(value, type) {
    if (value == null) {
        return "—";
    }
    if (type === "pct") {
        return `${Number(value).toFixed(2)}%`;
    }
    if (type === "currency") {
        return Number(value).toFixed(1);
    }
    return Number(value).toFixed(2);
}


function formatABDelta(value, type) {
    if (value == null) {
        return "—";
    }
    const number = Number(value);
    if (type === "pct") {
        return `${number >= 0 ? "+" : ""}${number.toFixed(2)} pp`;
    }
    return `${number >= 0 ? "+" : ""}${number.toFixed(1)}`;
}


function formatABPair(metric, controlLabel, variantLabel) {
    if (!metric) {
        return "—";
    }
    return `${escapeHtml(controlLabel)} ${formatABMetric(metric.control_avg, metric.type)} / ${formatABMetric(metric.control_median, metric.type)} · ${escapeHtml(variantLabel)} ${formatABMetric(metric.variant_avg, metric.type)} / ${formatABMetric(metric.variant_median, metric.type)}`;
}


function renderABFunnelChart(data) {
    const canvas = document.getElementById("abFunnelChart");
    if (!canvas || typeof Chart === "undefined") {
        return;
    }

    destroyChart("abFunnelChart");

    dashboardState.abFunnelChart = new Chart(canvas, {
        type: "line",
        data: {
            labels: data.funnel_curve.map((item) => item.label || `L${item.level}`),
            datasets: [
                {
                    label: `${data.control_label} funnel %`,
                    data: data.funnel_curve.map((item) => item.control_funnel_pct),
                    borderColor: "#8A8F98",
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.18,
                    yAxisID: "y",
                },
                {
                    label: `${data.variant_label} funnel %`,
                    data: data.funnel_curve.map((item) => item.variant_funnel_pct),
                    borderColor: "#2E6F95",
                    backgroundColor: "rgba(46, 111, 149, 0.10)",
                    fill: false,
                    borderWidth: 2,
                    pointRadius: 0,
                    tension: 0.18,
                    yAxisID: "y",
                },
                {
                    label: `${data.control_label} D3 churn %`,
                    data: data.funnel_curve.map((item) => item.control_d3_churn_pct),
                    borderColor: "#D8A24A",
                    borderDash: [5, 5],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.18,
                    yAxisID: "y1",
                },
                {
                    label: `${data.variant_label} D3 churn %`,
                    data: data.funnel_curve.map((item) => item.variant_d3_churn_pct),
                    borderColor: "#D45B5B",
                    borderDash: [5, 5],
                    borderWidth: 1.5,
                    pointRadius: 0,
                    tension: 0.18,
                    yAxisID: "y1",
                },
            ],
        },
        options: {
            ...baseLineChartOptions("Funnel %"),
            scales: {
                x: {
                    grid: { display: false },
                    ticks: { maxTicksLimit: 16 },
                },
                y: {
                    title: { display: true, text: "Funnel %" },
                    beginAtZero: true,
                },
                y1: {
                    position: "right",
                    title: { display: true, text: "D3 churn %" },
                    beginAtZero: true,
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });
}


function renderScopeCard(scope, summary, quality) {
    if (!scope) {
        setText("scopeGrade", "AB");
        setText("scopeScore", "AB Test Mode");
        setText("scopeHeadline", "This session only has an experiment workbook loaded.");
        setText("scopeDetail", quality.maturity_detail || "Upload a Level Data file to unlock the core dashboard analyses.");
        setHTML("summaryMeta", [
            pill("No Level Data", "warning"),
            pill("AB-only mode"),
        ].join(""));
        return;
    }

    setText("scopeGrade", String(summary.total_levels || "--"));
    setText("scopeScore", scope.analysis_range_label || "Analysis range");
    setText("scopeHeadline", "The app now distinguishes full range, active analysis range, and loop range.");
    setText(
        "scopeDetail",
        quality.has_immature_data
            ? quality.maturity_detail || "Some churn windows are still immature."
            : [quality.loop_scope_note, quality.params_note].filter(Boolean).join(" ")
    );
    setHTML("summaryMeta", [
        pill(`Full ${scope.full_range_label || "unknown"}`),
        pill(`Analyze ${scope.analysis_range_label || "unknown"}`),
        pill(`Loop ${scope.loop_start_label || "Not set"}`),
        pill(summary.avg_aps != null ? `Avg APS ${summary.avg_aps.toFixed(3)}` : "APS unavailable"),
        pill(summary.avg_completion_pct != null ? `Completion ${summary.avg_completion_pct.toFixed(1)}%` : "Completion unavailable"),
    ].join(""));
}


function renderTopCard(prefix, view, verdictLabels) {
    const titleId = `${prefix}Title`;
    const copyId = `${prefix}Copy`;
    const metaId = `${prefix}Meta`;

    if (!view || !view.available) {
        setText(titleId, "Not available in current scope");
        setText(copyId, view?.reason || "This view needs a different analysis scope.");
        setHTML(metaId, pill("Unavailable", "warning"));
        return;
    }

    const verdict = verdictLabels?.[view.verdict] || (view.verdict ? capitalize(view.verdict) : "Ready");
    setText(titleId, verdict);
    setText(copyId, view.headline || "Analysis ready.");

    const meta = [pill(verdict, toneForVerdict(view.verdict))];
    if (view.bucket_size) {
        meta.push(pill(`${view.bucket_size}-level windows`));
    }
    if (view.target_band) {
        meta.push(pill(`Target APS ${view.target_band.min.toFixed(1)}–${view.target_band.max.toFixed(1)}`));
        if (view.target_band.source === "optimized") {
            const optimizationSize = view.target_band.window_size || 10;
            meta.push(pill(`Optimized from ${optimizationSize}-level windows`));
            meta.push(pill(`${view.target_band.window_count} brackets used`));
            if (view.target_band.method === "weighted_revenue_churn") {
                meta.push(pill("Revenue/churn weighted"));
            }
        }
    }
    if (view.metric_tag) {
        meta.push(pill(view.metric_tag));
    } else if (view.metric_note) {
        meta.push(pill("D3 vs IAP composite"));
    }
    setHTML(metaId, meta.join(""));
}


function renderBracketCard(bracket) {
    const topLevels = bracket.top_levels?.length
        ? bracket.top_levels.map((level) => renderBracketLevel(level, "Top performer", "success")).join("")
        : emptyState("No strong performers found.");
    const bottomLevels = bracket.bottom_levels?.length
        ? bracket.bottom_levels.map((level) => renderBracketLevel(level, "Needs attention", "danger")).join("")
        : emptyState("No weak performers found.");

    return `
        <article class="focus-panel focus-bracket-card">
            <div class="focus-item-header">
                <div>
                    <h3>${escapeHtml(bracket.bracket)}</h3>
                    <p class="focus-item-copy">Business ${formatMaybe(bracket.avg_business_score, 3)} · Avg APS ${formatMaybe(bracket.avg_aps, 2)} · Revenue / 1k ${formatMaybe(bracket.avg_revenue_per_k_users, 1)} · Churn ${formatMaybe(bracket.avg_combined_churn_pct, 2, "%")}</p>
                </div>
                <div class="focus-pill-row">
                    ${pill(`${bracket.level_count} levels`)}
                    ${pill(bracket.avg_iap_users_pct != null ? `Payers ${bracket.avg_iap_users_pct.toFixed(2)}%` : "Payers n/a")}
                    ${pill(`${bracket.outlier_count || 0} outliers`, (bracket.outlier_count || 0) > 0 ? "warning" : "default")}
                </div>
            </div>
            <div class="focus-split focus-split-tight">
                <div>
                    <div class="focus-panel-title">Top Levels</div>
                    <div class="focus-list focus-list-compact">${topLevels}</div>
                </div>
                <div>
                    <div class="focus-panel-title">Bottom Levels</div>
                    <div class="focus-list focus-list-compact">${bottomLevels}</div>
                </div>
            </div>
        </article>
    `;
}


function renderTagAccuracyCard(target) {
    const mismatchExamples = target.mismatch_examples?.length
        ? target.mismatch_examples.map((item) => renderTagMismatch(item, target.target_bracket, target.target_band_label)).join("")
        : emptyState("All scoped levels with this target tag land inside the expected APS band.");
    const dominantActual = target.dominant_actual_bracket
        ? `${target.target_bracket} levels most often behave like ${target.dominant_actual_bracket}.`
        : "No dominant APS behavior found.";
    const tone = target.match_pct >= 70 ? "success" : target.match_pct >= 45 ? "warning" : "danger";

    return `
        <article class="focus-panel focus-bracket-card">
            <div class="focus-item-header">
                <div>
                    <h3>${escapeHtml(target.target_bracket)}</h3>
                    <p class="focus-item-copy">Target APS band ${escapeHtml(target.target_band_label)} · ${target.match_count}/${target.total_count} aligned</p>
                </div>
                <div class="focus-pill-row">
                    ${pill(`${target.match_pct.toFixed(1)}% accurate`, tone)}
                    ${pill(`${target.mismatch_count} mismatches`, target.mismatch_count > 0 ? "warning" : "default")}
                </div>
            </div>
            <p class="focus-item-copy">${escapeHtml(dominantActual)}</p>
            <div class="focus-pill-row mb-2">
                ${(target.distribution || []).map((item) => pill(`${item.bracket} ${item.count}`)).join("")}
            </div>
            <div class="focus-panel-title">Mismatch Examples</div>
            <div class="focus-list focus-list-compact">${mismatchExamples}</div>
        </article>
    `;
}


function renderQqfTierCard(tier) {
    return `
        <article class="focus-panel focus-bracket-card">
            <div class="focus-item-header">
                <div>
                    <h3>${escapeHtml(tier.bracket)}</h3>
                    <p class="focus-item-copy">Avg QQF ${formatMaybe(tier.avg_score, 2)} · APS target ${escapeHtml(tier.band_label)} · APS aligned ${formatMaybe(tier.aps_alignment_pct, 1, "%")}</p>
                </div>
                <div class="focus-pill-row">
                    ${pill(`${tier.level_count} levels`)}
                    ${pill(`Stars ${tier.status_counts?.Star || 0}`, "success")}
                    ${pill(`Killzones ${tier.status_counts?.Killzone || 0}`, (tier.status_counts?.Killzone || 0) > 0 ? "danger" : "default")}
                </div>
            </div>
            <div class="focus-split focus-split-tight">
                <div>
                    <div class="focus-panel-title">Top Levels</div>
                    <div class="focus-list focus-list-compact">
                        ${(tier.top_levels || []).length
                            ? tier.top_levels.map((item) => renderQqfLevel(item, "success")).join("")
                            : emptyState("No star-side levels in this target tag.")}
                    </div>
                </div>
                <div>
                    <div class="focus-panel-title">Fragile Levels</div>
                    <div class="focus-list focus-list-compact">
                        ${(tier.bottom_levels || []).length
                            ? tier.bottom_levels.map((item) => renderQqfLevel(item, item.qqf_status === "Killzone" ? "danger" : "warning")).join("")
                            : emptyState("No fragile levels in this target tag.")}
                    </div>
                </div>
            </div>
        </article>
    `;
}


function renderQqfLevel(item, tone) {
    const summary = [
        item.target_bracket ? `Target ${item.target_bracket}` : null,
        item.aps != null ? `APS ${item.aps.toFixed(2)}` : null,
        item.completion_pct != null ? `Completion ${item.completion_pct.toFixed(1)}%` : null,
        item.churn_pct != null ? `Churn ${item.churn_pct.toFixed(2)}%` : null,
        item.payer_pct != null ? `Payers ${item.payer_pct.toFixed(2)}%` : null,
    ].filter(Boolean).join(" · ");

    return itemCard(
        `L${item.level}`,
        `${summary}${summary ? " · " : ""}${item.reason || "No QQF explanation available."}`,
        [
            pill(item.qqf_status || "QQF", tone),
            pill(`Score ${Number(item.qqf_score || 0).toFixed(2)}`),
        ],
        true
    );
}


function renderBracketLevel(level, badge, tone) {
    const summary = [
        level.aps != null ? `APS ${level.aps.toFixed(2)}` : null,
        level.revenue_per_k_users != null ? `Revenue / 1k ${level.revenue_per_k_users.toFixed(1)}` : null,
        level.iap_users_pct != null ? `Payers ${level.iap_users_pct.toFixed(2)}%` : null,
        level.combined_churn_pct != null ? `Churn ${level.combined_churn_pct.toFixed(2)}%` : null,
        level.target_bracket ? `Target ${level.target_bracket}` : null,
    ].filter(Boolean).join(" · ");

    return itemCard(
        `L${level.level}`,
        `${summary}${summary ? " · " : ""}${level.reason}`,
        [
            pill(badge, tone),
            pill(`Score ${level.perf_score.toFixed(3)}`),
        ],
        true
    );
}


function renderTagMismatch(item, targetBracket, targetBandLabel) {
    return itemCard(
        `L${item.level}`,
        `APS ${item.aps.toFixed(2)} behaves like ${item.actual_bracket}, outside the ${targetBracket} band ${targetBandLabel}.`,
        [
            pill(`${capitalize(item.direction)} than tag`, item.direction === "harder" ? "danger" : "warning"),
            pill(`Actual ${item.actual_band_label}`),
        ],
        true
    );
}


function renderLateTrend(view) {
    const issuesEl = document.getElementById("lateTrendIssues");
    const bucketsEl = document.getElementById("lateTrendBuckets");

    if (!view.available) {
        renderUnavailableSection("lateTrendChart", issuesEl, bucketsEl, view.reason);
        return;
    }

    renderLateTrendChart(view);

    issuesEl.innerHTML = view.weak_ranges?.length
        ? view.weak_ranges.map((item) => itemCard(item.range_label, item.reason, [
            pill(item.severity === "high" ? "High" : "Medium", toneForVerdict(item.severity)),
        ], true)).join("")
        : emptyState("No APS slumps or oversized drops were found in the scoped late-game range.");

    const churnLabel = view.churn_label || "Churn";
    bucketsEl.innerHTML = view.buckets.slice(0, 6).map((bucket) => itemCard(
        bucket.range_label,
        `Avg APS ${bucket.avg_aps.toFixed(2)} · ${churnLabel} ${bucket.avg_churn_pct.toFixed(2)}% · IAP composite ${bucket.iap_composite.toFixed(3)}`,
        [
            pill(bucket.status, toneForVerdict(bucket.status)),
            pill(`Eff ${bucket.efficiency_score.toFixed(2)}`),
        ],
        true
    )).join("");
}


function renderEndGameLoop(view) {
    const issuesEl = document.getElementById("loopIssues");
    const bucketsEl = document.getElementById("loopBuckets");

    if (!view.available) {
        renderUnavailableSection("loopChart", issuesEl, bucketsEl, view.reason);
        return;
    }

    renderLoopChart(view);

    issuesEl.innerHTML = view.issues?.length
        ? view.issues.map((item) => itemCard(item.range_label, item.reason, [
            pill(item.severity === "high" ? "High" : "Medium", toneForVerdict(item.severity)),
        ], true)).join("")
        : emptyState("No major loop drift was detected in the selected loop range.");

    bucketsEl.innerHTML = view.buckets.slice(0, 6).map((bucket) => itemCard(
        bucket.range_label,
        `Avg APS ${bucket.avg_aps.toFixed(2)} · D3 churn ${bucket.avg_d3_churn_pct.toFixed(2)}% · Playtime ${bucket.avg_playtime_sec.toFixed(0)}s`,
        [
            pill(bucket.status, toneForVerdict(bucket.status)),
            pill(`APS drift ${signed(bucket.aps_drift)}`),
        ],
        true
    )).join("");
}


function renderDiminishingReturns(view) {
    const findingsEl = document.getElementById("drFindings");
    const tableEl = document.getElementById("drTable");

    if (!view.available) {
        destroyChart("drChart");
        findingsEl.innerHTML = emptyState(view.reason || "Diminishing-returns analysis is unavailable.");
        tableEl.innerHTML = "";
        return;
    }

    renderDiminishingReturnsChart(view);

    findingsEl.innerHTML = view.findings?.length
        ? view.findings.map((item) => itemCard(item.title, item.detail, [], false)).join("")
        : emptyState("No strong diminishing-return finding was detected.");

    tableEl.innerHTML = `
        <div class="focus-table-wrap">
            <table class="table focus-table">
                <thead>
                    <tr>
                        <th>APS Bucket</th>
                        <th>Levels</th>
                        <th>${escapeHtml(view.churn_label || "Churn")}</th>
                        <th>Revenue / 1k Users</th>
                        <th>Sweet Spot Score</th>
                        <th>Zone</th>
                    </tr>
                </thead>
                <tbody>
                    ${view.buckets.map((bucket) => `
                        <tr>
                            <td>${escapeHtml(bucket.label)}</td>
                            <td>${bucket.count}</td>
                            <td>${bucket.avg_churn_pct.toFixed(2)}%</td>
                            <td>${bucket.revenue_per_k_users.toFixed(1)}</td>
                            <td>${bucket.sweet_spot_score.toFixed(3)}</td>
                            <td>${pill(bucket.zone_label || bucket.zone, toneForVerdict(bucket.zone_tone || bucket.zone))}</td>
                        </tr>
                    `).join("")}
                </tbody>
            </table>
        </div>
    `;
}


function renderDiminishingReturnsChart(view) {
    const canvas = document.getElementById("drChart");
    if (!canvas || typeof Chart === "undefined") {
        return;
    }

    destroyChart("drChart");

    const labels = view.buckets.map((bucket) => bucket.label);
    dashboardState.drChart = new Chart(canvas, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: `${view.churn_label || "Churn"} %`,
                    data: view.buckets.map((bucket) => bucket.avg_churn_pct),
                    borderColor: "#D45B5B",
                    backgroundColor: "rgba(212, 91, 91, 0.10)",
                    borderWidth: 2,
                    pointRadius: 3,
                    tension: 0.22,
                    yAxisID: "y",
                },
                {
                    label: "IAP users %",
                    data: view.buckets.map((bucket) => bucket.avg_iap_users_pct),
                    borderColor: "#5DAA68",
                    borderWidth: 2,
                    pointRadius: 3,
                    tension: 0.22,
                    yAxisID: "y",
                },
                {
                    label: "IAP composite",
                    data: view.buckets.map((bucket) => bucket.iap_composite),
                    borderColor: "#2E6F95",
                    borderWidth: 2,
                    pointRadius: 3,
                    tension: 0.22,
                    yAxisID: "y1",
                },
            ],
        },
        options: {
            ...baseLineChartOptions("Percent"),
            scales: {
                x: {
                    grid: { display: false },
                },
                y: {
                    title: { display: true, text: "Percent" },
                    beginAtZero: true,
                },
                y1: {
                    position: "right",
                    title: { display: true, text: "IAP composite" },
                    beginAtZero: true,
                    suggestedMax: 1,
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });
}


function renderLateTrendChart(view) {
    const canvas = document.getElementById("lateTrendChart");
    if (!canvas || typeof Chart === "undefined") {
        return;
    }

    destroyChart("lateTrendChart");

    const labels = view.buckets.map((bucket) => bucket.range_label);
    const apsValues = view.buckets.map((bucket) => bucket.avg_aps);
    const targetMin = view.buckets.map(() => view.target_band.min);
    const targetMax = view.buckets.map(() => view.target_band.max);

    dashboardState.lateTrendChart = new Chart(canvas, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Avg APS",
                    data: apsValues,
                    borderColor: "#2E6F95",
                    backgroundColor: "rgba(46, 111, 149, 0.12)",
                    fill: true,
                    borderWidth: 2,
                    tension: 0.22,
                },
                {
                    label: "Target min",
                    data: targetMin,
                    borderColor: "#5DAA68",
                    borderDash: [6, 6],
                    pointRadius: 0,
                    borderWidth: 1.5,
                },
                {
                    label: "Target max",
                    data: targetMax,
                    borderColor: "#E8A838",
                    borderDash: [6, 6],
                    pointRadius: 0,
                    borderWidth: 1.5,
                },
            ],
        },
        options: baseLineChartOptions("Average APS"),
    });
}


function renderLoopChart(view) {
    const canvas = document.getElementById("loopChart");
    if (!canvas || typeof Chart === "undefined") {
        return;
    }

    destroyChart("loopChart");

    const labels = view.buckets.map((bucket) => bucket.range_label);
    dashboardState.loopChart = new Chart(canvas, {
        type: "line",
        data: {
            labels,
            datasets: [
                {
                    label: "Avg APS",
                    data: view.buckets.map((bucket) => bucket.avg_aps),
                    borderColor: "#8B5CF6",
                    backgroundColor: "rgba(139, 92, 246, 0.10)",
                    fill: true,
                    borderWidth: 2,
                    tension: 0.22,
                    yAxisID: "y",
                },
                {
                    label: "Avg D3 churn %",
                    data: view.buckets.map((bucket) => bucket.avg_d3_churn_pct),
                    borderColor: "#D45B5B",
                    borderWidth: 2,
                    pointRadius: 3,
                    tension: 0.22,
                    yAxisID: "y1",
                },
            ],
        },
        options: {
            ...baseLineChartOptions("APS"),
            scales: {
                x: {
                    grid: { display: false },
                },
                y: {
                    title: { display: true, text: "Average APS" },
                    beginAtZero: true,
                },
                y1: {
                    position: "right",
                    title: { display: true, text: "Average D3 churn (%)" },
                    beginAtZero: true,
                    grid: { drawOnChartArea: false },
                },
            },
        },
    });
}


function baseLineChartOptions(yTitle) {
    return {
        maintainAspectRatio: false,
        responsive: true,
        plugins: {
            legend: { position: "bottom" },
        },
        scales: {
            x: {
                grid: { display: false },
            },
            y: {
                title: { display: true, text: yTitle },
                beginAtZero: false,
            },
        },
    };
}


function renderUnavailableSection(chartId, leftEl, rightEl, reason) {
    destroyChart(chartId);
    if (leftEl) {
        leftEl.innerHTML = emptyState(reason || "Unavailable for the current scope.");
    }
    if (rightEl) {
        rightEl.innerHTML = "";
    }
}


function destroyChart(chartKey) {
    const instance = dashboardState[chartKey];
    if (instance) {
        instance.destroy();
        dashboardState[chartKey] = null;
    }
}


function itemCard(title, copy, pills, compact) {
    return `
        <article class="focus-item ${compact ? "focus-item-tight" : ""}">
            <div class="focus-item-header">
                <h3>${escapeHtml(title)}</h3>
                <div class="focus-pill-row">${(pills || []).join("")}</div>
            </div>
            <p class="focus-item-copy">${escapeHtml(copy)}</p>
        </article>
    `;
}


function pill(label, tone = "default") {
    return `<span class="focus-pill focus-pill-${escapeHtml(tone)}">${escapeHtml(label)}</span>`;
}


function emptyState(message) {
    return `<div class="focus-inline-note">${escapeHtml(message)}</div>`;
}


function toneForVerdict(value) {
    const normalized = String(value || "").toLowerCase();
    if (["danger", "downward", "softening", "slump", "high"].includes(normalized)) {
        return "danger";
    }
    if (["warning", "spike", "hardening", "medium"].includes(normalized)) {
        return "warning";
    }
    if (["stable", "safe", "healthy", "upward"].includes(normalized)) {
        return "success";
    }
    return "default";
}


function setText(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.textContent = value;
    }
}


function setHTML(id, value) {
    const el = document.getElementById(id);
    if (el) {
        el.innerHTML = value;
    }
}


function capitalize(value) {
    const text = String(value || "");
    return text.charAt(0).toUpperCase() + text.slice(1);
}


function signed(value) {
    const number = Number(value || 0);
    return `${number >= 0 ? "+" : ""}${number.toFixed(2)}`;
}


function formatMaybe(value, digits = 2, suffix = "") {
    if (value == null || Number.isNaN(Number(value))) {
        return "—";
    }
    return `${Number(value).toFixed(digits)}${suffix}`;
}


function formatCompact(value) {
    const number = Number(value || 0);
    if (number >= 1000000) {
        return `${(number / 1000000).toFixed(1)}M`;
    }
    if (number >= 1000) {
        return `${(number / 1000).toFixed(1)}k`;
    }
    return number.toFixed(0);
}


function escapeHtml(value) {
    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#39;");
}
