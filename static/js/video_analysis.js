// Video Analysis Page JavaScript

document.addEventListener('DOMContentLoaded', function() {
    // Mode detection
    const pageMode = document.querySelector('.container').dataset.mode || 'fitness';
    const isTrampolineMode = (pageMode === 'trampoline');

    // Elements
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

    const exerciseSelect = document.getElementById('exercise-select');
    const exerciseInfoPanel = document.getElementById('exercise-info-panel');
    const miniType = document.getElementById('mini-type');
    const miniDescription = document.getElementById('mini-description');

    const statReps = document.getElementById('stat-reps');
    const statScore = document.getElementById('stat-score');
    const statGrade = document.getElementById('stat-grade');
    const statState = document.getElementById('stat-state');
    const gaugeFill = document.getElementById('gauge-fill');
    const gaugeValue = document.getElementById('gauge-value');
    const feedbackLog = document.getElementById('feedback-log');
    const reportSection = document.getElementById('report-section');
    const reportContent = document.getElementById('report-content');
    const downloadReportBtn = document.getElementById('download-report-btn');

    // Terminal Elements
    const terminalContent = document.getElementById('terminal-content');
    const terminalStatus = document.getElementById('terminal-status');
    const terminalToggle = document.getElementById('terminal-toggle');
    const terminalBody = document.getElementById('terminal-body');

    // Trampoline Elements
    const actionCard = document.getElementById('action-card');
    const statAction = document.getElementById('stat-action');
    const cornerStep = document.getElementById('corner-marking-step');
    const cornerCanvas = document.getElementById('corner-canvas');
    const cornerCtx = cornerCanvas ? cornerCanvas.getContext('2d') : null;
    const cornerCount = document.getElementById('corner-count');
    const resetCornersBtn = document.getElementById('reset-corners');
    const saveKeyframeBtn = document.getElementById('save-keyframe');
    const addKeyframeBtn = document.getElementById('add-keyframe');
    const confirmCornersBtn = document.getElementById('confirm-corners');
    const keyframeListEl = document.getElementById('keyframe-list');
    const currentKeyframeLabel = document.getElementById('current-keyframe-label');
    const calibrationGeometry = window.TrampolineCalibrationGeometry;

    // LLM Elements
    const llmSection = document.getElementById('llm-section');
    const llmBtn = document.getElementById('llm-btn');
    const llmStreaming = document.getElementById('llm-streaming');
    const llmStreamingText = document.getElementById('llm-streaming-text');
    const llmCards = document.getElementById('llm-cards');
    const llmToggleRaw = document.getElementById('llm-toggle-raw');

    // State
    let videoFile = null;
    let isAnalyzing = false;
    let analysisInterval = null;
    let exercisesData = {};
    let currentVideoId = null;  // module-level for LLM access
    let pendingTrampolineVideoId = null;
    let cornerImage = null;
    let cornerImageSize = null;
    let cornerContentRect = null;
    let cornerPoints = [];
    let calibrationKeyframes = [];
    let activeKeyframeFrame = null;
    let pendingFrameImage = null;
    let uploadedFrameRate = 30;
    const cornerOrder = ['front_left', 'front_right', 'back_right', 'back_left'];
    const cornerLabels = ['前左', '前右', '后右', '后左'];
    let llmEventSource = null;
    let analysisResults = {
        reps: 0,
        scores: [],
        feedbacks: [],
        startTime: null,
        endTime: null,
        completedJumps: [],
    };

    // ==================== Mode Initialization ====================
    if (isTrampolineMode) {
        document.getElementById('fitness-selector').classList.add('hidden');
        document.getElementById('trampoline-selector').classList.remove('hidden');
        document.getElementById('count-label').textContent = 'Jumps';
        document.getElementById('state-label').textContent = 'Phase';
        actionCard.classList.remove('hidden');
    } else {
        loadExercises();
    }

    // ==================== Terminal/Log Functions ====================
    function getTimestamp() {
        const now = new Date();
        return now.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
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

    function clearTerminal() {
        terminalContent.innerHTML = '<div class="log-line info"><span class="timestamp">[' + getTimestamp() + ']</span> Terminal cleared. Ready for new analysis...</div>';
    }

    // Terminal toggle
    if (terminalToggle) {
        terminalToggle.addEventListener('click', function() {
            terminalBody.classList.toggle('collapsed');
            terminalToggle.classList.toggle('collapsed');
        });
    }

    // Initialize terminal
    addLog('System initialized. Ready for video upload.', 'info');

    // Exercise type info
    const exerciseTypeInfo = {
        'bilateral': { label: 'Bilateral', color: '#9b59b6', class: 'bilateral' },
        'duration': { label: 'Duration', color: '#e67e22', class: 'duration' },
        'standard': { label: 'Standard', color: '#3498db', class: 'standard' }
    };

    // Load exercises (fitness mode only)
    async function loadExercises() {
        try {
            addLog('Loading available exercises...', 'info');
            const response = await fetch('/exercises');
            const data = await response.json();
            exercisesData = data;

            data.exercises.forEach(exercise => {
                const info = data.info[exercise] || {};
                const option = document.createElement('option');
                option.value = exercise;
                option.textContent = info.name || exercise.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
                exerciseSelect.appendChild(option);
            });
            addLog(`Loaded ${data.exercises.length} exercises successfully.`, 'success');
        } catch (error) {
            console.error('Error loading exercises:', error);
            addLog(`Error loading exercises: ${error.message}`, 'error');
        }
    }

    // Exercise selection change (fitness mode)
    exerciseSelect.addEventListener('change', function() {
        const exercise = this.value;
        if (exercise && exercisesData.info[exercise]) {
            const info = exercisesData.info[exercise];
            const typeInfo = exerciseTypeInfo[info.type] || exerciseTypeInfo['standard'];
            addLog(`Selected exercise: ${info.name || exercise} (${info.type})`, 'info');

            miniType.textContent = typeInfo.label;
            miniType.className = `mini-badge ${typeInfo.class}`;
            miniDescription.textContent = info.description || 'No description available';
            exerciseInfoPanel.classList.remove('hidden');

            if (videoFile) {
                analyzeBtn.disabled = false;
            }
        } else {
            exerciseInfoPanel.classList.add('hidden');
            analyzeBtn.disabled = true;
        }
    });

    // File upload handling
    browseBtn.addEventListener('click', (e) => {
        e.stopPropagation();
        videoInput.click();
    });

    uploadArea.addEventListener('click', () => videoInput.click());

    uploadArea.addEventListener('dragover', (e) => {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });

    uploadArea.addEventListener('dragleave', () => {
        uploadArea.classList.remove('dragover');
    });

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

    function handleVideoFile(file) {
        videoFile = file;
        const url = URL.createObjectURL(file);
        videoPlayer.src = url;
        videoPlayer.hidden = false;
        uploadArea.hidden = true;

        playBtn.disabled = false;
        resetBtn.disabled = false;

        if (isTrampolineMode || exerciseSelect.value) {
            analyzeBtn.disabled = false;
        }

        const fileSizeMB = (file.size / (1024 * 1024)).toFixed(2);
        addLog(`Video file loaded: ${file.name}`, 'success');
        addLog(`File size: ${fileSizeMB} MB | Type: ${file.type}`, 'info');

        addFeedback('info', `Video loaded: ${file.name}`);
    }

    // Video controls
    playBtn.addEventListener('click', () => {
        if (videoPlayer.paused) {
            videoPlayer.play();
            playBtn.textContent = 'Pause';
        } else {
            videoPlayer.pause();
            playBtn.textContent = 'Play';
        }
    });

    videoPlayer.addEventListener('play', () => {
        playBtn.textContent = 'Pause';
    });

    videoPlayer.addEventListener('pause', () => {
        playBtn.textContent = 'Play';
    });

    videoPlayer.addEventListener('timeupdate', () => {
        if (!isAnalyzing && videoPlayer.duration && !isNaN(videoPlayer.duration)) {
            const progress = (videoPlayer.currentTime / videoPlayer.duration) * 100;
            progressFill.style.width = `${progress}%`;
            progressText.textContent = `${Math.round(progress)}%`;
        }
    });

    // Reset
    resetBtn.addEventListener('click', () => {
        stopAnalysis();
        videoPlayer.hidden = true;
        videoPlayer.src = '';
        uploadArea.hidden = false;
        analysisCanvas.hidden = true;
        if (cornerStep) cornerStep.classList.add('hidden');
        if (cornerCanvas && cornerCtx) cornerCtx.clearRect(0, 0, cornerCanvas.width, cornerCanvas.height);
        cornerContentRect = null;
        cornerImageSize = null;
        cornerPoints = [];
        calibrationKeyframes = [];
        activeKeyframeFrame = null;
        pendingFrameImage = null;
        pendingTrampolineVideoId = null;
        videoFile = null;

        playBtn.disabled = true;
        analyzeBtn.disabled = true;
        resetBtn.disabled = true;

        resetStats();
        reportSection.classList.add('hidden');
        feedbackLog.innerHTML = '<div class="feedback-item info"><span class="feedback-time">--:--</span><span class="feedback-text">Upload a video and start analysis to see feedback</span></div>';
        // Reset LLM
        if (llmEventSource) { llmEventSource.close(); llmEventSource = null; }
        currentVideoId = null;
        if (llmSection) llmSection.classList.add('hidden');
        if (llmStreaming) llmStreaming.classList.add('hidden');
        if (llmCards) { llmCards.classList.add('hidden'); llmCards.classList.remove('visible'); }
        if (llmStreamingText) llmStreamingText.innerHTML = '';
        if (llmToggleRaw) llmToggleRaw.classList.add('hidden');
        if (llmBtn) llmBtn.disabled = true;
    });

    // Start Analysis
    analyzeBtn.addEventListener('click', async () => {
        if (!videoFile) return;
        if (!isTrampolineMode && !exerciseSelect.value) return;

        isAnalyzing = true;
        analyzeBtn.disabled = true;
        stopAnalysisBtn.disabled = false;
        if (!isTrampolineMode) exerciseSelect.disabled = true;

        analysisResults = {
            reps: 0,
            scores: [],
            feedbacks: [],
            startTime: new Date(),
            endTime: null,
            completedJumps: [],
        };

        // Terminal logs
        setTerminalStatus('Processing', 'running');
        addLog('Starting video analysis...', 'processing');
        if (isTrampolineMode) {
            addLog('Mode: Trampoline Analysis', 'info');
        } else {
            addLog(`Exercise: ${exerciseSelect.options[exerciseSelect.selectedIndex].text}`, 'info');
        }
        addLog(`Video: ${videoFile.name}`, 'info');

        const analysisLabel = isTrampolineMode ? 'Trampoline Analysis' :
            exerciseSelect.options[exerciseSelect.selectedIndex].text;
        addFeedback('info', `Starting analysis: ${analysisLabel}`);

        // Upload video and start analysis
        const formData = new FormData();
        formData.append('video', videoFile);
        formData.append('exercise_type', isTrampolineMode ? 'trampoline' : exerciseSelect.value);

        addLog('Uploading video to server...', 'processing');

        try {
            const response = await fetch('/api/video/upload', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            if (data.success) {
                addLog(`Upload complete. Video ID: ${data.video_id}`, 'success');
                if (isTrampolineMode && data.status === 'uploaded_pending_calibration') {
                    pendingTrampolineVideoId = data.video_id;
                    currentVideoId = data.video_id;
                    isAnalyzing = false;
                    stopAnalysisBtn.disabled = true;
                    addLog('Trampoline calibration required before analysis starts.', 'info');
                    addFeedback('info', '请在视频预览中添加一个或多个关键帧标定后开始分析');
                    setupCornerCanvas(data.first_frame_image || `data:image/png;base64,${data.first_frame_b64}`, data.video_id);
                } else {
                    addLog('Initializing pose estimation engine...', 'processing');
                    addLog('Starting frame-by-frame analysis...', 'processing');
                    addFeedback('success', 'Video uploaded successfully. Processing...');
                    startAnalysisPolling(data.video_id);
                }
            } else {
                addLog(`Upload failed: ${data.error}`, 'error');
                setTerminalStatus('Error', 'error');
                addFeedback('error', `Upload failed: ${data.error}`);
                stopAnalysis();
            }
        } catch (error) {
            console.error('Error:', error);
            addLog(`Network error: ${error.message}`, 'error');
            setTerminalStatus('Error', 'error');
            addFeedback('error', 'Failed to upload video');
            stopAnalysis();
        }
    });


    function estimateFrameIndex() {
        const fps = uploadedFrameRate || 30;
        if (calibrationGeometry && calibrationGeometry.frameIndexFromTime) {
            return calibrationGeometry.frameIndexFromTime(videoPlayer.currentTime || 0, fps);
        }
        return Math.max(0, Math.round((videoPlayer.currentTime || 0) * fps));
    }

    function formatKeyframe(kf) {
        const time = Number(kf.time_s || 0).toFixed(2);
        return `F${kf.frame_index} / ${time}s`;
    }

    function setDraftImageFromDataUrl(imageSrc, frameIndex, timeS) {
        if (!cornerStep || !cornerCanvas || !cornerCtx) return;
        cornerImage = new Image();
        cornerImage.onload = function() {
            updateCornerCanvasSize();
            drawCornerCanvas();
        };
        cornerImage.src = imageSrc;
        activeKeyframeFrame = frameIndex;
        const existing = calibrationKeyframes.find(kf => kf.frame_index === frameIndex);
        cornerPoints = existing ? existing.corners_px.map(pt => ({ ...pt })) : [];
        if (cornerCount) cornerCount.textContent = `${cornerPoints.length}/4`;
        if (saveKeyframeBtn) saveKeyframeBtn.disabled = cornerPoints.length !== 4;
        if (currentKeyframeLabel) currentKeyframeLabel.textContent = `当前关键帧：F${frameIndex} / ${Number(timeS || 0).toFixed(2)}s`;
    }

    function captureCurrentVideoFrame() {
        if (!videoPlayer.videoWidth || !videoPlayer.videoHeight) {
            return pendingFrameImage;
        }
        const canvas = document.createElement('canvas');
        canvas.width = videoPlayer.videoWidth;
        canvas.height = videoPlayer.videoHeight;
        const tmpCtx = canvas.getContext('2d');
        tmpCtx.drawImage(videoPlayer, 0, 0, canvas.width, canvas.height);
        return canvas.toDataURL('image/png');
    }

    function addCalibrationAtCurrentFrame() {
        if (!pendingTrampolineVideoId) return;
        videoPlayer.pause();
        videoPlayer.hidden = false;
        const frameIndex = estimateFrameIndex();
        const timeS = Math.max(0, Number(videoPlayer.currentTime || 0));
        const imageSrc = captureCurrentVideoFrame();
        if (!imageSrc) {
            addFeedback('warning', '视频帧尚未准备好，请播放或稍等后再添加标定');
            return;
        }
        pendingFrameImage = imageSrc;
        setDraftImageFromDataUrl(imageSrc, frameIndex, timeS);
        addLog(`Editing trampoline calibration keyframe F${frameIndex} (${timeS.toFixed(2)}s).`, 'info');
    }

    function renderKeyframeList() {
        if (!keyframeListEl) return;
        const payload = calibrationGeometry && calibrationGeometry.buildCalibrationPayload
            ? calibrationGeometry.buildCalibrationPayload(calibrationKeyframes)
            : calibrationKeyframes.slice().sort((a, b) => a.frame_index - b.frame_index);
        keyframeListEl.innerHTML = '';
        if (!payload.length) {
            keyframeListEl.innerHTML = '<div class="keyframe-empty">尚未保存关键帧；至少保存 1 个后才能开始分析。</div>';
        } else {
            payload.forEach(kf => {
                const row = document.createElement('div');
                row.className = 'keyframe-row';
                row.innerHTML = `<span>${formatKeyframe(kf)} · ${kf.corners_px.length}/4</span>`;
                const actions = document.createElement('div');
                actions.className = 'keyframe-row-actions';
                const relabel = document.createElement('button');
                relabel.type = 'button';
                relabel.className = 'btn small-btn';
                relabel.textContent = '重标';
                relabel.addEventListener('click', () => {
                    videoPlayer.currentTime = Number(kf.time_s || 0);
                    setDraftImageFromDataUrl(pendingFrameImage || captureCurrentVideoFrame(), kf.frame_index, kf.time_s);
                });
                const del = document.createElement('button');
                del.type = 'button';
                del.className = 'btn small-btn danger-btn';
                del.textContent = '删除';
                del.addEventListener('click', () => {
                    calibrationKeyframes = calibrationKeyframes.filter(item => item.frame_index !== kf.frame_index);
                    if (activeKeyframeFrame === kf.frame_index) {
                        cornerPoints = [];
                        if (cornerCount) cornerCount.textContent = '0/4';
                        if (saveKeyframeBtn) saveKeyframeBtn.disabled = true;
                        drawCornerCanvas();
                    }
                    renderKeyframeList();
                });
                actions.appendChild(relabel);
                actions.appendChild(del);
                row.appendChild(actions);
                keyframeListEl.appendChild(row);
            });
        }
        if (confirmCornersBtn) confirmCornersBtn.disabled = payload.length < 1;
    }

    function updateCornerCanvasSize() {
        if (!cornerCanvas || !cornerImage || !calibrationGeometry) return;
        const parentWidth = cornerStep ? cornerStep.clientWidth : 0;
        const displayWidth = Math.max(320, Math.round(parentWidth || cornerImage.naturalWidth || cornerImage.width));
        const displayHeight = Math.min(500, Math.max(240, Math.round(displayWidth * 9 / 16)));
        cornerCanvas.width = displayWidth;
        cornerCanvas.height = displayHeight;
        cornerImageSize = {
            width: cornerImage.naturalWidth || cornerImage.width,
            height: cornerImage.naturalHeight || cornerImage.height,
        };
        cornerContentRect = calibrationGeometry.computeContainRect(
            cornerImageSize.width,
            cornerImageSize.height,
            cornerCanvas.width,
            cornerCanvas.height
        );
    }

    function setupCornerCanvas(imageSrc, videoId) {
        if (!cornerStep || !cornerCanvas || !cornerCtx) return;
        cornerStep.classList.remove('hidden');
        videoPlayer.pause();
        videoPlayer.hidden = false;
        analysisCanvas.hidden = true;
        calibrationKeyframes = [];
        cornerPoints = [];
        cornerContentRect = null;
        cornerImageSize = null;
        pendingFrameImage = imageSrc;
        pendingTrampolineVideoId = videoId;
        if (cornerCount) cornerCount.textContent = '0/4';
        if (confirmCornersBtn) confirmCornersBtn.disabled = true;
        if (saveKeyframeBtn) saveKeyframeBtn.disabled = true;
        setDraftImageFromDataUrl(imageSrc, 0, 0);
        renderKeyframeList();
    }

    function drawCornerCanvas() {
        if (!cornerCtx || !cornerImage || !calibrationGeometry) return;
        updateCornerCanvasSize();
        if (!cornerContentRect || !cornerImageSize) return;
        cornerCtx.clearRect(0, 0, cornerCanvas.width, cornerCanvas.height);
        cornerCtx.fillStyle = '#111';
        cornerCtx.fillRect(0, 0, cornerCanvas.width, cornerCanvas.height);
        cornerCtx.drawImage(
            cornerImage,
            cornerContentRect.x,
            cornerContentRect.y,
            cornerContentRect.width,
            cornerContentRect.height
        );
        cornerCtx.lineWidth = 3;
        cornerCtx.strokeStyle = '#00d4aa';
        cornerCtx.fillStyle = '#00d4aa';
        const displayPoints = cornerPoints
            .map(pt => calibrationGeometry.imageToDisplayPoint(pt, cornerContentRect, cornerImageSize))
            .filter(Boolean);
        if (displayPoints.length > 1) {
            cornerCtx.beginPath();
            cornerCtx.moveTo(displayPoints[0].x, displayPoints[0].y);
            for (let i = 1; i < displayPoints.length; i++) {
                cornerCtx.lineTo(displayPoints[i].x, displayPoints[i].y);
            }
            if (displayPoints.length === 4) cornerCtx.closePath();
            cornerCtx.stroke();
        }
        displayPoints.forEach((pt, idx) => {
            cornerCtx.beginPath();
            cornerCtx.arc(pt.x, pt.y, 7, 0, Math.PI * 2);
            cornerCtx.fill();
            cornerCtx.fillStyle = '#ffffff';
            cornerCtx.font = '18px sans-serif';
            cornerCtx.fillText(`${idx + 1}.${cornerLabels[idx]}`, pt.x + 10, pt.y - 10);
            cornerCtx.fillStyle = '#00d4aa';
        });
    }

    if (cornerCanvas) {
        cornerCanvas.addEventListener('click', (e) => {
            if (!cornerImage || cornerPoints.length >= 4 || !calibrationGeometry) return;
            updateCornerCanvasSize();
            if (!cornerContentRect || !cornerImageSize) return;
            const rect = cornerCanvas.getBoundingClientRect();
            const displayPoint = {
                x: (e.clientX - rect.left) * (cornerCanvas.width / rect.width),
                y: (e.clientY - rect.top) * (cornerCanvas.height / rect.height),
            };
            const imagePoint = calibrationGeometry.displayToImagePoint(displayPoint, cornerContentRect, cornerImageSize);
            if (!imagePoint) {
                addFeedback('warning', '请点击视频画面内的床面角点，黑边区域无效');
                addLog('Ignored calibration click outside the video image area.', 'warning');
                return;
            }
            cornerPoints.push({ name: cornerOrder[cornerPoints.length], x: imagePoint.x, y: imagePoint.y });
            if (cornerCount) cornerCount.textContent = `${cornerPoints.length}/4`;
            if (saveKeyframeBtn) saveKeyframeBtn.disabled = cornerPoints.length !== 4;
            drawCornerCanvas();
        });
    }

    window.addEventListener('resize', () => {
        if (cornerStep && !cornerStep.classList.contains('hidden') && cornerImage) {
            drawCornerCanvas();
        }
    });

    if (addKeyframeBtn) {
        addKeyframeBtn.addEventListener('click', addCalibrationAtCurrentFrame);
    }

    if (resetCornersBtn) {
        resetCornersBtn.addEventListener('click', () => {
            cornerPoints = [];
            if (cornerCount) cornerCount.textContent = '0/4';
            if (saveKeyframeBtn) saveKeyframeBtn.disabled = true;
            drawCornerCanvas();
        });
    }

    if (saveKeyframeBtn) {
        saveKeyframeBtn.addEventListener('click', () => {
            if (activeKeyframeFrame === null || cornerPoints.length !== 4) return;
            const timeS = Math.max(0, Number(videoPlayer.currentTime || 0));
            const keyframe = {
                frame_index: activeKeyframeFrame,
                time_s: timeS,
                corners_px: cornerPoints.map((pt, idx) => ({ name: cornerOrder[idx], x: pt.x, y: pt.y })),
            };
            calibrationKeyframes = calibrationKeyframes.filter(kf => kf.frame_index !== activeKeyframeFrame);
            calibrationKeyframes.push(keyframe);
            calibrationKeyframes.sort((a, b) => a.frame_index - b.frame_index);
            addLog(`Saved calibration keyframe ${formatKeyframe(keyframe)}.`, 'success');
            renderKeyframeList();
        });
    }

    if (confirmCornersBtn) {
        confirmCornersBtn.addEventListener('click', async () => {
            const calibrations = calibrationGeometry && calibrationGeometry.buildCalibrationPayload
                ? calibrationGeometry.buildCalibrationPayload(calibrationKeyframes)
                : calibrationKeyframes;
            if (!pendingTrampolineVideoId || calibrations.length < 1) return;
            confirmCornersBtn.disabled = true;
            addLog(`Submitting ${calibrations.length} bed calibration keyframe(s)...`, 'processing');
            try {
                const response = await fetch('/api/video/trampoline/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ video_id: pendingTrampolineVideoId, calibrations })
                });
                const data = await response.json();
                if (!data.success) {
                    addLog(`Calibration failed: ${data.error}`, 'error');
                    addFeedback('error', `Calibration failed: ${data.error}`);
                    confirmCornersBtn.disabled = false;
                    return;
                }
                addLog('Calibration accepted. Starting frame-by-frame analysis...', 'success');
                addFeedback('success', 'Calibration accepted. Processing...');
                if (cornerStep) cornerStep.classList.add('hidden');
                videoPlayer.hidden = false;
                isAnalyzing = true;
                analysisResults.startTime = new Date();
                stopAnalysisBtn.disabled = false;
                setTerminalStatus('Processing', 'running');
                startAnalysisPolling(pendingTrampolineVideoId);
            } catch (error) {
                addLog(`Calibration request failed: ${error.message}`, 'error');
                addFeedback('error', 'Failed to submit calibration');
                confirmCornersBtn.disabled = false;
            }
        });
    }

    // Poll for analysis results
    let lastProgress = 0;

    function startAnalysisPolling(videoId) {
        currentVideoId = videoId;
        // Setup canvas
        analysisCanvas.width = videoPlayer.videoWidth || 640;
        analysisCanvas.height = videoPlayer.videoHeight || 480;
        analysisCanvas.hidden = false;

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
                    progressText.textContent = `Processing: ${Math.round(data.progress)}%`;

                    const currentProgress = Math.floor(data.progress / 10) * 10;
                    if (currentProgress > lastProgress && currentProgress > 0) {
                        if (isTrampolineMode) {
                            addLog(`Progress: ${currentProgress}% | Jumps: ${data.reps || 0} | Action: ${data.current_action || '--'}`, 'progress');
                        } else {
                            addLog(`Progress: ${currentProgress}% | Reps: ${data.reps || 0} | Score: ${data.form_score || '--'}`, 'progress');
                        }
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

                    addLog('Analysis completed successfully!', 'success');
                    if (isTrampolineMode) {
                        addLog(`Total Jumps: ${data.reps || 0}`, 'success');
                        const jumps = data.completed_jumps || [];
                        const actions = jumps.filter(j => !j.is_intermediate).map(j => j.action);
                        if (actions.length > 0) {
                            addLog(`Actions: ${actions.join(', ')}`, 'success');
                        }
                    } else {
                        addLog(`Total Reps: ${data.reps || 0}`, 'success');
                        addLog(`Average Score: ${data.avg_form_score || data.form_score || '--'}/100`, 'success');
                        addLog(`Grade: ${data.grade || '--'}`, 'success');
                    }
                    setTerminalStatus('Completed', 'success');

                    if (data.has_processed_video && data.processed_video_url) {
                        addLog('Loading processed video with skeleton overlay...', 'processing');
                        addFeedback('success', 'Analysis completed! Loading video with skeleton overlay...');

                        videoPlayer.src = data.processed_video_url;
                        videoPlayer.load();
                        videoPlayer.play();

                        addLog('Video with skeleton overlay loaded.', 'success');
                    } else {
                        addFeedback('success', 'Analysis completed!');
                    }

                    showReport(data);
                    stopAnalysis();

                } else if (data.status === 'error') {
                    clearInterval(analysisInterval);
                    addLog(`Analysis error: ${data.error}`, 'error');
                    setTerminalStatus('Error', 'error');
                    addFeedback('error', `Analysis error: ${data.error}`);
                    stopAnalysis();
                }
            } catch (error) {
                console.error('Polling error:', error);
                addLog(`Network error during polling: ${error.message}`, 'warning');
            }
        }, 200);

        // Also poll frame-by-frame for real-time display
        requestAnimationFrame(function frameLoop() {
            if (isAnalyzing && !videoPlayer.paused) {
                sendFrameForAnalysis(videoId);
                requestAnimationFrame(frameLoop);
            }
        });
    }

    async function sendFrameForAnalysis(videoId) {
        const tempCanvas = document.createElement('canvas');
        tempCanvas.width = videoPlayer.videoWidth;
        tempCanvas.height = videoPlayer.videoHeight;
        const tempCtx = tempCanvas.getContext('2d');
        tempCtx.drawImage(videoPlayer, 0, 0);

        try {
            const blob = await new Promise(resolve => tempCanvas.toBlob(resolve, 'image/jpeg', 0.8));
            const formData = new FormData();
            formData.append('frame', blob);
            formData.append('video_id', videoId);
            formData.append('timestamp', videoPlayer.currentTime);

            const response = await fetch('/api/video/analyze_frame', {
                method: 'POST',
                body: formData
            });

            const data = await response.json();
            if (data.success) {
                drawPoseOnCanvas(data);
                updateStats(data);

                if (data.feedback && data.feedback !== lastFeedback) {
                    addFeedback('warning', data.feedback);
                    lastFeedback = data.feedback;
                }
            }
        } catch (error) {
            // Silently fail for frame analysis
        }
    }

    let lastFeedback = '';

    function drawPoseOnCanvas(data) {
        ctx.clearRect(0, 0, analysisCanvas.width, analysisCanvas.height);

        if (!data.landmarks) return;

        const connections = [
            [11, 13], [13, 15], // Left arm
            [12, 14], [14, 16], // Right arm
            [11, 12], // Shoulders
            [11, 23], [12, 24], // Torso
            [23, 24], // Hips
            [23, 25], [25, 27], // Left leg
            [24, 26], [26, 28]  // Right leg
        ];

        ctx.strokeStyle = '#00ff00';
        ctx.lineWidth = 3;

        connections.forEach(([i, j]) => {
            if (data.landmarks[i] && data.landmarks[j]) {
                ctx.beginPath();
                ctx.moveTo(data.landmarks[i].x * analysisCanvas.width, data.landmarks[i].y * analysisCanvas.height);
                ctx.lineTo(data.landmarks[j].x * analysisCanvas.width, data.landmarks[j].y * analysisCanvas.height);
                ctx.stroke();
            }
        });

        ctx.fillStyle = '#ff0000';
        Object.values(data.landmarks).forEach(point => {
            if (point) {
                ctx.beginPath();
                ctx.arc(point.x * analysisCanvas.width, point.y * analysisCanvas.height, 5, 0, 2 * Math.PI);
                ctx.fill();
            }
        });
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

            const offset = 251.2 - (251.2 * score / 100);
            gaugeFill.style.strokeDashoffset = offset;

            let color = '#27ae60';
            if (score < 60) color = '#e74c3c';
            else if (score < 70) color = '#e67e22';
            else if (score < 80) color = '#f1c40f';
            else if (score < 90) color = '#3498db';
            gaugeFill.style.stroke = color;
        }

        if (data.grade !== undefined) {
            statGrade.textContent = data.grade;
            statGrade.className = `stat-value grade grade-${data.grade.toLowerCase()}`;
        }

        if (data.state !== undefined) {
            statState.textContent = data.state;
        }

        // Trampoline-specific: update action card
        if (isTrampolineMode && data.current_action !== undefined) {
            statAction.textContent = data.current_action;
            statAction.className = `stat-value action-name action-${data.current_action.toLowerCase()}`;
        }
    }

    function resetStats() {
        statReps.textContent = '0';
        statScore.textContent = '--';
        statGrade.textContent = '--';
        statState.textContent = '--';
        gaugeValue.textContent = '--';
        gaugeFill.style.strokeDashoffset = 251.2;
        progressFill.style.width = '0%';
        progressText.textContent = '0%';
        if (statAction) statAction.textContent = '--';
    }

    // Stop Analysis
    stopAnalysisBtn.addEventListener('click', () => {
        addLog('Analysis stopped by user.', 'warning');
        setTerminalStatus('Stopped', 'idle');
        stopAnalysis();
        addFeedback('info', 'Analysis stopped by user');
    });

    function stopAnalysis() {
        isAnalyzing = false;
        lastProgress = 0;
        if (analysisInterval) {
            clearInterval(analysisInterval);
            analysisInterval = null;
        }

        videoPlayer.pause();
        analyzeBtn.disabled = false;
        stopAnalysisBtn.disabled = true;
        if (!isTrampolineMode) exerciseSelect.disabled = false;
    }

    // Add feedback to log
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

    // Show final report
    function showReport(data) {
        if (isTrampolineMode) {
            showTrampolineReport(data);
            return;
        }

        const avgScore = analysisResults.scores.length > 0
            ? Math.round(analysisResults.scores.reduce((a, b) => a + b, 0) / analysisResults.scores.length)
            : 0;

        const duration = analysisResults.endTime && analysisResults.startTime
            ? Math.round((analysisResults.endTime - analysisResults.startTime) / 1000)
            : 0;

        const grade = avgScore >= 90 ? 'A' : avgScore >= 80 ? 'B' : avgScore >= 70 ? 'C' : avgScore >= 60 ? 'D' : 'F';

        reportContent.innerHTML = `
            <div class="report-row">
                <span class="report-label">Exercise</span>
                <span class="report-value">${exerciseSelect.options[exerciseSelect.selectedIndex].text}</span>
            </div>
            <div class="report-row">
                <span class="report-label">Total Reps</span>
                <span class="report-value">${analysisResults.reps}</span>
            </div>
            <div class="report-row">
                <span class="report-label">Average Form Score</span>
                <span class="report-value">${avgScore}/100</span>
            </div>
            <div class="report-row">
                <span class="report-label">Final Grade</span>
                <span class="report-value">${grade}</span>
            </div>
            <div class="report-row">
                <span class="report-label">Duration</span>
                <span class="report-value">${duration}s</span>
            </div>
            <div class="report-row">
                <span class="report-label">Form Warnings</span>
                <span class="report-value">${analysisResults.feedbacks.filter(f => f.type === 'warning').length}</span>
            </div>
        `;

        reportSection.classList.remove('hidden');
    }

    function showTrampolineReport(data) {
        const jumps = data.completed_jumps || analysisResults.completedJumps || [];
        const jumpCount = data.reps || jumps.length;

        const duration = analysisResults.endTime && analysisResults.startTime
            ? Math.round((analysisResults.endTime - analysisResults.startTime) / 1000)
            : 0;

        // Action breakdown
        const actionCounts = {};
        const realJumps = jumps.filter(j => !j.is_intermediate);
        realJumps.forEach(j => {
            actionCounts[j.action] = (actionCounts[j.action] || 0) + 1;
        });

        const actionBreakdown = Object.entries(actionCounts)
            .map(([k, v]) => `${k}: ${v}`).join(', ') || '--';

        function fmtNum(value, digits = 2) {
            const n = Number(value);
            return Number.isFinite(n) ? n.toFixed(digits) : String(value ?? '?');
        }

        // Per-jump details
        let jumpDetails = '';
        realJumps.forEach((jump, i) => {
            const landing = jump.landing;
            let landingText = '落点: --';
            if (landing) {
                const xy = landing.bed_xy_m || ['?', '?'];
                const conf = landing.confidence !== undefined ? Number(landing.confidence).toFixed(2) : '--';
                const low = landing.confidence !== undefined && Number(landing.confidence) < 0.5;
                landingText = `落点: (${fmtNum(xy[0])}, ${fmtNum(xy[1])})m / ${landing.zone || '--'} / conf ${conf}${low ? ' <span class="landing-low-confidence">低置信</span>' : ''}`;
            }
            jumpDetails += `
                <div class="report-row">
                    <span class="report-label">Jump ${jump.jump_number || (i + 1)}</span>
                    <span class="report-value">${jump.action} <span class="jump-flight-info">(${jump.flight_frames}f)</span><br><small>${landingText}</small></span>
                </div>`;
        });

        const intermediateCount = jumps.filter(j => j.is_intermediate).length;

        reportContent.innerHTML = `
            <div class="report-row">
                <span class="report-label">Analysis Type</span>
                <span class="report-value">Trampoline</span>
            </div>
            <div class="report-row">
                <span class="report-label">Total Jumps</span>
                <span class="report-value">${jumpCount}</span>
            </div>
            ${intermediateCount > 0 ? `
            <div class="report-row">
                <span class="report-label">Intermediate Bounces</span>
                <span class="report-value">${intermediateCount}</span>
            </div>` : ''}
            <div class="report-row">
                <span class="report-label">Action Breakdown</span>
                <span class="report-value">${actionBreakdown}</span>
            </div>
            ${jumpDetails}
            <div class="report-row">
                <span class="report-label">Processing Duration</span>
                <span class="report-value">${duration}s</span>
            </div>
        `;

        reportSection.classList.remove('hidden');

        // Enable LLM analysis button
        if (llmSection) llmSection.classList.remove('hidden');
        if (llmBtn) llmBtn.disabled = false;
    }

    // ==================== LLM Analysis ====================

    function simpleMd(text) {
        // Minimal markdown: **bold**, \n→<br>, ## heading
        return text
            .replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
            .replace(/^## (.+)$/gm, '<div style="font-weight:700;color:#00d4aa;margin:8px 0 4px">$1</div>')
            .replace(/\n/g, '<br>');
    }

    if (llmBtn) {
        llmBtn.addEventListener('click', () => {
            if (!currentVideoId) return;
            llmBtn.disabled = true;
            if (llmEventSource) {
                llmEventSource.close();
                llmEventSource = null;
            }

            // Show streaming state
            llmStreaming.classList.remove('hidden');
            llmStreaming.classList.remove('collapsed');
            llmStreamingText.innerHTML = '';
            llmCards.classList.add('hidden');
            llmCards.classList.remove('visible');
            llmToggleRaw.classList.add('hidden');

            let llmStreamFinished = false;
            llmEventSource = new EventSource(`/api/video/llm_analysis/${currentVideoId}`);

            llmEventSource.onmessage = function(e) {
                let data;
                try { data = JSON.parse(e.data); } catch { return; }

                if (data.type === 'chunk') {
                    llmStreamingText.innerHTML += simpleMd(data.text);
                    llmStreamingText.scrollTop = llmStreamingText.scrollHeight;
                }
                else if (data.type === 'fast_done') {
                    // Fast model finished; waiting for quality model
                    const header = llmStreaming.querySelector('.llm-streaming-header');
                    if (header) {
                        header.innerHTML = `
                            <span class="llm-status-dot llm-quality-waiting"></span>
                            <span>正在生成高质量分析...</span>
                        `;
                    }
                }
                else if (data.type === 'done') {
                    llmStreamFinished = true;
                    llmEventSource.close();
                    llmEventSource = null;

                    // Populate cards
                    const sectionMap = {
                        '整体表现': 'llm-card-overview',
                        '主要问题': 'llm-card-issues',
                        '逐跳点评': 'llm-card-details',
                        '改进建议': 'llm-card-suggestions',
                    };
                    for (const [heading, cardId] of Object.entries(sectionMap)) {
                        const card = document.getElementById(cardId);
                        if (card) {
                            const body = card.querySelector('.llm-card-body');
                            const content = (data.sections && data.sections[heading]) || '';
                            body.innerHTML = content ? simpleMd(content) : '<span style="color:#999">AI 未能生成此部分分析</span>';
                        }
                    }

                    // Collapse streaming, show cards
                    llmStreaming.classList.add('collapsed');
                    llmCards.classList.remove('hidden');
                    // Trigger reflow for animation
                    requestAnimationFrame(() => llmCards.classList.add('visible'));
                    llmToggleRaw.classList.remove('hidden');
                    llmBtn.disabled = false;
                }
                else if (data.type === 'error') {
                    llmStreamFinished = true;
                    llmEventSource.close();
                    llmEventSource = null;
                    llmStreamingText.innerHTML += `<br><span style="color:#e74c3c">${data.message}</span>`;
                    llmBtn.disabled = false;
                }
            };

            llmEventSource.onerror = function() {
                if (llmStreamFinished) {
                    return;
                }
                llmEventSource.close();
                llmEventSource = null;
                llmStreamingText.innerHTML += '<br><span style="color:#e74c3c">连接中断</span>';
                llmBtn.disabled = false;
            };
        });
    }

    // Toggle raw text
    if (llmToggleRaw) {
        llmToggleRaw.addEventListener('click', () => {
            const isCollapsed = llmStreaming.classList.contains('collapsed');
            if (isCollapsed) {
                llmStreaming.classList.remove('collapsed');
                llmToggleRaw.textContent = '折叠原文';
            } else {
                llmStreaming.classList.add('collapsed');
                llmToggleRaw.textContent = '展开原文';
            }
        });
    }

    // ==================== Download Report ====================
    downloadReportBtn.addEventListener('click', () => {
        let reportText;

        if (isTrampolineMode) {
            const jumps = analysisResults.completedJumps || [];
            const realJumps = jumps.filter(j => !j.is_intermediate);
            reportText = `
TRAMPOLINE ANALYSIS REPORT
========================================
Date: ${new Date().toLocaleString()}
Video: ${videoFile ? videoFile.name : 'Unknown'}

RESULTS
-------
Total Jumps: ${analysisResults.reps}
Intermediate Bounces: ${jumps.filter(j => j.is_intermediate).length}

JUMP DETAILS
------------
${realJumps.map((j, i) => { const l = j.landing; const landing = l ? ` | landing: (${(l.bed_xy_m || [])[0]}, ${(l.bed_xy_m || [])[1]})m ${l.zone || ''} conf=${l.confidence}` : ''; return `Jump ${j.jump_number || (i + 1)}: ${j.action} (flight: ${j.flight_frames} frames)${landing}`; }).join('\n')}

FEEDBACK LOG
------------
${analysisResults.feedbacks.map(f => `[${f.time}] ${f.type.toUpperCase()}: ${f.message}`).join('\n')}
            `;
        } else {
            reportText = `
FITNESS TRAINER - VIDEO ANALYSIS REPORT
========================================
Date: ${new Date().toLocaleString()}
Video: ${videoFile ? videoFile.name : 'Unknown'}
Exercise: ${exerciseSelect.options[exerciseSelect.selectedIndex].text}

RESULTS
-------
Total Repetitions: ${analysisResults.reps}
Average Form Score: ${analysisResults.scores.length > 0 ? Math.round(analysisResults.scores.reduce((a, b) => a + b, 0) / analysisResults.scores.length) : 0}/100

FEEDBACK LOG
------------
${analysisResults.feedbacks.map(f => `[${f.time}] ${f.type.toUpperCase()}: ${f.message}`).join('\n')}
            `;
        }

        const blob = new Blob([reportText], { type: 'text/plain' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${isTrampolineMode ? 'trampoline' : 'fitness'}_report_${Date.now()}.txt`;
        a.click();
        URL.revokeObjectURL(url);
    });

    // Initialize
    if (!isTrampolineMode) {
        // Already called above via loadExercises()
    }
});
