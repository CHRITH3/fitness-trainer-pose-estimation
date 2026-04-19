import assert from 'node:assert/strict';
import ui from '../static/js/trampoline_calibration_ui.js';

const { describeCalibrationUiState } = ui;

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

console.log('trampoline calibration ui tests passed');
