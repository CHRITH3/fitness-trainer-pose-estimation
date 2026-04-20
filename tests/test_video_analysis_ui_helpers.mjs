import assert from 'node:assert/strict';
import helpers from '../static/js/video_analysis_helpers.js';

const { resolveCompactStats } = helpers;

{
    const state = resolveCompactStats({
        fps: 25,
        current_flight_frames: 20,
        phase: 'flight',
        current_action: 'Tuck',
        latest_landing: {
            bed_xy_m: [2.1, 1.0],
            norm_xy: [0.49, 0.47],
            confidence: 0.82,
        },
        completed_jumps: [],
    });
    assert.equal(state.flightSeconds, 0.8);
    assert.equal(state.action, 'Tuck');
    assert.equal(state.landing.confidence, 0.82);
}

{
    const state = resolveCompactStats({
        fps: 50,
        current_action: '--',
        completed_jumps: [
            { jump_number: 1, action: 'Straight', flight_frames: 25, landing: { bed_xy_m: [1, 1], norm_xy: [0.2, 0.4], confidence: 0.7 } },
            { jump_number: 2, action: 'Pike', flight_duration_s: 0.72, landing: { bed_xy_m: [3, 1.5], norm_xy: [0.7, 0.7], confidence: 0.5 } },
        ],
    });
    assert.equal(state.flightSeconds, 0.72);
    assert.equal(state.action, 'Pike');
    assert.deepEqual(state.landing.bed_xy_m, [3, 1.5]);
}

{
    const state = resolveCompactStats({
        fps: 30,
        phase: 'contact',
        current_flight_frames: 18,
        current_flight_duration_s: 0.6,
        current_action: '--',
        completed_jumps: [
            { jump_number: 2, action: 'Straight', flight_duration_s: 0.44, landing: { bed_xy_m: [2.2, 1.3], norm_xy: [0.51, 0.56], confidence: 0.76 } },
        ],
    });
    assert.equal(state.flightSeconds, 0.44);
    assert.equal(state.action, 'Straight');
    assert.deepEqual(state.landing.norm_xy, [0.51, 0.56]);
}

{
    const state = resolveCompactStats({
        current_action: 'Unknown',
        latest_landing: { confidence: 0.9 },
        completed_jumps: [
            { action: 'Tuck', flight_frames: 30, is_intermediate: true, landing: { norm_xy: [0.1, 0.1] } },
        ],
    });
    assert.equal(state.flightSeconds, null);
    assert.equal(state.action, '--');
    assert.equal(state.landing, null);
}

console.log('video analysis compact stats helper tests passed');
