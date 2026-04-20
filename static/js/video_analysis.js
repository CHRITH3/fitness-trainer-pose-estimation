// Trampoline-only video analysis page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    const uploadArea = document.getElementById('upload-area');
    const videoInput = document.getElementById('video-input');
    const browseBtn = document.getElementById('browse-btn');
    const videoPlayer = document.getElementById('video-player');
    const analysisCanvas = document.getElementById('analysis-canvas');
    const ctx = analysisCanvas.getContext('2d');

    const playBtn = document.getElementById('play-btn');
    const analyzeBtn = document.getElementById('analyze-btn');
    const stopAnalysisBtn = document.getElementById('stop-analysis-btn');
    const resetBtn = document.getElementById('reset-btn');
    const progressFill = document.getElementById('progress-fill');
    const progressText = document.getElementById('progress-text');

    const statReps = document.getElementById('stat-reps');
    const statScore = document.getElementById('stat-score');
    const statGrade = document.getElementById('stat-grade');
    const statState = document.getElementById('stat-state');
    const statAction = document.getElementById('stat-action');
    const gaugeFill = document.getElementById('gauge-fill');
    const gaugeValue = document.getElementById('gauge-value');
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

    const calibrationGeometry = window.TrampolineCalibrationGeometry;
    const trampolineCalibrationUi = window.TrampolineCalibrationUI;

    let videoFile = null;
    let isAnalyzing = false;
    let analysisInterval = null;
    let currentVideoId = null;
    let trampolineCalibrationController = null;
    let llmEventSource = null;
    let lastProgress = 0;

    let analysisResults = {
        reps: 0,
        scores: [],
        feedbacks: [],
        startTime: null,
        endTime: null,
        completedJumps: [],
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

    function resetStats() {
        statReps.textContent = '0';
        statScore.textContent = '--';
        statGrade.textContent = '--';
        statGrade.className = 'stat-value grade';
        statState.textContent = '--';
        statAction.textContent = '--';
        statAction.className = 'stat-value action-name';
        gaugeValue.textContent = '--';
        gaugeFill.style.strokeDashoffset = 251.2;
        gaugeFill.style.stroke = '#27ae60';
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
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

    function showTrampolineReport(data) {
        const jumps = data.completed_jumps || analysisResults.completedJumps || [];
        const jumpCount = data.reps || jumps.length;
        const duration = analysisResults.endTime && analysisResults.startTime
            ? Math.round((analysisResults.endTime - analysisResults.startTime) / 1000)
            : 0;

        const actionCounts = {};
        const realJumps = jumps.filter(j => !j.is_intermediate);
        realJumps.forEach(j => {
            actionCounts[j.action] = (actionCounts[j.action] || 0) + 1;
        });
        const actionBreakdown = Object.entries(actionCounts)
            .map(([k, v]) => `${k}: ${v}`)
            .join('，') || '—';

        function fmtNum(value, digits = 2) {
            const n = Number(value);
            return Number.isFinite(n) ? n.toFixed(digits) : String(value ?? '?');
        }

        let jumpDetails = '';
        realJumps.forEach((jump, i) => {
            const landing = jump.landing;
            let landingText = '落点：--';
            if (landing) {
                const xy = landing.bed_xy_m || ['?', '?'];
                const conf = landing.confidence !== undefined ? Number(landing.confidence).toFixed(2) : '--';
                const low = landing.confidence !== undefined && Number(landing.confidence) < 0.5;
                landingText = `落点：(${fmtNum(xy[0])}, ${fmtNum(xy[1])})m / ${landing.zone || '--'} / conf ${conf}${low ? ' <span class="landing-low-confidence">低置信</span>' : ''}`;
            }
            jumpDetails += `
                <div class="report-row">
                    <span class="report-label">第 ${jump.jump_number || (i + 1)} 跳</span>
                    <span class="report-value">${jump.action} <span class="jump-flight-info">(${jump.flight_frames} 帧)</span><br><small>${landingText}</small></span>
                </div>`;
        });

        const intermediateCount = jumps.filter(j => j.is_intermediate).length;

        reportContent.innerHTML = `
            <div class="report-row"><span class="report-label">分析类型</span><span class="report-value">蹦床</span></div>
            <div class="report-row"><span class="report-label">总跳次</span><span class="report-value">${jumpCount}</span></div>
            ${intermediateCount > 0 ? `<div class="report-row"><span class="report-label">中间过渡跳</span><span class="report-value">${intermediateCount}</span></div>` : ''}
            <div class="report-row"><span class="report-label">动作分布</span><span class="report-value">${actionBreakdown}</span></div>
            ${jumpDetails}
            <div class="report-row"><span class="report-label">处理耗时</span><span class="report-value">${duration}s</span></div>
        `;
        reportSection.classList.remove('hidden');
        llmSection.classList.remove('hidden');
        llmBtn.disabled = false;
    }

    function updateStats(data) {
        if (data.reps !== undefined) {
            statReps.textContent = data.reps;
            analysisResults.reps = data.reps;
        }
        if (data.form_score !== undefined) {
            const score = Math.round(data.form_score);
            statScore.textContent = score;
            gaugeValue.textContent = score;
            analysisResults.scores.push(score);
            gaugeFill.style.strokeDashoffset = 251.2 - (251.2 * score / 100);
        }
        if (data.grade !== undefined) {
            statGrade.textContent = data.grade;
            statGrade.className = `stat-value grade${data.grade ? ` grade-${String(data.grade).toLowerCase()}` : ''}`;
        }
        if (data.state !== undefined) {
            statState.textContent = data.state;
        }
        if (data.current_action !== undefined) {
            statAction.textContent = data.current_action;
            statAction.className = `stat-value action-name action-${String(data.current_action).toLowerCase()}`;
        }
    }

    function startAnalysisPolling(videoId) {
        currentVideoId = videoId;
        analysisCanvas.width = videoPlayer.videoWidth || 640;
        analysisCanvas.height = videoPlayer.videoHeight || 480;
        analysisCanvas.hidden = false;
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
                    addLog('分析完成。', 'success');
                    addFeedback('success', '分析完成，正在展示结果');
                    setTerminalStatus('Completed', 'success');
                    if (data.has_processed_video && data.processed_video_url) {
                        videoPlayer.src = data.processed_video_url;
                        videoPlayer.load();
                        videoPlayer.play();
                    }
                    showTrampolineReport(data);
                    stopAnalysis();
                } else if (data.status === 'error') {
                    clearInterval(analysisInterval);
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
        feedbackLog.innerHTML = '<div class="feedback-item info"><span class="feedback-time">--:--</span><span class="feedback-text">上传蹦床视频并开始分析后，这里会显示过程反馈。</span></div>';
        if (llmEventSource) {
            llmEventSource.close();
            llmEventSource = null;
        }
        llmSection.classList.add('hidden');
        llmStreaming.classList.add('hidden');
        llmCards.classList.add('hidden');
        llmCards.classList.remove('visible');
        llmStreamingText.innerHTML = '';
        llmToggleRaw.classList.add('hidden');
        llmBtn.disabled = true;
        resetStats();
    }

    function handleVideoFile(file) {
        videoFile = file;
        videoPlayer.src = URL.createObjectURL(file);
        videoPlayer.hidden = false;
        uploadArea.hidden = true;
        playBtn.disabled = false;
        analyzeBtn.disabled = false;
        resetBtn.disabled = false;
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
        analysisResults = { reps: 0, scores: [], feedbacks: [], startTime: new Date(), endTime: null, completedJumps: [] };

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
                stopAnalysis();
                return;
            }

            addLog(`上传完成，视频 ID：${data.video_id}`, 'success');
            currentVideoId = data.video_id;
            isAnalyzing = false;
            stopAnalysisBtn.disabled = true;
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

            let finished = false;
            llmEventSource = new EventSource(`/api/video/llm_analysis/${currentVideoId}`);
            llmEventSource.onmessage = function(e) {
                let data;
                try { data = JSON.parse(e.data); } catch { return; }
                if (data.type === 'chunk') {
                    llmStreamingText.innerHTML += simpleMd(data.text);
                    llmStreamingText.scrollTop = llmStreamingText.scrollHeight;
                } else if (data.type === 'fast_done') {
                    const header = llmStreaming.querySelector('.llm-streaming-header');
                    if (header) {
                        header.innerHTML = '<span class="llm-status-dot llm-quality-waiting"></span><span>正在生成高质量分析...</span>';
                    }
                } else if (data.type === 'done') {
                    finished = true;
                    llmEventSource.close();
                    llmEventSource = null;
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
                        const content = (data.sections && data.sections[heading]) || '';
                        body.innerHTML = content ? simpleMd(content) : '<span style="color:#999">AI 未生成此部分</span>';
                    }
                    llmStreaming.classList.add('collapsed');
                    llmCards.classList.remove('hidden');
                    requestAnimationFrame(() => llmCards.classList.add('visible'));
                    llmToggleRaw.classList.remove('hidden');
                    llmBtn.disabled = false;
                } else if (data.type === 'error') {
                    finished = true;
                    llmEventSource.close();
                    llmEventSource = null;
                    llmStreamingText.innerHTML += `<br><span style="color:#e74c3c">${data.message}</span>`;
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
过渡跳：${jumps.filter(j => j.is_intermediate).length}

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

    addLog('系统已初始化，等待上传蹦床视频。', 'info');
    initTrampolineCalibrationController();
});
