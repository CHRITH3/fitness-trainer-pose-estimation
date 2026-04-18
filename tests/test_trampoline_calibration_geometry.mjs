import assert from 'node:assert/strict';
import geometry from '../static/js/trampoline_calibration_geometry.js';

const {
    computeContainRect,
    displayToImagePoint,
    imageToDisplayPoint,
    frameIndexFromTime,
    buildCalibrationPayload,
} = geometry;

function approx(actual, expected, tolerance = 1) {
    assert.ok(Math.abs(actual - expected) <= tolerance, `${actual} not within ${tolerance} of ${expected}`);
}

// Portrait image inside a landscape display: side bars must be outside content.
{
    const rect = computeContainRect(720, 1280, 800, 500);
    assert.ok(rect.x > 250, 'portrait image should have side bars in a wide display');
    assert.equal(displayToImagePoint({ x: 10, y: 250 }, rect, { width: 720, height: 1280 }), null);

    const displayPoint = {
        x: rect.x + rect.width * 0.25,
        y: rect.y + rect.height * 0.75,
    };
    const mapped = displayToImagePoint(displayPoint, rect, { width: 720, height: 1280 });
    approx(mapped.x, 180);
    approx(mapped.y, 960);
}

// Landscape image with matching display aspect: no letterbox and mapping is direct scale.
{
    const rect = computeContainRect(1280, 720, 800, 450);
    approx(rect.x, 0, 1e-9);
    approx(rect.y, 0, 1e-9);
    const mapped = displayToImagePoint({ x: 400, y: 225 }, rect, { width: 1280, height: 720 });
    approx(mapped.x, 640);
    approx(mapped.y, 360);
}

// Drawing round-trip: original image point -> display -> original.
{
    const imageSize = { width: 720, height: 1280 };
    const rect = computeContainRect(imageSize.width, imageSize.height, 800, 500);
    const original = { x: 503, y: 1177 };
    const displayed = imageToDisplayPoint(original, rect, imageSize);
    const roundTrip = displayToImagePoint(displayed, rect, imageSize);
    approx(roundTrip.x, original.x);
    approx(roundTrip.y, original.y);
}

// Keyframe frame-index helper is stable and non-negative.
{
    assert.equal(frameIndexFromTime(0, 30), 0);
    assert.equal(frameIndexFromTime(2.4, 30), 72);
    assert.equal(frameIndexFromTime(-1, 30), 0);
}

// Keyframe payload builder sorts and normalizes complete drafts only.
{
    const payload = buildCalibrationPayload([
        { frame_index: 90, time_s: 3, corners_px: [
            { x: 1, y: 2 }, { x: 3, y: 4 }, { x: 5, y: 6 }, { x: 7, y: 8 },
        ] },
        { frame_index: 15, time_s: 0.5, corners_px: [
            { name: 'front_left', x: 9, y: 10 },
            { name: 'front_right', x: 11, y: 12 },
            { name: 'back_right', x: 13, y: 14 },
            { name: 'back_left', x: 15, y: 16 },
        ] },
        { frame_index: 120, time_s: 4, corners_px: [{ x: 0, y: 0 }] },
    ]);
    assert.equal(payload.length, 2);
    assert.deepEqual(payload.map(item => item.frame_index), [15, 90]);
    assert.equal(payload[1].corners_px[0].name, 'front_left');
    assert.equal(payload[1].corners_px[3].name, 'back_left');
}

console.log('trampoline calibration geometry tests passed');
