from __future__ import annotations

from trampoline.bed_calibration import create_bed_calibration
from trampoline.bounce_segmenter import (
    detect_apex_candidates,
    detect_contact_candidates,
    extract_contact_signal,
)


def _row(frame_index: int, timestamp_ms: int, hip_y: float, ankle_y: float, foot_y: float, *, missing: bool = False) -> dict:
    visibility = 0.0 if missing else 0.99
    return {
        "frame_index": frame_index,
        "timestamp_ms": timestamp_ms,
        "has_landmarks": True,
        "landmarks": [
            {"name": "left_hip", "x": 0.45, "y": hip_y, "visibility": visibility},
            {"name": "right_hip", "x": 0.55, "y": hip_y + 0.002, "visibility": visibility},
            {"name": "left_ankle", "x": 0.46, "y": ankle_y, "visibility": visibility},
            {"name": "right_ankle", "x": 0.54, "y": ankle_y + 0.003, "visibility": visibility},
            {"name": "left_foot_index", "x": 0.46, "y": foot_y, "visibility": visibility},
            {"name": "right_foot_index", "x": 0.54, "y": foot_y + 0.002, "visibility": visibility},
        ],
    }


def test_contact_signal_extracts_candidates_with_noise_and_missing_frames() -> None:
    rows = [
        _row(0, 0, 0.52, 0.86, 0.90),
        _row(1, 42, 0.525, 0.87, 0.905),
        _row(2, 83, 0.53, 0.875, 0.91),
        _row(3, 125, 0.535, 0.88, 0.915),
        _row(4, 167, 0.51, 0.84, 0.885),
        _row(5, 208, 0.485, 0.80, 0.86),
        _row(6, 250, 0.475, 0.79, 0.85, missing=True),
        _row(7, 292, 0.49, 0.81, 0.865),
        _row(8, 333, 0.515, 0.85, 0.89),
        _row(9, 375, 0.53, 0.875, 0.91),
        _row(10, 417, 0.535, 0.88, 0.915),
        _row(11, 458, 0.54, 0.885, 0.92),
        _row(12, 500, 0.515, 0.845, 0.89),
        _row(13, 542, 0.49, 0.805, 0.865),
        _row(14, 583, 0.48, 0.795, 0.855),
        _row(15, 625, 0.5, 0.83, 0.88),
        _row(16, 667, 0.52, 0.86, 0.9),
    ]
    calibration = create_bed_calibration(
        corners={
            "top_left": {"x": 20, "y": 20},
            "top_right": {"x": 340, "y": 20},
            "bottom_right": {"x": 340, "y": 620},
            "bottom_left": {"x": 20, "y": 620},
        },
        frame_width=360,
        frame_height=640,
    )

    points = extract_contact_signal(rows, calibration)
    contacts = detect_contact_candidates(points)
    apexes = detect_apex_candidates(points)

    assert len(points) == len(rows)
    assert points[6].coverage == 0.0
    assert points[6].contact_signal > 0.0
    assert points[0].foot_bed_y is not None
    assert [candidate.frame_index for candidate in contacts] == [1, 10]
    assert [candidate.frame_index for candidate in apexes] == [15]
