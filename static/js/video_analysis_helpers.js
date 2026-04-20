(function(root, factory) {
    const api = factory();
    if (typeof module !== 'undefined' && module.exports) {
        module.exports = api;
    }
    if (root) {
        root.VideoAnalysisHelpers = api;
    }
})(typeof globalThis !== 'undefined' ? globalThis : this, function() {
    function finiteNumber(value) {
        const n = Number(value);
        return Number.isFinite(n) ? n : null;
    }

    function validLanding(landing) {
        if (!landing || typeof landing !== 'object') return null;
        const xy = Array.isArray(landing.bed_xy_m) ? landing.bed_xy_m : null;
        const norm = Array.isArray(landing.norm_xy) ? landing.norm_xy : null;
        const hasMeters = xy && xy.length >= 2 && finiteNumber(xy[0]) !== null && finiteNumber(xy[1]) !== null;
        const hasNorm = norm && norm.length >= 2 && finiteNumber(norm[0]) !== null && finiteNumber(norm[1]) !== null;
        return hasMeters || hasNorm ? landing : null;
    }

    function resolveCompactStats(data = {}, previousCompletedJumps = []) {
        const completed = Array.isArray(data.completed_jumps) ? data.completed_jumps : previousCompletedJumps;
        const realJumps = (Array.isArray(completed) ? completed : []).filter(jump => jump && !jump.is_intermediate);
        const latestJump = realJumps[realJumps.length - 1] || null;
        const fps = finiteNumber(data.video_fps ?? data.fps) || 30;
        const phase = String(data.phase || '').toLowerCase();
        const currentFlightFrames = finiteNumber(data.current_flight_frames);

        let flightSeconds = null;
        if (phase === 'flight') {
            flightSeconds = finiteNumber(data.current_flight_duration_s ?? data.current_flight_time_s ?? data.flight_duration_s);
            if (flightSeconds === null && currentFlightFrames !== null) {
                flightSeconds = currentFlightFrames / fps;
            }
        }
        if (flightSeconds === null && latestJump) {
            const jumpDuration = finiteNumber(latestJump.flight_duration_s);
            const jumpFrames = finiteNumber(latestJump.flight_frames);
            flightSeconds = jumpDuration !== null ? jumpDuration : (jumpFrames !== null ? jumpFrames / fps : null);
        }

        let action = data.current_action;
        if (!action || action === '--' || action === 'Unknown') action = latestJump?.action || '--';

        let landing = validLanding(data.latest_landing);
        if (!landing) {
            const landings = Array.isArray(data.landings) ? data.landings.filter(validLanding) : [];
            landing = landings[landings.length - 1] || null;
        }
        if (!landing && latestJump) landing = validLanding(latestJump.landing);

        return { flightSeconds, action, landing };
    }

    return {
        finiteNumber,
        validLanding,
        resolveCompactStats,
    };
});
