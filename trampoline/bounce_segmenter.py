"""Automatic jump segmentation for the trampoline demo."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from trampoline.bed_calibration import BedCalibration, CalibrationPoint, load_calibration, transform_point
from trampoline.pipeline import (
    LANDMARKS_FILENAME,
    SEGMENTATION_FILENAME,
    iter_landmark_rows,
    load_analysis_model,
    normalize_jump_segments,
    save_analysis_model,
    sync_analysis_segments,
    sync_phase3_artifacts,
    write_json,
)
from trampoline.schema import JumpSegment


HIP_NAMES = ("left_hip", "right_hip")
ANKLE_NAMES = ("left_ankle", "right_ankle")
FOOT_NAMES = ("left_foot_index", "right_foot_index")
MIN_VISIBILITY = 0.35


@dataclass(frozen=True)
class SignalPoint:
    """One preprocessed vertical-motion sample."""

    frame_index: int
    timestamp_ms: int
    hip_y: float
    ankle_y: float
    foot_y: float
    contact_signal: float
    apex_signal: float
    foot_bed_y: float | None
    coverage: float


@dataclass(frozen=True)
class SignalCandidate:
    """One contact or apex candidate detected from the vertical signals."""

    frame_index: int
    timestamp_ms: int
    signal_value: float
    prominence: float
    kind: str


def _safe_average(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    if not present:
        return None
    return float(sum(present) / len(present))


def _landmark_map(row: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["name"]: item for item in row.get("landmarks", [])}


def _extract_y(landmarks: dict[str, dict[str, Any]], names: tuple[str, ...]) -> float | None:
    values: list[float | None] = []
    for name in names:
        landmark = landmarks.get(name)
        if not landmark:
            values.append(None)
            continue
        visibility = float(landmark.get("visibility") or 0.0)
        values.append(float(landmark["y"]) if visibility >= MIN_VISIBILITY else None)
    return _safe_average(values)


def _average_point(landmarks: dict[str, dict[str, Any]], names: tuple[str, ...]) -> CalibrationPoint | None:
    xs: list[float | None] = []
    ys: list[float | None] = []
    for name in names:
        landmark = landmarks.get(name)
        if not landmark:
            xs.append(None)
            ys.append(None)
            continue
        visibility = float(landmark.get("visibility") or 0.0)
        if visibility < MIN_VISIBILITY:
            xs.append(None)
            ys.append(None)
            continue
        xs.append(float(landmark["x"]))
        ys.append(float(landmark["y"]))
    point_x = _safe_average(xs)
    point_y = _safe_average(ys)
    if point_x is None or point_y is None:
        return None
    return CalibrationPoint(x=point_x, y=point_y)


def _interpolate_series(values: list[float | None]) -> list[float]:
    if not values:
        return []
    valid_indices = [index for index, value in enumerate(values) if value is not None]
    if not valid_indices:
        return [0.0 for _ in values]

    filled = [0.0 if value is None else float(value) for value in values]
    first_valid = valid_indices[0]
    last_valid = valid_indices[-1]

    for index in range(0, first_valid):
        filled[index] = filled[first_valid]
    for index in range(last_valid + 1, len(filled)):
        filled[index] = filled[last_valid]

    for start_index, end_index in zip(valid_indices, valid_indices[1:]):
        start_value = filled[start_index]
        end_value = filled[end_index]
        gap = end_index - start_index
        if gap <= 1:
            continue
        for offset in range(1, gap):
            ratio = offset / gap
            filled[start_index + offset] = start_value + (end_value - start_value) * ratio
    return filled


def _smooth_series(values: list[float], window: int = 5) -> list[float]:
    if window <= 1:
        return list(values)
    radius = window // 2
    smoothed: list[float] = []
    for index in range(len(values)):
        lower = max(0, index - radius)
        upper = min(len(values), index + radius + 1)
        chunk = values[lower:upper]
        smoothed.append(float(sum(chunk) / len(chunk)))
    return smoothed


def extract_contact_signal(
    landmark_rows: list[dict[str, Any]],
    calibration: BedCalibration | None = None,
) -> list[SignalPoint]:
    """Extract one smoothed contact/apex signal series from landmark rows."""

    hip_values: list[float | None] = []
    ankle_values: list[float | None] = []
    foot_values: list[float | None] = []
    foot_bed_values: list[float | None] = []
    coverage_values: list[float] = []

    frame_width = 1.0
    frame_height = 1.0
    if calibration:
        frame_width = float(calibration.frame_size["width"] or 1.0)
        frame_height = float(calibration.frame_size["height"] or 1.0)

    for row in landmark_rows:
        landmarks = _landmark_map(row)
        hip_y = _extract_y(landmarks, HIP_NAMES)
        ankle_y = _extract_y(landmarks, ANKLE_NAMES)
        foot_y = _extract_y(landmarks, FOOT_NAMES)
        hip_values.append(hip_y)
        ankle_values.append(ankle_y)
        foot_values.append(foot_y)

        visible_count = 0
        for name in (*HIP_NAMES, *ANKLE_NAMES, *FOOT_NAMES):
            landmark = landmarks.get(name)
            if landmark and float(landmark.get("visibility") or 0.0) >= MIN_VISIBILITY:
                visible_count += 1
        coverage_values.append(visible_count / 6.0)

        foot_point = _average_point(landmarks, FOOT_NAMES)
        if calibration and foot_point:
            bed_point = transform_point(
                CalibrationPoint(x=foot_point.x * frame_width, y=foot_point.y * frame_height),
                calibration.bed_to_normalized,
            )
            foot_bed_values.append(float(bed_point.y))
        else:
            foot_bed_values.append(None)

    hip_series = _smooth_series(_interpolate_series(hip_values))
    ankle_series = _smooth_series(_interpolate_series(ankle_values))
    foot_series = _smooth_series(_interpolate_series(foot_values))
    bed_series = _interpolate_series(foot_bed_values)

    signal_points: list[SignalPoint] = []
    for index, row in enumerate(landmark_rows):
        contact_signal = (0.55 * ankle_series[index]) + (0.30 * foot_series[index]) + (0.15 * hip_series[index])
        apex_signal = (0.80 * hip_series[index]) + (0.20 * ankle_series[index])
        signal_points.append(
            SignalPoint(
                frame_index=int(row["frame_index"]),
                timestamp_ms=int(row["timestamp_ms"]),
                hip_y=hip_series[index],
                ankle_y=ankle_series[index],
                foot_y=foot_series[index],
                contact_signal=contact_signal,
                apex_signal=apex_signal,
                foot_bed_y=bed_series[index] if any(value is not None for value in foot_bed_values) else None,
                coverage=coverage_values[index],
            )
        )
    return signal_points


def _compress_candidates(candidates: list[SignalCandidate], min_gap_frames: int) -> list[SignalCandidate]:
    if not candidates:
        return []
    compressed = [candidates[0]]
    for candidate in candidates[1:]:
        previous = compressed[-1]
        if candidate.frame_index - previous.frame_index < min_gap_frames:
            if candidate.prominence > previous.prominence:
                compressed[-1] = candidate
            continue
        compressed.append(candidate)
    return compressed


def _series_threshold(values: list[float]) -> float:
    if not values:
        return 0.0
    series_range = max(values) - min(values)
    return max(series_range * 0.04, 0.0004)


def detect_contact_candidates(
    signal_points: list[SignalPoint],
    *,
    min_gap_frames: int = 4,
) -> list[SignalCandidate]:
    """Detect local contact candidates from the smoothed contact signal."""

    values = [point.contact_signal for point in signal_points]
    threshold = _series_threshold(values)
    candidates: list[SignalCandidate] = []
    for index in range(1, len(signal_points) - 1):
        current = values[index]
        if current < values[index - 1] or current < values[index + 1]:
            continue
        lower = max(0, index - 6)
        upper = min(len(values), index + 7)
        neighborhood = values[lower:upper]
        prominence = current - min(neighborhood)
        if prominence < threshold or signal_points[index].coverage < 0.34:
            continue
        point = signal_points[index]
        candidates.append(
            SignalCandidate(
                frame_index=point.frame_index,
                timestamp_ms=point.timestamp_ms,
                signal_value=current,
                prominence=prominence,
                kind="contact",
            )
        )
    return _compress_candidates(candidates, min_gap_frames=min_gap_frames)


def detect_apex_candidates(
    signal_points: list[SignalPoint],
    *,
    min_gap_frames: int = 4,
) -> list[SignalCandidate]:
    """Detect local apex candidates from the smoothed apex signal."""

    values = [point.contact_signal for point in signal_points]
    threshold = _series_threshold(values)
    candidates: list[SignalCandidate] = []
    for index in range(1, len(signal_points) - 1):
        current = values[index]
        if current > values[index - 1] or current > values[index + 1]:
            continue
        lower = max(0, index - 6)
        upper = min(len(values), index + 7)
        neighborhood = values[lower:upper]
        prominence = max(neighborhood) - current
        if prominence < threshold or signal_points[index].coverage < 0.34:
            continue
        point = signal_points[index]
        candidates.append(
            SignalCandidate(
                frame_index=point.frame_index,
                timestamp_ms=point.timestamp_ms,
                signal_value=current,
                prominence=prominence,
                kind="apex",
            )
        )
    return _compress_candidates(candidates, min_gap_frames=min_gap_frames)


def _strong_contacts(
    contact_candidates: list[SignalCandidate],
    signal_points: list[SignalPoint],
    *,
    min_gap_frames: int = 8,
) -> list[SignalCandidate]:
    if not contact_candidates:
        return []
    values = [point.contact_signal for point in signal_points]
    amplitude_floor = max((max(values) - min(values)) * 0.08, 0.0012)
    strong = [candidate for candidate in contact_candidates if candidate.prominence >= amplitude_floor]
    if len(strong) < 2:
        strong = contact_candidates
    return _compress_candidates(strong, min_gap_frames=min_gap_frames)


def _first_crossing(
    signal_points: list[SignalPoint],
    *,
    start_frame: int,
    end_frame: int,
    threshold: float,
    direction: str,
) -> SignalPoint:
    frame_map = {point.frame_index: point for point in signal_points}
    frame_range = range(start_frame, end_frame + 1)
    if direction == "below":
        for frame_index in frame_range:
            point = frame_map[frame_index]
            if point.contact_signal <= threshold:
                return point
    else:
        for frame_index in frame_range:
            point = frame_map[frame_index]
            if point.contact_signal >= threshold:
                return point
    return frame_map[end_frame]


def build_jump_segments(
    signal_points: list[SignalPoint],
    contact_candidates: list[SignalCandidate],
    apex_candidates: list[SignalCandidate],
) -> list[JumpSegment]:
    """Assemble jump segments from contact and apex candidates."""

    primary_contacts = _strong_contacts(contact_candidates, signal_points)
    if len(primary_contacts) < 2:
        return []

    frame_map = {point.frame_index: point for point in signal_points}
    segments: list[JumpSegment] = []
    for sequence_index, (left_contact, right_contact) in enumerate(zip(primary_contacts, primary_contacts[1:])):
        frame_gap = right_contact.frame_index - left_contact.frame_index
        if frame_gap < 8:
            continue

        apex_pool = [
            candidate
            for candidate in apex_candidates
            if left_contact.frame_index < candidate.frame_index < right_contact.frame_index
        ]
        if not apex_pool:
            continue

        apex = min(apex_pool, key=lambda candidate: candidate.signal_value)
        start_point = frame_map[left_contact.frame_index]
        apex_point = frame_map[apex.frame_index]
        end_point = frame_map[right_contact.frame_index]
        amplitude = min(left_contact.signal_value, right_contact.signal_value) - apex.signal_value
        if amplitude < 0.001:
            continue

        takeoff_threshold = left_contact.signal_value - (amplitude * 0.45)
        landing_threshold = right_contact.signal_value - (amplitude * 0.35)
        takeoff_point = _first_crossing(
            signal_points,
            start_frame=left_contact.frame_index + 1,
            end_frame=apex.frame_index,
            threshold=takeoff_threshold,
            direction="below",
        )
        landing_point = _first_crossing(
            signal_points,
            start_frame=apex.frame_index,
            end_frame=right_contact.frame_index - 1,
            threshold=landing_threshold,
            direction="above",
        )

        segment = JumpSegment(
            jump_id=f"jump-{len(segments) + 1:03d}",
            sequence_index=sequence_index,
            start_ms=start_point.timestamp_ms,
            takeoff_ms=takeoff_point.timestamp_ms,
            apex_ms=apex_point.timestamp_ms,
            landing_ms=landing_point.timestamp_ms,
            end_ms=end_point.timestamp_ms,
            source="auto",
            confidence=min(0.99, max(0.2, amplitude * 90.0)),
            notes=["auto-segmented from hip/ankle vertical signal"],
            auto_jump_ids=[f"jump-{len(segments) + 1:03d}"],
        )
        segments.append(segment)

    return normalize_jump_segments(segments)


def empty_segmentation() -> list[JumpSegment]:
    """Return the default empty jump segmentation result."""

    return []


def generate_segmentation_payload(analysis_dir: Path) -> dict[str, Any]:
    """Generate one segmentation payload from existing analysis artifacts."""

    landmarks_path = analysis_dir / LANDMARKS_FILENAME
    if not landmarks_path.is_file():
        raise FileNotFoundError(f"Missing landmarks artifact: {landmarks_path}")

    calibration = load_calibration(analysis_dir)
    if calibration is None:
        raise FileNotFoundError(f"Missing calibration artifact: {analysis_dir / 'calibration.json'}")

    rows = iter_landmark_rows(landmarks_path)
    signal_points = extract_contact_signal(rows, calibration=calibration)
    contact_candidates = detect_contact_candidates(signal_points)
    apex_candidates = detect_apex_candidates(signal_points)
    jump_segments = build_jump_segments(signal_points, contact_candidates, apex_candidates)

    return {
        "analysis_id": analysis_dir.name,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "contact_candidates": [
            {
                "frame_index": candidate.frame_index,
                "timestamp_ms": candidate.timestamp_ms,
                "signal_value": candidate.signal_value,
                "prominence": candidate.prominence,
            }
            for candidate in contact_candidates
        ],
        "apex_candidates": [
            {
                "frame_index": candidate.frame_index,
                "timestamp_ms": candidate.timestamp_ms,
                "signal_value": candidate.signal_value,
                "prominence": candidate.prominence,
            }
            for candidate in apex_candidates
        ],
        "jump_segments": [segment.model_dump(mode="json") for segment in jump_segments],
        "calibration_used": {
            "center_point": calibration.center_point.model_dump(mode="json"),
            "frame_size": calibration.frame_size,
        },
    }


def segment_analysis_dir(analysis_dir: Path) -> dict[str, Any]:
    """Generate and persist the automatic segmentation artifact for one analysis directory."""

    segmentation = generate_segmentation_payload(analysis_dir)
    write_json(analysis_dir / SEGMENTATION_FILENAME, segmentation)

    analysis = load_analysis_model(analysis_dir)
    save_analysis_model(
        analysis_dir,
        analysis.model_copy(
            update={
                "artifacts": analysis.artifacts,
            }
        ),
    )
    sync_analysis_segments(
        analysis_dir,
        jump_segments=[JumpSegment.model_validate(item) for item in segmentation["jump_segments"]],
        manual_overrides=[],
    )
    sync_phase3_artifacts(analysis_dir)
    return segmentation
