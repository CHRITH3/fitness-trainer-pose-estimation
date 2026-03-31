from __future__ import annotations

import json
from pathlib import Path

from trampoline.pipeline import (
    SEGMENTATION_FILENAME,
    derive_manual_overrides,
    merge_segment_overrides,
    persist_timeline_overrides,
    write_json,
)
from trampoline.schema import JumpSegment, OverridesArtifact, RoutineAnalysis


def _auto_segments() -> list[JumpSegment]:
    return [
        JumpSegment(
            jump_id="jump-001",
            sequence_index=0,
            start_ms=750,
            takeoff_ms=1042,
            apex_ms=1333,
            landing_ms=1542,
            end_ms=1583,
            source="auto",
        ),
        JumpSegment(
            jump_id="jump-002",
            sequence_index=1,
            start_ms=1583,
            takeoff_ms=1708,
            apex_ms=1792,
            landing_ms=2167,
            end_ms=2375,
            source="auto",
        ),
    ]


def test_merge_segment_overrides_prefers_snapshot_segments() -> None:
    auto_segments = _auto_segments()
    edited = [
        auto_segments[0].model_copy(
            update={
                "landing_ms": 1550,
                "source": "merged",
                "manual_boundary_fields": ["landing_ms"],
            }
        ),
        auto_segments[1],
    ]
    overrides = OverridesArtifact(
        analysis_id="sample01",
        jump_segments=edited,
        manual_overrides=derive_manual_overrides(auto_segments, edited),
    )

    merged_segments, manual_overrides = merge_segment_overrides(auto_segments, overrides)

    assert merged_segments[0].landing_ms == 1550
    assert merged_segments[0].source == "merged"
    assert merged_segments[0].manual_boundary_fields == ["landing_ms"]
    assert manual_overrides


def test_persist_timeline_overrides_is_idempotent(tmp_path: Path) -> None:
    analysis_dir = tmp_path / "sample01"
    analysis_dir.mkdir(parents=True)
    auto_segments = _auto_segments()

    write_json(
        analysis_dir / SEGMENTATION_FILENAME,
        {
            "analysis_id": "sample01",
            "generated_at": "2026-03-26T00:00:00+00:00",
            "contact_candidates": [],
            "apex_candidates": [],
            "jump_segments": [segment.model_dump(mode="json") for segment in auto_segments],
        },
    )
    write_json(
        analysis_dir / "analysis.json",
        RoutineAnalysis(
            analysis_id="sample01",
            source_video="samples/tra_demo/sample01.mp4",
        ).model_dump(mode="json"),
    )

    edited = [
        JumpSegment(
            jump_id="jump-001a",
            sequence_index=0,
            start_ms=750,
            takeoff_ms=920,
            apex_ms=1080,
            landing_ms=1170,
            end_ms=1200,
            source="merged",
            auto_jump_ids=["jump-001"],
            manual_boundary_fields=["start_ms", "takeoff_ms", "apex_ms", "landing_ms", "end_ms"],
        ),
        JumpSegment(
            jump_id="jump-001b",
            sequence_index=1,
            start_ms=1200,
            takeoff_ms=1320,
            apex_ms=1440,
            landing_ms=1540,
            end_ms=1583,
            source="merged",
            auto_jump_ids=["jump-001"],
            manual_boundary_fields=["start_ms", "takeoff_ms", "apex_ms", "landing_ms", "end_ms"],
        ),
        auto_segments[1].model_copy(update={"sequence_index": 2}),
    ]

    first = persist_timeline_overrides(analysis_dir, edited)
    second = persist_timeline_overrides(analysis_dir, edited)

    assert [segment.model_dump(mode="json") for segment in first.jump_segments] == [
        segment.model_dump(mode="json") for segment in second.jump_segments
    ]
    assert [override.model_dump(mode="json") for override in first.manual_overrides] == [
        override.model_dump(mode="json") for override in second.manual_overrides
    ]

    overrides_payload = json.loads((analysis_dir / "overrides.json").read_text(encoding="utf-8"))
    assert len(overrides_payload["jump_segments"]) == 3
    assert any(item["operation"] == "split_jump" for item in overrides_payload["manual_overrides"])
    assert any(item["operation"] == "replace_segments" for item in overrides_payload["manual_overrides"])

