from __future__ import annotations

from trampoline.features import build_jump_feature_rows, calculate_angle, extract_frame_angles
from trampoline.schema import JumpSegment


def _landmark(name: str, x: float, y: float, visibility: float = 0.99) -> dict[str, float | str]:
    return {
        "index": 0,
        "name": name,
        "x": x,
        "y": y,
        "z": 0.0,
        "visibility": visibility,
        "presence": visibility,
    }


def test_calculate_angle_returns_expected_degrees() -> None:
    assert round(calculate_angle((0.0, 0.0), (0.0, 1.0), (1.0, 1.0)) or 0.0, 3) == 90.0
    assert round(calculate_angle((0.0, 0.0), (1.0, 0.0), (2.0, 0.0)) or 0.0, 3) == 180.0


def test_extract_frame_angles_filters_low_visibility_and_prefers_best_side() -> None:
    row = {
        "frame_index": 0,
        "timestamp_ms": 1000,
        "landmarks": [
            _landmark("left_shoulder", 0.0, 0.0),
            _landmark("left_hip", 0.0, 1.0),
            _landmark("left_knee", 1.0, 1.0),
            _landmark("left_ankle", 2.0, 1.0),
            _landmark("right_shoulder", 0.0, 0.0, visibility=0.2),
            _landmark("right_hip", 0.0, 1.0, visibility=0.2),
            _landmark("right_knee", 0.0, 2.0, visibility=0.2),
            _landmark("right_ankle", 0.0, 3.0, visibility=0.2),
        ],
    }

    angles = extract_frame_angles(row)

    assert angles["angle_side"] == "left"
    assert angles["landmark_visibility_ok"] is True
    assert angles["trunk_thigh_angle"] == 90.0
    assert angles["thigh_shank_angle"] == 180.0

    low_visibility_row = {
        **row,
        "landmarks": [
            _landmark("left_shoulder", 0.0, 0.0, visibility=0.2),
            _landmark("left_hip", 0.0, 1.0, visibility=0.2),
            _landmark("left_knee", 1.0, 1.0, visibility=0.2),
            _landmark("left_ankle", 2.0, 1.0, visibility=0.2),
        ],
    }
    filtered = extract_frame_angles(low_visibility_row)
    assert filtered["landmark_visibility_ok"] is False
    assert filtered["trunk_thigh_angle"] is None
    assert filtered["thigh_shank_angle"] is None


def test_build_jump_feature_rows_marks_flight_phase_and_mid_flight_window() -> None:
    jump = JumpSegment(
        jump_id="jump-001",
        sequence_index=0,
        start_ms=900,
        takeoff_ms=1000,
        apex_ms=1200,
        landing_ms=1400,
        end_ms=1500,
    )
    base_landmarks = [
        _landmark("left_shoulder", 0.0, 0.0),
        _landmark("left_hip", 0.0, 1.0),
        _landmark("left_knee", 1.0, 1.0),
        _landmark("left_ankle", 2.0, 1.0),
    ]
    rows = build_jump_feature_rows(
        analysis_id="sample01",
        landmark_rows=[
            {"frame_index": 0, "timestamp_ms": 950, "landmarks": base_landmarks},
            {"frame_index": 1, "timestamp_ms": 1200, "landmarks": base_landmarks},
            {"frame_index": 2, "timestamp_ms": 1450, "landmarks": base_landmarks},
        ],
        jump_segments=[jump],
    )

    assert len(rows) == 3
    assert rows[0]["flight_phase"] is None
    assert rows[0]["is_mid_flight_window"] is False
    assert rows[1]["flight_phase"] == 0.5
    assert rows[1]["is_mid_flight_window"] is True
    assert rows[2]["flight_phase"] is None
