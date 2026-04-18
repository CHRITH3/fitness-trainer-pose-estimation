"""Bed plane calibration, tracking, and landing-zone mapping for trampoline videos."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

import cv2
import numpy as np

import trampoline.config as cfg

CORNER_ORDER = ["front_left", "front_right", "back_right", "back_left"]
TRACKING_TRUSTED = "trusted"
TRACKING_LOW_CONFIDENCE = "low_confidence"
TRACKING_FROZEN = "frozen"
TRACKING_LOST = "tracking_lost"


class BedTrackerValidationError(ValueError):
    """Raised when calibration corners or sidecar data are invalid."""


@dataclass
class BedTrackerInfo:
    success: bool
    frame_index: Optional[int]
    corners: List[List[float]]
    inlier_ratio: float
    tracked_points: int
    tracking_confidence: float
    message: str = ""
    tracking_state: str = TRACKING_LOW_CONFIDENCE
    diagnostics: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "success": self.success,
            "frame_index": self.frame_index,
            "corners": self.corners,
            "inlier_ratio": self.inlier_ratio,
            "tracked_points": self.tracked_points,
            "tracking_confidence": self.tracking_confidence,
            "message": self.message,
            "tracking_state": self.tracking_state,
            "diagnostics": self.diagnostics,
        }


@dataclass(frozen=True)
class BedCalibration:
    frame_index: int
    time_s: Optional[float]
    corners_px: List[Dict[str, float]]

    def to_dict(self) -> Dict[str, Any]:
        data = {
            "frame_index": int(self.frame_index),
            "corners_px": [
                {"name": p["name"], "x": float(p["x"]), "y": float(p["y"])}
                for p in self.corners_px
            ],
        }
        if self.time_s is not None:
            data["time_s"] = float(self.time_s)
        return data


def _coerce_frame_index(value: Any) -> int:
    if isinstance(value, bool):
        raise BedTrackerValidationError("Calibration frame_index must be an integer")
    try:
        frame_index = int(value)
    except (TypeError, ValueError) as exc:
        raise BedTrackerValidationError("Calibration frame_index must be an integer") from exc
    if frame_index < 0 or float(frame_index) != float(value):
        raise BedTrackerValidationError("Calibration frame_index must be a non-negative integer")
    return frame_index


def normalize_calibrations(
    calibrations: Sequence[Any],
    image_size: Optional[Tuple[int, int]] = None,
) -> List[Dict[str, Any]]:
    """Validate and canonicalize manual bed calibration keyframes."""
    if not isinstance(calibrations, Sequence) or isinstance(calibrations, (str, bytes)):
        raise BedTrackerValidationError("calibrations must be a list")
    if not calibrations:
        raise BedTrackerValidationError("At least one calibration is required")

    seen_frames = set()
    normalized: List[BedCalibration] = []
    for item in calibrations:
        if not isinstance(item, dict):
            raise BedTrackerValidationError("Each calibration must be an object")
        frame_index = _coerce_frame_index(item.get("frame_index", 0))
        if frame_index in seen_frames:
            raise BedTrackerValidationError("Duplicate calibration frame_index values are not allowed")
        seen_frames.add(frame_index)

        time_s = item.get("time_s")
        if time_s is not None:
            try:
                time_s = float(time_s)
            except (TypeError, ValueError) as exc:
                raise BedTrackerValidationError("Calibration time_s must be numeric") from exc
            if not math.isfinite(time_s) or time_s < 0:
                raise BedTrackerValidationError("Calibration time_s must be a finite non-negative number")

        corners = item.get("corners_px", item.get("corners"))
        canonical_corners = validate_corners(corners or [], image_size=image_size)
        normalized.append(BedCalibration(frame_index, time_s, canonical_corners))

    normalized.sort(key=lambda cal: cal.frame_index)
    return [cal.to_dict() for cal in normalized]


def _calibration_corners_array(calibration: Dict[str, Any]) -> np.ndarray:
    return corners_to_array(calibration["corners_px"])


def _coerce_point(point: Any, default_name: Optional[str] = None) -> Dict[str, float]:
    if isinstance(point, dict):
        if "x" not in point or "y" not in point:
            raise BedTrackerValidationError("Corner point is missing x/y")
        name = point.get("name", default_name)
        x, y = point["x"], point["y"]
    elif isinstance(point, (list, tuple)) and len(point) >= 2:
        name = default_name
        x, y = point[0], point[1]
    else:
        raise BedTrackerValidationError("Corner point must be {x,y} or [x,y]")

    try:
        xf = float(x)
        yf = float(y)
    except (TypeError, ValueError) as exc:
        raise BedTrackerValidationError("Corner coordinates must be numeric") from exc
    if not (math.isfinite(xf) and math.isfinite(yf)):
        raise BedTrackerValidationError("Corner coordinates must be finite")
    return {"name": name or "", "x": xf, "y": yf}


def normalize_corners(corners: Sequence[Any]) -> List[Dict[str, float]]:
    """Normalize corner input to named `{name, x, y}` dictionaries."""
    if len(corners) != 4:
        raise BedTrackerValidationError("Exactly 4 bed corners are required")
    normalized = [_coerce_point(p, CORNER_ORDER[i]) for i, p in enumerate(corners)]
    names = [p.get("name") or CORNER_ORDER[i] for i, p in enumerate(normalized)]
    if names != CORNER_ORDER:
        raise BedTrackerValidationError(
            f"Corners must be ordered as {', '.join(CORNER_ORDER)}"
        )
    for i, p in enumerate(normalized):
        p["name"] = CORNER_ORDER[i]
    return normalized


def corners_to_array(corners: Sequence[Any]) -> np.ndarray:
    normalized = normalize_corners(corners)
    return np.array([[p["x"], p["y"]] for p in normalized], dtype=np.float32)


def _segment_intersection(a: np.ndarray, b: np.ndarray, c: np.ndarray, d: np.ndarray) -> bool:
    def orient(p, q, r):
        return float((q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0]))

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    return (o1 * o2 < 0) and (o3 * o4 < 0)


def _quad_area(corners: np.ndarray) -> float:
    return abs(float(cv2.contourArea(corners.astype(np.float32).reshape(-1, 1, 2))))


def _quad_center(corners: np.ndarray) -> np.ndarray:
    return np.mean(corners.astype(np.float32).reshape(-1, 2), axis=0)


def _edge_lengths(corners: np.ndarray) -> np.ndarray:
    pts = corners.astype(np.float32).reshape(-1, 2)
    return np.array([float(np.linalg.norm(pts[(i + 1) % 4] - pts[i])) for i in range(4)], dtype=np.float32)


def _is_convex_quad(corners: np.ndarray) -> bool:
    pts = corners.astype(np.float32).reshape(-1, 2)
    signs = []
    for i in range(4):
        a = pts[i]
        b = pts[(i + 1) % 4]
        c = pts[(i + 2) % 4]
        v1 = b - a
        v2 = c - b
        cross = float(v1[0] * v2[1] - v1[1] * v2[0])
        if abs(cross) < 1e-6:
            return False
        signs.append(cross > 0)
    return all(signs) or not any(signs)


def validate_corners(
    corners: Sequence[Any],
    image_size: Optional[Tuple[int, int]] = None,
    min_area_px: Optional[float] = None,
    min_area_ratio: Optional[float] = None,
) -> List[Dict[str, float]]:
    """Validate corner geometry and return normalized corners.

    `image_size` is `(width, height)` when available.
    """
    normalized = normalize_corners(corners)
    pts = np.array([[p["x"], p["y"]] for p in normalized], dtype=np.float32)

    if image_size is not None:
        width, height = image_size
        for p in normalized:
            if p["x"] < 0 or p["x"] >= width or p["y"] < 0 or p["y"] >= height:
                raise BedTrackerValidationError("Corner point is outside the first-frame bounds")

    min_dist = getattr(cfg, "BED_CORNER_MIN_DISTANCE_PX", 5.0)
    for i in range(4):
        for j in range(i + 1, 4):
            if float(np.linalg.norm(pts[i] - pts[j])) < min_dist:
                raise BedTrackerValidationError("Corner points are duplicated or too close together")

    area = _quad_area(pts)
    min_area_px = min_area_px if min_area_px is not None else getattr(cfg, "BED_MIN_QUAD_AREA_PX", 100.0)
    if area < min_area_px:
        raise BedTrackerValidationError("Bed quadrilateral area is too small")
    if image_size is not None:
        width, height = image_size
        ratio = area / max(1.0, float(width * height))
        min_area_ratio = min_area_ratio if min_area_ratio is not None else getattr(cfg, "BED_MIN_QUAD_AREA_RATIO", 0.01)
        if ratio < min_area_ratio:
            raise BedTrackerValidationError("Bed quadrilateral area is too small for the frame")

    if _segment_intersection(pts[0], pts[1], pts[2], pts[3]) or _segment_intersection(pts[1], pts[2], pts[3], pts[0]):
        raise BedTrackerValidationError("Bed corners form a self-intersecting quadrilateral")
    if not _is_convex_quad(pts):
        raise BedTrackerValidationError("Bed corners must form a convex quadrilateral")

    bed_ref = np.array([[0, 0], [1, 0], [1, 1], [0, 1]], dtype=np.float32)
    H, _ = cv2.findHomography(pts, bed_ref, 0)
    if H is None or not np.all(np.isfinite(H)):
        raise BedTrackerValidationError("Bed corners cannot form a valid homography")
    return normalized


def normalize_calibrations(calibrations: Sequence[Any], image_size: Optional[Tuple[int, int]] = None) -> List[Dict[str, Any]]:
    if not isinstance(calibrations, Sequence) or isinstance(calibrations, (str, bytes, bytearray)):
        raise BedTrackerValidationError("Calibrations must be a list")
    if not calibrations:
        raise BedTrackerValidationError("At least one calibration is required")

    normalized = []
    seen_frames = set()
    for idx, calibration in enumerate(calibrations):
        if not isinstance(calibration, dict):
            raise BedTrackerValidationError("Calibration entry must be an object")
        if "frame_index" not in calibration:
            raise BedTrackerValidationError("Calibration frame_index is required")
        try:
            frame_index = int(calibration.get("frame_index"))
        except (TypeError, ValueError) as exc:
            raise BedTrackerValidationError("Calibration frame_index must be an integer") from exc
        if frame_index < 0:
            raise BedTrackerValidationError("Calibration frame_index must be >= 0")
        if frame_index in seen_frames:
            raise BedTrackerValidationError("Calibration frame_index values must be unique")
        seen_frames.add(frame_index)

        time_s = calibration.get("time_s")
        if time_s is not None:
            try:
                time_s = float(time_s)
            except (TypeError, ValueError) as exc:
                raise BedTrackerValidationError("Calibration time_s must be numeric") from exc
            if not math.isfinite(time_s) or time_s < 0:
                raise BedTrackerValidationError("Calibration time_s must be >= 0")

        corners = calibration.get("corners_px")
        if corners is None and idx == 0 and calibration.get("corners") is not None:
            corners = calibration.get("corners")
        validated = validate_corners(corners or [], image_size=image_size)
        normalized.append({
            "frame_index": frame_index,
            "time_s": None if time_s is None else round(float(time_s), 6),
            "corners_px": [{"name": p["name"], "x": float(p["x"]), "y": float(p["y"])} for p in validated],
        })

    normalized.sort(key=lambda item: item["frame_index"])
    return normalized


def load_corners_sidecar(path: str, expected_video_id: Optional[str] = None) -> Dict[str, Any]:
    import json

    with open(path, "r") as f:
        data = json.load(f)

    base_required = [
        "schema_version",
        "video_id",
        "exercise_type",
        "image_size",
        "corner_order",
        "bed_dimensions_m",
        "created_at",
    ]
    missing = [key for key in base_required if key not in data]
    if missing:
        raise BedTrackerValidationError(f"Corners sidecar missing required fields: {', '.join(missing)}")
    if data.get("schema_version") not in (1, 2):
        raise BedTrackerValidationError("Unsupported corners sidecar schema_version")
    if expected_video_id and data.get("video_id") != expected_video_id:
        raise BedTrackerValidationError("Corners sidecar video_id does not match the job")
    if data.get("exercise_type") != "trampoline":
        raise BedTrackerValidationError("Corners sidecar is not for trampoline analysis")
    if data.get("corner_order") != CORNER_ORDER:
        raise BedTrackerValidationError(f"Corners sidecar corner_order must be {CORNER_ORDER}")

    image_size = data.get("image_size") or {}
    width = image_size.get("width")
    height = image_size.get("height")
    if not width or not height:
        raise BedTrackerValidationError("Corners sidecar image_size must include width and height")
    size = (int(width), int(height))

    dims = data.get("bed_dimensions_m") or {}
    if not dims.get("width") or not dims.get("length"):
        raise BedTrackerValidationError("Corners sidecar bed_dimensions_m must include width and length")
    if not data.get("created_at"):
        raise BedTrackerValidationError("Corners sidecar created_at is required")

    if data.get("calibrations") is not None:
        data["calibrations"] = normalize_calibrations(data.get("calibrations") or [], image_size=size)
    else:
        legacy_required = ["frame_index", "corners_px"]
        missing = [key for key in legacy_required if key not in data]
        if missing:
            raise BedTrackerValidationError(f"Corners sidecar missing required fields: {', '.join(missing)}")
        frame_index = _coerce_frame_index(data.get("frame_index"))
        if frame_index != 0:
            raise BedTrackerValidationError("Legacy corners sidecar must describe first-frame calibration (frame_index=0)")
        data["calibrations"] = normalize_calibrations(
            [{"frame_index": frame_index, "time_s": data.get("time_s", 0.0), "corners_px": data.get("corners_px", [])}],
            image_size=size,
        )

    first = data["calibrations"][0]
    data["frame_index"] = int(first["frame_index"])
    data["corners_px"] = first["corners_px"]
    return data

def classify_landing_zone(
    bed_xy_m: Sequence[float],
    bed_size_m: Tuple[float, float] = None,
) -> str:
    """Classify a landing coordinate into center/mid/edge/off_bed."""
    width, length = bed_size_m or (cfg.BED_WIDTH_M, cfg.BED_LENGTH_M)
    x, y = float(bed_xy_m[0]), float(bed_xy_m[1])
    if x < 0 or y < 0 or x > width or y > length:
        return "off_bed"

    edge_margin = getattr(cfg, "ZONE_EDGE_MARGIN_M", 0.3)
    dist_edge = min(x, y, width - x, length - y)
    if dist_edge < edge_margin:
        return "edge"

    center = np.array([width / 2.0, length / 2.0], dtype=np.float32)
    dist_center = float(np.linalg.norm(np.array([x, y], dtype=np.float32) - center))
    if dist_center <= getattr(cfg, "ZONE_CENTER_RADIUS_M", 0.5):
        return "center"
    if dist_center <= getattr(cfg, "ZONE_MID_RADIUS_M", 1.0):
        return "mid"
    return "edge"


class BedTracker:
    """Track a calibrated trampoline bed plane and map image points to bed coordinates."""

    def __init__(
        self,
        corners_image: Sequence[Any],
        bed_size_m: Tuple[float, float] = None,
        config: Optional[Any] = None,
        image_size: Optional[Tuple[int, int]] = None,
        calibrations: Optional[Sequence[Dict[str, Any]]] = None,
    ):
        self.config = config or cfg
        self.bed_size_m = bed_size_m or (cfg.BED_WIDTH_M, cfg.BED_LENGTH_M)
        self.image_size = image_size
        normalized = validate_corners(corners_image, image_size=image_size)
        self.initial_corners = corners_to_array(normalized)
        self.current_corners = self.initial_corners.copy()
        self.H_image_to_bed: Optional[np.ndarray] = None
        self._prev_gray: Optional[np.ndarray] = None
        self._prev_pts: Optional[np.ndarray] = None
        self._frame_index: Optional[int] = None
        self._initialized = False
        self._consecutive_failures = 0
        self._tracking_state = TRACKING_LOW_CONFIDENCE
        self._orb = cv2.ORB_create(nfeatures=getattr(cfg, "BED_ORB_MAX_FEATURES", 500))
        self._keyframe_gray: Optional[np.ndarray] = None
        self._keyframe_corners: Optional[np.ndarray] = None
        self._keyframe_keypoints = None
        self._keyframe_descriptors = None
        self._last_relocalize_frame = 0
        self.manual_calibrations = self._normalize_manual_calibrations(calibrations or [{
            "frame_index": 0,
            "time_s": 0.0,
            "corners_px": normalized,
        }])
        self._next_manual_idx = 1 if len(self.manual_calibrations) > 1 else len(self.manual_calibrations)
        self.current_info = BedTrackerInfo(
            success=False,
            frame_index=None,
            corners=self.current_corners.tolist(),
            inlier_ratio=0.0,
            tracked_points=0,
            tracking_confidence=0.0,
            message="not initialized",
            tracking_state=self._tracking_state,
        ).to_dict()
        self._compute_image_to_bed()

    def _normalize_manual_calibrations(self, calibrations: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        normalized = normalize_calibrations(calibrations, image_size=self.image_size)
        if not normalized:
            raise BedTrackerValidationError("At least one calibration is required")
        return normalized

    @classmethod
    def from_sidecar(cls, sidecar: Dict[str, Any]) -> "BedTracker":
        dims = sidecar.get("bed_dimensions_m") or {}
        bed_size = (float(dims.get("width", cfg.BED_WIDTH_M)), float(dims.get("length", cfg.BED_LENGTH_M)))
        image_size_d = sidecar.get("image_size") or {}
        image_size = None
        if image_size_d.get("width") and image_size_d.get("height"):
            image_size = (int(image_size_d["width"]), int(image_size_d["height"]))
        calibrations = sidecar.get("calibrations") or [{
            "frame_index": int(sidecar.get("frame_index", 0)),
            "time_s": sidecar.get("time_s", 0.0),
            "corners_px": sidecar["corners_px"],
        }]
        earliest = min(calibrations, key=lambda item: int(item.get("frame_index", 0)))
        return cls(earliest["corners_px"], bed_size_m=bed_size, image_size=image_size, calibrations=calibrations)

    def _bed_reference_points(self) -> np.ndarray:
        width, length = self.bed_size_m
        return np.array([[0, 0], [width, 0], [width, length], [0, length]], dtype=np.float32)

    def _compute_image_to_bed(self) -> None:
        H, _ = cv2.findHomography(self.current_corners.astype(np.float32), self._bed_reference_points(), 0)
        if H is None:
            raise BedTrackerValidationError("Could not compute image-to-bed homography")
        self.H_image_to_bed = H

    def initialize(self, first_frame_bgr: np.ndarray, frame_index: int = 0) -> Dict[str, Any]:
        if first_frame_bgr is None or first_frame_bgr.size == 0:
            raise BedTrackerValidationError("Cannot initialize tracker from an empty frame")
        self.image_size = (first_frame_bgr.shape[1], first_frame_bgr.shape[0])
        validate_corners(self.current_corners.tolist(), image_size=self.image_size)
        gray = cv2.cvtColor(first_frame_bgr, cv2.COLOR_BGR2GRAY)
        self._prev_gray = gray
        self._prev_pts = self._detect_features(gray)
        self._frame_index = frame_index
        self._initialized = True
        self._consecutive_failures = 0
        tracked = 0 if self._prev_pts is None else len(self._prev_pts)
        tracking_conf = self._tracking_confidence(1.0, tracked)
        self._tracking_state = self._state_for_confidence(tracking_conf)
        self._refresh_keyframe(gray)
        marker_lines = self._detect_marker_lines(first_frame_bgr, self.current_corners)
        self.current_info = self._make_info(
            success=True,
            frame_index=frame_index,
            inlier_ratio=1.0 if tracked else 0.0,
            tracked_points=tracked,
            tracking_confidence=tracking_conf,
            message="initialized",
            diagnostics={"source": "initialization", "marker_lines": marker_lines, "manual_calibration_count": len(self.manual_calibrations)},
        )
        return self.current_info

    def _bed_mask(self, shape: Tuple[int, int], corners: Optional[np.ndarray] = None) -> np.ndarray:
        mask = np.zeros(shape, dtype=np.uint8)
        cv2.fillConvexPoly(mask, np.round(corners if corners is not None else self.current_corners).astype(np.int32), 255)
        return mask

    def _detect_features(self, gray: np.ndarray) -> Optional[np.ndarray]:
        mask = self._bed_mask(gray.shape)
        pts = cv2.goodFeaturesToTrack(
            gray,
            maxCorners=getattr(self.config, "BED_MAX_FEATURES", 200),
            qualityLevel=getattr(self.config, "BED_FEATURE_QUALITY", 0.01),
            minDistance=getattr(self.config, "BED_FEATURE_MIN_DISTANCE", 8),
            mask=mask,
        )
        if pts is None:
            return None
        return pts.reshape(-1, 1, 2).astype(np.float32)

    def _tracking_confidence(self, inlier_ratio: float, tracked_points: int) -> float:
        min_points = max(1, getattr(self.config, "BED_MIN_TRACK_POINTS", 20))
        point_score = min(1.0, tracked_points / float(min_points))
        return float(max(0.0, min(1.0, 0.65 * inlier_ratio + 0.35 * point_score)))

    def _state_for_confidence(self, confidence: float) -> str:
        if self._consecutive_failures >= getattr(cfg, "BED_TRACKING_LOST_AFTER_FAILURES", 3):
            return TRACKING_LOST
        if self._consecutive_failures > 0:
            return TRACKING_FROZEN
        if confidence >= getattr(cfg, "BED_TRUSTED_CONFIDENCE", 0.6):
            return TRACKING_TRUSTED
        if confidence >= getattr(cfg, "BED_LOW_CONFIDENCE", 0.3):
            return TRACKING_LOW_CONFIDENCE
        return TRACKING_FROZEN

    def _make_info(
        self,
        success: bool,
        frame_index: Optional[int],
        inlier_ratio: float,
        tracked_points: int,
        tracking_confidence: float,
        message: str,
        diagnostics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return BedTrackerInfo(
            success=success,
            frame_index=frame_index,
            corners=self.current_corners.tolist(),
            inlier_ratio=float(inlier_ratio),
            tracked_points=int(tracked_points),
            tracking_confidence=float(max(0.0, min(1.0, tracking_confidence))),
            message=message,
            tracking_state=self._tracking_state,
            diagnostics=diagnostics or {},
        ).to_dict()

    def validate_candidate_corners(
        self,
        candidate_corners: Sequence[Sequence[float]],
        inlier_ratio: float = 1.0,
        tracked_points: Optional[int] = None,
        source: str = "lk",
    ) -> Dict[str, Any]:
        candidate = np.asarray(candidate_corners, dtype=np.float32).reshape(-1, 2)
        diagnostics: Dict[str, Any] = {"source": source, "accepted": False, "reasons": []}
        tracked_points = tracked_points if tracked_points is not None else getattr(self.config, "BED_MIN_TRACK_POINTS", 20)

        if candidate.shape != (4, 2) or not np.all(np.isfinite(candidate)):
            diagnostics["reasons"].append("non_finite_or_wrong_shape")
            return diagnostics

        min_points = getattr(self.config, "BED_MIN_TRACK_POINTS", 20)
        if tracked_points < min_points:
            diagnostics["reasons"].append("too_few_points")
        if inlier_ratio < getattr(self.config, "BED_ACCEPT_INLIER_RATIO", 0.35):
            diagnostics["reasons"].append("low_inlier_ratio")
        if _segment_intersection(candidate[0], candidate[1], candidate[2], candidate[3]) or _segment_intersection(candidate[1], candidate[2], candidate[3], candidate[0]):
            diagnostics["reasons"].append("self_intersection")
        if not _is_convex_quad(candidate):
            diagnostics["reasons"].append("not_convex")

        current_area = max(1.0, _quad_area(self.current_corners))
        candidate_area = _quad_area(candidate)
        area_ratio = candidate_area / current_area
        diagnostics["area_ratio"] = area_ratio
        if area_ratio > getattr(self.config, "BED_MAX_AREA_RATIO_CHANGE", 1.75) or area_ratio < getattr(self.config, "BED_MIN_AREA_RATIO_CHANGE", 0.45):
            diagnostics["reasons"].append("area_jump")

        if self.image_size:
            width, height = self.image_size
            diag = math.hypot(width, height)
            center_shift = float(np.linalg.norm(_quad_center(candidate) - _quad_center(self.current_corners)))
            max_shift_ratio = getattr(self.config, "BED_ORB_MAX_CENTER_SHIFT_RATIO", 0.65) if source == "orb" else getattr(self.config, "BED_MAX_CENTER_SHIFT_RATIO", 0.25)
            diagnostics["center_shift_ratio"] = center_shift / max(1.0, diag)
            if center_shift > diag * max_shift_ratio:
                diagnostics["reasons"].append("center_shift")

            margin = getattr(self.config, "BED_BOUNDS_MARGIN_RATIO", 0.2)
            min_x, min_y = -width * margin, -height * margin
            max_x, max_y = width * (1.0 + margin), height * (1.0 + margin)
            if np.any(candidate[:, 0] < min_x) or np.any(candidate[:, 0] > max_x) or np.any(candidate[:, 1] < min_y) or np.any(candidate[:, 1] > max_y):
                diagnostics["reasons"].append("out_of_bounds")

        current_edges = np.maximum(_edge_lengths(self.current_corners), 1.0)
        candidate_edges = _edge_lengths(candidate)
        edge_ratios = candidate_edges / current_edges
        diagnostics["edge_scale_min"] = float(np.min(edge_ratios))
        diagnostics["edge_scale_max"] = float(np.max(edge_ratios))
        if np.any(edge_ratios > getattr(self.config, "BED_MAX_EDGE_SCALE_CHANGE", 2.5)) or np.any(edge_ratios < getattr(self.config, "BED_MIN_EDGE_SCALE_CHANGE", 0.35)):
            diagnostics["reasons"].append("edge_scale_jump")

        H, _ = cv2.findHomography(candidate.astype(np.float32), self._bed_reference_points(), 0)
        if H is None or not np.all(np.isfinite(H)):
            diagnostics["reasons"].append("bad_homography")

        diagnostics["accepted"] = not diagnostics["reasons"]
        return diagnostics

    def _detect_marker_lines(self, frame_bgr: np.ndarray, corners: Optional[np.ndarray] = None) -> List[Dict[str, Any]]:
        if frame_bgr is None or frame_bgr.size == 0:
            return []
        quad = np.asarray(corners if corners is not None else self.current_corners, dtype=np.float32).reshape(-1, 2)
        if quad.shape != (4, 2) or not np.all(np.isfinite(quad)):
            return []
        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        mask = self._bed_mask(gray.shape, quad)
        masked = cv2.bitwise_and(gray, gray, mask=mask)
        edges = cv2.Canny(masked, 60, 160)
        lines = cv2.HoughLinesP(
            edges,
            1,
            np.pi / 180.0,
            threshold=30,
            minLineLength=getattr(self.config, "BED_MARKER_LINE_MIN_LENGTH_PX", 24),
            maxLineGap=8,
        )
        if lines is None:
            return []
        segments: List[Dict[str, Any]] = []
        max_segments = getattr(self.config, "BED_MARKER_LINE_MAX_SEGMENTS", 8)
        for raw in lines[:max_segments]:
            x1, y1, x2, y2 = [int(v) for v in raw[0]]
            midpoint = ((x1 + x2) / 2.0, (y1 + y2) / 2.0)
            if cv2.pointPolygonTest(quad.astype(np.float32), midpoint, False) < 0:
                continue
            length = float(math.hypot(x2 - x1, y2 - y1))
            segments.append({
                "p1": [x1, y1],
                "p2": [x2, y2],
                "length_px": round(length, 2),
                "score": round(length / max(1.0, min(frame_bgr.shape[0], frame_bgr.shape[1])), 3),
            })
        return segments

    def _accept_candidate(
        self,
        candidate_corners: np.ndarray,
        gray: np.ndarray,
        frame_index: int,
        inlier_ratio: float,
        tracked_points: int,
        source: str,
        extra_diagnostics: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        self.current_corners = candidate_corners.astype(np.float32)
        self._compute_image_to_bed()
        self._consecutive_failures = 0
        tracking_conf = self._tracking_confidence(inlier_ratio, tracked_points)
        self._tracking_state = self._state_for_confidence(tracking_conf)
        if self._tracking_state == TRACKING_TRUSTED or source == "orb":
            self._refresh_keyframe(gray)
        diagnostics = {"source": source, "accepted": True}
        if extra_diagnostics:
            diagnostics.update(extra_diagnostics)
        self.current_info = self._make_info(
            success=True,
            frame_index=frame_index,
            inlier_ratio=inlier_ratio,
            tracked_points=tracked_points,
            tracking_confidence=tracking_conf,
            message="tracked" if source == "lk" else "relocalized",
            diagnostics=diagnostics,
        )
        return self.current_info

    def _reject_candidate(
        self,
        gray: np.ndarray,
        frame_index: int,
        inlier_ratio: float,
        tracked_points: int,
        diagnostics: Optional[Dict[str, Any]],
        message: str = "tracking degraded; frozen on last trusted homography",
    ) -> Dict[str, Any]:
        self._consecutive_failures += 1
        tracking_conf = self._tracking_confidence(max(0.0, inlier_ratio * 0.35), tracked_points)
        tracking_conf *= 0.5
        self._tracking_state = self._state_for_confidence(tracking_conf)
        self.current_info = self._make_info(
            success=False,
            frame_index=frame_index,
            inlier_ratio=inlier_ratio,
            tracked_points=tracked_points,
            tracking_confidence=tracking_conf,
            message=message,
            diagnostics=diagnostics or {"accepted": False},
        )
        return self.current_info

    def _refresh_keyframe(self, gray: np.ndarray) -> None:
        mask = self._bed_mask(gray.shape)
        keypoints, descriptors = self._orb.detectAndCompute(gray, mask)
        if descriptors is None or not keypoints:
            return
        self._keyframe_gray = gray.copy()
        self._keyframe_corners = self.current_corners.copy()
        self._keyframe_keypoints = keypoints
        self._keyframe_descriptors = descriptors

    def _try_relocalize(self, gray: np.ndarray, frame_index: int) -> Optional[Dict[str, Any]]:
        if self._keyframe_descriptors is None or self._keyframe_keypoints is None or self._keyframe_corners is None:
            return self._reject_candidate(
                gray,
                frame_index,
                0.0,
                0,
                {"source": "orb", "accepted": False, "reasons": ["no_keyframe"]},
                message="tracking lost; no ORB keyframe available",
            )
        keypoints, descriptors = self._orb.detectAndCompute(gray, None)
        if descriptors is None or not keypoints:
            return self._reject_candidate(
                gray,
                frame_index,
                0.0,
                0,
                {"source": "orb", "accepted": False, "reasons": ["no_descriptors"]},
                message="tracking lost; ORB relocalization found no descriptors",
            )
        matcher = cv2.BFMatcher(cv2.NORM_HAMMING, crossCheck=True)
        matches = sorted(matcher.match(self._keyframe_descriptors, descriptors), key=lambda m: m.distance)
        min_matches = getattr(self.config, "BED_ORB_MIN_MATCHES", 8)
        if len(matches) < min_matches:
            return self._reject_candidate(
                gray,
                frame_index,
                0.0,
                len(matches),
                {"source": "orb", "accepted": False, "reasons": ["too_few_orb_matches"], "matches": len(matches)},
                message="tracking lost; ORB relocalization had too few matches",
            )
        good = matches[: min(len(matches), max(min_matches, 60))]
        src = np.float32([self._keyframe_keypoints[m.queryIdx].pt for m in good])
        dst = np.float32([keypoints[m.trainIdx].pt for m in good])
        H, inliers = cv2.findHomography(src, dst, cv2.RANSAC, getattr(self.config, "BED_RANSAC_REPROJ_THRESH", 3.0))
        if H is None or inliers is None:
            return self._reject_candidate(
                gray,
                frame_index,
                0.0,
                len(good),
                {"source": "orb", "accepted": False, "reasons": ["homography_failed"], "matches": len(good)},
                message="tracking lost; ORB relocalization homography failed",
            )
        inlier_ratio = float(inliers.sum()) / max(1, len(good))
        candidate = cv2.perspectiveTransform(self._keyframe_corners.reshape(-1, 1, 2), H).reshape(-1, 2)
        diagnostics = self.validate_candidate_corners(candidate, inlier_ratio, int(inliers.sum()), source="orb")
        diagnostics["matches"] = len(good)
        if diagnostics["accepted"]:
            self._last_relocalize_frame = frame_index
            return self._accept_candidate(candidate, gray, frame_index, inlier_ratio, int(inliers.sum()), source="orb")
        return self._reject_candidate(
            gray,
            frame_index,
            inlier_ratio,
            int(inliers.sum()),
            diagnostics,
            message="tracking lost; ORB relocalization rejected by sanity gate",
        )

    def _relocalize_due(self, frame_index: int, failed_lk: bool) -> bool:
        if failed_lk and getattr(self.config, "BED_ORB_RELOCALIZE_ON_FAILURE", True):
            return True
        interval = getattr(self.config, "BED_ORB_RELOCALIZE_INTERVAL", 30)
        return interval > 0 and frame_index - self._last_relocalize_frame >= interval

    def _manual_anchor_due(self, frame_index: int) -> Optional[Dict[str, Any]]:
        if self._next_manual_idx >= len(self.manual_calibrations):
            return None
        anchor = self.manual_calibrations[self._next_manual_idx]
        transition_frames = max(1, int(getattr(self.config, "BED_KEYFRAME_TRANSITION_FRAMES", 20)))
        start_frame = max(0, int(anchor["frame_index"]) - transition_frames)
        if frame_index < start_frame:
            return None
        return anchor

    def _apply_manual_anchor(self, frame_bgr: np.ndarray, gray: np.ndarray, frame_index: int, anchor: Dict[str, Any]) -> Dict[str, Any]:
        anchor_corners = corners_to_array(anchor["corners_px"])
        anchor_frame = int(anchor["frame_index"])
        transition_frames = max(1, int(getattr(self.config, "BED_KEYFRAME_TRANSITION_FRAMES", 20)))
        start_frame = max(0, anchor_frame - transition_frames)
        if frame_index >= anchor_frame:
            candidate = anchor_corners.copy()
            transition_progress = 1.0
            snap_direct = False
            reasons = []
        else:
            start_corners = self.current_corners.copy()
            progress = float(frame_index - start_frame + 1) / float(max(1, anchor_frame - start_frame + 1))
            progress = max(0.0, min(1.0, progress))
            candidate = start_corners + (anchor_corners - start_corners) * progress
            transition_progress = progress
            diagnostics = self.validate_candidate_corners(candidate, inlier_ratio=1.0, tracked_points=max(getattr(self.config, "BED_MIN_TRACK_POINTS", 20), 20), source="manual_transition")
            if diagnostics["accepted"]:
                snap_direct = False
                reasons = []
            else:
                candidate = anchor_corners.copy()
                snap_direct = True
                reasons = diagnostics.get("reasons", [])
        self.current_corners = candidate.astype(np.float32)
        self._compute_image_to_bed()
        self._consecutive_failures = 0
        tracked_points = 0 if self._prev_pts is None else len(self._prev_pts)
        tracking_conf = max(0.75, self._tracking_confidence(1.0, tracked_points))
        self._tracking_state = TRACKING_TRUSTED
        self._refresh_keyframe(gray)
        self._prev_pts = self._detect_features(gray)
        marker_lines = self._detect_marker_lines(frame_bgr, self.current_corners)
        if frame_index >= anchor_frame:
            self._next_manual_idx += 1
        self.current_info = self._make_info(
            success=True,
            frame_index=frame_index,
            inlier_ratio=1.0,
            tracked_points=tracked_points,
            tracking_confidence=tracking_conf,
            message="manual anchor applied",
            diagnostics={
                "source": "manual_keyframe",
                "accepted": True,
                "manual_anchor": {
                    "frame_index": anchor_frame,
                    "time_s": anchor.get("time_s"),
                },
                "transition_progress": round(transition_progress, 3),
                "snap_direct": snap_direct,
                "reasons": reasons,
                "marker_lines": marker_lines,
            },
        )
        return self.current_info

    def update(self, frame_bgr: np.ndarray, frame_index: Optional[int] = None) -> Dict[str, Any]:
        if not self._initialized:
            return self.initialize(frame_bgr, frame_index or 0)

        gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
        frame_index = frame_index if frame_index is not None else ((self._frame_index or -1) + 1)
        self._frame_index = frame_index

        manual_anchor = self._manual_anchor_due(frame_index)
        if manual_anchor is not None:
            info = self._apply_manual_anchor(frame_bgr, gray, frame_index, manual_anchor)
            self._prev_gray = gray
            return info

        success = False
        relocalization_attempted = False
        inlier_ratio = 0.0
        tracked_points = 0
        diagnostics: Dict[str, Any] = {"source": "lk", "accepted": False, "reasons": ["no_candidate"]}

        if self._prev_gray is not None and self._prev_pts is not None and len(self._prev_pts) >= 4:
            curr_pts, status, _ = cv2.calcOpticalFlowPyrLK(
                self._prev_gray,
                gray,
                self._prev_pts,
                None,
                winSize=getattr(self.config, "BED_LK_WIN_SIZE", (15, 15)),
                maxLevel=getattr(self.config, "BED_LK_MAX_LEVEL", 3),
                criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
            )
            if curr_pts is not None and status is not None:
                back_pts, _, _ = cv2.calcOpticalFlowPyrLK(
                    gray,
                    self._prev_gray,
                    curr_pts,
                    None,
                    winSize=getattr(self.config, "BED_LK_WIN_SIZE", (15, 15)),
                    maxLevel=getattr(self.config, "BED_LK_MAX_LEVEL", 3),
                    criteria=(cv2.TERM_CRITERIA_EPS | cv2.TERM_CRITERIA_COUNT, 20, 0.03),
                )
                fb = np.linalg.norm(self._prev_pts.reshape(-1, 2) - back_pts.reshape(-1, 2), axis=1) if back_pts is not None else np.full(len(status), np.inf)
                valid = (status.reshape(-1) == 1) & (fb < getattr(self.config, "BED_FB_THRESHOLD", 1.0))
                prev_good = self._prev_pts.reshape(-1, 2)[valid]
                curr_good = curr_pts.reshape(-1, 2)[valid]
                tracked_points = int(len(curr_good))
                if tracked_points >= 4:
                    H_delta, inliers = cv2.findHomography(
                        prev_good,
                        curr_good,
                        cv2.RANSAC,
                        getattr(self.config, "BED_RANSAC_REPROJ_THRESH", 3.0),
                    )
                    if H_delta is not None and inliers is not None:
                        inlier_count = int(inliers.sum())
                        inlier_ratio = inlier_count / max(1, tracked_points)
                        candidate = cv2.perspectiveTransform(
                            self.current_corners.reshape(-1, 1, 2), H_delta
                        ).reshape(-1, 2)
                        diagnostics = self.validate_candidate_corners(candidate, inlier_ratio, inlier_count, source="lk")
                        if diagnostics["accepted"]:
                            self._prev_pts = curr_good.reshape(-1, 1, 2).astype(np.float32)
                            marker_lines = self._detect_marker_lines(frame_bgr, candidate)
                            info = self._accept_candidate(
                                candidate,
                                gray,
                                frame_index,
                                inlier_ratio,
                                inlier_count,
                                source="lk",
                                extra_diagnostics={"marker_lines": marker_lines},
                            )
                            success = True
                        else:
                            tracked_points = max(tracked_points, inlier_count)

        if not success and self._relocalize_due(frame_index, failed_lk=True):
            relocalization_attempted = True
            info = self._try_relocalize(gray, frame_index)
            if info and info.get("success"):
                marker_lines = self._detect_marker_lines(frame_bgr, self.current_corners)
                info.setdefault("diagnostics", {})["marker_lines"] = marker_lines
                success = True

        if not success and not relocalization_attempted:
            diagnostics["marker_lines"] = self._detect_marker_lines(frame_bgr, self.current_corners)
            info = self._reject_candidate(gray, frame_index, inlier_ratio, tracked_points, diagnostics)

        redetect_due = (
            not success
            or tracked_points < getattr(self.config, "BED_MIN_TRACK_POINTS", 20)
            or (frame_index % getattr(self.config, "BED_REDETECT_INTERVAL", 30) == 0)
            or inlier_ratio < getattr(self.config, "BED_REDETECT_INLIER_RATIO", 0.5)
        )
        if redetect_due:
            pts = self._detect_features(gray)
            if pts is not None:
                self._prev_pts = pts
        self._prev_gray = gray
        return info

    def image_to_bed(self, pt_xy: Sequence[float]) -> Tuple[float, float]:
        if self.H_image_to_bed is None:
            raise BedTrackerValidationError("Tracker is not initialized")
        pt = np.array([[[float(pt_xy[0]), float(pt_xy[1])]]], dtype=np.float32)
        mapped = cv2.perspectiveTransform(pt, self.H_image_to_bed)[0, 0]
        return float(mapped[0]), float(mapped[1])

    def is_inside_bed(self, pt_xy: Sequence[float]) -> bool:
        x, y = self.image_to_bed(pt_xy)
        width, length = self.bed_size_m
        return 0 <= x <= width and 0 <= y <= length

    def landing_payload(self, pt_xy: Sequence[float], ankle_visibility: float = 1.0) -> Dict[str, Any]:
        bed_xy = self.image_to_bed(pt_xy)
        width, length = self.bed_size_m
        norm = [bed_xy[0] / width if width else 0.0, bed_xy[1] / length if length else 0.0]
        zone = classify_landing_zone(bed_xy, self.bed_size_m)
        center = np.array([width / 2.0, length / 2.0], dtype=np.float32)
        dist_center = float(np.linalg.norm(np.array(bed_xy, dtype=np.float32) - center))
        tracking = float(self.current_info.get("tracking_confidence", 0.0))
        ankle = max(0.0, min(1.0, float(ankle_visibility)))
        bounds = self._bounds_confidence(norm)
        confidence = max(0.0, min(1.0, 0.5 * tracking + 0.3 * ankle + 0.2 * bounds))
        return {
            "bed_xy_m": [round(float(bed_xy[0]), 3), round(float(bed_xy[1]), 3)],
            "norm_xy": [round(float(norm[0]), 4), round(float(norm[1]), 4)],
            "zone": zone,
            "dist_from_center_m": round(dist_center, 3),
            "confidence": round(confidence, 3),
            "confidence_factors": {
                "tracking": round(tracking, 3),
                "ankle_visibility": round(ankle, 3),
                "bounds": round(bounds, 3),
            },
        }

    def _bounds_confidence(self, norm_xy: Sequence[float]) -> float:
        nx, ny = float(norm_xy[0]), float(norm_xy[1])
        if 0.0 <= nx <= 1.0 and 0.0 <= ny <= 1.0:
            return 1.0
        overflow = max(-nx, nx - 1.0, -ny, ny - 1.0, 0.0)
        return float(max(0.0, 1.0 - overflow / max(0.001, getattr(cfg, "BED_OFF_BED_CONFIDENCE_DECAY", 0.25))))

    def draw_debug_overlay(self, frame: np.ndarray) -> np.ndarray:
        pts = np.round(self.current_corners).astype(np.int32)
        cv2.polylines(frame, [pts], isClosed=True, color=(0, 220, 80), thickness=2)
        return frame
