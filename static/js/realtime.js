document.addEventListener('DOMContentLoaded', () => {
    const video = document.getElementById('realtime-video');
    const stage = document.getElementById('realtime-stage');
    const placeholder = document.getElementById('realtime-placeholder');
    const connectBtn = document.getElementById('connect-realtime');
    const stopBtn = document.getElementById('stop-realtime');
    const recordBtn = document.getElementById('start-record');
    const clearBtn = document.getElementById('clear-landing');
    const saveBtn = document.getElementById('save-landing');
    const progressText = document.getElementById('progress-text');
    const progressFill = document.querySelector('.realtime-progress');
    const headerStatus = document.querySelector('.realtime-page .status-chip span');

    const state = {
        connected: false,
        recording: false,
        frameWidth: 640,
        frameHeight: 400,
        filterSyncing: false,
        filterTimer: null,
        statusTimer: null,
    };

    const fields = {
        connection: document.getElementById('realtime-connection-state'),
        frameSize: document.getElementById('realtime-frame-size'),
        fps: document.getElementById('realtime-fps'),
        source: document.getElementById('realtime-source-state'),
        persons: document.getElementById('realtime-persons'),
        inference: document.getElementById('realtime-inference'),
        sync: document.getElementById('realtime-sync'),
        bed: document.getElementById('realtime-bed-state'),
        clicks: document.getElementById('realtime-clicks'),
        landings: document.getElementById('realtime-landings'),
        landingEmpty: document.getElementById('realtime-landing-empty'),
    };

    const filterControls = {
        blend_depth_pct: document.getElementById('filter-blend-depth'),
        order_preset: document.getElementById('filter-order-preset'),
        median_mode: document.getElementById('filter-median-mode'),
        speckle_enable: document.getElementById('filter-speckle-enable'),
        speckle_range: document.getElementById('filter-speckle-range'),
        speckle_diff: document.getElementById('filter-speckle-diff'),
        spatial_enable: document.getElementById('filter-spatial-enable'),
        spatial_alpha_pct: document.getElementById('filter-spatial-alpha'),
        spatial_delta: document.getElementById('filter-spatial-delta'),
        spatial_hole_radius: document.getElementById('filter-spatial-hole'),
        spatial_iterations: document.getElementById('filter-spatial-iterations'),
        show_raw_depth: document.getElementById('filter-show-raw'),
        show_filtered_depth: document.getElementById('filter-show-filtered'),
    };

    const valueLabels = {
        blend_depth_pct: document.getElementById('filter-blend-depth-value'),
        speckle_range: document.getElementById('filter-speckle-range-value'),
        speckle_diff: document.getElementById('filter-speckle-diff-value'),
        spatial_alpha_pct: document.getElementById('filter-spatial-alpha-value'),
        spatial_delta: document.getElementById('filter-spatial-delta-value'),
        spatial_hole_radius: document.getElementById('filter-spatial-hole-value'),
        spatial_iterations: document.getElementById('filter-spatial-iterations-value'),
    };

    function setText(node, value) {
        if (node) node.textContent = value;
    }

    function setConnected(connected, label) {
        state.connected = connected;
        stage.classList.toggle('is-connected', connected);
        if (placeholder) placeholder.classList.toggle('is-hidden', connected);
        setText(fields.connection, label || (connected ? '已连接' : '未连接'));
        setText(fields.source, connected ? 'OAK RGBD' : '未连接');
        setText(progressText, connected ? '运行中' : '待机');
        setText(headerStatus, connected ? '已连接' : '等待连接');
        if (progressFill) progressFill.style.width = connected ? '100%' : '8%';
    }

    function connectStream() {
        if (!video) return;
        video.src = `/api/realtime/video_feed?t=${Date.now()}`;
        setConnected(true, '连接中');
    }

    function stopStream() {
        if (!video) return;
        video.removeAttribute('src');
        setConnected(false, '已停止显示');
    }

    async function postJson(url, payload) {
        const response = await fetch(url, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify(payload),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok || data.success === false) {
            throw new Error(data.error || `请求失败：${response.status}`);
        }
        return data;
    }

    function readFilterParams() {
        return Object.fromEntries(Object.entries(filterControls).map(([key, control]) => {
            if (!control) return [key, 0];
            if (control.type === 'checkbox') return [key, control.checked ? 1 : 0];
            return [key, Number(control.value)];
        }));
    }

    function updateFilterLabels() {
        Object.entries(valueLabels).forEach(([key, label]) => {
            const control = filterControls[key];
            if (control && label) label.textContent = control.value;
        });
    }

    function applyFilterParams(params) {
        if (!params) return;
        state.filterSyncing = true;
        Object.entries(params).forEach(([key, value]) => {
            const control = filterControls[key];
            if (!control) return;
            if (control.type === 'checkbox') {
                control.checked = Number(value) !== 0;
            } else {
                control.value = String(value);
            }
        });
        updateFilterLabels();
        state.filterSyncing = false;
    }

    function scheduleFilterUpdate() {
        if (state.filterSyncing) return;
        updateFilterLabels();
        window.clearTimeout(state.filterTimer);
        state.filterTimer = window.setTimeout(async () => {
            try {
                await postJson('/api/realtime/filter', readFilterParams());
            } catch (error) {
                setConnected(false, error.message);
            }
        }, 120);
    }

    async function sendControl(action) {
        try {
            await postJson('/api/realtime/control', {action});
            await pollStatus();
        } catch (error) {
            setConnected(false, error.message);
        }
    }

    function updateStatus(data) {
        const frame = data.frame || {};
        state.frameWidth = Number(frame.width || state.frameWidth || 640);
        state.frameHeight = Number(frame.height || state.frameHeight || 400);
        state.recording = Boolean(data.recording);

        setConnected(Boolean(data.connected), data.connected ? '已连接' : '服务未连接');
        setText(fields.frameSize, `${state.frameWidth} x ${state.frameHeight}`);
        setText(fields.fps, data.fps == null ? '--' : Number(data.fps).toFixed(1));
        setText(fields.persons, data.detected_persons == null ? '--' : String(data.detected_persons));
        setText(fields.inference, data.inference_ms == null ? '--' : Number(data.inference_ms).toFixed(1));
        setText(fields.sync, data.sync_dt_ms == null ? '--' : Number(data.sync_dt_ms).toFixed(1));
        setText(fields.bed, data.bed_ready ? '已完成' : '未完成');
        setText(fields.clicks, `${Math.min(Number(data.roi_clicks || 0), 4)} / 4`);
        setText(fields.landings, String(data.landing_count || 0));
        setText(fields.landingEmpty, data.landing_count ? `已记录 ${data.landing_count} 个实时落点` : '等待实时落点');
        if (recordBtn) recordBtn.textContent = state.recording ? '停止记录落点' : '开始记录落点';
        applyFilterParams(data.filter_params);
    }

    async function pollStatus() {
        try {
            const response = await fetch('/api/realtime/status', {cache: 'no-store'});
            const data = await response.json();
            if (!response.ok || data.success === false) {
                throw new Error(data.error || '实时服务未连接');
            }
            updateStatus(data);
        } catch (error) {
            setConnected(false, '等待连接');
        }
    }

    function imagePointFromEvent(event) {
        const rect = video.getBoundingClientRect();
        const width = video.naturalWidth || state.frameWidth || 640;
        const height = video.naturalHeight || state.frameHeight || 400;
        return {
            x: Math.round((event.clientX - rect.left) * width / rect.width),
            y: Math.round((event.clientY - rect.top) * height / rect.height),
            button: 'left',
        };
    }

    if (connectBtn) connectBtn.addEventListener('click', connectStream);
    if (stopBtn) stopBtn.addEventListener('click', stopStream);
    if (recordBtn) {
        recordBtn.addEventListener('click', () => sendControl(state.recording ? 'stop_record' : 'start_record'));
    }
    if (clearBtn) clearBtn.addEventListener('click', () => sendControl('clear_landing'));
    if (saveBtn) saveBtn.addEventListener('click', () => sendControl('save_landing'));
    if (video) {
        video.addEventListener('click', async (event) => {
            try {
                await postJson('/api/realtime/click', imagePointFromEvent(event));
                await pollStatus();
            } catch (error) {
                setConnected(false, error.message);
            }
        });
        video.addEventListener('error', () => setConnected(false, '等待连接'));
        video.addEventListener('load', () => setConnected(true, '已连接'));
    }

    document.querySelectorAll('[data-realtime-action]').forEach((button) => {
        button.addEventListener('click', () => sendControl(button.dataset.realtimeAction));
    });

    Object.values(filterControls).forEach((control) => {
        if (!control) return;
        control.addEventListener('input', scheduleFilterUpdate);
        control.addEventListener('change', scheduleFilterUpdate);
    });

    updateFilterLabels();
    connectStream();
    pollStatus();
    state.statusTimer = window.setInterval(pollStatus, 1000);
    window.addEventListener('beforeunload', () => window.clearInterval(state.statusTimer));
});
