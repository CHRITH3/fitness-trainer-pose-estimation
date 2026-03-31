from __future__ import annotations

import pytest
from pydantic import ValidationError

from trampoline.schema import JumpSegment, ManualOverride, RoutineAnalysis


def test_routine_analysis_defaults() -> None:
    analysis = RoutineAnalysis(
        analysis_id="analysis-001",
        source_video="samples/tra_demo/sample01.mp4",
    )

    assert analysis.discipline == "TRA"
    assert analysis.athlete_count == 1
    assert analysis.status == "pending"
    assert analysis.jump_segments == []
    assert analysis.manual_overrides == []
    assert analysis.artifacts == []


def test_jump_segment_requires_monotonic_times() -> None:
    with pytest.raises(ValidationError):
        JumpSegment(
            jump_id="jump-001",
            sequence_index=0,
            start_ms=100,
            takeoff_ms=90,
            apex_ms=150,
            landing_ms=200,
            end_ms=250,
        )


def test_jump_segment_rejects_blank_notes() -> None:
    with pytest.raises(ValidationError):
        JumpSegment(
            jump_id="jump-001",
            sequence_index=0,
            start_ms=0,
            takeoff_ms=100,
            apex_ms=200,
            landing_ms=300,
            end_ms=400,
            notes=[""],
        )


def test_manual_override_validation_and_defaults() -> None:
    override = ManualOverride(
        jump_id="jump-001",
        field_name="landing_ms",
        value_ms=2450,
        reason="manual trim",
    )

    assert override.author == "operator"
    assert override.applied is True

    with pytest.raises(ValidationError):
        ManualOverride(jump_id="", field_name="start_ms", value_ms=-1)
