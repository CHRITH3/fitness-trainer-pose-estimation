(function(root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.TrampolineCalibrationUI = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    const DEFAULT_CORNER_ORDER = ['front_left', 'front_right', 'back_right', 'back_left'];
    const DEFAULT_CORNER_LABELS = ['前左', '前右', '后右', '后左'];

    function describeCalibrationUiState({
        activeKeyframeFrame = null,
        activeKeyframeTimeS = 0,
        draftCornerCount = 0,
        savedCalibrationCount = 0,
        hasSelectedCalibration = false,
    } = {}) {
        return {
            draftLabel: activeKeyframeFrame === null
                ? '当前草稿：未选择'
                : `当前草稿：F${Math.max(0, Math.round(Number(activeKeyframeFrame) || 0))} / ${Math.max(0, Number(activeKeyframeTimeS) || 0).toFixed(2)}s`,
            statusText: savedCalibrationCount > 0
                ? `已保存 ${savedCalibrationCount} 个有效标定，可开始分析。`
                : '至少保存 1 个有效标定后才能开始分析。',
            canSave: activeKeyframeFrame !== null && draftCornerCount === 4,
            canStart: savedCalibrationCount > 0,
            canDelete: Boolean(hasSelectedCalibration),
        };
    }

    function createController(options = {}) {
        const {
            documentRef = (typeof document !== 'undefined' ? document : null),
            videoPlayer,
            analysisCanvas,
            geometry,
            fetchImpl = (...args) => fetch(...args),
            onLog = () => {},
            onFeedback = () => {},
            onProcessingStart = () => {},
            cornerOrder = DEFAULT_CORNER_ORDER,
            cornerLabels = DEFAULT_CORNER_LABELS,
        } = options;

        if (!documentRef || !videoPlayer || !analysisCanvas || !geometry) {
            throw new Error('createController requires documentRef, videoPlayer, analysisCanvas, and geometry');
        }

        const cornerStep = documentRef.getElementById('corner-marking-step');
        const cornerCanvas = documentRef.getElementById('corner-canvas');
        const cornerCtx = cornerCanvas ? cornerCanvas.getContext('2d') : null;
        const cornerCount = documentRef.getElementById('corner-count');
        const resetCornersBtn = documentRef.getElementById('reset-corners');
        const keyframeList = documentRef.getElementById('keyframe-list');
        const confirmCornersBtn = documentRef.getElementById('confirm-corners');
        const addCalibrationFrameBtn = documentRef.getElementById('add-calibration-frame');
        const deleteCalibrationBtn = documentRef.getElementById('delete-calibration');
        const startTrampolineAnalysisBtn = documentRef.getElementById('start-trampoline-analysis');
        const calibrationList = documentRef.getElementById('calibration-list');
        const calibrationDraftLabel = documentRef.getElementById('calibration-draft-label');
        const calibrationStatusText = documentRef.getElementById('calibration-status-text');

        let pendingTrampolineVideoId = null;
        let cornerImage = null;
        let cornerImageSize = null;
        let cornerContentRect = null;
        let cornerPoints = [];
        let calibrationKeyframes = [];
        let activeKeyframeFrame = null;
        let activeKeyframeTimeS = 0;
        let selectedCalibrationFrame = null;
        let pendingFrameImage = null;
        let uploadedFrameRate = 30;

        function getCalibrationPayload() {
            return geometry && geometry.buildCalibrationPayload
                ? geometry.buildCalibrationPayload(calibrationKeyframes)
                : calibrationKeyframes.slice();
        }

        function updateCalibrationUi() {
            const payload = getCalibrationPayload();
            const selected = calibrationKeyframes.find(kf => kf.frame_index === selectedCalibrationFrame);
            const uiState = describeCalibrationUiState({
                activeKeyframeFrame,
                activeKeyframeTimeS,
                draftCornerCount: cornerPoints.length,
                savedCalibrationCount: payload.length,
                hasSelectedCalibration: Boolean(selected),
            });

            if (calibrationDraftLabel) calibrationDraftLabel.textContent = uiState.draftLabel;
            if (calibrationStatusText) calibrationStatusText.textContent = uiState.statusText;
            if (confirmCornersBtn) confirmCornersBtn.disabled = !uiState.canSave;
            if (startTrampolineAnalysisBtn) startTrampolineAnalysisBtn.disabled = !uiState.canStart;
            if (deleteCalibrationBtn) deleteCalibrationBtn.disabled = !uiState.canDelete;
        }

        function updateCornerCanvasSize() {
            if (!cornerCanvas || !cornerImage || !geometry) return;
            const parentWidth = cornerStep ? cornerStep.clientWidth : 0;
            const displayWidth = Math.max(320, Math.round(parentWidth || cornerImage.naturalWidth || cornerImage.width));
            const displayHeight = Math.min(500, Math.max(240, Math.round(displayWidth * 9 / 16)));
            cornerCanvas.width = displayWidth;
            cornerCanvas.height = displayHeight;
            cornerImageSize = {
                width: cornerImage.naturalWidth || cornerImage.width,
                height: cornerImage.naturalHeight || cornerImage.height,
            };
            cornerContentRect = geometry.computeContainRect(
                cornerImageSize.width,
                cornerImageSize.height,
                cornerCanvas.width,
                cornerCanvas.height
            );
        }

        function drawCornerCanvas() {
            if (!cornerCtx || !cornerImage || !geometry) return;
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
                .map(pt => geometry.imageToDisplayPoint(pt, cornerContentRect, cornerImageSize))
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

        function setDraftImageFromDataUrl(imageSrc, frameIndex, timeS) {
            if (!cornerStep || !cornerCanvas || !cornerCtx || !imageSrc) return;
            const existing = calibrationKeyframes.find(kf => kf.frame_index === frameIndex);
            activeKeyframeFrame = Math.max(0, Math.round(Number(frameIndex) || 0));
            activeKeyframeTimeS = Math.max(0, Number(timeS) || 0);
            selectedCalibrationFrame = existing ? existing.frame_index : activeKeyframeFrame;
            pendingFrameImage = existing?.preview_image || imageSrc;
            cornerPoints = existing ? existing.corners_px.map(pt => ({ ...pt })) : [];

            cornerImage = new Image();
            cornerImage.onload = function() {
                updateCornerCanvasSize();
                drawCornerCanvas();
            };
            cornerImage.src = pendingFrameImage;

            if (cornerCount) cornerCount.textContent = `${cornerPoints.length}/4`;
            updateCalibrationUi();
        }

        function captureCurrentVideoFrame() {
            if (!videoPlayer.videoWidth || !videoPlayer.videoHeight) {
                return pendingFrameImage || (cornerImage ? cornerImage.src : null);
            }
            const canvas = documentRef.createElement('canvas');
            canvas.width = videoPlayer.videoWidth;
            canvas.height = videoPlayer.videoHeight;
            const tmpCtx = canvas.getContext('2d');
            tmpCtx.drawImage(videoPlayer, 0, 0, canvas.width, canvas.height);
            return canvas.toDataURL('image/png');
        }

        function renderCalibrationList() {
            if (!calibrationList) return;
            calibrationList.innerHTML = '';
            calibrationKeyframes
                .slice()
                .sort((a, b) => a.frame_index - b.frame_index)
                .forEach(kf => {
                    const chip = documentRef.createElement('button');
                    chip.type = 'button';
                    chip.className = `calibration-chip${kf.frame_index === selectedCalibrationFrame ? ' active' : ''}${kf.corners_px.length === 4 ? ' complete' : ''}`;
                    chip.textContent = `F${kf.frame_index} / ${Number(kf.time_s || 0).toFixed(2)}s`;
                    chip.addEventListener('click', () => {
                        videoPlayer.pause();
                        videoPlayer.currentTime = Number(kf.time_s || 0);
                        setDraftImageFromDataUrl(
                            kf.preview_image || captureCurrentVideoFrame(),
                            kf.frame_index,
                            kf.time_s
                        );
                        renderCalibrationList();
                        renderKeyframeList();
                    });
                    calibrationList.appendChild(chip);
                });
        }

        function renderKeyframeList() {
            if (!keyframeList) return;
            const sortedKeyframes = calibrationKeyframes.slice().sort((a, b) => a.frame_index - b.frame_index);
            keyframeList.innerHTML = '';
            if (!sortedKeyframes.length) {
                keyframeList.innerHTML = '<div class="keyframe-empty">尚未保存关键帧；至少保存 1 个后才能开始分析。</div>';
            } else {
                sortedKeyframes.forEach(kf => {
                    const row = documentRef.createElement('div');
                    row.className = 'keyframe-row';
                    if (kf.frame_index === selectedCalibrationFrame) row.classList.add('active');

                    const label = documentRef.createElement('span');
                    label.textContent = `F${kf.frame_index} / ${Number(kf.time_s || 0).toFixed(2)}s · ${kf.corners_px.length}/4`;
                    row.appendChild(label);

                    const actions = documentRef.createElement('div');
                    actions.className = 'keyframe-row-actions';

                    const relabel = documentRef.createElement('button');
                    relabel.type = 'button';
                    relabel.className = 'btn small-btn';
                    relabel.textContent = '重标';
                    relabel.addEventListener('click', () => {
                        videoPlayer.pause();
                        videoPlayer.currentTime = Number(kf.time_s || 0);
                        setDraftImageFromDataUrl(
                            kf.preview_image || captureCurrentVideoFrame(),
                            kf.frame_index,
                            kf.time_s
                        );
                        renderCalibrationList();
                        renderKeyframeList();
                    });

                    const del = documentRef.createElement('button');
                    del.type = 'button';
                    del.className = 'btn small-btn danger-btn';
                    del.textContent = '删除';
                    del.addEventListener('click', () => deleteCalibration(kf.frame_index));

                    actions.appendChild(relabel);
                    actions.appendChild(del);
                    row.appendChild(actions);
                    keyframeList.appendChild(row);
                });
            }
            renderCalibrationList();
            updateCalibrationUi();
        }

        function deleteCalibration(frameIndex) {
            const numericFrameIndex = Math.max(0, Math.round(Number(frameIndex) || 0));
            calibrationKeyframes = calibrationKeyframes.filter(item => item.frame_index !== numericFrameIndex);
            if (selectedCalibrationFrame === numericFrameIndex) {
                selectedCalibrationFrame = calibrationKeyframes[0]?.frame_index ?? null;
            }
            if (activeKeyframeFrame === numericFrameIndex) {
                cornerPoints = [];
                activeKeyframeFrame = null;
                activeKeyframeTimeS = 0;
                if (cornerCount) cornerCount.textContent = '0/4';
                drawCornerCanvas();
            }
            renderKeyframeList();
        }

        function estimateFrameIndex() {
            const fps = uploadedFrameRate || 30;
            if (geometry && geometry.frameIndexFromTime) {
                return geometry.frameIndexFromTime(videoPlayer.currentTime || 0, fps);
            }
            return Math.max(0, Math.round((videoPlayer.currentTime || 0) * fps));
        }

        function addCalibrationAtCurrentFrame() {
            if (!pendingTrampolineVideoId) return;
            videoPlayer.pause();
            videoPlayer.hidden = false;
            const frameIndex = estimateFrameIndex();
            const timeS = Math.max(0, Number(videoPlayer.currentTime || 0));
            const imageSrc = captureCurrentVideoFrame();
            if (!imageSrc) {
                onFeedback('warning', '视频帧尚未准备好，请播放或稍等后再添加标定');
                return;
            }
            setDraftImageFromDataUrl(imageSrc, frameIndex, timeS);
            onLog(`Editing trampoline calibration keyframe F${frameIndex} (${timeS.toFixed(2)}s).`, 'info');
            renderKeyframeList();
        }

        function resetDraftCorners() {
            cornerPoints = [];
            if (cornerCount) cornerCount.textContent = '0/4';
            drawCornerCanvas();
            updateCalibrationUi();
        }

        function saveCurrentCalibration() {
            if (activeKeyframeFrame === null || cornerPoints.length !== 4) return;
            const keyframe = {
                frame_index: activeKeyframeFrame,
                time_s: activeKeyframeTimeS,
                preview_image: captureCurrentVideoFrame() || pendingFrameImage,
                corners_px: cornerPoints.map((pt, idx) => ({ name: cornerOrder[idx], x: pt.x, y: pt.y })),
            };

            calibrationKeyframes = calibrationKeyframes.filter(kf => kf.frame_index !== activeKeyframeFrame);
            calibrationKeyframes.push(keyframe);
            calibrationKeyframes.sort((a, b) => a.frame_index - b.frame_index);
            selectedCalibrationFrame = activeKeyframeFrame;

            onLog(`Saved calibration keyframe F${keyframe.frame_index} / ${Number(keyframe.time_s || 0).toFixed(2)}s.`, 'success');
            onFeedback('success', `已保存标定 F${keyframe.frame_index} / ${Number(keyframe.time_s || 0).toFixed(2)}s`);
            renderKeyframeList();
        }

        async function startTrampolineAnalysis() {
            const calibrations = getCalibrationPayload();
            if (!pendingTrampolineVideoId || calibrations.length < 1) return;
            if (startTrampolineAnalysisBtn) startTrampolineAnalysisBtn.disabled = true;
            onLog('Submitting bed keyframe calibrations...', 'processing');
            try {
                const response = await fetchImpl('/api/video/trampoline/start', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ video_id: pendingTrampolineVideoId, calibrations })
                });
                const data = await response.json();
                if (!data.success) {
                    onLog(`Calibration failed: ${data.error}`, 'error');
                    onFeedback('error', `Calibration failed: ${data.error}`);
                    if (startTrampolineAnalysisBtn) startTrampolineAnalysisBtn.disabled = false;
                    return;
                }
                onLog(`Calibration accepted (${calibrations.length} keyframe(s)). Starting frame-by-frame analysis...`, 'success');
                onFeedback('success', 'Calibration accepted. Processing...');
                if (cornerStep) cornerStep.classList.add('hidden');
                videoPlayer.hidden = false;
                onProcessingStart({ videoId: pendingTrampolineVideoId, calibrationCount: calibrations.length, response: data });
            } catch (error) {
                onLog(`Calibration request failed: ${error.message}`, 'error');
                onFeedback('error', 'Failed to submit calibration');
                if (startTrampolineAnalysisBtn) startTrampolineAnalysisBtn.disabled = false;
            }
        }

        function enterPendingCalibration({ videoId, imageSrc, videoFps }) {
            if (!cornerStep || !cornerCanvas || !cornerCtx) return;
            cornerStep.classList.remove('hidden');
            videoPlayer.pause();
            videoPlayer.hidden = false;
            analysisCanvas.hidden = true;
            calibrationKeyframes = [];
            cornerPoints = [];
            activeKeyframeFrame = null;
            activeKeyframeTimeS = 0;
            selectedCalibrationFrame = null;
            cornerContentRect = null;
            cornerImageSize = null;
            pendingFrameImage = imageSrc;
            pendingTrampolineVideoId = videoId;
            uploadedFrameRate = Number(videoFps || videoPlayer.dataset.fps || uploadedFrameRate || 30) || 30;
            videoPlayer.dataset.fps = String(uploadedFrameRate);
            if (cornerCount) cornerCount.textContent = '0/4';
            renderKeyframeList();
            setDraftImageFromDataUrl(imageSrc, 0, 0);
        }

        function reset() {
            pendingTrampolineVideoId = null;
            cornerImage = null;
            cornerImageSize = null;
            cornerContentRect = null;
            cornerPoints = [];
            calibrationKeyframes = [];
            activeKeyframeFrame = null;
            activeKeyframeTimeS = 0;
            selectedCalibrationFrame = null;
            pendingFrameImage = null;
            uploadedFrameRate = 30;
            if (cornerStep) cornerStep.classList.add('hidden');
            if (cornerCanvas && cornerCtx) {
                cornerCtx.clearRect(0, 0, cornerCanvas.width, cornerCanvas.height);
            }
            if (cornerCount) cornerCount.textContent = '0/4';
            renderKeyframeList();
        }

        if (cornerCanvas) {
            cornerCanvas.addEventListener('click', (e) => {
                if (!cornerImage || cornerPoints.length >= 4 || !geometry) return;
                updateCornerCanvasSize();
                if (!cornerContentRect || !cornerImageSize) return;
                const rect = cornerCanvas.getBoundingClientRect();
                const displayPoint = {
                    x: (e.clientX - rect.left) * (cornerCanvas.width / rect.width),
                    y: (e.clientY - rect.top) * (cornerCanvas.height / rect.height),
                };
                const imagePoint = geometry.displayToImagePoint(displayPoint, cornerContentRect, cornerImageSize);
                if (!imagePoint) {
                    onFeedback('warning', '请点击视频画面内的床面角点，黑边区域无效');
                    onLog('Ignored calibration click outside the video image area.', 'warning');
                    return;
                }
                cornerPoints.push({ name: cornerOrder[cornerPoints.length], x: imagePoint.x, y: imagePoint.y });
                if (cornerCount) cornerCount.textContent = `${cornerPoints.length}/4`;
                drawCornerCanvas();
                updateCalibrationUi();
            });
        }

        if (addCalibrationFrameBtn) addCalibrationFrameBtn.addEventListener('click', addCalibrationAtCurrentFrame);
        if (resetCornersBtn) resetCornersBtn.addEventListener('click', resetDraftCorners);
        if (confirmCornersBtn) confirmCornersBtn.addEventListener('click', saveCurrentCalibration);
        if (deleteCalibrationBtn) deleteCalibrationBtn.addEventListener('click', () => {
            if (selectedCalibrationFrame === null) return;
            deleteCalibration(selectedCalibrationFrame);
        });
        if (startTrampolineAnalysisBtn) startTrampolineAnalysisBtn.addEventListener('click', startTrampolineAnalysis);
        if (typeof window !== 'undefined') {
            window.addEventListener('resize', () => {
                if (cornerStep && !cornerStep.classList.contains('hidden') && cornerImage) {
                    drawCornerCanvas();
                }
            });
        }

        return {
            enterPendingCalibration,
            reset,
            getCalibrationPayload,
        };
    }

    return {
        createController,
        describeCalibrationUiState,
    };
});
