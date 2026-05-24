// Trampoline-only video analysis page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const uploadArea = document.getElementById('upload-area');
    const videoInput = document.getElementById('video-input');
    const browseBtn = document.getElementById('browse-btn');
    const videoPlayer = document.getElementById('video-player');
    const analysisCanvas = document.getElementById('analysis-canvas');
    const ctx = analysisCanvas.getContext('2d');
    const appShell = document.querySelector('.app-shell');
    const processChip = document.getElementById('process-chip');
    const videoStateTag = document.getElementById('video-state-tag');
    const progressStage = document.getElementById('progress-stage');
    const frameInfo = document.getElementById('frame-info');
    const filenameEl = document.getElementById('filename');
    const calibrationFooter = document.getElementById('calibration-footer');
    const calibrationFooterBottom = document.getElementById('calibration-footer-bottom');
    const jumpCount = document.getElementById('jump-count');

    const playBtn = document.getElementById('play-btn');
    const analyzeBtn = document.getElementById('analyze-btn');
    const stopAnalysisBtn = document.getElementById('stop-analysis-btn');
    const resetBtn = document.getElementById('reset-btn');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');

    const statReps = document.getElementById('stat-reps');
    const statFlightTime = document.getElementById('stat-flight-time');
    const statAction = document.getElementById('stat-action');
    const statLanding = document.getElementById('stat-landing');
    const landingMap = document.getElementById('landing-map');
    const landingMapBed = document.getElementById('landing-map-bed');
    const flightChart = document.getElementById('flight-chart');
    const feedbackLog = document.getElementById('feedback-log');
    const reportSection = document.getElementById('report-section');
    const reportContent = document.getElementById('report-content');
    const downloadReportBtn = document.getElementById('download-report-btn');

    const terminalContent = document.getElementById('terminal-content');
    const terminalStatus = document.getElementById('terminal-status');
    const terminalToggle = document.getElementById('terminal-toggle');
    const terminalBody = document.getElementById('terminal-body');

    const llmSection = document.getElementById('llm-section');
    const llmBtn = document.getElementById('llm-btn');
    const llmStreaming = document.getElementById('llm-streaming');
    const llmStreamingText = document.getElementById('llm-streaming-text');
    const llmCards = document.getElementById('llm-cards');
    const llmToggleRaw = document.getElementById('llm-toggle-raw');
    const llmTabs = Array.from(document.querySelectorAll('.llm-tab'));
    const llmActivePanel = document.getElementById('llm-active-panel');
    const aiWaiting = document.getElementById('ai-waiting');
    const sequenceStep = document.getElementById('sequence-step');
    const sequenceJumpCount = document.getElementById('sequence-jump-count');
    const sequenceTotal = document.getElementById('sequence-total');
    const sequenceTransition = document.getElementById('sequence-transition');
    const sequenceActionBreakdown = document.getElementById('sequence-action-breakdown');
    const sequenceDuration = document.getElementById('sequence-duration');
    const jumpTableBody = document.getElementById('jump-table-body');
    const recalibrateBtn = document.getElementById('recalibrate-btn');
    const showCalibrationBtn = document.getElementById('show-calibration');
    const showResultsBtn = document.getElementById('show-results');
    const scoreIds = ['score-d', 'score-e', 'score-t', 'score-h', 'score-p', 'score-total'];
    const scoreStatusLabel = document.getElementById('score-status-label');
    const scoreActions = document.getElementById('score-actions');
    const confirmScoreSelectionBtn = document.getElementById('confirm-score-selection');
    const editScoreSelectionBtn = document.getElementById('edit-score-selection');
    const submitScoreSelectionBtn = document.getElementById('submit-score-selection');
    const scoreSelectionCount = document.getElementById('score-selection-count');

    const calibrationGeometry = window.TrampolineCalibrationGeometry;
    const trampolineCalibrationUi = window.TrampolineCalibrationUI;
    const videoAnalysisHelpers = window.VideoAnalysisHelpers;

    if (!calibrationGeometry || !trampolineCalibrationUi || !videoAnalysisHelpers) {
        throw new Error('Required trampoline/video analysis helpers failed to load');
    }

    let videoFile = null;
    let isAnalyzing = false;
    let analysisInterval = null;
    let currentVideoId = null;
    let trampolineCalibrationController = null;
    let llmEventSource = null;
    let lastProgress = 0;
    let scoreSelectionEditing = false;
    let selectedScoreJumpNumbers = new Set();

    let analysisResults = {
        reps: 0,
        feedbacks: [],
        startTime: null,
        endTime: null,
        completedJumps: [],
        durationSeconds: 0,
        actionBreakdown: '—',
        transitionCount: 0,
        llmSections: {},
        llmFullText: '',
        llmSource: '',
        activeLlmSection: '整体表现',
        score: null,
    };

    function getTimestamp() {
        const now = new Date();
        return now.toLocaleTimeString('en-US', {
            hour12: false,
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
        });
    }

    function addLog(message, type = 'info') {
        const line = document.createElement('div');
        line.className = `log-line ${type}`;
        line.innerHTML = `<span class="timestamp">[${getTimestamp()}]</span> ${message}`;
        terminalContent.appendChild(line);
        terminalContent.scrollTop = terminalContent.scrollHeight;
    }

    function setTerminalStatus(status, type = 'idle') {
        terminalStatus.textContent = `● ${status}`;
        terminalStatus.className = `terminal-status ${type}`;
    }

    function addFeedback(type, message) {
        const now = new Date();
        const timeStr = `${now.getMinutes().toString().padStart(2, '0')}:${now.getSeconds().toString().padStart(2, '0')}`;
        const item = document.createElement('div');
        item.className = `feedback-item ${type}`;
        item.innerHTML = `<span class="feedback-time">${timeStr}</span><span class="feedback-text">${message}</span>`;
        feedbackLog.insertBefore(item, feedbackLog.firstChild);
        while (feedbackLog.children.length > 50) {
            feedbackLog.removeChild(feedbackLog.lastChild);
        }
        analysisResults.feedbacks.push({ time: timeStr, type, message });
    }

    function setText(node, text) {
        if (node) node.textContent = text;
    }

    function setProcessState(kind, text) {
        if (!processChip) return;
        const color = {
            idle: 'amber',
            ready: 'blue',
            processing: 'blue',
            success: 'green',
            error: 'red',
        }[kind] || 'amber';
        processChip.innerHTML = `<i class="dot ${color}"></i><span>${text}</span>`;
    }

    function setStage(stageName, label, detailHtml) {
        if (appShell) appShell.dataset.analysisStage = stageName;
        setText(videoStateTag, label);
        setText(progressStage, label);
        if (detailHtml && frameInfo) frameInfo.innerHTML = detailHtml;
    }

    function setCalibrationStatus(text) {
        setText(calibrationFooter, text);
        setText(calibrationFooterBottom, text);
    }

    function clearScorePlaceholders() {
        scoreIds.forEach(id => setText(document.getElementById(id), '--'));
        setText(scoreStatusLabel, '待分析');
        if (scoreActions) scoreActions.classList.add('hidden');
        scoreSelectionEditing = false;
        selectedScoreJumpNumbers = new Set();
    }

    function setWorkflowTab(tab) {
        const showCalibration = tab === 'calibration';
        if (showCalibrationBtn) {
            showCalibrationBtn.classList.toggle('active', showCalibration);
            showCalibrationBtn.setAttribute('aria-selected', String(showCalibration));
        }
        if (showResultsBtn) {
            showResultsBtn.classList.toggle('active', !showCalibration);
            showResultsBtn.setAttribute('aria-selected', String(!showCalibration));
        }
        if (sequenceStep) sequenceStep.classList.toggle('hidden', showCalibration);
        const cornerStep = document.getElementById('corner-marking-step');
        if (cornerStep && (currentVideoId || analysisResults.completedJumps.length)) {
            cornerStep.classList.toggle('hidden', !showCalibration);
        }
        setText(document.getElementById('workflow-title'), showCalibration ? '床面标定' : '动作序列');
    }

    function summarizeJumps(jumps) {
        const allJumps = Array.isArray(jumps) ? jumps : [];
        const realJumps = allJumps.filter(j => j && !j.is_intermediate);
        const actionCounts = {};
        realJumps.forEach(j => {
            const action = j.action || '--';
            actionCounts[action] = (actionCounts[action] || 0) + 1;
        });
        return {
            realJumps,
            transitionCount: allJumps.filter(j => j && j.is_intermediate).length,
            actionBreakdown: Object.entries(actionCounts).map(([k, v]) => `${k}: ${v}`).join('，') || '—',
        };
    }

    function formatJumpLanding(jump) {
        const landing = validLanding(jump?.landing);
        if (!landing) return { coord: '--', confidence: '--' };
        const xy = Array.isArray(landing.bed_xy_m) ? landing.bed_xy_m : null;
        const coord = xy && finiteNumber(xy[0]) !== null && finiteNumber(xy[1]) !== null
            ? `(${formatFixed(xy[0])}, ${formatFixed(xy[1])})m`
            : landing.zone || '--';
        const conf = finiteNumber(landing.confidence);
        return {
            coord,
            confidence: conf === null ? '--' : conf.toFixed(2),
        };
    }

    function formatScoreValue(value) {
        const n = finiteNumber(value);
        return n === null ? '--' : n.toFixed(2);
    }

    function setLlmAvailabilityFromScore(score) {
        if (!llmBtn) return;
        const analysisCompleted = appShell?.dataset.analysisStage === 'completed' || Boolean(analysisResults.endTime);
        if (!currentVideoId || !score || !analysisCompleted) {
            llmBtn.disabled = true;
            return;
        }
        llmBtn.disabled = score.status === 'selection_required';
    }

    function updateScoreSelectionCount() {
        if (!scoreSelectionCount) return;
        const count = selectedScoreJumpNumbers.size;
        scoreSelectionCount.textContent = `已选择 ${count} / 10`;
        if (submitScoreSelectionBtn) submitScoreSelectionBtn.disabled = count !== 10;
    }

    function toggleScoreSelectionColumns(show) {
        document.querySelectorAll('.score-select-col').forEach(node => {
            node.classList.toggle('hidden', !show);
        });
    }

    function renderScore(score) {
        analysisResults.score = score || null;
        const components = score?.components || {};
        setText(document.getElementById('score-d'), formatScoreValue(components.D));
        setText(document.getElementById('score-e'), formatScoreValue(components.E));
        setText(document.getElementById('score-t'), formatScoreValue(components.T));
        setText(document.getElementById('score-h'), formatScoreValue(components.H));
        setText(document.getElementById('score-p'), formatScoreValue(components.P));
        setText(document.getElementById('score-total'), formatScoreValue(components.total));

        const labels = {
            ready: '评分完成',
            incomplete: '辅助估计',
            selection_required: '需选择10跳',
            insufficient_data: '数据不足',
        };
        setText(scoreStatusLabel, labels[score?.status] || '待分析');

        const needsSelection = score?.status === 'selection_required';
        if (scoreActions) scoreActions.classList.toggle('hidden', !needsSelection && !scoreSelectionEditing);
        if (confirmScoreSelectionBtn) confirmScoreSelectionBtn.classList.toggle('hidden', scoreSelectionEditing || !needsSelection);
        if (editScoreSelectionBtn) editScoreSelectionBtn.classList.toggle('hidden', scoreSelectionEditing || !needsSelection);
        if (submitScoreSelectionBtn) submitScoreSelectionBtn.classList.toggle('hidden', !scoreSelectionEditing);
        if (needsSelection && !selectedScoreJumpNumbers.size) {
            selectedScoreJumpNumbers = new Set(score.default_selected_jump_numbers || []);
        }
        updateScoreSelectionCount();
        setLlmAvailabilityFromScore(score);
        toggleScoreSelectionColumns(scoreSelectionEditing);
    }

    function selectedScoreJumpList() {
        return Array.from(selectedScoreJumpNumbers).sort((a, b) => a - b);
    }

    async function submitScoreSelection(numbers) {
        if (!currentVideoId) return;
        try {
            const response = await fetch(`/api/video/score/${currentVideoId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ selected_jump_numbers: numbers }),
            });
            const payload = await response.json();
            if (!payload.success) {
                addFeedback('error', payload.error || '评分失败');
                return;
            }
            scoreSelectionEditing = false;
            selectedScoreJumpNumbers = new Set(payload.score.selected_jump_numbers || []);
            renderScore(payload.score);
            renderJumpSequence({ completed_jumps: analysisResults.completedJumps, reps: analysisResults.reps });
            addFeedback('success', '评分已更新，可启动 AI 分析');
        } catch (error) {
            addFeedback('error', `评分提交失败：${error.message}`);
        }
    }

    function formatLlmErrorMessage(data = {}) {
        const parts = [data.message || 'AI 分析失败'];
        if (data.hint) parts.push(data.hint);
        if (data.fast_error) parts.push(`快速模型：${data.fast_error}`);
        if (data.quality_error) parts.push(`高质量模型：${data.quality_error}`);
        return parts.filter(Boolean).join('\n');
    }

    function scoreDeductionByJumpNumber() {
        const rows = analysisResults.score?.deductions;
        if (!Array.isArray(rows)) return new Map();
        return new Map(rows.map(row => [Number(row.jump_number), row]));
    }

    function renderScoreDetailButton(row) {
        if (!row) return '';
        const notes = Array.isArray(row.notes) ? row.notes.join('；') : '';
        const detail = notes || row.difficulty_note || '暂无额外扣分说明';
        return `
            <span class="score-detail-wrap">
                <button class="score-detail-trigger" type="button" aria-label="查看第 ${escapeHtml(row.jump_number)} 跳详细扣分说明">详细扣分说明</button>
                <span class="score-detail-popover" role="tooltip">
                    <strong>第 ${escapeHtml(row.jump_number)} 跳 · ${escapeHtml(row.action || '--')}</strong>
                    <span>D ${formatScoreValue(row.difficulty)}</span>
                    <span>T ${formatScoreValue(row.flight_s)}s</span>
                    <span>H扣 ${formatScoreValue(row.h_deduction)}</span>
                    <span>E扣 ${formatScoreValue(row.e_deduction)}</span>
                    <span>落点 ${formatScoreValue(row.landing_distance_m)}m</span>
                    <em>${escapeHtml(detail)}</em>
                </span>
            </span>
        `;
    }

    function renderJumpSequence(data = {}) {
        if (!sequenceStep || !jumpTableBody) return;
        const jumps = data.completed_jumps || analysisResults.completedJumps || [];
        const { realJumps, transitionCount, actionBreakdown } = summarizeJumps(jumps);
        const deductionMap = scoreDeductionByJumpNumber();
        const duration = analysisResults.durationSeconds || 0;
        analysisResults.actionBreakdown = actionBreakdown;
        analysisResults.transitionCount = transitionCount;
        setText(sequenceJumpCount, String(realJumps.length));
        setText(sequenceTotal, String(data.reps || realJumps.length || 0));
        setText(sequenceTransition, String(transitionCount));
        setText(sequenceActionBreakdown, actionBreakdown);
        setText(sequenceDuration, `处理耗时：${duration ? `${duration}s` : '--'}`);
        setText(jumpCount, String(data.reps || realJumps.length || 0));

        if (!realJumps.length) {
            jumpTableBody.innerHTML = '<tr><td colspan="7">完成分析后显示动作序列</td></tr>';
            return;
        }

        jumpTableBody.innerHTML = realJumps.map((jump, index) => {
            const landing = formatJumpLanding(jump);
            const flight = finiteNumber(jump.flight_duration_s);
            const flightText = flight === null
                ? (finiteNumber(jump.flight_frames) === null ? '--' : `${jump.flight_frames} 帧`)
                : `${flight.toFixed(2)}s`;
            const jumpNumber = jump.jump_number || index + 1;
            const deduction = deductionMap.get(Number(jumpNumber));
            const checked = selectedScoreJumpNumbers.has(Number(jumpNumber)) ? ' checked' : '';
            return `
                <tr>
                    <td class="score-select-col${scoreSelectionEditing ? '' : ' hidden'}"><input class="score-jump-checkbox" type="checkbox" data-jump-number="${jumpNumber}"${checked}></td>
                    <td><span class="jump-number-cell"><b>${jumpNumber}</b>${renderScoreDetailButton(deduction)}</span></td>
                    <td>${jump.action || '--'}</td>
                    <td>${flightText}</td>
                    <td>${landing.coord}</td>
                    <td>${landing.confidence}</td>
                    <td>${jump.is_intermediate ? '过渡' : '有效'}</td>
                </tr>
            `;
        }).join('');
        jumpTableBody.querySelectorAll('.score-jump-checkbox').forEach(input => {
            input.addEventListener('change', () => {
                const jumpNumber = Number(input.dataset.jumpNumber);
                if (input.checked) {
                    selectedScoreJumpNumbers.add(jumpNumber);
                } else {
                    selectedScoreJumpNumbers.delete(jumpNumber);
                }
                updateScoreSelectionCount();
            });
        });
        toggleScoreSelectionColumns(scoreSelectionEditing);
        sequenceStep.classList.remove('hidden');
    }

    function resetStats() {
        statReps.textContent = '0';
        statFlightTime.textContent = '--';
        statAction.textContent = '--';
        statAction.className = 'stat-value action-name';
        statLanding.textContent = '--';
        renderLandingMap([]);
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
        setText(jumpCount, '0');
        setText(sequenceJumpCount, '0');
        setText(sequenceTotal, '0');
        setText(sequenceTransition, '0');
        setText(sequenceActionBreakdown, '--');
        setText(sequenceDuration, '处理耗时：--');
        if (sequenceStep) sequenceStep.classList.add('hidden');
        if (jumpTableBody) jumpTableBody.innerHTML = '<tr><td colspan="6">完成分析后显示动作序列</td></tr>';
        clearScorePlaceholders();
        renderFlightChart({});
    }

    function stopAnalysis() {
        isAnalyzing = false;
        lastProgress = 0;
        if (analysisInterval) {
            clearInterval(analysisInterval);
            analysisInterval = null;
        }
        videoPlayer.pause();
        analyzeBtn.disabled = !videoFile;
        stopAnalysisBtn.disabled = true;
    }

    function simpleMd(text) {
        return text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^## (.+)$/gm, '<div style="font-weight:700;color:#00d4aa;margin:8px 0 4px">$1</div>')
            .replace(/\n/g, '<br>');
    }

    const llmSectionOrder = ['整体表现', '主要问题', '逐跳点评', '改进建议'];

    function escapeHtml(value) {
        return String(value ?? '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function findJumpAction(jumpNumber, fallbackText = '') {
        const jumps = analysisResults.completedJumps || [];
        const numeric = Number(jumpNumber);
        const jump = jumps.find(item => Number(item?.jump_number) === numeric)
            || jumps.filter(item => item && !item.is_intermediate)[numeric - 1];
        if (jump?.action) return jump.action;
        const match = String(fallbackText).match(/第\s*\d+\s*跳[：:\s，,]*(.+?)(?:[，,。；;（(]|\n|$)/);
        return match ? match[1].trim() : '--';
    }

    function parseJumpDetailItems(text) {
        const source = String(text || '').trim();
        if (!source) return [];
        const matches = [...source.matchAll(/第\s*(\d+)\s*跳/g)];
        if (!matches.length) return [];
        return matches.map((match, idx) => {
            const start = match.index || 0;
            const end = idx + 1 < matches.length ? matches[idx + 1].index : source.length;
            const detail = source.slice(start, end).trim();
            return {
                jumpNumber: Number(match[1]),
                action: findJumpAction(match[1], detail),
                detail,
            };
        });
    }

    function renderJumpDetailPanel(text) {
        const items = parseJumpDetailItems(text);
        if (!items.length) {
            return simpleMd(text || 'AI 未生成此部分');
        }
        return `<div class="llm-jump-list">${items.map(item => `
            <div class="llm-jump-item" tabindex="0">
                <span class="llm-jump-index">第 ${item.jumpNumber} 跳</span>
                <span class="llm-jump-action">${escapeHtml(item.action)}</span>
                <div class="llm-jump-detail-popover">${simpleMd(item.detail)}</div>
            </div>
        `).join('')}</div>`;
    }

    function renderLlmSection(sectionName = analysisResults.activeLlmSection || '整体表现') {
        analysisResults.activeLlmSection = sectionName;
        llmTabs.forEach(tab => {
            const active = tab.dataset.llmSection === sectionName;
            tab.classList.toggle('active', active);
            tab.setAttribute('aria-selected', String(active));
        });
        if (!llmActivePanel) return;
        const content = (analysisResults.llmSections && analysisResults.llmSections[sectionName]) || '';
        llmActivePanel.innerHTML = sectionName === '逐跳点评'
            ? renderJumpDetailPanel(content)
            : (content ? simpleMd(content) : '<span style="color:#999">AI 未生成此部分</span>');
    }

    function setLlmSections(sections = {}, fullText = '', source = '') {
        analysisResults.llmSections = {};
        llmSectionOrder.forEach(name => {
            analysisResults.llmSections[name] = sections[name] || '';
        });
        analysisResults.llmFullText = fullText || '';
        analysisResults.llmSource = source || '';

        const sectionMap = {
            '整体表现': 'llm-card-overview',
            '主要问题': 'llm-card-issues',
            '逐跳点评': 'llm-card-details',
            '改进建议': 'llm-card-suggestions',
        };
        for (const [heading, cardId] of Object.entries(sectionMap)) {
            const card = document.getElementById(cardId);
            if (!card) continue;
            const body = card.querySelector('.llm-card-body');
            const content = analysisResults.llmSections[heading] || '';
            if (body) body.innerHTML = content ? simpleMd(content) : '<span style="color:#999">AI 未生成此部分</span>';
        }
        renderLlmSection('整体表现');
    }

    function resetLlmResults() {
        analysisResults.llmSections = {};
        analysisResults.llmFullText = '';
        analysisResults.llmSource = '';
        analysisResults.activeLlmSection = '整体表现';
        if (llmActivePanel) llmActivePanel.innerHTML = '';
        llmTabs.forEach(tab => {
            const active = tab.dataset.llmSection === '整体表现';
            tab.classList.toggle('active', active);
            tab.setAttribute('aria-selected', String(active));
        });
    }

    function formatAiReportText() {
        const hasSections = analysisResults.llmSections
            && llmSectionOrder.some(name => (analysisResults.llmSections[name] || '').trim());
        if (!hasSections && !analysisResults.llmFullText) {
            return 'AI 分析：尚未生成';
        }
        const sectionText = llmSectionOrder.map(name => {
            const content = (analysisResults.llmSections[name] || '').trim() || '未生成';
            return `${name}\n${content}`;
        }).join('\n\n');
        const fullText = analysisResults.llmFullText
            ? `\n\nAI 原文\n${analysisResults.llmFullText}`
            : '';
        return `${sectionText}${fullText}`;
    }

    function formatScoreReportText() {
        const score = analysisResults.score;
        if (!score) return '视觉量化评分：尚未生成';
        const components = score.components || {};
        const lines = [
            `评分状态：${score.status || '--'}`,
            `选中跳次：${(score.selected_jump_numbers || []).join(', ') || '--'}`,
            `D：${formatScoreValue(components.D)}`,
            `E：${formatScoreValue(components.E)}`,
            `T：${formatScoreValue(components.T)}`,
            `H：${formatScoreValue(components.H)}`,
            `P：${formatScoreValue(components.P)}`,
            `总分：${formatScoreValue(components.total)}`,
        ];
        const deductions = (score.deductions || []).map(row => {
            const notes = Array.isArray(row.notes) ? row.notes.join('；') : '';
            return `第 ${row.jump_number} 跳 ${row.action}: D=${formatScoreValue(row.difficulty)}, T=${formatScoreValue(row.flight_s)}s, H扣=${formatScoreValue(row.h_deduction)}, E扣=${formatScoreValue(row.e_deduction)} ${notes}`;
        });
        return `${lines.join('\n')}${deductions.length ? `\n\n逐跳评分依据\n${deductions.join('\n')}` : ''}`;
    }

    const { finiteNumber, validLanding, resolveCompactStats } = videoAnalysisHelpers;

    function formatFixed(value, digits = 2) {
        const n = finiteNumber(value);
        return n === null ? '--' : n.toFixed(digits);
    }

    function getCompletedRealJumps(data = {}) {
        const jumps = data.completed_jumps || analysisResults.completedJumps || [];
        return Array.isArray(jumps) ? jumps.filter(j => j && !j.is_intermediate) : [];
    }

    function formatLandingText(landing) {
        const valid = validLanding(landing);
        if (!valid) return '--';
        const xy = Array.isArray(valid.bed_xy_m) ? valid.bed_xy_m : null;
        const coord = xy && finiteNumber(xy[0]) !== null && finiteNumber(xy[1]) !== null
            ? `(${formatFixed(xy[0])}, ${formatFixed(xy[1])})m`
            : '坐标 --';
        const conf = finiteNumber(valid.confidence);
        return `${coord} / conf ${conf === null ? '--' : conf.toFixed(2)}`;
    }

    function landingDotClass(landing, isLatest) {
        const conf = finiteNumber(landing?.confidence);
        const confidenceClass = conf === null || conf >= 0.6 ? 'high' : (conf >= 0.35 ? 'medium' : 'low');
        return `landing-dot ${confidenceClass}${isLatest ? ' latest' : ''}`;
    }

    function renderLandingMap(landings) {
        if (!landingMap || !landingMapBed) return;
        landingMapBed.querySelectorAll('.landing-dot').forEach(dot => dot.remove());
        const validLandings = (Array.isArray(landings) ? landings : []).filter(validLanding).slice(-20);
        landingMap.classList.toggle('has-landings', validLandings.length > 0);
        validLandings.forEach((landing, idx) => {
            const norm = Array.isArray(landing.norm_xy) ? landing.norm_xy : null;
            if (!norm || finiteNumber(norm[0]) === null || finiteNumber(norm[1]) === null) return;
            const dot = document.createElement('span');
            dot.className = landingDotClass(landing, idx === validLandings.length - 1);
            const x = Math.max(0, Math.min(1, Number(norm[0]))) * 100;
            const y = Math.max(0, Math.min(1, Number(norm[1]))) * 100;
            dot.style.left = `${x}%`;
            dot.style.top = `${y}%`;
            dot.title = formatLandingText(landing);
            landingMapBed.appendChild(dot);
        });
    }

    function resolveFlightSeconds(jump, fps) {
        const explicit = finiteNumber(jump?.flight_duration_s);
        if (explicit !== null) return explicit;
        const frames = finiteNumber(jump?.flight_frames);
        const rate = finiteNumber(fps);
        if (frames !== null && rate !== null && rate > 0) {
            return frames / rate;
        }
        return null;
    }

    function renderFlightChart(data = {}) {
        if (!flightChart) return;
        const fps = data.fps || data.video_fps || videoPlayer.dataset.fps || 30;
        const allJumps = Array.isArray(data.completed_jumps)
            ? data.completed_jumps
            : analysisResults.completedJumps;
        const values = (Array.isArray(allJumps) ? allJumps : [])
            .filter(jump => jump && !jump.is_intermediate)
            .map(jump => resolveFlightSeconds(jump, fps))
            .filter(value => value !== null);

        const current = finiteNumber(data.current_flight_duration_s);
        if (current !== null && current > 0 && values.length < 10) {
            values.push(current);
        }

        const visible = values.slice(-10);
        const w = 410;
        const h = 170;
        const left = 35;
        const right = 12;
        const top = 14;
        const bottom = 35;
        const chartWidth = w - left - right;
        const chartHeight = h - top - bottom;
        const maxValue = Math.max(2, ...visible.map(v => Math.ceil(v * 10) / 10));
        const x = i => left + (chartWidth / 9) * i;
        const y = value => top + chartHeight - (Math.max(0, Math.min(maxValue, value)) / maxValue) * chartHeight;

        let output = '';
        for (let i = 0; i <= 4; i++) {
            const yy = top + (chartHeight / 4) * i;
            const label = (maxValue - (maxValue / 4) * i).toFixed(1);
            output += `<line class="chart-grid" x1="${left}" y1="${yy}" x2="${w - right}" y2="${yy}"></line>`;
            output += `<text class="chart-label" x="4" y="${yy + 4}">${label}</text>`;
        }
        output += `<line class="chart-axis" x1="${left}" y1="${top}" x2="${left}" y2="${h - bottom}"></line>`;
        output += `<line class="chart-axis" x1="${left}" y1="${h - bottom}" x2="${w - right}" y2="${h - bottom}"></line>`;

        if (visible.length) {
            const points = visible.map((value, i) => ({ x: x(i), y: y(value), value }));
            output += `<path class="chart-line" d="${points.map((point, i) => `${i ? 'L' : 'M'}${point.x} ${point.y}`).join(' ')}"></path>`;
            points.forEach((point, i) => {
                output += `<circle class="chart-dot" cx="${point.x}" cy="${point.y}" r="4"></circle>`;
                output += `<text class="chart-value" x="${point.x - 11}" y="${point.y - 9}">${point.value.toFixed(2)}</text>`;
                output += `<text class="chart-label" x="${point.x - 3}" y="${h - 16}">${i + 1}</text>`;
            });
        } else {
            for (let i = 0; i < 10; i++) {
                output += `<circle class="chart-placeholder" cx="${x(i)}" cy="${y(maxValue * 0.55)}" r="3"></circle>`;
                output += `<text class="chart-label" x="${x(i) - 3}" y="${h - 16}">${i + 1}</text>`;
            }
        }

        output += `<text class="chart-label" x="${left}" y="${h - 3}">跳次</text>`;
        output += `<text class="chart-label" x="${w / 2 - 24}" y="${h - 3}">— 腾空时间</text>`;
        flightChart.innerHTML = output;
    }

    function showAnalysisSummary(data) {
        const jumps = data.completed_jumps || analysisResults.completedJumps || [];
        analysisResults.durationSeconds = analysisResults.endTime && analysisResults.startTime
            ? Math.round((analysisResults.endTime - analysisResults.startTime) / 1000)
            : 0;
        const summary = summarizeJumps(jumps);
        analysisResults.actionBreakdown = summary.actionBreakdown;
        analysisResults.transitionCount = summary.transitionCount;
        if (reportContent) {
            reportContent.textContent = '';
        }
        if (reportSection) reportSection.classList.add('hidden');
        if (llmSection) llmSection.classList.remove('hidden');
        if (aiWaiting) aiWaiting.classList.add('hidden');
        renderJumpSequence(data);
        renderScore(data.score || analysisResults.score);
        setWorkflowTab('results');
    }

    function updateStats(data) {
        if (data.reps !== undefined) {
            statReps.textContent = data.reps;
            analysisResults.reps = data.reps;
            setText(jumpCount, String(data.reps));
        }
        if (Array.isArray(data.completed_jumps)) {
            analysisResults.completedJumps = data.completed_jumps;
        }

        const compactStats = resolveCompactStats(
            data,
            analysisResults.completedJumps,
        );
        statFlightTime.textContent = compactStats.flightSeconds === null ? '--' : `${compactStats.flightSeconds.toFixed(2)}s`;
        statAction.textContent = compactStats.action || '--';
        statAction.className = `stat-value action-name action-${String(compactStats.action || 'unknown').toLowerCase()}`;
        statLanding.textContent = formatLandingText(compactStats.landing);

        const sourceLandings = Array.isArray(data.landings)
            ? data.landings
            : getCompletedRealJumps(data).map(j => j.landing).filter(Boolean);
        const landings = sourceLandings.slice();
        if (compactStats.landing && !landings.includes(compactStats.landing)) {
            landings.push(compactStats.landing);
        }
        renderLandingMap(landings);
        renderFlightChart(data);
        if (data.score) renderScore(data.score);
    }

    function startAnalysisPolling(videoId) {
        currentVideoId = videoId;
        setProcessState('processing', '处理中');
        setStage('processing', '处理中', '<p>步骤：<strong>视频分析</strong></p><p>正在识别跳次、动作和落点</p>');
        setCalibrationStatus('分析中');
        if (sequenceStep) sequenceStep.classList.add('hidden');
        analysisCanvas.width = videoPlayer.videoWidth || 640;
        analysisCanvas.height = videoPlayer.videoHeight || 480;
        analysisCanvas.hidden = true;
        const videoContainer = document.getElementById('video-container');
        if (videoContainer) videoContainer.classList.remove('calibration-active');
        ctx.clearRect(0, 0, analysisCanvas.width, analysisCanvas.height);

        videoPlayer.currentTime = 0;
        videoPlayer.play();

        analysisInterval = setInterval(async () => {
            if (!isAnalyzing) {
                clearInterval(analysisInterval);
                return;
            }

            try {
                const response = await fetch(`/api/video/status/${videoId}`);
                const data = await response.json();

                if (data.status === 'processing') {
                    progressFill.style.width = `${data.progress}%`;
                    progressText.textContent = `处理中：${Math.round(data.progress)}%`;
                    setText(progressStage, `正在分析视频：${Math.round(data.progress)}%`);
                    const currentProgress = Math.floor(data.progress / 10) * 10;
                    if (currentProgress > lastProgress && currentProgress > 0) {
                        addLog(`进度：${currentProgress}% | 跳次：${data.reps || 0} | 动作：${data.current_action || '--'}`, 'progress');
                        lastProgress = currentProgress;
                    }
                    updateStats(data);
                } else if (data.status === 'completed') {
                    clearInterval(analysisInterval);
                    analysisResults.endTime = new Date();
                    analysisResults.completedJumps = data.completed_jumps || [];
                    updateStats(data);
                    progressFill.style.width = '100%';
                    progressText.textContent = '100%';
                    setProcessState('success', '分析完成');
                    setStage('completed', '分析完成', '<p>步骤：<strong>分析完成</strong></p><p>可查看动作序列、落点图和 AI 建议</p>');
                    setCalibrationStatus('已完成');
                    addLog('分析完成。', 'success');
                    addFeedback('success', '分析完成，正在展示结果');
                    setTerminalStatus('Completed', 'success');
                    if (data.has_processed_video && data.processed_video_url) {
                        videoPlayer.src = data.processed_video_url;
                        videoPlayer.load();
                        videoPlayer.play();
                    }
                    showAnalysisSummary(data);
                    stopAnalysis();
                } else if (data.status === 'error') {
                    clearInterval(analysisInterval);
                    setProcessState('error', '分析失败');
                    setStage('error', '分析失败', '<p>步骤：<strong>处理失败</strong></p><p>请查看日志反馈</p>');
                    addLog(`分析失败：${data.error}`, 'error');
                    addFeedback('error', `分析失败：${data.error}`);
                    setTerminalStatus('Error', 'error');
                    stopAnalysis();
                }
            } catch (error) {
                addLog(`轮询失败：${error.message}`, 'warning');
            }
        }, 200);
    }

    function resetPageState() {
        stopAnalysis();
        videoPlayer.hidden = true;
        videoPlayer.pause();
        videoPlayer.src = '';
        uploadArea.hidden = false;
        analysisCanvas.hidden = true;
        if (trampolineCalibrationController) trampolineCalibrationController.reset();
        videoFile = null;
        currentVideoId = null;
        playBtn.disabled = true;
        analyzeBtn.disabled = true;
        resetBtn.disabled = true;
        reportSection.classList.add('hidden');
        feedbackLog.innerHTML = '<div class="feedback-item info"><span class="feedback-time">--:--</span><span class="feedback-text">上传蹦床视频并开始分析后，这里会记录后台消息。</span></div>';
        if (llmEventSource) {
            llmEventSource.close();
            llmEventSource = null;
        }
        llmSection.classList.remove('hidden');
        llmStreaming.classList.add('hidden');
        llmCards.classList.add('hidden');
        llmCards.classList.remove('visible');
        llmStreamingText.innerHTML = '';
        llmToggleRaw.classList.add('hidden');
        llmBtn.disabled = true;
        resetLlmResults();
        if (aiWaiting) aiWaiting.classList.remove('hidden');
        setProcessState('idle', '等待上传');
        setStage('upload', '等待上传', '<p>步骤：<strong>上传视频</strong></p><p>完成后进入床面四角标定</p>');
        setCalibrationStatus('待上传');
        setText(filenameEl, '未选择');
        clearScorePlaceholders();
        resetStats();
        setWorkflowTab('calibration');
    }

    function handleVideoFile(file) {
        videoFile = file;
        videoPlayer.src = URL.createObjectURL(file);
        videoPlayer.hidden = false;
        uploadArea.hidden = true;
        playBtn.disabled = false;
        analyzeBtn.disabled = false;
        resetBtn.disabled = false;
        setText(filenameEl, file.name);
        setProcessState('ready', '视频已载入');
        setStage('ready', '待上传', '<p>步骤：<strong>视频预览</strong></p><p>点击“上传并进入标定”开始床面标定</p>');
        setCalibrationStatus('待上传');
        addLog(`已加载视频：${file.name}`, 'success');
        addLog(`文件大小：${(file.size / (1024 * 1024)).toFixed(2)} MB`, 'info');
        addFeedback('info', `已加载视频：${file.name}`);
    }

    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        videoInput.click();
    });
    uploadArea.addEventListener('click', () => videoInput.click());
    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    uploadArea.addEventListener('dragleave', () => uploadArea.classList.remove('dragover'));
    uploadArea.addEventListener('drop', (e) => {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const files = e.dataTransfer.files;
        if (files.length > 0 && files[0].type.startsWith('video/')) {
            handleVideoFile(files[0]);
        }
    });
    videoInput.addEventListener('change', (e) => {
        if (e.target.files.length > 0) {
            handleVideoFile(e.target.files[0]);
        }
    });

    playBtn.addEventListener('click', () => {
        if (videoPlayer.paused) {
            videoPlayer.play();
            playBtn.textContent = '⏸️ Pause';
        } else {
            videoPlayer.pause();
            playBtn.textContent = '▶️ Play';
        }
    });
    videoPlayer.addEventListener('play', () => {
        playBtn.textContent = '⏸️ Pause';
    });
    videoPlayer.addEventListener('pause', () => {
        playBtn.textContent = '▶️ Play';
    });
    videoPlayer.addEventListener('timeupdate', () => {
        if (!isAnalyzing && videoPlayer.duration && !Number.isNaN(videoPlayer.duration)) {
            const progress = (videoPlayer.currentTime / videoPlayer.duration) * 100;
            progressFill.style.width = `${progress}%`;
            progressText.textContent = `${Math.round(progress)}%`;
        }
    });

    resetBtn.addEventListener('click', resetPageState);

    analyzeBtn.addEventListener('click', async () => {
        if (!videoFile) return;

        isAnalyzing = true;
        analyzeBtn.disabled = true;
        stopAnalysisBtn.disabled = false;
        analysisResults = {
            reps: 0,
            feedbacks: [],
            startTime: new Date(),
            endTime: null,
            completedJumps: [],
            durationSeconds: 0,
            actionBreakdown: '—',
            transitionCount: 0,
            llmSections: {},
            llmFullText: '',
            llmSource: '',
            activeLlmSection: '整体表现',
            score: null,
        };
        clearScorePlaceholders();
        setProcessState('processing', '上传中');
        setStage('uploading', '上传中', '<p>步骤：<strong>上传视频</strong></p><p>正在提取首帧并准备标定</p>');
        setCalibrationStatus('待标定');
        if (sequenceStep) sequenceStep.classList.add('hidden');

        setTerminalStatus('Processing', 'running');
        addLog('开始蹦床视频分析...', 'processing');
        addLog(`视频文件：${videoFile.name}`, 'info');
        addFeedback('info', '正在上传视频，请稍候');

        const formData = new FormData();
        formData.append('video', videoFile);
        formData.append('exercise_type', 'trampoline');

        try {
            const response = await fetch('/api/video/upload', { method: 'POST', body: formData });
            const data = await response.json();
            if (!data.success) {
                addLog(`上传失败：${data.error}`, 'error');
                addFeedback('error', `上传失败：${data.error}`);
                setTerminalStatus('Error', 'error');
                setProcessState('error', '上传失败');
                setStage('error', '上传失败', '<p>步骤：<strong>上传失败</strong></p><p>请查看反馈后重新选择视频</p>');
                stopAnalysis();
                return;
            }

            addLog(`上传完成，视频 ID：${data.video_id}`, 'success');
            currentVideoId = data.video_id;
            isAnalyzing = false;
            stopAnalysisBtn.disabled = true;
            setProcessState('idle', '等待标定');
            setStage('calibration', '床面标定', '<p>步骤：<strong>床面四角标定</strong></p><p>顺序：<strong>前左 → 前右 → 后右 → 后左</strong></p><p>添加当前帧后点击视频标记角点</p>');
            setCalibrationStatus('标定中');
            setWorkflowTab('calibration');
            addLog('请先完成床面关键帧标定，再启动分析。', 'info');
            addFeedback('info', '请预览/暂停视频，在一个或多个关键帧标记床面四角后开始分析');
            if (!trampolineCalibrationController) {
                throw new Error('Trampoline calibration UI failed to initialize');
            }
            trampolineCalibrationController.enterPendingCalibration({
                videoId: data.video_id,
                imageSrc: data.first_frame_image || `data:image/png;base64,${data.first_frame_b64}`,
                videoFps: data.video_fps,
            });
        } catch (error) {
            addLog(`网络错误：${error.message}`, 'error');
            addFeedback('error', 'Failed to upload video');
            setTerminalStatus('Error', 'error');
            setProcessState('error', '上传失败');
            setStage('error', '上传失败', '<p>步骤：<strong>上传失败</strong></p><p>请查看反馈后重试</p>');
            stopAnalysis();
        }
    });

    stopAnalysisBtn.addEventListener('click', () => {
        addLog('用户手动停止分析。', 'warning');
        addFeedback('info', '分析已停止');
        setTerminalStatus('Stopped', 'idle');
        stopAnalysis();
    });

    function initTrampolineCalibrationController() {
        if (!trampolineCalibrationUi || !calibrationGeometry) {
            addLog('Trampoline calibration UI failed to load.', 'error');
            return;
        }
        trampolineCalibrationController = trampolineCalibrationUi.createController({
            documentRef: document,
            videoPlayer,
            analysisCanvas,
            geometry: calibrationGeometry,
            onLog: addLog,
            onFeedback: addFeedback,
            onProcessingStart: ({ videoId }) => {
                isAnalyzing = true;
                analysisResults.startTime = new Date();
                stopAnalysisBtn.disabled = false;
                setTerminalStatus('Processing', 'running');
                setProcessState('processing', '处理中');
                setStage('processing', '处理中', '<p>步骤：<strong>视频分析</strong></p><p>正在识别跳次、动作和落点</p>');
                setCalibrationStatus('分析中');
                startAnalysisPolling(videoId);
            },
        });
    }

    if (llmBtn) {
        llmBtn.addEventListener('click', () => {
            if (!currentVideoId) return;
            llmBtn.disabled = true;
            if (llmEventSource) {
                llmEventSource.close();
                llmEventSource = null;
            }

            llmStreaming.classList.remove('hidden');
            llmStreaming.classList.remove('collapsed');
            llmStreamingText.innerHTML = '';
            llmCards.classList.add('hidden');
            llmCards.classList.remove('visible');
            llmToggleRaw.classList.add('hidden');
            resetLlmResults();

            let finished = false;
            const header = llmStreaming.querySelector('.llm-streaming-header');
            if (header) {
                header.innerHTML = '<span class="llm-status-dot"></span><span>正在分析...</span>';
            }
            llmEventSource = new EventSource(`/api/video/llm_analysis/${currentVideoId}`);
            llmEventSource.onmessage = function(e) {
                let data;
                try { data = JSON.parse(e.data); } catch { return; }
                if (data.type === 'chunk') {
                    llmStreamingText.innerHTML += simpleMd(data.text);
                    llmStreamingText.scrollTop = llmStreamingText.scrollHeight;
                } else if (data.type === 'fast_done') {
                    if (header) {
                        header.innerHTML = '<span class="llm-status-dot llm-quality-waiting"></span><span>正在生成高质量分析...</span>';
                    }
                } else if (data.type === 'fast_error') {
                    if (header) {
                        header.innerHTML = '<span class="llm-status-dot llm-quality-waiting"></span><span>快速模型失败，继续等待高质量模型...</span>';
                    }
                    const warningText = `${data.message || '快速模型失败，继续等待高质量模型'}${data.hint ? `\n${data.hint}` : ''}`;
                    llmStreamingText.innerHTML += `<br><span style="color:#f39c12; white-space: pre-wrap">${escapeHtml(warningText)}</span>`;
                    llmStreamingText.scrollTop = llmStreamingText.scrollHeight;
                } else if (data.type === 'done') {
                    finished = true;
                    llmEventSource.close();
                    llmEventSource = null;
                    setLlmSections(data.sections || {}, data.full_text || '', data.source || '');
                    llmStreaming.classList.add('collapsed');
                    llmCards.classList.remove('hidden');
                    requestAnimationFrame(() => llmCards.classList.add('visible'));
                    llmToggleRaw.classList.remove('hidden');
                    llmBtn.disabled = false;
                } else if (data.type === 'error') {
                    finished = true;
                    llmEventSource.close();
                    llmEventSource = null;
                    if (header) {
                        header.innerHTML = '<span class="llm-status-dot"></span><span>AI 分析失败</span>';
                    }
                    llmStreamingText.innerHTML += `<br><span style="color:#e74c3c; white-space: pre-wrap">${escapeHtml(formatLlmErrorMessage(data))}</span>`;
                    llmBtn.disabled = false;
                }
            };
            llmEventSource.onerror = function() {
                if (finished) return;
                llmEventSource.close();
                llmEventSource = null;
                llmStreamingText.innerHTML += '<br><span style="color:#e74c3c">连接中断</span>';
                llmBtn.disabled = false;
            };
        });
    }

    if (llmToggleRaw) {
        llmToggleRaw.addEventListener('click', () => {
            const collapsed = llmStreaming.classList.contains('collapsed');
            llmStreaming.classList.toggle('collapsed', !collapsed);
            llmToggleRaw.textContent = collapsed ? '折叠原文' : '展开原文';
        });
    }

    llmTabs.forEach(tab => {
        tab.addEventListener('click', () => renderLlmSection(tab.dataset.llmSection || '整体表现'));
    });

    if (showCalibrationBtn) {
        showCalibrationBtn.addEventListener('click', () => setWorkflowTab('calibration'));
    }

    if (showResultsBtn) {
        showResultsBtn.addEventListener('click', () => setWorkflowTab('results'));
    }

    if (confirmScoreSelectionBtn) {
        confirmScoreSelectionBtn.addEventListener('click', () => {
            const defaults = analysisResults.score?.default_selected_jump_numbers || [];
            submitScoreSelection(defaults);
        });
    }

    if (editScoreSelectionBtn) {
        editScoreSelectionBtn.addEventListener('click', () => {
            const defaults = analysisResults.score?.default_selected_jump_numbers || [];
            selectedScoreJumpNumbers = new Set(defaults);
            scoreSelectionEditing = true;
            setWorkflowTab('results');
            renderScore(analysisResults.score);
            renderJumpSequence({ completed_jumps: analysisResults.completedJumps, reps: analysisResults.reps });
        });
    }

    if (submitScoreSelectionBtn) {
        submitScoreSelectionBtn.addEventListener('click', () => {
            submitScoreSelection(selectedScoreJumpList());
        });
    }

    if (recalibrateBtn) {
        recalibrateBtn.addEventListener('click', () => {
            if (!videoFile) {
                addFeedback('warning', '请重新选择原始视频后再标定');
                return;
            }
            addFeedback('info', '正在重新上传原始视频以进入新一轮床面标定');
            handleVideoFile(videoFile);
            reportSection.classList.add('hidden');
            llmSection.classList.remove('hidden');
            llmBtn.disabled = true;
            llmStreaming.classList.add('hidden');
            llmCards.classList.add('hidden');
            llmCards.classList.remove('visible');
            llmStreamingText.innerHTML = '';
            llmToggleRaw.classList.add('hidden');
            resetLlmResults();
            if (aiWaiting) aiWaiting.classList.remove('hidden');
            setWorkflowTab('calibration');
            analyzeBtn.click();
        });
    }

    downloadReportBtn.addEventListener('click', () => {
        const jumps = analysisResults.completedJumps || [];
        const realJumps = jumps.filter(j => !j.is_intermediate);
        const reportText = `
蹦床视频分析报告
==============================
时间：${new Date().toLocaleString()}
视频：${videoFile ? videoFile.name : 'Unknown'}

结果摘要
------------------------------
总跳次：${analysisResults.reps}
过渡跳：${analysisResults.transitionCount}
动作分布：${analysisResults.actionBreakdown}
处理耗时：${analysisResults.durationSeconds ? `${analysisResults.durationSeconds}s` : '--'}

视觉量化评分
------------------------------
${formatScoreReportText()}

逐跳明细
------------------------------
${realJumps.map((j, i) => {
            const landing = j.landing;
            const landingText = landing
                ? ` | 落点=(${(landing.bed_xy_m || [])[0]}, ${(landing.bed_xy_m || [])[1]})m ${landing.zone || ''} conf=${landing.confidence}`
                : '';
            return `第 ${j.jump_number || (i + 1)} 跳：${j.action}（腾空 ${j.flight_frames} 帧）${landingText}`;
        }).join('\n')}

反馈日志
------------------------------
${analysisResults.feedbacks.map(f => `[${f.time}] ${f.type.toUpperCase()}: ${f.message}`).join('\n')}

AI 分析
------------------------------
${formatAiReportText()}
        `;
        const blob = new Blob([reportText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `trampoline_report_${Date.now()}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    });

    if (terminalToggle) {
        terminalToggle.addEventListener('click', function() {
            terminalBody.classList.toggle('collapsed');
            terminalToggle.classList.toggle('collapsed');
        });
    }

    clearScorePlaceholders();
    renderFlightChart({});
    setProcessState('idle', '等待上传');
    setStage('upload', '等待上传', '<p>步骤：<strong>上传视频</strong></p><p>完成后进入床面四角标定</p>');
    setCalibrationStatus('待上传');
    setWorkflowTab('calibration');
    addLog('系统已初始化，等待上传蹦床视频。', 'info');
    initTrampolineCalibrationController();
});
