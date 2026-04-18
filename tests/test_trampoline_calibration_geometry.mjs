import assert from 'node:assert/strict';
import geometry from '../static/js/trampoline_calibration_geometry.js';

const { computeContainRect, displayToImagePoint, imageToDisplayPoint, buildCalibrationPayload } = geometry;

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

// Keyframe payload builder sorts and serializes original-pixel corners.
{
    const corners = [
        { name: 'front_left', x: 10, y: 90 },
        { name: 'front_right', x: 90, y: 90 },
        { name: 'back_right', x: 90, y: 10 },
        { name: 'back_left', x: 10, y: 10 },
    ];
    const payload = buildCalibrationPayload([
        { frameIndex: 45, timeS: 1.5, corners },
        { frameIndex: 0, timeS: 0, corners },
    ]);
    assert.equal(payload.length, 2);
    assert.equal(payload[0].frame_index, 0);
    assert.equal(payload[1].frame_index, 45);
    assert.deepEqual(payload[1].corners_px.map(p => p.name), ['front_left', 'front_right', 'back_right', 'back_left']);
}

console.log('trampoline calibration geometry tests passed');
