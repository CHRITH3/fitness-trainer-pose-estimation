import assert from 'node:assert/strict';
import ui from '../static/js/trampoline_calibration_ui.js';
import geometry from '../static/js/trampoline_calibration_geometry.js';

const { describeCalibrationUiState, getCalibrationOverlayRequirement, createController } = ui;

class FakeClassList {
    constructor(initial = []) {
        this._set = new Set(initial);
    }
    add(...names) { names.forEach(name => this._set.add(name)); }
    remove(...names) { names.forEach(name => this._set.delete(name)); }
    toggle(name, force) {
        if (force === undefined) {
            if (this._set.has(name)) {
                this._set.delete(name);
                return false;
            }
            this._set.add(name);
            return true;
        }
        if (force) this._set.add(name);
        else this._set.delete(name);
        return Boolean(force);
    }
    contains(name) { return this._set.has(name); }
}

class FakeElement {
    constructor(id = null, tagName = 'div') {
        this.id = id;
        this.tagName = tagName.toUpperCase();
        this.children = [];
        this.listeners = new Map();
        this.classList = new FakeClassList();
        this.style = {};
        this.dataset = {};
        this.hidden = false;
        this.disabled = false;
        this.textContent = '';
        this.innerHTML = '';
        this.clientWidth = 0;
        this.width = 0;
        this.height = 0;
    }

    addEventListener(type, handler) {
        const handlers = this.listeners.get(type) || [];
        handlers.push(handler);
        this.listeners.set(type, handlers);
    }

    dispatchEvent(type, event = {}) {
        const handlers = this.listeners.get(type) || [];
        handlers.forEach(handler => handler(event));
    }

    click(event = {}) {
        this.dispatchEvent('click', event);
    }

    appendChild(child) {
        this.children.push(child);
        return child;
    }

    querySelectorAll() {
        return [];
    }

    getBoundingClientRect() {
        return { left: 0, top: 0, width: this.width || 0, height: this.height || 0 };
    }
}

class FakeCanvasElement extends FakeElement {
    constructor(id = null, dataUrlFactory = null) {
        super(id, 'canvas');
        this._dataUrlFactory = dataUrlFactory || (() => 'data:image/png;base64,FAKE');
    }

    getContext() {
        return {
            clearRect() {},
            save() {},
            restore() {},
            beginPath() {},
            moveTo() {},
            lineTo() {},
            closePath() {},
            stroke() {},
            fill() {},
            arc() {},
            fillText() {},
            drawImage() {},
        };
    }

    toDataURL() {
        return this._dataUrlFactory();
    }
}

class FakeImage {
    constructor() {
        this.naturalWidth = 640;
        this.naturalHeight = 360;
        this.width = 640;
        this.height = 360;
        this.onload = null;
    }

    set src(value) {
        this._src = value;
        if (this.onload) this.onload();
    }

    get src() {
        return this._src;
    }
}

function createFakeControllerEnv() {
    const elements = new Map();
    const videoPlayer = new FakeElement('video-player', 'video');
    videoPlayer.videoWidth = 640;
    videoPlayer.videoHeight = 360;
    videoPlayer.currentTime = 0;
    videoPlayer.pause = () => {};
    videoPlayer.play = () => {};
    videoPlayer.getBoundingClientRect = () => ({ left: 0, top: 0, width: 640, height: 360 });

    const analysisCanvas = new FakeCanvasElement('analysis-canvas');
    analysisCanvas.hidden = true;
    analysisCanvas.width = 640;
    analysisCanvas.height = 360;
    analysisCanvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 640, height: 360 });

    const videoContainer = new FakeElement('video-container');
    videoContainer.width = 640;
    videoContainer.height = 360;
    videoContainer.getBoundingClientRect = () => ({ left: 0, top: 0, width: 640, height: 360 });

    const cornerStep = new FakeElement('corner-marking-step');
    cornerStep.classList.add('hidden');

    const ids = [
        'corner-count',
        'reset-corners',
        'keyframe-list',
        'confirm-corners',
        'add-calibration-frame',
        'delete-calibration',
        'start-trampoline-analysis',
        'calibration-list',
        'calibration-draft-label',
        'calibration-status-text',
    ];

    elements.set('video-player', videoPlayer);
    elements.set('analysis-canvas', analysisCanvas);
    elements.set('video-container', videoContainer);
    elements.set('corner-marking-step', cornerStep);
    ids.forEach(id => elements.set(id, new FakeElement(id, id.includes('button') ? 'button' : 'div')));

    const documentRef = {
        getElementById(id) {
            return elements.get(id) || null;
        },
        createElement(tag) {
            if (tag === 'canvas') {
                return new FakeCanvasElement(null, () => `data:image/png;base64,frame-${videoPlayer.currentTime.toFixed(2)}`);
            }
            return new FakeElement(null, tag);
        },
    };

    return {
        documentRef,
        elements,
        videoPlayer,
        analysisCanvas,
        videoContainer,
    };
}

{
    const state = describeCalibrationUiState();
    assert.equal(state.draftLabel, '当前草稿：未选择');
    assert.equal(state.statusText, '至少保存 1 个有效标定后才能开始分析。');
    assert.equal(state.canSave, false);
    assert.equal(state.canStart, false);
    assert.equal(state.canDelete, false);
}

{
    const state = describeCalibrationUiState({
        activeKeyframeFrame: 42,
        activeKeyframeTimeS: 1.4,
        draftCornerCount: 4,
        savedCalibrationCount: 2,
        hasSelectedCalibration: true,
    });
    assert.equal(state.draftLabel, '当前草稿：F42 / 1.40s');
    assert.equal(state.statusText, '已保存 2 个有效标定，可开始分析。');
    assert.equal(state.canSave, true);
    assert.equal(state.canStart, true);
    assert.equal(state.canDelete, true);
}

{
    const requirement = getCalibrationOverlayRequirement();
    assert.equal(requirement.clickSurfaceId, 'analysis-canvas');
    assert.equal(requirement.requiresLowerStandaloneCanvas, false);
}

{
    const previousWindow = globalThis.window;
    globalThis.window = { addEventListener() {} };

    const { documentRef, elements, videoPlayer, analysisCanvas, videoContainer } = createFakeControllerEnv();
    const controller = createController({
        documentRef,
        videoPlayer,
        analysisCanvas,
        geometry,
        ImageCtor: FakeImage,
        fetchImpl: async () => ({ json: async () => ({ success: true }) }),
    });

    controller.enterPendingCalibration({
        videoId: 'video-1',
        imageSrc: 'data:image/png;base64,initial',
        videoFps: 30,
    });

    assert.equal(analysisCanvas.hidden, true);
    assert.equal(videoContainer.classList.contains('calibration-active'), false);
    assert.equal(elements.get('calibration-draft-label').textContent, '当前草稿：未选择');

    videoPlayer.currentTime = 2;
    elements.get('add-calibration-frame').click();

    assert.equal(analysisCanvas.hidden, false);
    assert.equal(videoContainer.classList.contains('calibration-active'), true);
    assert.equal(elements.get('calibration-draft-label').textContent, '当前草稿：F60 / 2.00s');

    const clicks = [
        { clientX: 10, clientY: 20 },
        { clientX: 630, clientY: 20 },
        { clientX: 630, clientY: 340 },
        { clientX: 10, clientY: 340 },
    ];
    clicks.forEach(event => analysisCanvas.click(event));

    assert.equal(elements.get('corner-count').textContent, '4/4');
    assert.equal(elements.get('confirm-corners').disabled, false);

    elements.get('confirm-corners').click();

    assert.equal(analysisCanvas.hidden, true);
    assert.equal(videoContainer.classList.contains('calibration-active'), false);
    assert.equal(elements.get('calibration-draft-label').textContent, '当前草稿：未选择');

    const payload = controller.getCalibrationPayload();
    assert.equal(payload.length, 1);
    assert.equal(payload[0].frame_index, 60);
    assert.equal(payload[0].time_s, 2);
    assert.deepEqual(
        payload[0].corners_px.map(({ x, y }) => [Math.round(x), Math.round(y)]),
        [[10, 20], [630, 20], [630, 340], [10, 340]],
    );

    globalThis.window = previousWindow;
}

{
    const previousWindow = globalThis.window;
    globalThis.window = { addEventListener() {} };

    const { documentRef, elements, videoPlayer, analysisCanvas, videoContainer } = createFakeControllerEnv();
    const controller = createController({
        documentRef,
        videoPlayer,
        analysisCanvas,
        geometry,
        ImageCtor: FakeImage,
    });

    controller.enterPendingCalibration({
        videoId: 'video-2',
        imageSrc: 'data:image/png;base64,initial',
        videoFps: 30,
    });
    analysisCanvas.click({ clientX: 50, clientY: 60 });
    assert.equal(elements.get('corner-count').textContent, '0/4');

    videoPlayer.currentTime = 1;
    elements.get('add-calibration-frame').click();
    analysisCanvas.click({ clientX: 50, clientY: 60 });

    assert.equal(analysisCanvas.hidden, false);
    assert.equal(videoContainer.classList.contains('calibration-active'), true);

    elements.get('reset-corners').click();

    assert.equal(elements.get('corner-count').textContent, '0/4');
    assert.equal(analysisCanvas.hidden, false);
    assert.equal(videoContainer.classList.contains('calibration-active'), true);
    assert.equal(controller.getCalibrationPayload().length, 0);

    globalThis.window = previousWindow;
}

console.log('trampoline calibration ui tests passed');
