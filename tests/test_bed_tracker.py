"""Tests for trampoline bed-plane calibration and landing mapping."""

import json

import cv2
import numpy as np
import pytest

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
