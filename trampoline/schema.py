"""Shared schema objects for trampoline analysis artifacts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


ArtifactMediaType = Literal["json", "jsonl", "video", "image", "text", "directory"]
BodyShapeLabel = Literal["tuck", "pike", "straight"]
JumpSource = Literal["auto", "manual", "merged"]
OverrideFieldName = Literal["start_ms", "takeoff_ms", "apex_ms", "landing_ms", "end_ms"]
OverrideOperation = Literal["update_boundary", "split_jump", "merge_jumps", "replace_segments"]
RoutineStatus = Literal["pending", "running", "complete", "needs_review", "failed"]
LandingZone = Literal["center", "inner", "edge", "out", "unknown"]


class AnalysisArtifactRef(BaseModel):
    """Reference to a generated artifact inside an analysis directory."""

    name: str = Field(..., min_length=1)
    path: str = Field(..., min_length=1)
    media_type: ArtifactMediaType = "json"
    description: Optional[str] = None


class ManualOverride(BaseModel):
    """Human-authored jump timeline edit metadata."""

    jump_id: Optional[str] = Field(default=None, min_length=1)
    jump_ids: list[str] = Field(default_factory=list)
    operation: OverrideOperation = "update_boundary"
    field_name: Optional[OverrideFieldName] = None
    value_ms: Optional[int] = Field(default=None, ge=0)
    result_jump_id: Optional[str] = Field(default=None, min_length=1)
    reason: Optional[str] = None
    author: str = Field(default="operator", min_length=1)
    applied: bool = True

    @field_validator("jump_ids")
    @classmethod
    def validate_jump_ids(cls, jump_ids: list[str]) -> list[str]:
        if any(not jump_id.strip() for jump_id in jump_ids):
            raise ValueError("jump_ids cannot contain blank strings")
        return jump_ids

    @model_validator(mode="after")
    def validate_override_shape(self) -> "ManualOverride":
        if self.operation == "update_boundary":
            if not self.jump_id or self.field_name is None or self.value_ms is None:
                raise ValueError("update_boundary overrides require jump_id, field_name, and value_ms")
            return self

        if self.operation == "split_jump":
            if not self.jump_id or self.value_ms is None:
                raise ValueError("split_jump overrides require jump_id and value_ms")
            return self

        if self.operation in {"merge_jumps", "replace_segments"} and not self.jump_ids:
            raise ValueError(f"{self.operation} overrides require jump_ids")
        return self


class FeatureSummary(BaseModel):
    """Jump-level angle summary used by the UI and exported label artifact."""

    frame_count: int = Field(default=0, ge=0)
    mid_flight_frame_count: int = Field(default=0, ge=0)
    valid_frame_count: int = Field(default=0, ge=0)
    mid_flight_valid_frame_count: int = Field(default=0, ge=0)
    trunk_thigh_min_angle: Optional[float] = Field(default=None, ge=0.0, le=180.0)
    trunk_thigh_max_angle: Optional[float] = Field(default=None, ge=0.0, le=180.0)
    thigh_shank_min_angle: Optional[float] = Field(default=None, ge=0.0, le=180.0)
    thigh_shank_max_angle: Optional[float] = Field(default=None, ge=0.0, le=180.0)
    representative_timestamp_ms: Optional[int] = Field(default=None, ge=0)


class JumpLabelRecord(BaseModel):
    """Persisted automatic and manual body-shape decision for one jump."""

    jump_id: str = Field(..., min_length=1)
    sequence_index: int = Field(..., ge=0)
    auto_label: Optional[BodyShapeLabel] = None
    resolved_label: Optional[BodyShapeLabel] = None
    override_label: Optional[BodyShapeLabel] = None
    override_note: Optional[str] = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(default="rules_tra_v1", min_length=1)
    decision_reason: str = ""
    fallback_reason: Optional[str] = None
    feature_summary: FeatureSummary = Field(default_factory=FeatureSummary)


class LabelsArtifact(BaseModel):
    """Persisted Phase 3 label artifact for one analysis."""

    analysis_id: str = Field(..., min_length=1)
    labels: list[JumpLabelRecord] = Field(default_factory=list)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class LandingRecord(BaseModel):
    """Persisted normalized landing data for one jump."""

    jump_id: str = Field(..., min_length=1)
    sequence_index: int = Field(..., ge=0)
    landing_ms: int = Field(..., ge=0)
    landing_frame_index: Optional[int] = Field(default=None, ge=0)
    landing_source: str = Field(default="missing", min_length=1)
    landing_x_norm: Optional[float] = None
    landing_y_norm: Optional[float] = None
    center_deviation: Optional[float] = Field(default=None, ge=0.0)
    zone: LandingZone = "unknown"
    jump_flags: list[str] = Field(default_factory=list)
    support_sides: list[str] = Field(default_factory=list)
    source_landmarks: list[str] = Field(default_factory=list)
    valid: bool = False

    @field_validator("jump_flags", "support_sides", "source_landmarks")
    @classmethod
    def validate_non_blank_items(cls, items: list[str]) -> list[str]:
        if any(not item.strip() for item in items):
            raise ValueError("list items cannot contain blank strings")
        return list(dict.fromkeys(items))


class RoutineSummary(BaseModel):
    """Demo-level routine summary derived from normalized landing positions."""

    jump_count: int = Field(default=0, ge=0)
    landed_jump_count: int = Field(default=0, ge=0)
    mean_center_deviation: Optional[float] = Field(default=None, ge=0.0)
    max_center_deviation: Optional[float] = Field(default=None, ge=0.0)
    zone_summary: dict[str, int] = Field(default_factory=dict)
    jump_flag_counts: dict[str, int] = Field(default_factory=dict)
    routine_flags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)

    @field_validator("routine_flags", "notes")
    @classmethod
    def validate_summary_lists(cls, items: list[str]) -> list[str]:
        if any(not item.strip() for item in items):
            raise ValueError("summary items cannot contain blank strings")
        return list(dict.fromkeys(items))


class LandingArtifact(BaseModel):
    """Persisted Phase 4 landing and routine-summary artifact."""

    analysis_id: str = Field(..., min_length=1)
    jumps: list[LandingRecord] = Field(default_factory=list)
    routine_summary: RoutineSummary = Field(default_factory=RoutineSummary)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class JumpSegment(BaseModel):
    """Canonical representation of one jump boundary set."""

    jump_id: str = Field(..., min_length=1)
    sequence_index: int = Field(..., ge=0)
    start_ms: int = Field(..., ge=0)
    takeoff_ms: int = Field(..., ge=0)
    apex_ms: int = Field(..., ge=0)
    landing_ms: int = Field(..., ge=0)
    end_ms: int = Field(..., ge=0)
    label: Optional[str] = None
    source: JumpSource = "auto"
    confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    notes: list[str] = Field(default_factory=list)
    auto_jump_ids: list[str] = Field(default_factory=list)
    manual_boundary_fields: list[OverrideFieldName] = Field(default_factory=list)
    auto_label: Optional[BodyShapeLabel] = None
    resolved_label: Optional[BodyShapeLabel] = None
    override_label: Optional[BodyShapeLabel] = None
    override_note: Optional[str] = None
    label_confidence: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    label_source: Optional[str] = None
    decision_reason: Optional[str] = None
    fallback_reason: Optional[str] = None
    feature_summary: Optional[FeatureSummary] = None
    landing_x_norm: Optional[float] = None
    landing_y_norm: Optional[float] = None
    landing_source: Optional[str] = None
    center_deviation: Optional[float] = Field(default=None, ge=0.0)
    zone: Optional[LandingZone] = None
    jump_flags: list[str] = Field(default_factory=list)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, notes: list[str]) -> list[str]:
        if any(not note.strip() for note in notes):
            raise ValueError("notes cannot contain blank strings")
        return notes

    @field_validator("auto_jump_ids")
    @classmethod
    def validate_auto_jump_ids(cls, auto_jump_ids: list[str]) -> list[str]:
        if any(not jump_id.strip() for jump_id in auto_jump_ids):
            raise ValueError("auto_jump_ids cannot contain blank strings")
        deduped = list(dict.fromkeys(auto_jump_ids))
        return deduped

    @field_validator("manual_boundary_fields")
    @classmethod
    def validate_manual_fields(cls, fields: list[OverrideFieldName]) -> list[OverrideFieldName]:
        return list(dict.fromkeys(fields))

    @field_validator("jump_flags")
    @classmethod
    def validate_jump_flags(cls, flags: list[str]) -> list[str]:
        if any(not flag.strip() for flag in flags):
            raise ValueError("jump_flags cannot contain blank strings")
        return list(dict.fromkeys(flags))

    @model_validator(mode="after")
    def validate_time_order(self) -> "JumpSegment":
        ordered_times = [
            self.start_ms,
            self.takeoff_ms,
            self.apex_ms,
            self.landing_ms,
            self.end_ms,
        ]
        if ordered_times != sorted(ordered_times):
            raise ValueError("jump timing fields must be monotonically increasing")
        if not self.auto_jump_ids:
            self.auto_jump_ids = [self.jump_id]
        return self


class OverridesArtifact(BaseModel):
    """Persisted manual timeline edits for one analysis."""

    analysis_id: str = Field(..., min_length=1)
    jump_segments: list[JumpSegment] = Field(default_factory=list)
    manual_overrides: list[ManualOverride] = Field(default_factory=list)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class RoutineAnalysis(BaseModel):
    """Top-level analysis contract shared by CLI, pipeline, and app layers."""

    analysis_id: str = Field(..., min_length=1)
    source_video: str = Field(..., min_length=1)
    discipline: Literal["TRA"] = "TRA"
    athlete_count: Literal[1] = 1
    routine_label: str = Field(default="single_person_tra_demo", min_length=1)
    status: RoutineStatus = "pending"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    jump_segments: list[JumpSegment] = Field(default_factory=list)
    manual_overrides: list[ManualOverride] = Field(default_factory=list)
    routine_summary: Optional[RoutineSummary] = None
    artifacts: list[AnalysisArtifactRef] = Field(default_factory=list)
