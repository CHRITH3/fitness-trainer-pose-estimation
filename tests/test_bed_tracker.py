"""Tests for trampoline bed-plane calibration and landing mapping."""

import json

import cv2
import numpy as np
import pytest

from trampoline.overlay import draw_bed_minimap, draw_marker_lines
from trampoline.bed_tracker import (
    BedTracker,
    BedTrackerValidationError,
    classify_landing_zone,
    load_corners_sidecar,
    validate_corners,
)


RECT_CORNERS = [
    {"name": "front_left", "x": 100, "y": 300},
    {"name": "front_right", "x": 500, "y": 300},
    {"name": "back_right", "x": 500, "y": 100},
    {"name": "back_left", "x": 100, "y": 100},
]


def textured_frame(width=640, height=480):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    cv2.rectangle(frame, (100, 100), (500, 300), (35, 35, 35), -1)
    for x in range(120, 500, 35):
        for y in range(120, 300, 30):
            cv2.circle(frame, (x, y), 3, (255, 255, 255), -1)
    return frame


def test_image_to_bed_mapping_center_and_axes():
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))

    assert tracker.image_to_bed((100, 300)) == pytest.approx((0.0, 0.0), abs=1e-4)
    assert tracker.image_to_bed((500, 300)) == pytest.approx((4.0, 0.0), abs=1e-4)
    assert tracker.image_to_bed((500, 100)) == pytest.approx((4.0, 2.0), abs=1e-4)
    assert tracker.image_to_bed((300, 200)) == pytest.approx((2.0, 1.0), abs=1e-4)


def test_classify_landing_zone():
    assert classify_landing_zone((2.14, 1.07), (4.28, 2.14)) == "center"
    assert classify_landing_zone((2.14, 1.8), (4.28, 2.14)) == "mid"
    assert classify_landing_zone((0.1, 1.0), (4.28, 2.14)) == "edge"
    assert classify_landing_zone((-0.1, 1.0), (4.28, 2.14)) == "off_bed"


def test_invalid_quadrilaterals_rejected():
    with pytest.raises(BedTrackerValidationError):
        validate_corners(RECT_CORNERS[:3], image_size=(640, 480))
    with pytest.raises(BedTrackerValidationError):
        validate_corners([RECT_CORNERS[0], RECT_CORNERS[0], RECT_CORNERS[2], RECT_CORNERS[3]], image_size=(640, 480))
    crossing = [RECT_CORNERS[0], RECT_CORNERS[2], RECT_CORNERS[1], RECT_CORNERS[3]]
    with pytest.raises(BedTrackerValidationError):
        validate_corners(crossing, image_size=(640, 480))
    out_of_bounds = [dict(p) for p in RECT_CORNERS]
    out_of_bounds[0]["x"] = -1
    with pytest.raises(BedTrackerValidationError):
        validate_corners(out_of_bounds, image_size=(640, 480))


def test_sidecar_parsing_tolerates_unknown_fields(tmp_path):
    path = tmp_path / "vid_corners.json"
    data = {
        "schema_version": 1,
        "video_id": "vid",
        "exercise_type": "trampoline",
        "frame_index": 0,
        "image_size": {"width": 640, "height": 480},
        "corner_order": ["front_left", "front_right", "back_right", "back_left"],
        "corners_px": RECT_CORNERS,
        "bed_dimensions_m": {"width": 4.28, "length": 2.14},
        "created_at": "2026-04-17T00:00:00Z",
        "unknown": "ok",
    }
    path.write_text(json.dumps(data))
    parsed = load_corners_sidecar(str(path), expected_video_id="vid")
    assert parsed["unknown"] == "ok"


def test_sidecar_missing_required_fields_rejected(tmp_path):
    path = tmp_path / "vid_corners.json"
    data = {
        "schema_version": 1,
        "video_id": "vid",
        "exercise_type": "trampoline",
        "image_size": {"width": 640, "height": 480},
        "corner_order": ["front_left", "front_right", "back_right", "back_left"],
        "corners_px": RECT_CORNERS,
        "bed_dimensions_m": {"width": 4.28, "length": 2.14},
    }
    path.write_text(json.dumps(data))
    with pytest.raises(BedTrackerValidationError, match="created_at|frame_index"):
        load_corners_sidecar(str(path), expected_video_id="vid")

def test_landing_payload_low_confidence_still_outputs_coordinates():
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    tracker.current_info["tracking_confidence"] = 0.1

    payload = tracker.landing_payload((300, 200), ankle_visibility=0.2)

    assert payload["bed_xy_m"] == pytest.approx([2.0, 1.0], abs=1e-3)
    assert payload["confidence"] < 0.5
    assert payload["zone"] == "center"


def test_known_warp_recovery():
    first = textured_frame()
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    tracker.initialize(first, frame_index=1)

    src = np.array([[0, 0], [639, 0], [639, 479], [0, 479]], dtype=np.float32)
    dst = np.array([[5, 3], [634, 8], [631, 474], [8, 470]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(first, H, (640, 480))
    info = tracker.update(warped, frame_index=2)

    expected_corners = np.array([[[p["x"], p["y"]] for p in RECT_CORNERS]], dtype=np.float32)
    expected = cv2.perspectiveTransform(expected_corners, H).reshape(-1, 2)
    assert info["success"]
    assert np.max(np.linalg.norm(np.array(info["corners"]) - expected, axis=1)) < 4.0


def noisy_textured_frame(width=640, height=480):
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    rng = np.random.default_rng(42)
    cv2.rectangle(frame, (100, 100), (500, 300), (25, 25, 25), -1)
    for idx in range(120):
        x = int(rng.integers(115, 485))
        y = int(rng.integers(115, 285))
        color = int(rng.integers(90, 255))
        cv2.circle(frame, (x, y), int(rng.integers(2, 5)), (color, color, color), -1)
        if idx % 10 == 0:
            cv2.rectangle(frame, (x - 4, y - 3), (x + 5, y + 4), (255 - color, color, 180), 1)
    cv2.putText(frame, "TRAMP", (170, 205), cv2.FONT_HERSHEY_SIMPLEX, 1.3, (220, 220, 220), 3)
    return frame


def test_candidate_sanity_rejects_self_intersection_and_preserves_trusted_corners():
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    frame = textured_frame()
    tracker.initialize(frame, frame_index=1)
    trusted = tracker.current_corners.copy()
    bad = np.array([[100, 300], [500, 100], [500, 300], [100, 100]], dtype=np.float32)

    diagnostics = tracker.validate_candidate_corners(bad, inlier_ratio=1.0, tracked_points=50)
    info = tracker._reject_candidate(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 2, 1.0, 50, diagnostics)

    assert not diagnostics["accepted"]
    assert "self_intersection" in diagnostics["reasons"]
    assert np.allclose(tracker.current_corners, trusted)
    assert info["tracking_state"] in {"frozen", "tracking_lost"}
    assert info["tracking_confidence"] < 0.6


def test_candidate_sanity_rejects_area_and_center_jumps():
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    tracker.initialize(textured_frame(), frame_index=1)

    huge = np.array([[0, 470], [639, 470], [639, 0], [0, 0]], dtype=np.float32)
    huge_diag = tracker.validate_candidate_corners(huge, inlier_ratio=1.0, tracked_points=50)
    assert not huge_diag["accepted"]
    assert "area_jump" in huge_diag["reasons"] or "center_shift" in huge_diag["reasons"]

    shifted = tracker.current_corners + np.array([400, 0], dtype=np.float32)
    shifted_diag = tracker.validate_candidate_corners(shifted, inlier_ratio=1.0, tracked_points=50)
    assert not shifted_diag["accepted"]
    assert "center_shift" in shifted_diag["reasons"] or "out_of_bounds" in shifted_diag["reasons"]


def test_candidate_sanity_rejects_low_inlier_support():
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    tracker.initialize(textured_frame(), frame_index=1)

    diagnostics = tracker.validate_candidate_corners(tracker.current_corners + 1, inlier_ratio=0.1, tracked_points=3)

    assert not diagnostics["accepted"]
    assert "too_few_points" in diagnostics["reasons"]
    assert "low_inlier_ratio" in diagnostics["reasons"]


def test_rejected_update_preserves_low_confidence_landing_output():
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    frame = textured_frame()
    tracker.initialize(frame, frame_index=1)
    diagnostics = tracker.validate_candidate_corners(tracker.current_corners + np.array([400, 0], dtype=np.float32), 0.1, 3)
    tracker._reject_candidate(cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY), 2, 0.1, 3, diagnostics)

    payload = tracker.landing_payload((300, 200), ankle_visibility=0.5)

    assert payload["bed_xy_m"] == pytest.approx([2.0, 1.0], abs=1e-3)
    assert payload["confidence"] < 0.6


def test_orb_relocalization_recovers_controlled_warp():
    first = noisy_textured_frame()
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    tracker.initialize(first, frame_index=1)

    src = np.array([[0, 0], [639, 0], [639, 479], [0, 479]], dtype=np.float32)
    dst = np.array([[16, 10], [620, 18], [612, 460], [24, 452]], dtype=np.float32)
    H = cv2.getPerspectiveTransform(src, dst)
    warped = cv2.warpPerspective(first, H, (640, 480))
    info = tracker._try_relocalize(cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY), frame_index=2)
    expected = cv2.perspectiveTransform(
        np.array([[[p["x"], p["y"]] for p in RECT_CORNERS]], dtype=np.float32), H
    ).reshape(-1, 2)

    assert info["success"], info
    assert info["diagnostics"]["source"] == "orb"
    assert np.max(np.linalg.norm(np.array(info["corners"]) - expected, axis=1)) < 20.0


def test_failed_orb_relocalization_freezes_without_moving_corners():
    first = noisy_textured_frame()
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    tracker.initialize(first, frame_index=1)
    trusted = tracker.current_corners.copy()
    blank = np.zeros((480, 640), dtype=np.uint8)

    info = tracker._try_relocalize(blank, frame_index=2)

    assert not info["success"]
    assert np.allclose(tracker.current_corners, trusted)
    assert info["tracking_state"] in {"frozen", "tracking_lost"}


def test_update_without_orb_keyframe_degrades_instead_of_returning_none():
    first = textured_frame()
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    tracker.initialize(first, frame_index=1)
    tracker._keyframe_descriptors = None
    tracker._keyframe_keypoints = None
    tracker._keyframe_corners = None
    tracker._prev_pts = None

    info = tracker.update(np.zeros_like(first), frame_index=2)

    assert info is not None
    assert not info["success"]
    assert info["tracking_state"] in {"frozen", "tracking_lost"}
    assert info["tracking_confidence"] < 0.6
    assert "no_keyframe" in info["diagnostics"]["reasons"]


def shifted_corners(dx=20, dy=0):
    return [{**p, "x": p["x"] + dx, "y": p["y"] + dy} for p in RECT_CORNERS]


def test_extended_sidecar_loads_multiple_calibrations(tmp_path):
    path = tmp_path / "vid_corners.json"
    path.write_text(json.dumps({
        "schema_version": 2,
        "video_id": "vid",
        "exercise_type": "trampoline",
        "frame_index": 0,
        "image_size": {"width": 640, "height": 480},
        "corner_order": ["front_left", "front_right", "back_right", "back_left"],
        "corners_px": RECT_CORNERS,
        "calibrations": [
            {"frame_index": 20, "time_s": 0.66, "corners_px": shifted_corners(20)},
            {"frame_index": 0, "time_s": 0.0, "corners_px": RECT_CORNERS},
        ],
        "bed_dimensions_m": {"width": 4.28, "length": 2.14},
        "created_at": "2026-04-18T00:00:00Z",
    }))

    parsed = load_corners_sidecar(str(path), expected_video_id="vid")
    tracker = BedTracker.from_sidecar(parsed)

    assert [c["frame_index"] for c in parsed["calibrations"]] == [0, 20]
    assert len(tracker.manual_calibrations) == 2


def test_manual_keyframe_transition_applies_smoothly():
    frame = textured_frame()
    tracker = BedTracker(
        RECT_CORNERS,
        bed_size_m=(4.0, 2.0),
        image_size=(640, 480),
        calibrations=[
            {"frame_index": 0, "time_s": 0, "corners_px": RECT_CORNERS},
            {"frame_index": 20, "time_s": 0.66, "corners_px": shifted_corners(20)},
        ],
    )
    tracker.initialize(frame, frame_index=0)

    info = tracker.update(frame, frame_index=1)
    assert info["diagnostics"]["source"] == "manual_keyframe"
    assert 0 < info["diagnostics"]["transition_progress"] < 1
    assert 0 < np.max(np.array(info["corners"]) - np.array([[p["x"], p["y"]] for p in RECT_CORNERS])) < 20

    info = tracker.update(frame, frame_index=20)
    assert info["diagnostics"]["source"] == "manual_keyframe"
    assert np.allclose(np.array(info["corners"]), np.array([[p["x"], p["y"]] for p in shifted_corners(20)]), atol=1)


def test_marker_line_detection_and_overlay_safe():
    frame = textured_frame()
    cv2.line(frame, (120, 200), (480, 200), (255, 255, 255), 4)
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    tracker.initialize(frame, frame_index=0)

    lines = tracker.current_info["diagnostics"].get("marker_lines", [])
    assert lines
    before = frame.copy()
    draw_marker_lines(frame, lines)
    assert np.count_nonzero(cv2.absdiff(before, frame)) > 0


def test_blank_marker_line_detection_is_safe():
    frame = np.zeros((480, 640, 3), dtype=np.uint8)
    tracker = BedTracker(RECT_CORNERS, bed_size_m=(4.0, 2.0), image_size=(640, 480))
    info = tracker.initialize(frame, frame_index=0)
    assert info["diagnostics"].get("marker_lines") == []


def test_adaptive_minimap_scales_on_high_resolution_and_bounds_small():
    landings = [{"norm_xy": [0.5, 0.5], "confidence": 0.9}]
    high = np.zeros((1080, 1920, 3), dtype=np.uint8)
    draw_bed_minimap(high, landings)
    ys, xs = np.nonzero(np.any(high != 0, axis=2))
    assert xs.max() - xs.min() > 150
    assert ys.max() < high.shape[0] and xs.max() < high.shape[1]

    small = np.zeros((240, 320, 3), dtype=np.uint8)
    draw_bed_minimap(small, landings)
    ys, xs = np.nonzero(np.any(small != 0, axis=2))
    assert ys.size > 0
    assert ys.min() >= 0 and xs.min() >= 0
    assert ys.max() < small.shape[0] and xs.max() < small.shape[1]
