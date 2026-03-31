from __future__ import annotations

from trampoline.landing import summarize_landings
from trampoline.schema import LandingRecord


def test_zone_summary_and_jump_flag_counts_are_aggregated() -> None:
    summary = summarize_landings(
        [
            LandingRecord(
                jump_id="jump-001",
                sequence_index=0,
                landing_ms=1200,
                landing_source="feet",
                landing_x_norm=0.5,
                landing_y_norm=0.5,
                center_deviation=0.0,
                zone="center",
                valid=True,
            ),
            LandingRecord(
                jump_id="jump-002",
                sequence_index=1,
                landing_ms=2400,
                landing_source="feet",
                landing_x_norm=0.98,
                landing_y_norm=1.04,
                center_deviation=0.722,
                zone="out",
                jump_flags=["single_leg", "out_of_bed"],
                valid=True,
            ),
        ],
        frames_meta={"duration_ms": 2600},
    )

    assert summary.jump_count == 2
    assert summary.landed_jump_count == 2
    assert summary.zone_summary["center"] == 1
    assert summary.zone_summary["out"] == 1
    assert summary.jump_flag_counts["single_leg"] == 1
    assert summary.jump_flag_counts["out_of_bed"] == 1
    assert summary.routine_flags == ["final_out_bounce"]


def test_final_stable_3s_is_reported_when_video_runs_long_after_last_landing() -> None:
    summary = summarize_landings(
        [
            LandingRecord(
                jump_id="jump-001",
                sequence_index=0,
                landing_ms=1500,
                landing_source="feet",
                landing_x_norm=0.52,
                landing_y_norm=0.51,
                center_deviation=0.022,
                zone="center",
                valid=True,
            )
        ],
        frames_meta={"duration_ms": 4700},
    )

    assert summary.routine_flags == ["final_stable_3s"]
    assert summary.mean_center_deviation == 0.022
