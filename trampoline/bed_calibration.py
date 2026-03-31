"""Bed calibration persistence and perspective transforms for the demo."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from pydantic import BaseModel, Field, model_validator


CALIBRATION_FILENAME = "calibration.json"
CORNER_ORDER = ("top_left", "top_right", "bottom_right", "bottom_left")


class CalibrationPoint(BaseModel):
    """One 2D point in pixel or normalized coordinates."""

    x: float
    y: float


class BedCalibration(BaseModel):
    """Serializable bed calibration artifact."""

    corners: dict[str, CalibrationPoint]
    center_point: CalibrationPoint
    frame_size: dict[str, int]
    normalized_corners: dict[str, CalibrationPoint] = Field(
        default_factory=lambda: {
            "top_left": CalibrationPoint(x=0.0, y=0.0),
            "top_right": CalibrationPoint(x=1.0, y=0.0),
            "bottom_right": CalibrationPoint(x=1.0, y=1.0),
            "bottom_left": CalibrationPoint(x=0.0, y=1.0),
        }
    )
    bed_to_normalized: list[list[float]]
    normalized_to_bed: list[list[float]]
    updated_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @model_validator(mode="after")
    def validate_corner_keys(self) -> "BedCalibration":
        if tuple(self.corners.keys()) != CORNER_ORDER:
            raise ValueError(f"corners must be ordered as {CORNER_ORDER}")
        return self


def _coerce_point(point: Any) -> CalibrationPoint:
    if isinstance(point, CalibrationPoint):
        return point
    return CalibrationPoint.model_validate(point)


def _ordered_corner_points(corners: dict[str, Any]) -> dict[str, CalibrationPoint]:
    return {name: _coerce_point(corners[name]) for name in CORNER_ORDER}


def _matrix_from_points(source_points: np.ndarray, target_points: np.ndarray) -> np.ndarray:
    return cv2.getPerspectiveTransform(source_points.astype(np.float32), target_points.astype(np.float32))


def transform_point(point: CalibrationPoint | dict[str, float], matrix: list[list[float]] | np.ndarray) -> CalibrationPoint:
    """Apply one homography matrix to one point."""

    coerced_point = _coerce_point(point)
    transform = np.asarray(matrix, dtype=np.float64)
    homogeneous = np.array([coerced_point.x, coerced_point.y, 1.0], dtype=np.float64)
    mapped = transform @ homogeneous
    scale = mapped[2] if mapped[2] else 1.0
    return CalibrationPoint(x=float(mapped[0] / scale), y=float(mapped[1] / scale))


def create_bed_calibration(
    *,
    corners: dict[str, CalibrationPoint | dict[str, float]],
    frame_width: int,
    frame_height: int,
) -> BedCalibration:
    """Create a persistent bed calibration payload from four corners."""

    ordered_corners = _ordered_corner_points(corners)
    bed_points = np.array([[point.x, point.y] for point in ordered_corners.values()], dtype=np.float32)
    normalized_points = np.array(
        [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]],
        dtype=np.float32,
    )
    bed_to_normalized = _matrix_from_points(bed_points, normalized_points)
    normalized_to_bed = _matrix_from_points(normalized_points, bed_points)
    center_point = transform_point({"x": 0.5, "y": 0.5}, normalized_to_bed)
    return BedCalibration(
        corners=ordered_corners,
        center_point=center_point,
        frame_size={"width": int(frame_width), "height": int(frame_height)},
        bed_to_normalized=bed_to_normalized.tolist(),
        normalized_to_bed=normalized_to_bed.tolist(),
    )


def save_calibration(calibration: BedCalibration, analysis_dir: Path) -> Path:
    """Persist one bed calibration into its analysis directory."""

    analysis_dir.mkdir(parents=True, exist_ok=True)
    target = analysis_dir / CALIBRATION_FILENAME
    target.write_text(json.dumps(calibration.model_dump(mode="json"), indent=2), encoding="utf-8")
    return target


def load_calibration(analysis_dir: Path) -> BedCalibration | None:
    """Load a saved bed calibration when it exists."""

    calibration_path = analysis_dir / CALIBRATION_FILENAME
    if not calibration_path.is_file():
        return None
    return BedCalibration.model_validate_json(calibration_path.read_text(encoding="utf-8"))
