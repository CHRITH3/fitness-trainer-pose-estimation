(function(root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.TrampolineCalibrationGeometry = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    function validPositive(value) {
        return Number.isFinite(value) && value > 0;
    }

    function computeContainRect(imageWidth, imageHeight, displayWidth, displayHeight) {
        imageWidth = Number(imageWidth);
        imageHeight = Number(imageHeight);
        displayWidth = Number(displayWidth);
        displayHeight = Number(displayHeight);
        if (!validPositive(imageWidth) || !validPositive(imageHeight) ||
                !validPositive(displayWidth) || !validPositive(displayHeight)) {
            return null;
        }

        const scale = Math.min(displayWidth / imageWidth, displayHeight / imageHeight);
        const width = imageWidth * scale;
        const height = imageHeight * scale;
        return {
            x: (displayWidth - width) / 2,
            y: (displayHeight - height) / 2,
            width,
            height,
            scale,
        };
    }

    function displayToImagePoint(point, contentRect, imageSize) {
        if (!point || !contentRect || !imageSize) return null;
        const x = Number(point.x);
        const y = Number(point.y);
        const imageWidth = Number(imageSize.width);
        const imageHeight = Number(imageSize.height);
        if (!Number.isFinite(x) || !Number.isFinite(y) ||
                !validPositive(imageWidth) || !validPositive(imageHeight) ||
                !validPositive(contentRect.width) || !validPositive(contentRect.height)) {
            return null;
        }
        const epsilon = 1e-9;
        if (x < contentRect.x - epsilon || y < contentRect.y - epsilon ||
                x > contentRect.x + contentRect.width + epsilon ||
                y > contentRect.y + contentRect.height + epsilon) {
            return null;
        }
        return {
            x: ((x - contentRect.x) / contentRect.width) * imageWidth,
            y: ((y - contentRect.y) / contentRect.height) * imageHeight,
        };
    }

    function imageToDisplayPoint(point, contentRect, imageSize) {
        if (!point || !contentRect || !imageSize) return null;
        const x = Number(point.x);
        const y = Number(point.y);
        const imageWidth = Number(imageSize.width);
        const imageHeight = Number(imageSize.height);
        if (!Number.isFinite(x) || !Number.isFinite(y) ||
                !validPositive(imageWidth) || !validPositive(imageHeight) ||
                !validPositive(contentRect.width) || !validPositive(contentRect.height)) {
            return null;
        }
        return {
            x: contentRect.x + (x / imageWidth) * contentRect.width,
            y: contentRect.y + (y / imageHeight) * contentRect.height,
        };
    }

    function frameIndexFromTime(timeS, fps) {
        const t = Number(timeS);
        const f = Number(fps);
        if (!Number.isFinite(t) || t < 0 || !Number.isFinite(f) || f <= 0) {
            return 0;
        }
        return Math.max(0, Math.round(t * f));
    }

    function buildCalibrationPayload(keyframes) {
        if (!Array.isArray(keyframes)) return [];
        return keyframes
            .filter(kf => kf && Array.isArray(kf.corners_px) && kf.corners_px.length === 4)
            .map(kf => ({
                frame_index: Math.max(0, Math.round(Number(kf.frame_index) || 0)),
                time_s: Math.max(0, Number(kf.time_s) || 0),
                corners_px: kf.corners_px.map((pt, idx) => ({
                    name: pt.name || ['front_left', 'front_right', 'back_right', 'back_left'][idx],
                    x: Number(pt.x),
                    y: Number(pt.y),
                })),
            }))
            .sort((a, b) => a.frame_index - b.frame_index);
    }

    return {
        computeContainRect,
        displayToImagePoint,
        imageToDisplayPoint,
        frameIndexFromTime,
        buildCalibrationPayload,
    };
});
