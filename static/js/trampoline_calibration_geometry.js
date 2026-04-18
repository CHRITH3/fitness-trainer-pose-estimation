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

    return {
        computeContainRect,
        displayToImagePoint,
        imageToDisplayPoint,
    };
});
