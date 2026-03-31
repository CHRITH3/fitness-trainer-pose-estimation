"""Offline landmark extraction pipeline for the trampoline demo."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import mediapipe as mp

from trampoline.bed_calibration import load_calibration
from trampoline.features import build_jump_feature_rows
from trampoline.landing import build_landing_artifact, build_summary_markdown
from trampoline.rules_tra import classify_labels_artifact
from trampoline.schema import (
    AnalysisArtifactRef,
    JumpSegment,
    LandingArtifact,
    LabelsArtifact,
    ManualOverride,
    OverridesArtifact,
    RoutineAnalysis,
)


PROJECT_ROOT = Path(__file__).resolve().parent.parent
LANDMARKS_FILENAME = "landmarks.jsonl"
FRAMES_META_FILENAME = "frames_meta.json"
ANALYSIS_FILENAME = "analysis.json"
SEGMENTATION_FILENAME = "segmentation.json"
OVERRIDES_FILENAME = "overrides.json"
FEATURES_FILENAME = "features.jsonl"
LABELS_FILENAME = "labels.json"
LANDING_FILENAME = "landing.json"
SUMMARY_FILENAME = "summary.md"
LANDMARK_NAMES = [landmark.name.lower() for landmark in mp.solutions.pose.PoseLandmark]
POSE_CONNECTIONS = sorted(
    (int(start), int(end)) for start, end in mp.solutions.pose.POSE_CONNECTIONS
)


def initialize_analysis(analysis_id: str, source_video: str) -> RoutineAnalysis:
    """Create the baseline analysis object used by the Phase 1 pipeline."""

    return RoutineAnalysis(analysis_id=analysis_id, source_video=source_video)


def resolve_analysis_dir(output_root: Path, analysis_id: str) -> Path:
    """Return the canonical output directory path for an analysis run."""

    return output_root / analysis_id


def repo_relative_path(path: Path) -> str:
    """Prefer repository-relative artifact paths so reports stay portable."""

    resolved = path.resolve()
    try:
        return str(resolved.relative_to(PROJECT_ROOT))
    except ValueError:
        return str(resolved)


def resolve_repo_path(path_str: str) -> Path:
    """Resolve either repo-relative or absolute paths back to a filesystem path."""

    path = Path(path_str)
    return path if path.is_absolute() else PROJECT_ROOT / path


def timestamp_ms_for_frame(frame_index: int, fps: float) -> int:
    """Map one frame index to a millisecond timestamp."""

    safe_fps = fps if fps > 0 else 30.0
    return int(round((frame_index * 1000.0) / safe_fps))


def build_frames_meta(
    *,
    source_video: str,
    fps: float,
    frame_count: int,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Build the JSON payload that maps each frame index to its timestamp."""

    frames = [
        {
            "frame_index": frame_index,
            "timestamp_ms": timestamp_ms_for_frame(frame_index, fps),
        }
        for frame_index in range(frame_count)
    ]
    duration_ms = frames[-1]["timestamp_ms"] if frames else 0
    return {
        "source_video": source_video,
        "fps": fps,
        "frame_count": frame_count,
        "width": width,
        "height": height,
        "duration_ms": duration_ms,
        "frames": frames,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }


def serialize_landmarks(landmarks: Any) -> list[dict[str, float | int | str | None]]:
    """Convert MediaPipe landmarks into a stable JSON-serializable format."""

    if not landmarks:
        return []

    rows: list[dict[str, float | int | str | None]] = []
    for index, landmark in enumerate(landmarks):
        rows.append(
            {
                "index": index,
                "name": LANDMARK_NAMES[index],
                "x": float(landmark.x),
                "y": float(landmark.y),
                "z": float(landmark.z),
                "visibility": float(getattr(landmark, "visibility", 0.0)),
                "presence": float(getattr(landmark, "presence", 0.0))
                if hasattr(landmark, "presence")
                else None,
            }
        )
    return rows


def write_json(path: Path, payload: Any) -> None:
    """Write one JSON payload using stable formatting."""

    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    """Write one JSONL artifact using a stable record order."""

    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row) + "\n")


def read_json(path: Path) -> Any:
    """Read one JSON file from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


def upsert_artifact(
    artifacts: list[AnalysisArtifactRef],
    *,
    name: str,
    path: Path,
    media_type: str,
    description: str,
) -> list[AnalysisArtifactRef]:
    """Insert or replace one artifact entry while preserving order for others."""

    artifact = AnalysisArtifactRef(
        name=name,
        path=repo_relative_path(path),
        media_type=media_type,
        description=description,
    )
    updated = [item for item in artifacts if item.name != name]
    updated.append(artifact)
    return updated


def load_analysis_model(analysis_dir: Path) -> RoutineAnalysis:
    """Load the persisted analysis contract from disk."""

    analysis_path = analysis_dir / ANALYSIS_FILENAME
    if analysis_path.is_file():
        return RoutineAnalysis.model_validate_json(analysis_path.read_text(encoding="utf-8"))

    frames_meta = read_json(analysis_dir / FRAMES_META_FILENAME)
    return initialize_analysis(
        analysis_id=analysis_dir.name,
        source_video=frames_meta["source_video"],
    )


def save_analysis_model(analysis_dir: Path, analysis: RoutineAnalysis) -> Path:
    """Persist the canonical analysis contract to disk."""

    analysis_dir.mkdir(parents=True, exist_ok=True)
    analysis_path = analysis_dir / ANALYSIS_FILENAME
    write_json(analysis_path, analysis.model_dump(mode="json"))
    return analysis_path


def load_segmentation_payload(analysis_dir: Path) -> dict[str, Any] | None:
    """Load the automatic segmentation artifact when present."""

    path = analysis_dir / SEGMENTATION_FILENAME
    if not path.is_file():
        return None
    return read_json(path)


def load_overrides_artifact(analysis_dir: Path) -> OverridesArtifact | None:
    """Load the persisted timeline overrides when present."""

    path = analysis_dir / OVERRIDES_FILENAME
    if not path.is_file():
        return None
    return OverridesArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def load_labels_artifact(analysis_dir: Path) -> LabelsArtifact | None:
    """Load the persisted Phase 3 labels artifact when present."""

    path = analysis_dir / LABELS_FILENAME
    if not path.is_file():
        return None
    return LabelsArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def save_overrides_artifact(analysis_dir: Path, overrides: OverridesArtifact) -> Path:
    """Persist one overrides artifact."""

    analysis_dir.mkdir(parents=True, exist_ok=True)
    path = analysis_dir / OVERRIDES_FILENAME
    write_json(path, overrides.model_dump(mode="json"))
    return path


def save_labels_artifact(analysis_dir: Path, labels: LabelsArtifact) -> Path:
    """Persist one Phase 3 labels artifact."""

    analysis_dir.mkdir(parents=True, exist_ok=True)
    path = analysis_dir / LABELS_FILENAME
    write_json(path, labels.model_dump(mode="json"))
    return path


def load_landing_artifact(analysis_dir: Path) -> LandingArtifact | None:
    """Load the persisted Phase 4 landing artifact when present."""

    path = analysis_dir / LANDING_FILENAME
    if not path.is_file():
        return None
    return LandingArtifact.model_validate_json(path.read_text(encoding="utf-8"))


def save_landing_artifact(analysis_dir: Path, landing: LandingArtifact) -> Path:
    """Persist one Phase 4 landing artifact."""

    analysis_dir.mkdir(parents=True, exist_ok=True)
    path = analysis_dir / LANDING_FILENAME
    write_json(path, landing.model_dump(mode="json"))
    return path


def save_summary_markdown(analysis_dir: Path, content: str) -> Path:
    """Persist the human-readable Phase 4 summary."""

    analysis_dir.mkdir(parents=True, exist_ok=True)
    path = analysis_dir / SUMMARY_FILENAME
    path.write_text(content, encoding="utf-8")
    return path


def normalize_jump_segments(jump_segments: list[JumpSegment]) -> list[JumpSegment]:
    """Sort and re-index jump segments while preserving their ids."""

    normalized: list[JumpSegment] = []
    for index, segment in enumerate(sorted(jump_segments, key=lambda item: (item.start_ms, item.end_ms, item.jump_id))):
        normalized.append(segment.model_copy(update={"sequence_index": index}))
    return normalized


def derive_manual_overrides(
    auto_segments: list[JumpSegment],
    merged_segments: list[JumpSegment],
) -> list[ManualOverride]:
    """Summarize persisted jump edits into stable override metadata."""

    overrides: list[ManualOverride] = []
    auto_by_id = {segment.jump_id: segment for segment in auto_segments}

    if len(merged_segments) != len(auto_segments):
        overrides.append(
            ManualOverride(
                operation="replace_segments",
                jump_ids=[segment.jump_id for segment in merged_segments],
                reason="timeline topology changed via split/merge",
            )
        )

    for segment in merged_segments:
        lineage = segment.auto_jump_ids or [segment.jump_id]
        if len(lineage) > 1:
            overrides.append(
                ManualOverride(
                    operation="merge_jumps",
                    jump_ids=lineage,
                    result_jump_id=segment.jump_id,
                    reason="merged adjacent jump segments",
                )
            )
        elif lineage[0] in auto_by_id:
            auto_segment = auto_by_id[lineage[0]]
            for field_name in ("start_ms", "takeoff_ms", "apex_ms", "landing_ms", "end_ms"):
                merged_value = getattr(segment, field_name)
                if merged_value != getattr(auto_segment, field_name):
                    overrides.append(
                        ManualOverride(
                            operation="update_boundary",
                            jump_id=segment.jump_id,
                            field_name=field_name,
                            value_ms=merged_value,
                            reason="manual boundary adjustment",
                        )
                    )

    lineage_counts: dict[str, int] = {}
    for segment in merged_segments:
        for lineage_id in segment.auto_jump_ids:
            lineage_counts[lineage_id] = lineage_counts.get(lineage_id, 0) + 1
    for lineage_id, count in lineage_counts.items():
        if count > 1:
            lineage_segments = [
                segment for segment in merged_segments if lineage_id in segment.auto_jump_ids
            ]
            lineage_segments.sort(key=lambda item: (item.start_ms, item.end_ms))
            overrides.append(
                ManualOverride(
                    operation="split_jump",
                    jump_id=lineage_id,
                    value_ms=lineage_segments[0].end_ms,
                    reason="jump split into multiple manual segments",
                )
            )

    return overrides


def merge_segment_overrides(
    auto_segments: list[JumpSegment],
    overrides: OverridesArtifact | None,
) -> tuple[list[JumpSegment], list[ManualOverride]]:
    """Merge automatic jump segments with persisted manual edits."""

    if not overrides:
        return normalize_jump_segments(auto_segments), []

    if overrides.jump_segments:
        merged_segments = normalize_jump_segments(overrides.jump_segments)
        finalized_segments: list[JumpSegment] = []
        for segment in merged_segments:
            source = "merged" if segment.auto_jump_ids else "manual"
            finalized_segments.append(segment.model_copy(update={"source": source}))
        return finalized_segments, overrides.manual_overrides

    merged_by_id = {segment.jump_id: segment.model_copy(deep=True) for segment in auto_segments}
    for override in overrides.manual_overrides:
        if override.operation != "update_boundary" or not override.applied:
            continue
        if override.jump_id not in merged_by_id:
            continue
        segment = merged_by_id[override.jump_id]
        updated_fields = list(segment.manual_boundary_fields)
        updated_fields.append(override.field_name)
        merged_by_id[override.jump_id] = segment.model_copy(
            update={
                override.field_name: override.value_ms,
                "source": "merged",
                "manual_boundary_fields": updated_fields,
            }
        )

    return normalize_jump_segments(list(merged_by_id.values())), overrides.manual_overrides


def merge_jump_labels(
    jump_segments: list[JumpSegment],
    labels_artifact: LabelsArtifact | None,
) -> list[JumpSegment]:
    """Apply persisted Phase 3 label data onto jump segments."""

    if not labels_artifact:
        return normalize_jump_segments(jump_segments)

    labels_by_jump_id = {item.jump_id: item for item in labels_artifact.labels}
    enriched: list[JumpSegment] = []
    for jump_segment in normalize_jump_segments(jump_segments):
        label_record = labels_by_jump_id.get(jump_segment.jump_id)
        if label_record is None:
            enriched.append(jump_segment)
            continue
        enriched.append(
            jump_segment.model_copy(
                update={
                    "label": label_record.resolved_label,
                    "auto_label": label_record.auto_label,
                    "resolved_label": label_record.resolved_label,
                    "override_label": label_record.override_label,
                    "override_note": label_record.override_note,
                    "label_confidence": label_record.confidence,
                    "label_source": label_record.source,
                    "decision_reason": label_record.decision_reason,
                    "fallback_reason": label_record.fallback_reason,
                    "feature_summary": label_record.feature_summary,
                }
            )
        )
    return enriched


def merge_jump_landings(
    jump_segments: list[JumpSegment],
    landing_artifact: LandingArtifact | None,
) -> list[JumpSegment]:
    """Apply persisted Phase 4 landing data onto jump segments."""

    if not landing_artifact:
        return normalize_jump_segments(jump_segments)

    landing_by_jump_id = {item.jump_id: item for item in landing_artifact.jumps}
    enriched: list[JumpSegment] = []
    for jump_segment in normalize_jump_segments(jump_segments):
        landing_record = landing_by_jump_id.get(jump_segment.jump_id)
        if landing_record is None:
            enriched.append(jump_segment)
            continue
        enriched.append(
            jump_segment.model_copy(
                update={
                    "landing_x_norm": landing_record.landing_x_norm,
                    "landing_y_norm": landing_record.landing_y_norm,
                    "landing_source": landing_record.landing_source,
                    "center_deviation": landing_record.center_deviation,
                    "zone": landing_record.zone,
                    "jump_flags": landing_record.jump_flags,
                }
            )
        )
    return enriched


def current_timeline_state(analysis_dir: Path) -> tuple[list[JumpSegment], list[ManualOverride]]:
    """Load the merged jump timeline that should drive Phase 3 artifacts."""

    segmentation = load_segmentation_payload(analysis_dir)
    auto_segments = [
        JumpSegment.model_validate(item)
        for item in (segmentation or {}).get("jump_segments", [])
    ]
    overrides = load_overrides_artifact(analysis_dir)
    return merge_segment_overrides(auto_segments, overrides)


def sync_analysis_segments(
    analysis_dir: Path,
    *,
    jump_segments: list[JumpSegment],
    manual_overrides: list[ManualOverride],
) -> RoutineAnalysis:
    """Update the top-level analysis contract after segmentation or manual edits."""

    analysis = load_analysis_model(analysis_dir)
    analysis_path = analysis_dir / ANALYSIS_FILENAME
    artifacts = list(analysis.artifacts)
    labels_artifact = load_labels_artifact(analysis_dir)
    landing_artifact = load_landing_artifact(analysis_dir)
    merged_jump_segments = merge_jump_labels(jump_segments, labels_artifact)
    merged_jump_segments = merge_jump_landings(merged_jump_segments, landing_artifact)
    if (analysis_dir / SEGMENTATION_FILENAME).is_file():
        artifacts = upsert_artifact(
            artifacts,
            name="segmentation",
            path=analysis_dir / SEGMENTATION_FILENAME,
            media_type="json",
            description="Automatic jump segmentation with contact/apex candidates.",
        )
    if (analysis_dir / OVERRIDES_FILENAME).is_file():
        artifacts = upsert_artifact(
            artifacts,
            name="overrides",
            path=analysis_dir / OVERRIDES_FILENAME,
            media_type="json",
            description="Persisted manual jump timeline overrides.",
        )
    if (analysis_dir / FEATURES_FILENAME).is_file():
        artifacts = upsert_artifact(
            artifacts,
            name="features",
            path=analysis_dir / FEATURES_FILENAME,
            media_type="jsonl",
            description="Per-jump frame features including flight-phase windows and angles.",
        )
    if (analysis_dir / LABELS_FILENAME).is_file():
        artifacts = upsert_artifact(
            artifacts,
            name="labels",
            path=analysis_dir / LABELS_FILENAME,
            media_type="json",
            description="Per-jump body-shape decisions, explainability, and manual overrides.",
        )
    if (analysis_dir / LANDING_FILENAME).is_file():
        artifacts = upsert_artifact(
            artifacts,
            name="landing",
            path=analysis_dir / LANDING_FILENAME,
            media_type="json",
            description="Normalized landing positions, zone summary, and routine flags.",
        )
    if (analysis_dir / SUMMARY_FILENAME).is_file():
        artifacts = upsert_artifact(
            artifacts,
            name="summary",
            path=analysis_dir / SUMMARY_FILENAME,
            media_type="text",
            description="Human-readable demo summary for landing assistance and export.",
        )
    artifacts = upsert_artifact(
        artifacts,
        name="analysis",
        path=analysis_path,
        media_type="json",
        description="High-level RoutineAnalysis payload for the demo app.",
    )
    updated = analysis.model_copy(
        update={
            "status": "needs_review"
            if manual_overrides or any(segment.override_label for segment in merged_jump_segments)
            else "complete",
            "jump_segments": normalize_jump_segments(merged_jump_segments),
            "manual_overrides": manual_overrides,
            "routine_summary": landing_artifact.routine_summary if landing_artifact else None,
            "artifacts": artifacts,
        }
    )
    save_analysis_model(analysis_dir, updated)
    return updated


def sync_phase3_artifacts(analysis_dir: Path) -> LabelsArtifact:
    """Generate features.jsonl and labels.json from the current merged jump timeline."""

    landmarks_path = analysis_dir / LANDMARKS_FILENAME
    if not landmarks_path.is_file():
        raise FileNotFoundError(f"Missing landmarks artifact: {landmarks_path}")

    jump_segments, manual_overrides = current_timeline_state(analysis_dir)
    if not jump_segments:
        labels_artifact = LabelsArtifact(analysis_id=analysis_dir.name, labels=[])
        save_labels_artifact(analysis_dir, labels_artifact)
        write_jsonl(analysis_dir / FEATURES_FILENAME, [])
        sync_analysis_segments(
            analysis_dir,
            jump_segments=jump_segments,
            manual_overrides=manual_overrides,
        )
        return labels_artifact

    prior_labels = load_labels_artifact(analysis_dir)
    override_map = {
        item.jump_id: (item.override_label, item.override_note)
        for item in (prior_labels.labels if prior_labels else [])
    }

    landmark_rows = iter_landmark_rows(landmarks_path)
    feature_rows = build_jump_feature_rows(
        analysis_id=analysis_dir.name,
        landmark_rows=landmark_rows,
        jump_segments=jump_segments,
    )
    write_jsonl(analysis_dir / FEATURES_FILENAME, feature_rows)

    labels_artifact = classify_labels_artifact(
        analysis_id=analysis_dir.name,
        jump_segments=jump_segments,
        feature_rows=feature_rows,
        override_map=override_map,
    )
    save_labels_artifact(analysis_dir, labels_artifact)
    sync_analysis_segments(
        analysis_dir,
        jump_segments=jump_segments,
        manual_overrides=manual_overrides,
    )
    sync_phase4_artifacts(analysis_dir)
    return labels_artifact


def sync_phase4_artifacts(analysis_dir: Path) -> LandingArtifact:
    """Generate landing.json and summary.md from the current merged jump timeline."""

    analysis = load_analysis_model(analysis_dir)
    frames_meta = read_json(analysis_dir / FRAMES_META_FILENAME)
    calibration = load_calibration(analysis_dir)
    jump_segments, manual_overrides = current_timeline_state(analysis_dir)
    jump_segments = merge_jump_labels(jump_segments, load_labels_artifact(analysis_dir))
    landing_artifact = build_landing_artifact(
        analysis_id=analysis.analysis_id,
        jump_segments=jump_segments,
        landmark_rows=iter_landmark_rows(analysis_dir / LANDMARKS_FILENAME),
        calibration=calibration,
        frames_meta=frames_meta,
    )
    save_landing_artifact(analysis_dir, landing_artifact)
    save_summary_markdown(
        analysis_dir,
        build_summary_markdown(
            analysis_id=analysis.analysis_id,
            source_video=analysis.source_video,
            landing_artifact=landing_artifact,
        ),
    )
    sync_analysis_segments(
        analysis_dir,
        jump_segments=jump_segments,
        manual_overrides=manual_overrides,
    )
    return landing_artifact


def persist_timeline_overrides(
    analysis_dir: Path,
    jump_segments: list[JumpSegment],
) -> OverridesArtifact:
    """Persist a full manual timeline snapshot and update the merged analysis view."""

    segmentation = load_segmentation_payload(analysis_dir)
    auto_segments = [
        JumpSegment.model_validate(item)
        for item in (segmentation or {}).get("jump_segments", [])
    ]
    normalized_segments = normalize_jump_segments(jump_segments)
    manual_overrides = derive_manual_overrides(auto_segments, normalized_segments)
    overrides = OverridesArtifact(
        analysis_id=analysis_dir.name,
        jump_segments=[
            segment.model_copy(
                update={
                    "source": "merged" if segment.auto_jump_ids else "manual",
                }
            )
            for segment in normalized_segments
        ],
        manual_overrides=manual_overrides,
    )
    save_overrides_artifact(analysis_dir, overrides)
    sync_analysis_segments(
        analysis_dir,
        jump_segments=overrides.jump_segments,
        manual_overrides=manual_overrides,
    )
    if (analysis_dir / LANDMARKS_FILENAME).is_file():
        sync_phase3_artifacts(analysis_dir)
    return overrides


def persist_label_override(
    analysis_dir: Path,
    *,
    jump_id: str,
    override_label: str | None,
    override_note: str | None = None,
) -> LabelsArtifact:
    """Persist one jump label override and keep analysis.json in sync."""

    labels_artifact = sync_phase3_artifacts(analysis_dir)
    updated_labels = []
    jump_found = False
    for label_record in labels_artifact.labels:
        if label_record.jump_id != jump_id:
            updated_labels.append(label_record)
            continue
        jump_found = True
        updated_labels.append(
            label_record.model_copy(
                update={
                    "override_label": override_label,
                    "override_note": override_note if override_label else None,
                    "resolved_label": override_label or label_record.auto_label,
                }
            )
        )

    if not jump_found:
        raise ValueError(f"Unknown jump_id: {jump_id}")

    updated_artifact = labels_artifact.model_copy(update={"labels": updated_labels})
    save_labels_artifact(analysis_dir, updated_artifact)
    jump_segments, manual_overrides = current_timeline_state(analysis_dir)
    sync_analysis_segments(
        analysis_dir,
        jump_segments=jump_segments,
        manual_overrides=manual_overrides,
    )
    return updated_artifact


def iter_landmark_rows(landmarks_path: Path) -> list[dict[str, Any]]:
    """Load all landmark rows from the JSONL artifact."""

    rows: list[dict[str, Any]] = []
    if not landmarks_path.is_file():
        return rows

    for line in landmarks_path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            rows.append(json.loads(line))
    return rows


def load_analysis_output(analysis_dir: Path) -> dict[str, Any]:
    """Load the app-facing preview payload for one finished analysis."""

    frames_meta_path = analysis_dir / FRAMES_META_FILENAME
    landmarks_path = analysis_dir / LANDMARKS_FILENAME
    analysis_path = analysis_dir / ANALYSIS_FILENAME

    if not frames_meta_path.is_file() or not landmarks_path.is_file():
        raise FileNotFoundError(f"Missing Phase 1 artifacts in {analysis_dir}")

    frames_meta = read_json(frames_meta_path)
    analysis_payload = read_json(analysis_path) if analysis_path.is_file() else {}
    calibration = load_calibration(analysis_dir)
    segmentation = load_segmentation_payload(analysis_dir)
    labels_artifact = load_labels_artifact(analysis_dir)
    landing_artifact = load_landing_artifact(analysis_dir)
    jump_segments, manual_overrides = current_timeline_state(analysis_dir)
    jump_segments = merge_jump_labels(jump_segments, labels_artifact)
    jump_segments = merge_jump_landings(jump_segments, landing_artifact)

    preview_rows = iter_landmark_rows(landmarks_path)
    preview_row = next(
        (row for row in preview_rows if row.get("has_landmarks")),
        preview_rows[0] if preview_rows else {"frame_index": 0, "timestamp_ms": 0, "landmarks": []},
    )

    return {
        "analysis_id": analysis_dir.name,
        "analysis_dir": str(analysis_dir),
        "source_video": frames_meta["source_video"],
        "frames_meta": frames_meta,
        "artifacts": analysis_payload.get("artifacts", []),
        "pose_connections": [list(connection) for connection in POSE_CONNECTIONS],
        "preview_frame": preview_row,
        "calibration": calibration.model_dump(mode="json") if calibration else None,
        "segmentation": segmentation,
        "jump_segments": [segment.model_dump(mode="json") for segment in jump_segments],
        "labels": labels_artifact.model_dump(mode="json")["labels"] if labels_artifact else [],
        "landing": landing_artifact.model_dump(mode="json") if landing_artifact else None,
        "routine_summary": analysis_payload.get("routine_summary") or (
            landing_artifact.routine_summary.model_dump(mode="json") if landing_artifact else None
        ),
        "summary_markdown": (analysis_dir / SUMMARY_FILENAME).read_text(encoding="utf-8")
        if (analysis_dir / SUMMARY_FILENAME).is_file()
        else None,
        "manual_overrides": [override.model_dump(mode="json") for override in manual_overrides],
        "has_overrides": bool((analysis_dir / OVERRIDES_FILENAME).is_file()),
        "has_labels": labels_artifact is not None,
        "has_landing": landing_artifact is not None,
        "updated_at": frames_meta.get("generated_at"),
    }


def list_analysis_outputs(output_root: Path) -> list[dict[str, Any]]:
    """Return lightweight metadata for analyses already on disk."""

    if not output_root.exists():
        return []

    items: list[dict[str, Any]] = []
    for analysis_dir in sorted(
        (path for path in output_root.iterdir() if path.is_dir()),
        key=lambda path: path.name,
    ):
        frames_meta_path = analysis_dir / FRAMES_META_FILENAME
        if not frames_meta_path.is_file():
            continue
        frames_meta = read_json(frames_meta_path)
        items.append(
            {
                "analysis_id": analysis_dir.name,
                "source_video": frames_meta["source_video"],
                "frame_count": frames_meta["frame_count"],
                "duration_ms": frames_meta["duration_ms"],
                "has_segmentation": (analysis_dir / SEGMENTATION_FILENAME).is_file(),
                "has_overrides": (analysis_dir / OVERRIDES_FILENAME).is_file(),
                "has_labels": (analysis_dir / LABELS_FILENAME).is_file(),
                "has_landing": (analysis_dir / LANDING_FILENAME).is_file(),
                "updated_at": frames_meta.get("generated_at"),
            }
        )
    return items


def analyze_video(
    *,
    video_path: Path,
    output_dir: Path,
    landmarks_only: bool = False,
    analysis_id: str | None = None,
) -> RoutineAnalysis:
    """Run the Phase 1 offline landmark extraction pipeline."""

    del landmarks_only

    video_path = resolve_repo_path(str(video_path)) if not video_path.is_absolute() else video_path
    if not video_path.is_file():
        raise FileNotFoundError(f"Video not found: {video_path}")

    output_dir.mkdir(parents=True, exist_ok=True)
    resolved_analysis_id = analysis_id or output_dir.name

    capture = cv2.VideoCapture(str(video_path))
    if not capture.isOpened():
        raise RuntimeError(f"Unable to open video: {video_path}")

    fps = float(capture.get(cv2.CAP_PROP_FPS) or 30.0)
    width = int(capture.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
    height = int(capture.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    landmarks_path = output_dir / LANDMARKS_FILENAME

    frame_index = 0
    with landmarks_path.open("w", encoding="utf-8") as landmarks_file:
        with mp.solutions.pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            smooth_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        ) as pose:
            while True:
                ok, frame = capture.read()
                if not ok:
                    break

                timestamp_ms = timestamp_ms_for_frame(frame_index, fps)
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                result = pose.process(rgb_frame)
                serialized_landmarks = serialize_landmarks(
                    result.pose_landmarks.landmark if result.pose_landmarks else None
                )
                row = {
                    "frame_index": frame_index,
                    "timestamp_ms": timestamp_ms,
                    "has_landmarks": bool(serialized_landmarks),
                    "landmarks": serialized_landmarks,
                }
                landmarks_file.write(json.dumps(row) + "\n")
                frame_index += 1

    capture.release()

    frames_meta = build_frames_meta(
        source_video=repo_relative_path(video_path),
        fps=fps,
        frame_count=frame_index,
        width=width,
        height=height,
    )
    frames_meta_path = output_dir / FRAMES_META_FILENAME
    write_json(frames_meta_path, frames_meta)

    analysis = initialize_analysis(
        analysis_id=resolved_analysis_id,
        source_video=repo_relative_path(video_path),
    ).model_copy(
        update={
            "status": "complete",
            "created_at": datetime.now(timezone.utc),
            "artifacts": [
                AnalysisArtifactRef(
                    name="landmarks",
                    path=repo_relative_path(landmarks_path),
                    media_type="jsonl",
                    description="Frame-wise pose landmarks generated by MediaPipe Pose.",
                ),
                AnalysisArtifactRef(
                    name="frames_meta",
                    path=repo_relative_path(frames_meta_path),
                    media_type="json",
                    description="Frame index to timestamp map and source video metadata.",
                ),
                AnalysisArtifactRef(
                    name="analysis",
                    path=repo_relative_path(output_dir / ANALYSIS_FILENAME),
                    media_type="json",
                    description="High-level RoutineAnalysis payload for the demo app.",
                ),
            ],
        }
    )
    write_json(output_dir / ANALYSIS_FILENAME, analysis.model_dump(mode="json"))
    return analysis
