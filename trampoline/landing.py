"""Phase 4 landing extraction and demo summary helpers."""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any

from trampoline.bed_calibration import BedCalibration, CalibrationPoint, transform_point
from trampoline.schema import JumpSegment, LandingArtifact, LandingRecord, RoutineSummary


LANDING_VISIBILITY_THRESHOLD = 0.55
LANDING_BOUNDS_MARGIN = 0.25
CENTER_ZONE_THRESHOLD = 0.12
INNER_ZONE_THRESHOLD = 0.28
EDGE_ZONE_THRESHOLD = 0.5


def _landmark_map(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in row.get("landmarks", [])}


def _visible_landmarks(
    landmarks: dict[str, dict[str, Any]],
    names: list[str],
    *,
    visibility_threshold: float,
) -> list[dict[str, Any]]:
    visible: list[dict[str, Any]] = []
    for name in names:
        landmark = landmarks.get(name)
        if not landmark:
            continue
        if float(landmark.get("visibility") or 0.0) < visibility_threshold:
            continue
        visible.append(landmark)
    return visible


def _to_pixel_point(
    landmarks: list[dict[str, Any]],
    *,
    frame_width: int,
    frame_height: int,
    use_lowest_y: bool,
) -> CalibrationPoint | None:
    if not landmarks:
        return None

    x_value = sum(float(item["x"]) for item in landmarks) / len(landmarks)
    if use_lowest_y:
        y_value = max(float(item["y"]) for item in landmarks)
    else:
        y_value = sum(float(item["y"]) for item in landmarks) / len(landmarks)
    return CalibrationPoint(x=x_value * frame_width, y=y_value * frame_height)


def _support_sides(landmarks: list[dict[str, Any]]) -> list[str]:
    sides = {
        landmark["name"].split("_", 1)[0]
        for landmark in landmarks
        if isinstance(landmark.get("name"), str) and "_" in landmark["name"]
    }
    return sorted(side for side in sides if side in {"left", "right"})


def _reasonable_normalized_point(point: CalibrationPoint) -> bool:
    return (
        math.isfinite(point.x)
        and math.isfinite(point.y)
        and -LANDING_BOUNDS_MARGIN <= point.x <= 1.0 + LANDING_BOUNDS_MARGIN
        and -LANDING_BOUNDS_MARGIN <= point.y <= 1.0 + LANDING_BOUNDS_MARGIN
    )


def zone_for_landing(x_norm: float | None, y_norm: float | None) -> tuple[str, float | None]:
    """Return the demo landing zone and center deviation."""

    if x_norm is None or y_norm is None:
        return "unknown", None

    deviation = round(math.hypot(x_norm - 0.5, y_norm - 0.5), 3)
    if x_norm < 0.0 or x_norm > 1.0 or y_norm < 0.0 or y_norm > 1.0:
        return "out", deviation
    if deviation <= CENTER_ZONE_THRESHOLD:
        return "center", deviation
    if deviation <= INNER_ZONE_THRESHOLD:
        return "inner", deviation
    if deviation <= EDGE_ZONE_THRESHOLD:
        return "edge", deviation
    return "out", deviation


def _nearest_row(landmark_rows: list[dict[str, Any]], timestamp_ms: int) -> dict[str, Any] | None:
    if not landmark_rows:
        return None
    return min(
        landmark_rows,
        key=lambda row: abs(int(row.get("timestamp_ms") or 0) - timestamp_ms),
    )


def extract_landing_record(
    *,
    jump_segment: JumpSegment,
    landing_row: dict[str, Any] | None,
    calibration: BedCalibration,
    frame_width: int,
    frame_height: int,
    visibility_threshold: float = LANDING_VISIBILITY_THRESHOLD,
) -> LandingRecord:
    """Extract one normalized landing point using feet first, hips second."""

    if landing_row is None:
        return LandingRecord(
            jump_id=jump_segment.jump_id,
            sequence_index=jump_segment.sequence_index,
            landing_ms=jump_segment.landing_ms,
            landing_source="missing",
            zone="unknown",
        )

    landmarks = _landmark_map(landing_row)
    foot_landmarks = _visible_landmarks(
        landmarks,
        [
            "left_foot_index",
            "left_heel",
            "left_ankle",
            "right_foot_index",
            "right_heel",
            "right_ankle",
        ],
        visibility_threshold=visibility_threshold,
    )
    hip_landmarks = _visible_landmarks(
        landmarks,
        ["left_hip", "right_hip"],
        visibility_threshold=visibility_threshold,
    )

    landing_source = "missing"
    source_landmarks: list[dict[str, Any]] = []
    pixel_point = None
    if foot_landmarks:
        landing_source = "feet"
        source_landmarks = foot_landmarks
        pixel_point = _to_pixel_point(
            foot_landmarks,
            frame_width=frame_width,
            frame_height=frame_height,
            use_lowest_y=True,
        )
    elif hip_landmarks:
        landing_source = "hip_fallback"
        source_landmarks = hip_landmarks
        pixel_point = _to_pixel_point(
            hip_landmarks,
            frame_width=frame_width,
            frame_height=frame_height,
            use_lowest_y=False,
        )

    if pixel_point is None:
        return LandingRecord(
            jump_id=jump_segment.jump_id,
            sequence_index=jump_segment.sequence_index,
            landing_ms=jump_segment.landing_ms,
            landing_frame_index=int(landing_row.get("frame_index") or 0),
            landing_source="missing",
            zone="unknown",
        )

    normalized_point = transform_point(pixel_point, calibration.bed_to_normalized)
    if not _reasonable_normalized_point(normalized_point):
        return LandingRecord(
            jump_id=jump_segment.jump_id,
            sequence_index=jump_segment.sequence_index,
            landing_ms=jump_segment.landing_ms,
            landing_frame_index=int(landing_row.get("frame_index") or 0),
            landing_source=f"{landing_source}_invalid",
            support_sides=_support_sides(source_landmarks),
            source_landmarks=sorted(landmark["name"] for landmark in source_landmarks),
            zone="unknown",
        )

    zone, deviation = zone_for_landing(normalized_point.x, normalized_point.y)
    jump_flags: list[str] = []
    support_sides = _support_sides(source_landmarks)
    if landing_source == "feet" and len(support_sides) == 1:
        jump_flags.append("single_leg")
    if zone == "out":
        jump_flags.append("out_of_bed")

    return LandingRecord(
        jump_id=jump_segment.jump_id,
        sequence_index=jump_segment.sequence_index,
        landing_ms=jump_segment.landing_ms,
        landing_frame_index=int(landing_row.get("frame_index") or 0),
        landing_source=landing_source,
        landing_x_norm=round(normalized_point.x, 4),
        landing_y_norm=round(normalized_point.y, 4),
        center_deviation=deviation,
        zone=zone,
        jump_flags=jump_flags,
        support_sides=support_sides,
        source_landmarks=sorted(landmark["name"] for landmark in source_landmarks),
        valid=True,
    )


def build_landing_artifact(
    *,
    analysis_id: str,
    jump_segments: list[JumpSegment],
    landmark_rows: list[dict[str, Any]],
    calibration: BedCalibration | None,
    frames_meta: dict[str, Any],
) -> LandingArtifact:
    """Build the landing artifact from the current merged timeline."""

    if calibration is None:
        return LandingArtifact(
            analysis_id=analysis_id,
            jumps=[],
            routine_summary=RoutineSummary(
                jump_count=len(jump_segments),
                landed_jump_count=0,
                zone_summary={zone: 0 for zone in ("center", "inner", "edge", "out", "unknown")},
                jump_flag_counts={},
                notes=["Landing summary unavailable because calibration.json is missing."],
            ),
        )

    frame_width = int(frames_meta.get("width") or calibration.frame_size.get("width") or 0)
    frame_height = int(frames_meta.get("height") or calibration.frame_size.get("height") or 0)
    records = [
        extract_landing_record(
            jump_segment=jump_segment,
            landing_row=_nearest_row(landmark_rows, jump_segment.landing_ms),
            calibration=calibration,
            frame_width=frame_width,
            frame_height=frame_height,
        )
        for jump_segment in jump_segments
    ]
    return LandingArtifact(
        analysis_id=analysis_id,
        jumps=records,
        routine_summary=summarize_landings(records, frames_meta=frames_meta),
        generated_at=datetime.now(timezone.utc),
    )


def summarize_landings(
    landing_records: list[LandingRecord],
    *,
    frames_meta: dict[str, Any] | None = None,
) -> RoutineSummary:
    """Build the demo routine summary and routine-level flags."""

    zone_summary = {zone: 0 for zone in ("center", "inner", "edge", "out", "unknown")}
    jump_flag_counts: dict[str, int] = {}
    valid_records = [record for record in landing_records if record.valid and record.center_deviation is not None]

    for record in landing_records:
        zone_summary[record.zone] = zone_summary.get(record.zone, 0) + 1
        for flag in record.jump_flags:
            jump_flag_counts[flag] = jump_flag_counts.get(flag, 0) + 1

    routine_flags: list[str] = []
    if landing_records:
        last_record = landing_records[-1]
        if "out_of_bed" in last_record.jump_flags:
            routine_flags.append("final_out_bounce")
        if frames_meta and (int(frames_meta.get("duration_ms") or 0) - int(last_record.landing_ms)) >= 3000:
            routine_flags.append("final_stable_3s")

    return RoutineSummary(
        jump_count=len(landing_records),
        landed_jump_count=len(valid_records),
        mean_center_deviation=round(sum(record.center_deviation for record in valid_records) / len(valid_records), 3)
        if valid_records
        else None,
        max_center_deviation=max((record.center_deviation for record in valid_records), default=None),
        zone_summary=zone_summary,
        jump_flag_counts=jump_flag_counts,
        routine_flags=routine_flags,
        notes=[
            "Demo-only landing assistance. No official H-score or judging output is produced.",
        ],
    )


def build_summary_markdown(
    *,
    analysis_id: str,
    source_video: str,
    landing_artifact: LandingArtifact,
) -> str:
    """Render the lightweight human-readable Phase 4 summary."""

    summary = landing_artifact.routine_summary
    lines = [
        f"# TRA Demo Summary: {analysis_id}",
        "",
        f"- Source video: `{source_video}`",
        f"- Jumps detected: {summary.jump_count}",
        f"- Landings mapped: {summary.landed_jump_count}",
        f"- Mean center deviation: {summary.mean_center_deviation if summary.mean_center_deviation is not None else 'n/a'}",
        f"- Max center deviation: {summary.max_center_deviation if summary.max_center_deviation is not None else 'n/a'}",
        f"- Zone summary: {', '.join(f'{name}={count}' for name, count in summary.zone_summary.items())}",
        f"- Routine flags: {', '.join(summary.routine_flags) if summary.routine_flags else 'none'}",
        "",
        "## Jump Summary",
        "",
    ]
    for record in landing_artifact.jumps:
        lines.append(
            "- "
            f"{record.jump_id}: source={record.landing_source}, "
            f"landing=({record.landing_x_norm if record.landing_x_norm is not None else 'n/a'}, "
            f"{record.landing_y_norm if record.landing_y_norm is not None else 'n/a'}), "
            f"zone={record.zone}, "
            f"center_deviation={record.center_deviation if record.center_deviation is not None else 'n/a'}, "
            f"flags={','.join(record.jump_flags) if record.jump_flags else 'none'}"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
            "- Single-athlete TRA demo only.",
            "- No D-score, ToF, SYN, TUM, DMT, or official judging output.",
        ]
    )
    return "\n".join(lines) + "\n"
