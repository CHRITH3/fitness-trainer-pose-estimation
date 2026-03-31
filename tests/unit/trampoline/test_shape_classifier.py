from __future__ import annotations

from trampoline.rules_tra import classify_frame_shape, classify_jump_shape
from trampoline.schema import JumpSegment


def test_classify_frame_shape_thresholds() -> None:
    assert classify_frame_shape(80.0, 120.0)[0] == "tuck"
    assert classify_frame_shape(100.0, 155.0)[0] == "pike"
    assert classify_frame_shape(165.0, 170.0)[0] == "straight"


def test_classify_jump_shape_uses_mid_flight_window_and_lowest_difficulty_rule() -> None:
    jump = JumpSegment(
        jump_id="jump-001",
        sequence_index=0,
        start_ms=0,
        takeoff_ms=100,
        apex_ms=200,
        landing_ms=300,
        end_ms=400,
    )
    feature_rows = [
        {
            "jump_id": "jump-001",
            "timestamp_ms": 90,
            "is_flight_phase": False,
            "is_mid_flight_window": False,
            "trunk_thigh_angle": 165.0,
            "thigh_shank_angle": 170.0,
            "visibility_score": 0.98,
        },
        {
            "jump_id": "jump-001",
            "timestamp_ms": 150,
            "is_flight_phase": True,
            "is_mid_flight_window": True,
            "trunk_thigh_angle": 102.0,
            "thigh_shank_angle": 158.0,
            "visibility_score": 0.98,
        },
        {
            "jump_id": "jump-001",
            "timestamp_ms": 210,
            "is_flight_phase": True,
            "is_mid_flight_window": True,
            "trunk_thigh_angle": 82.0,
            "thigh_shank_angle": 130.0,
            "visibility_score": 0.98,
        },
    ]

    result = classify_jump_shape(jump, feature_rows)

    assert result.auto_label == "tuck"
    assert result.resolved_label == "tuck"
    assert "lowest-difficulty rule" in result.decision_reason
    assert "tuck=1" in result.decision_reason
    assert result.fallback_reason is None


def test_classify_jump_shape_falls_back_when_mid_flight_rows_are_missing() -> None:
    jump = JumpSegment(
        jump_id="jump-002",
        sequence_index=1,
        start_ms=0,
        takeoff_ms=100,
        apex_ms=200,
        landing_ms=300,
        end_ms=400,
    )
    feature_rows = [
        {
            "jump_id": "jump-002",
            "timestamp_ms": 140,
            "is_flight_phase": True,
            "is_mid_flight_window": True,
            "trunk_thigh_angle": None,
            "thigh_shank_angle": None,
            "visibility_score": 0.2,
        },
        {
            "jump_id": "jump-002",
            "timestamp_ms": 180,
            "is_flight_phase": True,
            "is_mid_flight_window": False,
            "trunk_thigh_angle": 108.0,
            "thigh_shank_angle": 156.0,
            "visibility_score": 0.75,
        },
    ]

    result = classify_jump_shape(jump, feature_rows)

    assert result.auto_label == "pike"
    assert result.fallback_reason is not None
    assert "full flight window" in result.fallback_reason
    assert result.confidence <= 0.58
