(function () {
    const bootstrapNode = document.getElementById("trampoline-bootstrap");
    if (!bootstrapNode) {
        return;
    }

    const state = JSON.parse(bootstrapNode.textContent || "{}");
    state.editable_segments = [];
    state.auto_segments = [];
    state.selected_jump_id = null;
    state.dirty = false;

    const uploadForm = document.getElementById("trampoline-upload-form");
    const videoInput = document.getElementById("trampoline-video");
    const analyzeButton = document.getElementById("analyze-trigger");
    const segmentButton = document.getElementById("segment-trigger");
    const saveCalibrationButton = document.getElementById("save-calibration");
    const saveOverridesButton = document.getElementById("save-overrides");
    const suggestCalibrationButton = document.getElementById("suggest-calibration");
    const splitJumpButton = document.getElementById("split-jump");
    const mergeJumpButton = document.getElementById("merge-jump");
    const resetJumpButton = document.getElementById("reset-jump");
    const statusPill = document.getElementById("analysis-status");
    const analysisList = document.getElementById("analysis-list");
    const previewVideo = document.getElementById("preview-video");
    const overlayCanvas = document.getElementById("overlay-canvas");
    const detailAnalysisId = document.getElementById("detail-analysis-id");
    const detailVideoMeta = document.getElementById("detail-video-meta");
    const detailCalibration = document.getElementById("detail-calibration");
    const detailTimeline = document.getElementById("detail-timeline");
    const detailSummary = document.getElementById("detail-summary");
    const exportAnalysisButton = document.getElementById("export-analysis");
    const summaryHeadline = document.getElementById("summary-headline");
    const summaryCenterDeviation = document.getElementById("summary-center-deviation");
    const summaryMaxDeviation = document.getElementById("summary-max-deviation");
    const summaryZone = document.getElementById("summary-zone");
    const summaryFlags = document.getElementById("summary-flags");
    const summaryMarkdown = document.getElementById("summary-markdown");
    const landingHeatmap = document.getElementById("landing-heatmap");
    const timelineTrack = document.getElementById("timeline-track");
    const timelineSummary = document.getElementById("timeline-summary");
    const jumpEditorSummary = document.getElementById("jump-editor-summary");
    const jumpDetailSummary = document.getElementById("jump-detail-summary");
    const jumpAutoLabel = document.getElementById("jump-auto-label");
    const jumpResolvedLabel = document.getElementById("jump-resolved-label");
    const jumpLabelConfidence = document.getElementById("jump-label-confidence");
    const jumpFeatureWindow = document.getElementById("jump-feature-window");
    const jumpAngleSummary = document.getElementById("jump-angle-summary");
    const jumpDecisionReason = document.getElementById("jump-decision-reason");
    const jumpFallbackReason = document.getElementById("jump-fallback-reason");
    const labelOverrideNote = document.getElementById("label-override-note");
    const overrideTuckButton = document.getElementById("override-tuck");
    const overridePikeButton = document.getElementById("override-pike");
    const overrideStraightButton = document.getElementById("override-straight");
    const clearLabelOverrideButton = document.getElementById("clear-label-override");
    const calibrationInputs = Array.from(document.querySelectorAll("[data-corner][data-axis]"));
    const boundaryInputs = Array.from(document.querySelectorAll("[data-boundary]"));

    function clone(value) {
        return JSON.parse(JSON.stringify(value));
    }

    function formatLabel(value) {
        return value ? String(value).toUpperCase() : "n/a";
    }

    function formatMetric(value) {
        if (value == null || Number.isNaN(Number(value))) {
            return "n/a";
        }
        return Number(value).toFixed(3).replace(/\.?0+$/, "");
    }

    function setStatus(value) {
        statusPill.textContent = value || "idle";
    }

    function currentAnalysisId() {
        return state.selected_analysis_id || null;
    }

    function setCurrentAnalysisId(analysisId) {
        state.selected_analysis_id = analysisId;
        const enabled = Boolean(analysisId);
        analyzeButton.disabled = !enabled;
        segmentButton.disabled = !enabled;
        saveCalibrationButton.disabled = !enabled;
        saveOverridesButton.disabled = !enabled || !state.editable_segments.length;
        exportAnalysisButton.disabled = !enabled;
    }

    function pointFields() {
        return ["top_left", "top_right", "bottom_right", "bottom_left"];
    }

    function boundaryFields() {
        return ["start_ms", "takeoff_ms", "apex_ms", "landing_ms", "end_ms"];
    }

    function selectedSegmentIndex() {
        return state.editable_segments.findIndex((segment) => segment.jump_id === state.selected_jump_id);
    }

    function selectedSegment() {
        return state.editable_segments[selectedSegmentIndex()] || null;
    }

    function totalDurationMs() {
        const result = state.selected_result;
        return result && result.frames_meta ? Number(result.frames_meta.duration_ms || 0) : 0;
    }

    function currentVideoMs() {
        return Math.round((previewVideo.currentTime || 0) * 1000);
    }

    function updateDirtyState(isDirty) {
        state.dirty = isDirty;
        saveOverridesButton.disabled = !currentAnalysisId() || !state.editable_segments.length;
        saveOverridesButton.textContent = isDirty ? "Save Overrides*" : "Save Overrides";
    }

    function syncSegmentsFromResult(result) {
        const segmentation = result && result.segmentation ? result.segmentation : null;
        state.auto_segments = segmentation ? clone(segmentation.jump_segments || []) : [];
        state.editable_segments = clone((result && result.jump_segments) || []);
        if (!state.selected_jump_id || !state.editable_segments.find((segment) => segment.jump_id === state.selected_jump_id)) {
            state.selected_jump_id = state.editable_segments[0] ? state.editable_segments[0].jump_id : null;
        }
        updateDirtyState(false);
    }

    function drawLandingHeatmap() {
        const ctx = landingHeatmap.getContext("2d");
        const width = landingHeatmap.width;
        const height = landingHeatmap.height;
        ctx.clearRect(0, 0, width, height);
        ctx.fillStyle = "#112429";
        ctx.fillRect(0, 0, width, height);
        ctx.strokeStyle = "#74d1d9";
        ctx.lineWidth = 3;
        ctx.strokeRect(18, 18, width - 36, height - 36);
        ctx.strokeStyle = "rgba(255, 255, 255, 0.18)";
        ctx.beginPath();
        ctx.moveTo(width / 2, 18);
        ctx.lineTo(width / 2, height - 18);
        ctx.moveTo(18, height / 2);
        ctx.lineTo(width - 18, height / 2);
        ctx.stroke();

        const landing = state.selected_result && state.selected_result.landing;
        const jumps = landing && landing.jumps ? landing.jumps : [];
        if (!jumps.length) {
            ctx.fillStyle = "#f4e9d8";
            ctx.font = "16px Space Grotesk";
            ctx.fillText("No landing points", 28, height / 2);
            return;
        }

        const colors = {
            center: "#5ae0a0",
            inner: "#ffdf8a",
            edge: "#ff8459",
            out: "#f44f38",
            unknown: "#9fb2b8",
        };
        jumps.forEach((jump, index) => {
            if (jump.landing_x_norm == null || jump.landing_y_norm == null) {
                return;
            }
            const x = 18 + (Number(jump.landing_x_norm) * (width - 36));
            const y = 18 + (Number(jump.landing_y_norm) * (height - 36));
            ctx.beginPath();
            ctx.fillStyle = colors[jump.zone] || colors.unknown;
            ctx.globalAlpha = 0.35 + (0.15 * index);
            ctx.arc(x, y, 12, 0, Math.PI * 2);
            ctx.fill();
            ctx.globalAlpha = 1;
            ctx.fillStyle = "#f7f2e8";
            ctx.font = "12px Space Grotesk";
            ctx.fillText(String(index + 1), x - 4, y + 4);
        });
    }

    function renderSummary() {
        const result = state.selected_result;
        const summary = result && result.routine_summary ? result.routine_summary : null;
        exportAnalysisButton.disabled = !currentAnalysisId() || !result;

        if (!summary) {
            summaryHeadline.textContent = "No landing summary loaded.";
            summaryCenterDeviation.textContent = "n/a";
            summaryMaxDeviation.textContent = "n/a";
            summaryZone.textContent = "n/a";
            summaryFlags.textContent = "none";
            summaryMarkdown.textContent = "No summary markdown loaded.";
            drawLandingHeatmap();
            return;
        }

        summaryHeadline.textContent = `${summary.landed_jump_count || 0}/${summary.jump_count || 0} jumps mapped with demo landing assistance.`;
        summaryCenterDeviation.textContent = formatMetric(summary.mean_center_deviation);
        summaryMaxDeviation.textContent = formatMetric(summary.max_center_deviation);
        summaryZone.textContent = Object.entries(summary.zone_summary || {})
            .map(([name, count]) => `${name} ${count}`)
            .join(" · ");
        summaryFlags.textContent = summary.routine_flags && summary.routine_flags.length
            ? summary.routine_flags.join(", ")
            : "none";
        summaryMarkdown.textContent = result.summary_markdown
            ? result.summary_markdown.split("\n").filter(Boolean).slice(0, 6).join(" ")
            : "No summary markdown loaded.";
        drawLandingHeatmap();
    }

    function getCalibrationCorners() {
        const corners = {};
        for (const corner of pointFields()) {
            const xInput = document.querySelector(`[data-corner="${corner}"][data-axis="x"]`);
            const yInput = document.querySelector(`[data-corner="${corner}"][data-axis="y"]`);
            corners[corner] = {
                x: Number(xInput.value),
                y: Number(yInput.value),
            };
        }
        return corners;
    }

    function fillCalibrationInputs(calibration) {
        if (!calibration || !calibration.corners) {
            calibrationInputs.forEach((input) => {
                input.value = "";
            });
            return;
        }

        for (const [corner, point] of Object.entries(calibration.corners)) {
            const xInput = document.querySelector(`[data-corner="${corner}"][data-axis="x"]`);
            const yInput = document.querySelector(`[data-corner="${corner}"][data-axis="y"]`);
            if (xInput) {
                xInput.value = point.x;
            }
            if (yInput) {
                yInput.value = point.y;
            }
        }
    }

    function suggestedCalibration() {
        const result = state.selected_result;
        if (!result || !result.frames_meta) {
            return null;
        }
        const width = result.frames_meta.width;
        const height = result.frames_meta.height;
        const insetX = Math.round(width * 0.18);
        const insetY = Math.round(height * 0.18);
        return {
            top_left: { x: insetX, y: insetY },
            top_right: { x: width - insetX, y: insetY },
            bottom_right: { x: width - insetX, y: height - insetY },
            bottom_left: { x: insetX, y: height - insetY },
        };
    }

    function drawOverlay() {
        const result = state.selected_result;
        const ctx = overlayCanvas.getContext("2d");
        ctx.clearRect(0, 0, overlayCanvas.width, overlayCanvas.height);
        if (!result || !result.preview_frame) {
            return;
        }

        const width = Number(result.frames_meta.width || overlayCanvas.width);
        const height = Number(result.frames_meta.height || overlayCanvas.height);
        overlayCanvas.width = width;
        overlayCanvas.height = height;

        const landmarks = result.preview_frame.landmarks || [];
        const landmarkMap = new Map(landmarks.map((item) => [item.index, item]));
        ctx.lineWidth = 3;
        ctx.strokeStyle = "#ffdf8a";
        for (const [start, end] of result.pose_connections || []) {
            const startPoint = landmarkMap.get(start);
            const endPoint = landmarkMap.get(end);
            if (!startPoint || !endPoint) {
                continue;
            }
            ctx.beginPath();
            ctx.moveTo(startPoint.x * width, startPoint.y * height);
            ctx.lineTo(endPoint.x * width, endPoint.y * height);
            ctx.stroke();
        }

        ctx.fillStyle = "#ff8459";
        for (const landmark of landmarks) {
            ctx.beginPath();
            ctx.arc(landmark.x * width, landmark.y * height, 4, 0, Math.PI * 2);
            ctx.fill();
        }

        const calibration = result.calibration;
        if (!calibration || !calibration.corners) {
            return;
        }

        const orderedCorners = pointFields().map((corner) => calibration.corners[corner]);
        ctx.strokeStyle = "#74d1d9";
        ctx.lineWidth = 4;
        ctx.beginPath();
        ctx.moveTo(orderedCorners[0].x, orderedCorners[0].y);
        for (let index = 1; index < orderedCorners.length; index += 1) {
            ctx.lineTo(orderedCorners[index].x, orderedCorners[index].y);
        }
        ctx.closePath();
        ctx.stroke();

        ctx.beginPath();
        ctx.moveTo(calibration.center_point.x - 24, calibration.center_point.y);
        ctx.lineTo(calibration.center_point.x + 24, calibration.center_point.y);
        ctx.moveTo(calibration.center_point.x, calibration.center_point.y - 24);
        ctx.lineTo(calibration.center_point.x, calibration.center_point.y + 24);
        ctx.stroke();
    }

    function syncBoundaryInputs() {
        const segment = selectedSegment();
        boundaryInputs.forEach((input) => {
            input.disabled = !segment;
            input.value = segment ? segment[input.dataset.boundary] : "";
        });
        splitJumpButton.disabled = !segment;
        mergeJumpButton.disabled = !segment || selectedSegmentIndex() >= state.editable_segments.length - 1;
        resetJumpButton.disabled = !segment;
        if (!segment) {
            jumpEditorSummary.textContent = "Choose a jump block to edit its boundaries.";
            return;
        }
        jumpEditorSummary.textContent = `${segment.jump_id} • ${segment.start_ms}ms to ${segment.end_ms}ms • source ${segment.source || "merged"}`;
    }

    function syncJumpDetail() {
        const segment = selectedSegment();
        const hasSelectedSegment = Boolean(segment);
        const canOverride = hasSelectedSegment && !state.dirty && currentAnalysisId();
        [overrideTuckButton, overridePikeButton, overrideStraightButton, clearLabelOverrideButton].forEach((button) => {
            button.disabled = !canOverride;
        });
        labelOverrideNote.disabled = !canOverride;

        if (!segment) {
            jumpDetailSummary.textContent = "Choose a jump block to inspect auto labels, explainability, and manual overrides.";
            jumpAutoLabel.textContent = "waiting";
            jumpResolvedLabel.textContent = "waiting";
            jumpLabelConfidence.textContent = "waiting";
            jumpFeatureWindow.textContent = "waiting";
            jumpAngleSummary.textContent = "No jump selected.";
            jumpDecisionReason.textContent = "No jump selected.";
            jumpFallbackReason.textContent = "none";
            labelOverrideNote.value = "";
            return;
        }

        const summary = segment.feature_summary || {};
        const midFrameCount = Number(summary.mid_flight_valid_frame_count || 0);
        const totalFrameCount = Number(summary.valid_frame_count || 0);
        jumpDetailSummary.textContent = state.dirty
            ? "Save timeline edits before applying a manual label override."
            : `${segment.jump_id} detail loaded from features.jsonl and labels.json.`;
        jumpAutoLabel.textContent = formatLabel(segment.auto_label);
        jumpResolvedLabel.textContent = formatLabel(segment.resolved_label || segment.label || segment.auto_label);
        jumpLabelConfidence.textContent = segment.label_confidence != null ? `${Math.round(segment.label_confidence * 100)}%` : "n/a";
        jumpFeatureWindow.textContent = `${midFrameCount} mid-flight frames / ${totalFrameCount} valid frames`;
        jumpAngleSummary.textContent = `trunk_thigh ${summary.trunk_thigh_min_angle ?? "n/a"}-${summary.trunk_thigh_max_angle ?? "n/a"}°, thigh_shank ${summary.thigh_shank_min_angle ?? "n/a"}-${summary.thigh_shank_max_angle ?? "n/a"}°.`;
        jumpDecisionReason.textContent = segment.decision_reason || "No decision reason recorded.";
        jumpFallbackReason.textContent = segment.fallback_reason || "none";
        labelOverrideNote.value = segment.override_note || "";
    }

    function normalizeSegment(segment) {
        const minGap = 20;
        const ordered = boundaryFields().map((field) => Number(segment[field] || 0));
        for (let index = 1; index < ordered.length; index += 1) {
            ordered[index] = Math.max(ordered[index], ordered[index - 1] + (index === ordered.length - 1 ? 0 : minGap));
        }
        if (ordered[4] < ordered[3]) {
            ordered[4] = ordered[3];
        }
        return {
            ...segment,
            start_ms: ordered[0],
            takeoff_ms: ordered[1],
            apex_ms: ordered[2],
            landing_ms: ordered[3],
            end_ms: ordered[4],
        };
    }

    function renderTimeline() {
        timelineTrack.innerHTML = "";
        const segments = state.editable_segments || [];
        if (!segments.length) {
            timelineSummary.textContent = "No segmentation loaded.";
            detailTimeline.textContent = "no jumps";
            syncBoundaryInputs();
            syncJumpDetail();
            timelineTrack.innerHTML = `
                <div class="timeline-empty">
                    <div class="timeline-chip">analyze</div>
                    <div class="timeline-chip">calibrate</div>
                    <div class="timeline-chip">segment</div>
                    <div class="timeline-chip muted">edit timeline</div>
                </div>
            `;
            return;
        }

        const duration = Math.max(totalDurationMs(), segments[segments.length - 1].end_ms);
        timelineSummary.textContent = `${segments.length} jumps loaded${state.dirty ? " • unsaved edits" : ""}. Click a block to seek and edit.`;
        detailTimeline.textContent = `${segments.length} jumps`;

        segments.forEach((segment) => {
            const button = document.createElement("button");
            const left = (segment.start_ms / duration) * 100;
            const width = Math.max(((segment.end_ms - segment.start_ms) / duration) * 100, 4);
            const currentMs = currentVideoMs();
            const isCurrent = currentMs >= segment.start_ms && currentMs <= segment.end_ms;
            const isSelected = segment.jump_id === state.selected_jump_id;
            button.type = "button";
            button.className = `timeline-block${isSelected ? " selected" : ""}${isCurrent ? " current" : ""}`;
            button.dataset.jumpId = segment.jump_id;
            button.style.left = `${left}%`;
            button.style.width = `${width}%`;
            button.innerHTML = `
                <span class="timeline-block-id">${segment.sequence_index + 1}</span>
                <span class="timeline-block-label">${formatLabel(segment.resolved_label || segment.auto_label)}</span>
                <span class="timeline-block-time">${segment.start_ms}-${segment.end_ms}ms</span>
            `;
            button.addEventListener("click", () => {
                state.selected_jump_id = segment.jump_id;
                previewVideo.currentTime = segment.start_ms / 1000;
                renderTimeline();
                syncBoundaryInputs();
                syncJumpDetail();
            });
            timelineTrack.appendChild(button);
        });
        syncBoundaryInputs();
        syncJumpDetail();
    }

    function renderResult() {
        const result = state.selected_result;
        const analysisId = currentAnalysisId();
        detailAnalysisId.textContent = analysisId || "none";

        if (!result) {
            previewVideo.removeAttribute("src");
            detailVideoMeta.textContent = "waiting";
            detailCalibration.textContent = "not saved";
            detailTimeline.textContent = "no jumps";
            detailSummary.textContent = "Select an analysis to view its video preview, skeleton overlay, calibration, and current jump selection.";
            fillCalibrationInputs(null);
            syncSegmentsFromResult(null);
            drawOverlay();
            renderSummary();
            renderTimeline();
            return;
        }

        previewVideo.src = `/api/trampoline/video/${result.analysis_id}`;
        detailVideoMeta.textContent = `${result.frames_meta.width}x${result.frames_meta.height} @ ${result.frames_meta.fps.toFixed(2)}fps`;
        detailCalibration.textContent = result.calibration ? "saved" : "not saved";
        detailSummary.textContent = `Frame ${result.preview_frame.frame_index} at ${result.preview_frame.timestamp_ms}ms with ${result.preview_frame.landmarks.length} landmarks.`;
        fillCalibrationInputs(result.calibration);
        syncSegmentsFromResult(result);
        drawOverlay();
        renderSummary();
        renderTimeline();
    }

    function renderAnalysisList() {
        analysisList.innerHTML = "";
        for (const item of state.analyses || []) {
            const button = document.createElement("button");
            button.type = "button";
            button.className = item.analysis_id === currentAnalysisId() ? "active" : "";
            button.innerHTML = `
                <span>${item.analysis_id}</span>
                <span>${item.has_segmentation ? "seg" : "raw"}${item.has_labels ? " + labels" : ""}${item.has_landing ? " + landing" : ""} · ${item.frame_count}f</span>
            `;
            button.addEventListener("click", () => {
                fetch(`/api/trampoline/result/${item.analysis_id}`)
                    .then((response) => response.json())
                    .then((payload) => {
                        if (!payload.success) {
                            throw new Error(payload.error || "Failed to load analysis");
                        }
                        setCurrentAnalysisId(item.analysis_id);
                        state.selected_result = payload.result;
                        renderAnalysisList();
                        renderResult();
                        setStatus(payload.status);
                        window.history.replaceState({}, "", `/trampoline?analysis_id=${item.analysis_id}`);
                    })
                    .catch((error) => {
                        setStatus(error.message);
                    });
            });
            analysisList.appendChild(button);
        }
    }

    function pollStatus(analysisId) {
        const poll = () => {
            fetch(`/api/trampoline/status/${analysisId}`)
                .then((response) => response.json())
                .then((payload) => {
                    if (!payload.success) {
                        throw new Error(payload.error || "status failed");
                    }
                    setStatus(payload.status);
                    if (payload.result) {
                        state.selected_result = payload.result;
                        setCurrentAnalysisId(analysisId);
                        state.analyses = state.analyses || [];
                        if (!state.analyses.find((item) => item.analysis_id === analysisId)) {
                            state.analyses.push({
                                analysis_id: analysisId,
                                frame_count: payload.result.frames_meta.frame_count,
                                duration_ms: payload.result.frames_meta.duration_ms,
                                source_video: payload.result.source_video,
                                updated_at: payload.result.updated_at,
                                has_segmentation: Boolean(payload.result.segmentation),
                                has_overrides: Boolean(payload.result.has_overrides),
                                has_labels: Boolean(payload.result.has_labels),
                                has_landing: Boolean(payload.result.has_landing),
                            });
                        }
                        renderAnalysisList();
                        renderResult();
                    }
                    if (payload.status === "queued" || payload.status === "running") {
                        window.setTimeout(poll, 800);
                    }
                })
                .catch((error) => {
                    setStatus(error.message);
                });
        };
        poll();
    }

    function reframeSegment(original, newStart, newEnd, jumpId) {
        const baseDuration = Math.max(original.end_ms - original.start_ms, 1);
        const newDuration = Math.max(newEnd - newStart, 1);
        const ratios = {
            takeoff_ms: (original.takeoff_ms - original.start_ms) / baseDuration,
            apex_ms: (original.apex_ms - original.start_ms) / baseDuration,
            landing_ms: (original.landing_ms - original.start_ms) / baseDuration,
        };
        return normalizeSegment({
            ...clone(original),
            jump_id: jumpId,
            start_ms: Math.round(newStart),
            takeoff_ms: Math.round(newStart + (newDuration * ratios.takeoff_ms)),
            apex_ms: Math.round(newStart + (newDuration * ratios.apex_ms)),
            landing_ms: Math.round(newStart + (newDuration * ratios.landing_ms)),
            end_ms: Math.round(newEnd),
            source: "merged",
        });
    }

    function refreshSequenceIds() {
        state.editable_segments = state.editable_segments
            .slice()
            .sort((left, right) => left.start_ms - right.start_ms)
            .map((segment, index) => ({
                ...segment,
                jump_id: `jump-${String(index + 1).padStart(3, "0")}`,
                sequence_index: index,
            }));
        if (state.editable_segments.length && !state.editable_segments.find((segment) => segment.jump_id === state.selected_jump_id)) {
            state.selected_jump_id = state.editable_segments[0].jump_id;
        }
    }

    function applyLabelOverride(overrideLabel) {
        const analysisId = currentAnalysisId();
        const segment = selectedSegment();
        if (!analysisId || !segment || state.dirty) {
            return;
        }
        setStatus(overrideLabel ? "saving label override" : "clearing label override");
        fetch(`/api/trampoline/labels/${analysisId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                jump_id: segment.jump_id,
                override_label: overrideLabel,
                override_note: labelOverrideNote.value.trim() || null,
            }),
        })
            .then((response) => response.json())
            .then((payload) => {
                if (!payload.success) {
                    throw new Error(payload.error || "label override failed");
                }
                state.selected_result = payload.result;
                renderAnalysisList();
                renderResult();
                setStatus(overrideLabel ? "label override saved" : "label override cleared");
            })
            .catch((error) => {
                setStatus(error.message);
            });
    }

    uploadForm.addEventListener("submit", (event) => {
        event.preventDefault();
        const file = videoInput.files[0];
        if (!file) {
            setStatus("choose a video");
            return;
        }

        const formData = new FormData();
        formData.append("video", file);
        setStatus("uploading");
        fetch("/api/trampoline/upload", {
            method: "POST",
            body: formData,
        })
            .then((response) => response.json())
            .then((payload) => {
                if (!payload.success) {
                    throw new Error(payload.error || "upload failed");
                }
                setCurrentAnalysisId(payload.analysis_id);
                state.selected_result = null;
                setStatus(payload.status);
                renderResult();
            })
            .catch((error) => {
                setStatus(error.message);
            });
    });

    analyzeButton.addEventListener("click", () => {
        const analysisId = currentAnalysisId();
        if (!analysisId) {
            return;
        }
        setStatus("queued");
        fetch("/api/trampoline/analyze", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ analysis_id: analysisId }),
        })
            .then((response) => response.json())
            .then((payload) => {
                if (!payload.success) {
                    throw new Error(payload.error || "analyze failed");
                }
                pollStatus(analysisId);
            })
            .catch((error) => {
                setStatus(error.message);
            });
    });

    segmentButton.addEventListener("click", () => {
        const analysisId = currentAnalysisId();
        if (!analysisId) {
            return;
        }
        setStatus("segmenting");
        fetch(`/api/trampoline/segment/${analysisId}`, {
            method: "POST",
        })
            .then((response) => response.json())
            .then((payload) => {
                if (!payload.success) {
                    throw new Error(payload.error || "segment failed");
                }
                state.selected_result = payload.result;
                renderAnalysisList();
                renderResult();
                setStatus("segmented");
            })
            .catch((error) => {
                setStatus(error.message);
            });
    });

    suggestCalibrationButton.addEventListener("click", () => {
        const corners = suggestedCalibration();
        if (!corners) {
            return;
        }
        fillCalibrationInputs({ corners });
    });

    document.getElementById("calibration-form").addEventListener("submit", (event) => {
        event.preventDefault();
        const analysisId = currentAnalysisId();
        if (!analysisId) {
            return;
        }
        fetch(`/api/trampoline/calibration/${analysisId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ corners: getCalibrationCorners() }),
        })
            .then((response) => response.json())
            .then((payload) => {
                if (!payload.success) {
                    throw new Error(payload.error || "calibration save failed");
                }
                return fetch(`/api/trampoline/result/${analysisId}`);
            })
            .then((response) => response.json())
            .then((payload) => {
                if (!payload.success) {
                    throw new Error(payload.error || "result refresh failed");
                }
                state.selected_result = payload.result;
                renderAnalysisList();
                renderResult();
                setStatus("calibration saved");
            })
            .catch((error) => {
                setStatus(error.message);
            });
    });

    boundaryInputs.forEach((input) => {
        input.addEventListener("change", () => {
            const segment = selectedSegment();
            if (!segment) {
                return;
            }
            const index = selectedSegmentIndex();
            state.editable_segments[index] = normalizeSegment({
                ...segment,
                [input.dataset.boundary]: Number(input.value),
                source: "merged",
                manual_boundary_fields: boundaryFields(),
            });
            updateDirtyState(true);
            renderTimeline();
        });
    });

    splitJumpButton.addEventListener("click", () => {
        const segment = selectedSegment();
        if (!segment) {
            return;
        }
        const index = selectedSegmentIndex();
        const splitMs = Math.min(Math.max(currentVideoMs(), segment.start_ms + 80), segment.end_ms - 80);
        const left = reframeSegment(segment, segment.start_ms, splitMs, `${segment.jump_id}-a`);
        const right = reframeSegment(segment, splitMs, segment.end_ms, `${segment.jump_id}-b`);
        left.auto_jump_ids = clone(segment.auto_jump_ids || [segment.jump_id]);
        right.auto_jump_ids = clone(segment.auto_jump_ids || [segment.jump_id]);
        state.editable_segments.splice(index, 1, left, right);
        refreshSequenceIds();
        state.selected_jump_id = state.editable_segments[index].jump_id;
        updateDirtyState(true);
        renderTimeline();
    });

    mergeJumpButton.addEventListener("click", () => {
        const index = selectedSegmentIndex();
        const left = state.editable_segments[index];
        const right = state.editable_segments[index + 1];
        if (!left || !right) {
            return;
        }
        const merged = normalizeSegment({
            ...clone(left),
            start_ms: left.start_ms,
            takeoff_ms: Math.min(left.takeoff_ms, right.takeoff_ms),
            apex_ms: Math.round((left.apex_ms + right.apex_ms) / 2),
            landing_ms: Math.max(left.landing_ms, right.landing_ms),
            end_ms: right.end_ms,
            source: "merged",
            auto_jump_ids: Array.from(new Set([...(left.auto_jump_ids || [left.jump_id]), ...(right.auto_jump_ids || [right.jump_id])])),
            manual_boundary_fields: boundaryFields(),
        });
        state.editable_segments.splice(index, 2, merged);
        refreshSequenceIds();
        state.selected_jump_id = state.editable_segments[index].jump_id;
        updateDirtyState(true);
        renderTimeline();
    });

    resetJumpButton.addEventListener("click", () => {
        const index = selectedSegmentIndex();
        const segment = selectedSegment();
        if (!segment) {
            return;
        }
        const autoMatch = state.auto_segments.find((item) => (item.auto_jump_ids || [item.jump_id]).some((jumpId) => (segment.auto_jump_ids || []).includes(jumpId)));
        if (!autoMatch) {
            return;
        }
        state.editable_segments[index] = clone(autoMatch);
        updateDirtyState(true);
        renderTimeline();
    });

    saveOverridesButton.addEventListener("click", () => {
        const analysisId = currentAnalysisId();
        if (!analysisId) {
            return;
        }
        setStatus("saving");
        fetch(`/api/trampoline/overrides/${analysisId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ jump_segments: state.editable_segments }),
        })
            .then((response) => response.json())
            .then((payload) => {
                if (!payload.success) {
                    throw new Error(payload.error || "override save failed");
                }
                state.selected_result = payload.result;
                renderAnalysisList();
                renderResult();
                setStatus("overrides saved");
            })
            .catch((error) => {
                setStatus(error.message);
            });
    });

    exportAnalysisButton.addEventListener("click", () => {
        const analysisId = currentAnalysisId();
        if (!analysisId) {
            return;
        }
        setStatus("exporting");
        window.location.assign(`/api/trampoline/export/${analysisId}`);
    });

    overrideTuckButton.addEventListener("click", () => {
        applyLabelOverride("tuck");
    });

    overridePikeButton.addEventListener("click", () => {
        applyLabelOverride("pike");
    });

    overrideStraightButton.addEventListener("click", () => {
        applyLabelOverride("straight");
    });

    clearLabelOverrideButton.addEventListener("click", () => {
        applyLabelOverride(null);
    });

    previewVideo.addEventListener("timeupdate", () => {
        if (state.editable_segments.length) {
            renderTimeline();
        }
    });

    setCurrentAnalysisId(state.selected_analysis_id || null);
    renderAnalysisList();
    renderResult();
    if (state.selected_analysis_id) {
        setStatus("done");
    }
})();
