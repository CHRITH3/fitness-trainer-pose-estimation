from __future__ import annotations

from trampoline.bed_calibration import create_bed_calibration
from trampoline.landing import extract_landing_record
from trampoline.schema import JumpSegment


def _calibration():
    return create_bed_calibration(
        corners={
            "top_left": {"x": 0, "y": 0},
            "top_right": {"x": 100, "y": 0},
            "bottom_right": {"x": 100, "y": 100},
            "bottom_left": {"x": 0, "y": 100},
        },
        frame_width=100,
        frame_height=100,
    )


def _jump() -> JumpSegment:
    return JumpSegment(
        jump_id="jump-001",
        sequence_index=0,
        start_ms=0,
        takeoff_ms=100,
        apex_ms=200,
        landing_ms=300,
        end_ms=350,
    )


def test_extract_landing_prefers_feet_and_marks_single_leg() -> None:
    record = extract_landing_record(
        jump_segment=_jump(),
        landing_row={
            "frame_index": 9,
            "timestamp_ms": 300,
            "landmarks": [
                {"name": "left_foot_index", "x": 0.25, "y": 0.88, "visibility": 0.9},
                {"name": "left_heel", "x": 0.22, "y": 0.86, "visibility": 0.9},
                {"name": "left_ankle", "x": 0.24, "y": 0.8, "visibility": 0.9},
                {"name": "left_hip", "x": 0.3, "y": 0.6, "visibility": 0.9},
                {"name": "right_hip", "x": 0.7, "y": 0.6, "visibility": 0.9},
            ],
        },
        calibration=_calibration(),
        frame_width=100,
        frame_height=100,
    )

    assert record.valid is True
    assert record.landing_source == "feet"
    assert record.landing_x_norm == 0.2367
    assert record.landing_y_norm == 0.88
    assert record.zone in {"inner", "edge"}
    assert record.jump_flags == ["single_leg"]


def test_extract_landing_uses_hips_when_feet_are_missing() -> None:
    record = extract_landing_record(
        jump_segment=_jump(),
        landing_row={
            "frame_index": 9,
            "timestamp_ms": 300,
            "landmarks": [
                {"name": "left_hip", "x": 0.4, "y": 0.55, "visibility": 0.9},
                {"name": "right_hip", "x": 0.6, "y": 0.57, "visibility": 0.9},
            ],
        },
        calibration=_calibration(),
        frame_width=100,
        frame_height=100,
    )

    assert record.valid is True
    assert record.landing_source == "hip_fallback"
    assert record.landing_x_norm == 0.5
    assert record.landing_y_norm == 0.56
    assert record.jump_flags == []


def test_extract_landing_rejects_invalid_normalized_points() -> None:
    record = extract_landing_record(
        jump_segment=_jump(),
        landing_row={
            "frame_index": 9,
            "timestamp_ms": 300,
            "landmarks": [
                {"name": "left_foot_index", "x": 1.8, "y": 1.8, "visibility": 0.9},
            ],
        },
        calibration=_calibration(),
        frame_width=100,
        frame_height=100,
    )

    assert record.valid is False
    assert record.landing_source == "feet_invalid"
    assert record.landing_x_norm is None
    assert record.zone == "unknown"
