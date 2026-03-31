"""TRA body-shape rules for Phase 3 label generation."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any

from trampoline.features import summarize_jump_feature_rows
from trampoline.schema import BodyShapeLabel, JumpLabelRecord, JumpSegment, LabelsArtifact


TRA_V1_EXCLUSIONS = [
    "D-score",
    "ToF",
    "SYN",
    "TUM",
    "DMT",
]


DIFFICULTY_ORDER: dict[BodyShapeLabel, int] = {
    "tuck": 0,
    "pike": 1,
    "straight": 2,
}


@dataclass(frozen=True)
class ShapeClassifierConfig:
    """Thresholds for the simplified TRA body-shape classifier."""

    tuck_trunk_max: float = 90.0
    tuck_knee_max: float = 135.0
    pike_trunk_max: float = 130.0
    pike_knee_min: float = 140.0
    straight_trunk_min: float = 145.0
    straight_knee_min: float = 150.0
    min_confidence: float = 0.30


def _canonical_scores(trunk_thigh_angle: float, thigh_shank_angle: float) -> dict[BodyShapeLabel, float]:
    """Return soft similarity scores used for ambiguous frames."""

    canonical_targets: dict[BodyShapeLabel, tuple[float, float]] = {
        "tuck": (70.0, 85.0),
        "pike": (92.0, 160.0),
        "straight": (165.0, 170.0),
    }
    scores: dict[BodyShapeLabel, float] = {}
    for label, (target_trunk, target_knee) in canonical_targets.items():
        distance = abs(trunk_thigh_angle - target_trunk) + abs(thigh_shank_angle - target_knee)
        scores[label] = 1.0 / (1.0 + distance)
    return scores


def classify_frame_shape(
    trunk_thigh_angle: float | None,
    thigh_shank_angle: float | None,
    *,
    config: ShapeClassifierConfig | None = None,
) -> tuple[BodyShapeLabel | None, float]:
    """Classify a single frame into tuck, pike, or straight."""

    if trunk_thigh_angle is None or thigh_shank_angle is None:
        return None, 0.0

    thresholds = config or ShapeClassifierConfig()
    if trunk_thigh_angle <= thresholds.tuck_trunk_max and thigh_shank_angle <= thresholds.tuck_knee_max:
        margin = min(
            (thresholds.tuck_trunk_max - trunk_thigh_angle) / thresholds.tuck_trunk_max,
            (thresholds.tuck_knee_max - thigh_shank_angle) / thresholds.tuck_knee_max,
        )
        return "tuck", max(0.0, min(1.0, 0.65 + margin))

    if trunk_thigh_angle <= thresholds.pike_trunk_max and thigh_shank_angle >= thresholds.pike_knee_min:
        margin = min(
            (thresholds.pike_trunk_max - trunk_thigh_angle) / thresholds.pike_trunk_max,
            (thigh_shank_angle - thresholds.pike_knee_min) / max(1.0, 180.0 - thresholds.pike_knee_min),
        )
        return "pike", max(0.0, min(1.0, 0.60 + margin))

    if trunk_thigh_angle >= thresholds.straight_trunk_min and thigh_shank_angle >= thresholds.straight_knee_min:
        margin = min(
            (trunk_thigh_angle - thresholds.straight_trunk_min) / max(1.0, 180.0 - thresholds.straight_trunk_min),
            (thigh_shank_angle - thresholds.straight_knee_min) / max(1.0, 180.0 - thresholds.straight_knee_min),
        )
        return "straight", max(0.0, min(1.0, 0.60 + margin))

    canonical_scores = _canonical_scores(trunk_thigh_angle, thigh_shank_angle)
    best_label = max(canonical_scores, key=canonical_scores.get)
    return best_label, min(0.55, round(canonical_scores[best_label] * 10.0, 3))


def _resolved_label(frame_labels: list[BodyShapeLabel]) -> BodyShapeLabel:
    return min(frame_labels, key=lambda label: (DIFFICULTY_ORDER[label], label))


def classify_jump_shape(
    jump_segment: JumpSegment,
    feature_rows: list[dict[str, Any]],
    *,
    override_label: BodyShapeLabel | None = None,
    override_note: str | None = None,
    config: ShapeClassifierConfig | None = None,
) -> JumpLabelRecord:
    """Classify one jump using the mid-flight lowest-difficulty rule."""

    thresholds = config or ShapeClassifierConfig()
    summary = summarize_jump_feature_rows(feature_rows)
    eligible_rows = [
        row
        for row in feature_rows
        if row.get("is_mid_flight_window")
        and row.get("trunk_thigh_angle") is not None
        and row.get("thigh_shank_angle") is not None
    ]
    fallback_reason = None
    if not eligible_rows:
        eligible_rows = [
            row
            for row in feature_rows
            if row.get("is_flight_phase")
            and row.get("trunk_thigh_angle") is not None
            and row.get("thigh_shank_angle") is not None
        ]
        fallback_reason = "No valid mid-flight frames above visibility threshold; used the full flight window."

    frame_labels: list[BodyShapeLabel] = []
    frame_confidences: list[float] = []
    for row in eligible_rows:
        frame_label, frame_confidence = classify_frame_shape(
            row.get("trunk_thigh_angle"),
            row.get("thigh_shank_angle"),
            config=thresholds,
        )
        if frame_label is None:
            continue
        frame_labels.append(frame_label)
        frame_confidences.append(frame_confidence)

    if not frame_labels:
        frame_labels = ["straight"]
        frame_confidences = [thresholds.min_confidence]
        if fallback_reason:
            fallback_reason = (
                f"{fallback_reason} No valid angle pair remained, so the classifier defaulted to straight."
            )
        else:
            fallback_reason = "No valid mid-flight angle pair was available, so the classifier defaulted to straight."

    counts = Counter(frame_labels)
    auto_label = _resolved_label(frame_labels)
    share = counts[auto_label] / len(frame_labels)
    visibility_values = [float(row.get("visibility_score") or 0.0) for row in eligible_rows] or [0.0]
    confidence = min(
        0.99,
        max(
            thresholds.min_confidence,
            0.35 + (0.40 * share) + (0.15 * (sum(frame_confidences) / len(frame_confidences))) + (0.10 * (sum(visibility_values) / len(visibility_values))),
        ),
    )
    if fallback_reason:
        confidence = min(confidence, 0.58)

    decision_reason = (
        "mid-flight lowest-difficulty rule: "
        f"tuck={counts.get('tuck', 0)}, pike={counts.get('pike', 0)}, straight={counts.get('straight', 0)}; "
        f"resolved to {auto_label}."
    )
    resolved_label = override_label or auto_label
    if override_label:
        decision_reason = f"{decision_reason} Manual override applied as {override_label}."

    return JumpLabelRecord(
        jump_id=jump_segment.jump_id,
        sequence_index=jump_segment.sequence_index,
        auto_label=auto_label,
        resolved_label=resolved_label,
        override_label=override_label,
        override_note=override_note,
        confidence=round(confidence, 3),
        source="rules_tra_v1",
        decision_reason=decision_reason,
        fallback_reason=fallback_reason,
        feature_summary=summary,
    )


def classify_labels_artifact(
    *,
    analysis_id: str,
    jump_segments: list[JumpSegment],
    feature_rows: list[dict[str, Any]],
    override_map: dict[str, tuple[BodyShapeLabel | None, str | None]] | None = None,
    config: ShapeClassifierConfig | None = None,
) -> LabelsArtifact:
    """Classify every jump in one analysis into the Phase 3 label artifact."""

    override_map = override_map or {}
    rows_by_jump_id: dict[str, list[dict[str, Any]]] = {}
    for row in feature_rows:
        rows_by_jump_id.setdefault(str(row["jump_id"]), []).append(row)

    labels = []
    for jump_segment in jump_segments:
        override_label, override_note = override_map.get(jump_segment.jump_id, (None, None))
        labels.append(
            classify_jump_shape(
                jump_segment,
                rows_by_jump_id.get(jump_segment.jump_id, []),
                override_label=override_label,
                override_note=override_note,
                config=config,
            )
        )

    return LabelsArtifact(analysis_id=analysis_id, labels=labels)
