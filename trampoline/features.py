"""Per-jump feature extraction for the trampoline analysis flow."""

from __future__ import annotations

import math
from statistics import median
from typing import Any, Iterable

from trampoline.schema import FeatureSummary, JumpSegment


VISIBILITY_THRESHOLD = 0.60
MID_FLIGHT_WINDOW = (0.25, 0.75)


def summarize_landmark_stream(landmark_rows: Iterable[dict]) -> dict:
    """Return a minimal summary used by earlier phases."""

    row_count = sum(1 for _ in landmark_rows)
    return {"row_count": row_count}


def calculate_angle(point_a: tuple[float, float], point_b: tuple[float, float], point_c: tuple[float, float]) -> float | None:
    """Return the inner angle ABC in degrees."""

    vector_ba = (point_a[0] - point_b[0], point_a[1] - point_b[1])
    vector_bc = (point_c[0] - point_b[0], point_c[1] - point_b[1])
    magnitude_ba = math.hypot(*vector_ba)
    magnitude_bc = math.hypot(*vector_bc)
    if magnitude_ba == 0.0 or magnitude_bc == 0.0:
        return None
    cosine = ((vector_ba[0] * vector_bc[0]) + (vector_ba[1] * vector_bc[1])) / (magnitude_ba * magnitude_bc)
    cosine = max(-1.0, min(1.0, cosine))
    return math.degrees(math.acos(cosine))


def _landmark_map(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in row.get("landmarks", [])}


def _landmark_point(landmark: dict[str, Any]) -> tuple[float, float]:
    return (float(landmark["x"]), float(landmark["y"]))


def _side_angles(
    landmarks: dict[str, dict[str, Any]],
    side: str,
    *,
    visibility_threshold: float,
) -> dict[str, float | str | bool | None]:
    shoulder = landmarks.get(f"{side}_shoulder")
    hip = landmarks.get(f"{side}_hip")
    knee = landmarks.get(f"{side}_knee")
    ankle = landmarks.get(f"{side}_ankle")
    required = [shoulder, hip, knee, ankle]
    if not all(required):
        return {
            "side": side,
            "visibility_score": 0.0,
            "landmark_visibility_ok": False,
            "trunk_thigh_angle": None,
            "thigh_shank_angle": None,
        }

    visibility_score = min(float(item.get("visibility") or 0.0) for item in required)
    if visibility_score < visibility_threshold:
        return {
            "side": side,
            "visibility_score": visibility_score,
            "landmark_visibility_ok": False,
            "trunk_thigh_angle": None,
            "thigh_shank_angle": None,
        }

    return {
        "side": side,
        "visibility_score": visibility_score,
        "landmark_visibility_ok": True,
        "trunk_thigh_angle": calculate_angle(_landmark_point(shoulder), _landmark_point(hip), _landmark_point(knee)),
        "thigh_shank_angle": calculate_angle(_landmark_point(hip), _landmark_point(knee), _landmark_point(ankle)),
    }


def extract_frame_angles(
    row: dict[str, Any],
    *,
    visibility_threshold: float = VISIBILITY_THRESHOLD,
) -> dict[str, float | str | bool | None]:
    """Extract the jump-shape angles for one frame using the best visible body side."""

    landmarks = _landmark_map(row)
    candidates = [
        _side_angles(landmarks, "left", visibility_threshold=visibility_threshold),
        _side_angles(landmarks, "right", visibility_threshold=visibility_threshold),
    ]
    candidates.sort(
        key=lambda item: (
            bool(item["landmark_visibility_ok"]),
            float(item["visibility_score"] or 0.0),
        ),
        reverse=True,
    )
    best = candidates[0]
    return {
        "angle_side": best["side"],
        "visibility_score": float(best["visibility_score"] or 0.0),
        "landmark_visibility_ok": bool(best["landmark_visibility_ok"]),
        "trunk_thigh_angle": round(float(best["trunk_thigh_angle"]), 3)
        if best["trunk_thigh_angle"] is not None
        else None,
        "thigh_shank_angle": round(float(best["thigh_shank_angle"]), 3)
        if best["thigh_shank_angle"] is not None
        else None,
    }


def _flight_phase(timestamp_ms: int, jump_segment: JumpSegment) -> float | None:
    flight_duration = jump_segment.landing_ms - jump_segment.takeoff_ms
    if flight_duration <= 0:
        return None
    if timestamp_ms < jump_segment.takeoff_ms or timestamp_ms > jump_segment.landing_ms:
        return None
    return (timestamp_ms - jump_segment.takeoff_ms) / flight_duration


def build_jump_feature_rows(
    *,
    analysis_id: str,
    landmark_rows: list[dict[str, Any]],
    jump_segments: list[JumpSegment],
    visibility_threshold: float = VISIBILITY_THRESHOLD,
) -> list[dict[str, Any]]:
    """Expand frame landmarks into per-jump feature rows."""

    feature_rows: list[dict[str, Any]] = []
    for jump_segment in jump_segments:
        for row in landmark_rows:
            timestamp_ms = int(row["timestamp_ms"])
            if timestamp_ms < jump_segment.start_ms or timestamp_ms > jump_segment.end_ms:
                continue
            flight_phase = _flight_phase(timestamp_ms, jump_segment)
            angles = extract_frame_angles(row, visibility_threshold=visibility_threshold)
            is_mid_flight_window = (
                flight_phase is not None and MID_FLIGHT_WINDOW[0] <= flight_phase <= MID_FLIGHT_WINDOW[1]
            )
            feature_rows.append(
                {
                    "analysis_id": analysis_id,
                    "jump_id": jump_segment.jump_id,
                    "sequence_index": jump_segment.sequence_index,
                    "frame_index": int(row["frame_index"]),
                    "timestamp_ms": timestamp_ms,
                    "flight_phase": round(flight_phase, 4) if flight_phase is not None else None,
                    "is_flight_phase": flight_phase is not None,
                    "is_mid_flight_window": is_mid_flight_window,
                    **angles,
                }
            )
    return feature_rows


def summarize_jump_feature_rows(feature_rows: list[dict[str, Any]]) -> FeatureSummary:
    """Produce a compact jump-level angle summary for UI display and labels."""

    valid_rows = [
        row
        for row in feature_rows
        if row.get("trunk_thigh_angle") is not None and row.get("thigh_shank_angle") is not None
    ]
    valid_mid_rows = [row for row in valid_rows if row.get("is_mid_flight_window")]
    representative_timestamp_ms = None
    if valid_mid_rows:
        representative_timestamp_ms = int(median(row["timestamp_ms"] for row in valid_mid_rows))
    elif valid_rows:
        representative_timestamp_ms = int(median(row["timestamp_ms"] for row in valid_rows))

    return FeatureSummary(
        frame_count=len(feature_rows),
        mid_flight_frame_count=sum(1 for row in feature_rows if row.get("is_mid_flight_window")),
        valid_frame_count=len(valid_rows),
        mid_flight_valid_frame_count=len(valid_mid_rows),
        trunk_thigh_min_angle=round(min(row["trunk_thigh_angle"] for row in valid_rows), 3) if valid_rows else None,
        trunk_thigh_max_angle=round(max(row["trunk_thigh_angle"] for row in valid_rows), 3) if valid_rows else None,
        thigh_shank_min_angle=round(min(row["thigh_shank_angle"] for row in valid_rows), 3) if valid_rows else None,
        thigh_shank_max_angle=round(max(row["thigh_shank_angle"] for row in valid_rows), 3) if valid_rows else None,
        representative_timestamp_ms=representative_timestamp_ms,
    )
