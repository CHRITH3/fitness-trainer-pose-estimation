"""
Trampoline-specific video overlay drawing.
Replaces draw_stats_overlay() when in trampoline mode.
All sizes scale proportionally to video dimensions.
"""

import math
import cv2
import numpy as np
from trampoline.config import LANDMARK


# Action colors (BGR)
ACTION_COLORS = {
    "Straight": (0, 230, 118),     # green
    "Pike":     (255, 180, 0),     # blue-ish
    "Tuck":     (0, 200, 255),     # orange-ish
    "Straddle": (255, 100, 255),   # magenta
    "Unknown":  (140, 140, 140),   # gray
}

PHASE_COLORS = {
    "flight":  (0, 230, 118),   # green
    "contact": (0, 165, 255),   # orange
    "unknown": (140, 140, 140), # gray
}

# Reference resolution for scaling (720p)
_REF_W = 640


def draw_trampoline_overlay(frame, stats, bed_info=None):
    """
    Draw trampoline analysis overlay on video frame.
    All dimensions scale with video resolution.
    """
    h, w = frame.shape[:2]
    ref = min(w, h)

    def sx(v):
        return max(1, int(v * ref / _REF_W))

    def font_scale(v):
        return v * ref / _REF_W

    margin = sx(15)
    box_w = sx(340)
    box_h = sx(170)
    padding = sx(14)
    accent_w = sx(5)

    # Semi-transparent background box
    overlay = frame.copy()
    cv2.rectangle(overlay, (margin, margin), (margin + box_w, margin + box_h),
                  (30, 30, 30), -1)
    cv2.rectangle(overlay, (margin, margin), (margin + accent_w, margin + box_h),
                  (0, 200, 100), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_bold = cv2.FONT_HERSHEY_DUPLEX
    x = margin + padding + sx(8)
    y_base = margin + sx(35)
    thickness_sm = max(1, sx(1))
    thickness_lg = max(1, sx(2))

    # --- JUMPS count ---
    jump_count = stats.get("jump_count", stats.get("reps", 0))
    cv2.putText(frame, "JUMPS", (x, y_base - sx(8)),
                font, font_scale(0.5), (150, 150, 150), thickness_sm, cv2.LINE_AA)
    cv2.putText(frame, str(jump_count), (x, y_base + sx(28)),
                font_bold, font_scale(1.4), (255, 255, 255), thickness_lg, cv2.LINE_AA)

    # --- PHASE indicator ---
    phase = stats.get("phase", "unknown")
    phase_x = x + sx(90)
    phase_color = PHASE_COLORS.get(phase, PHASE_COLORS["unknown"])
    cv2.putText(frame, "PHASE", (phase_x, y_base - sx(8)),
                font, font_scale(0.5), (150, 150, 150), thickness_sm, cv2.LINE_AA)
    cv2.circle(frame, (phase_x + sx(8), y_base + sx(15)), sx(6), phase_color, -1)
    cv2.putText(frame, phase.upper(), (phase_x + sx(22), y_base + sx(20)),
                font, font_scale(0.6), phase_color, thickness_lg, cv2.LINE_AA)

    # --- ACTION name ---
    action = stats.get("current_action", "Unknown")
    action_y = y_base + sx(65)
    action_color = ACTION_COLORS.get(action, ACTION_COLORS["Unknown"])
    cv2.putText(frame, "ACTION", (x, action_y - sx(8)),
                font, font_scale(0.5), (150, 150, 150), thickness_sm, cv2.LINE_AA)
    cv2.putText(frame, action.upper(), (x, action_y + sx(28)),
                font_bold, font_scale(1.2), action_color, thickness_lg, cv2.LINE_AA)

    # --- Velocity bar ---
    velocity = stats.get("velocity", 0)
    _draw_velocity_bar(frame, velocity, w, h, ref)

    # --- Optional bed tracking overlay ---
    if bed_info:
        draw_bed_quad(
            frame,
            bed_info.get("corners"),
            bed_info.get("tracking_confidence"),
            bed_info.get("tracking_state"),
            bed_info.get("message"),
        )
        marker_lines = (bed_info.get("diagnostics") or {}).get("marker_lines")
        draw_marker_lines(frame, marker_lines)
    latest_landing = stats.get("latest_landing")
    if latest_landing:
        draw_landing_marker(frame, latest_landing.get("ankle_px"), latest_landing, latest_landing.get("zone"))
    landings = stats.get("landings") or []
    if landings:
        draw_bed_minimap(frame, landings)

    return frame


def bed_quad_style(confidence=None, tracking_state=None):
    """Return BGR color and label prefix for bed-tracking trust state."""
    state = tracking_state or "trusted"
    conf = 1.0 if confidence is None else float(confidence)
    if state == "tracking_lost":
        return (0, 0, 255), "Bed lost"
    if state == "frozen":
        return (160, 160, 160), "Bed frozen"
    if state == "low_confidence" or conf < 0.6:
        return (0, 190, 255), "Bed low"
    return (0, 230, 118), "Bed"


def draw_bed_quad(frame, corners, confidence=None, tracking_state=None, message=None):
    """Draw the tracked trampoline bed quadrilateral with trust-state styling."""
    if not corners or len(corners) != 4:
        return frame
    quad = np.array(corners, dtype=np.float32).reshape(-1, 2)
    if not np.all(np.isfinite(quad)):
        return frame
    quad_i = np.round(quad).astype(np.int32)
    color, label_prefix = bed_quad_style(confidence, tracking_state)
    overlay = frame.copy()
    cv2.fillConvexPoly(overlay, quad_i, color)
    cv2.addWeighted(overlay, 0.12, frame, 0.88, 0, frame)
    cv2.polylines(frame, [quad_i], isClosed=True, color=color, thickness=2, lineType=cv2.LINE_AA)
    label = label_prefix
    if confidence is not None:
        label = f"{label} {float(confidence):.2f}"
    if message and tracking_state in {"frozen", "tracking_lost"}:
        label = f"{label} ({tracking_state})"
    x, y = int(quad_i[0][0]), int(quad_i[0][1])
    cv2.putText(frame, label, (x, max(15, y - 8)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return frame


def draw_marker_lines(frame, marker_lines):
    """Draw best-effort trampoline marker-line detections."""
    if not marker_lines:
        return frame
    for idx, line in enumerate(marker_lines[:8]):
        try:
            p1 = tuple(int(round(v)) for v in line.get("p1", [])[:2])
            p2 = tuple(int(round(v)) for v in line.get("p2", [])[:2])
        except (TypeError, ValueError):
            continue
        if len(p1) != 2 or len(p2) != 2:
            continue
        color = (255, 255, 0) if idx % 2 == 0 else (255, 0, 255)
        cv2.line(frame, p1, p2, color, 3, cv2.LINE_AA)
    return frame


def draw_landing_marker(frame, ankle_px, landing, zone=None):
    """Draw a cross marker at the ankle pixel for the latest landing."""
    if not ankle_px or len(ankle_px) < 2:
        return frame
    try:
        x, y = int(round(float(ankle_px[0]))), int(round(float(ankle_px[1])))
    except (TypeError, ValueError):
        return frame
    conf = landing.get("confidence") if isinstance(landing, dict) else None
    color = (0, 230, 118) if conf is None or conf >= 0.6 else (0, 190, 255) if conf >= 0.35 else (0, 0, 255)
    size = 10
    cv2.line(frame, (x - size, y), (x + size, y), color, 2, cv2.LINE_AA)
    cv2.line(frame, (x, y - size), (x, y + size), color, 2, cv2.LINE_AA)
    label = zone or (landing.get("zone") if isinstance(landing, dict) else "landing")
    if conf is not None:
        label = f"{label} {float(conf):.2f}"
    cv2.putText(frame, label, (x + 12, y - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1, cv2.LINE_AA)
    return frame


def draw_bed_minimap(frame, landings):
    """Draw an adaptive top-down landing map in the lower-right corner."""
    if not landings:
        return frame
    h, w = frame.shape[:2]
    ref = min(w, h)

    def scaled(value, lo=1, hi=None):
        out = max(lo, int(round(value * ref / _REF_W)))
        return min(out, hi) if hi is not None else out

    box_w = min(max(scaled(170, 130), 150), int(w * 0.32))
    box_h = min(max(scaled(96, 74), 85), int(h * 0.24))
    margin = scaled(15, 8, 36)
    x0 = max(0, w - box_w - margin)
    y0 = max(0, h - box_h - margin)
    overlay = frame.copy()
    cv2.rectangle(overlay, (x0, y0), (x0 + box_w, y0 + box_h), (25, 25, 25), -1)
    cv2.addWeighted(overlay, 0.75, frame, 0.25, 0, frame)
    pad = min(scaled(12, 8, 28), max(4, box_h // 4))
    rect = (x0 + pad, y0 + pad, max(1, box_w - 2 * pad), max(1, box_h - 2 * pad - scaled(10, 6, 18)))
    thickness = scaled(1, 1, 4)
    cv2.rectangle(frame, (rect[0], rect[1]), (rect[0] + rect[2], rect[1] + rect[3]), (180, 180, 180), thickness)
    cv2.line(frame, (rect[0] + rect[2] // 2, rect[1]), (rect[0] + rect[2] // 2, rect[1] + rect[3]), (90, 90, 90), thickness)
    cv2.line(frame, (rect[0], rect[1] + rect[3] // 2), (rect[0] + rect[2], rect[1] + rect[3] // 2), (90, 90, 90), thickness)
    radius = scaled(3, 3, 8)
    for landing in landings[-20:]:
        norm = landing.get("norm_xy") if isinstance(landing, dict) else None
        if not norm or len(norm) < 2:
            continue
        nx = max(0.0, min(1.0, float(norm[0])))
        ny = max(0.0, min(1.0, float(norm[1])))
        px = int(rect[0] + nx * rect[2])
        py = int(rect[1] + ny * rect[3])
        conf = float(landing.get("confidence", 1.0))
        color = (0, 230, 118) if conf >= 0.6 else (0, 190, 255) if conf >= 0.35 else (0, 0, 255)
        cv2.circle(frame, (px, py), radius, color, -1, cv2.LINE_AA)
    cv2.putText(frame, "Landings", (x0 + pad, min(h - 3, y0 + box_h - scaled(5, 3, 10))), cv2.FONT_HERSHEY_SIMPLEX, max(0.35, min(0.75, 0.35 * ref / _REF_W)), (210, 210, 210), thickness, cv2.LINE_AA)
    return frame

def draw_angle_arcs(frame, landmarks):
    """
    Draw angle arcs at hip (trunk-thigh) and knee (thigh-shin) joints
    directly on the skeleton, with angle value labels.

    Args:
        frame: BGR numpy array
        landmarks: MediaPipe pose landmarks object (with .landmark list)
    """
    h, w = frame.shape[:2]
    ref = min(w, h)
    arc_radius = max(15, int(30 * ref / _REF_W))
    font_sc = max(0.3, 0.45 * ref / _REF_W)
    thickness = max(1, int(2 * ref / _REF_W))

    lm = landmarks.landmark

    def get_px(idx):
        return (int(lm[idx].x * w), int(lm[idx].y * h))

    def is_vis(idx):
        return lm[idx].visibility > 0.4

    # Joints to annotate: (label_prefix, point_a_idx, vertex_idx, point_c_idx)
    joints = [
        # Trunk-thigh at hip
        ("left_hip",  LANDMARK["left_shoulder"],  LANDMARK["left_hip"],   LANDMARK["left_knee"]),
        ("right_hip", LANDMARK["right_shoulder"], LANDMARK["right_hip"],  LANDMARK["right_knee"]),
        # Thigh-shin at knee
        ("left_knee",  LANDMARK["left_hip"],  LANDMARK["left_knee"],  LANDMARK["left_ankle"]),
        ("right_knee", LANDMARK["right_hip"], LANDMARK["right_knee"], LANDMARK["right_ankle"]),
    ]

    for _, a_idx, v_idx, c_idx in joints:
        if not (is_vis(a_idx) and is_vis(v_idx) and is_vis(c_idx)):
            continue

        pa = get_px(a_idx)
        pv = get_px(v_idx)
        pc = get_px(c_idx)

        # Compute angle at vertex
        va = [pa[0] - pv[0], pa[1] - pv[1]]
        vc = [pc[0] - pv[0], pc[1] - pv[1]]
        dot = va[0] * vc[0] + va[1] * vc[1]
        mag_a = math.sqrt(va[0]**2 + va[1]**2)
        mag_c = math.sqrt(vc[0]**2 + vc[1]**2)
        if mag_a * mag_c == 0:
            continue
        cos_val = max(-1.0, min(1.0, dot / (mag_a * mag_c)))
        angle_deg = math.degrees(math.acos(cos_val))

        # Compute arc start/end angles for cv2.ellipse (0=right, counter-clockwise)
        angle_a = math.degrees(math.atan2(-va[1], va[0]))  # negative y because image coords
        angle_c = math.degrees(math.atan2(-vc[1], vc[0]))

        # Ensure we draw the smaller arc
        start = angle_a
        end = angle_c
        diff = (end - start) % 360
        if diff > 180:
            start, end = end, start

        # Color based on angle
        if angle_deg > 135:
            color = (0, 200, 100)    # green
        elif angle_deg > 90:
            color = (0, 180, 255)    # orange
        else:
            color = (60, 76, 231)    # red

        # Draw arc
        cv2.ellipse(frame, pv, (arc_radius, arc_radius), 0, -start, -end,
                     color, thickness, cv2.LINE_AA)

        # Place angle text at midpoint of arc
        mid_angle_rad = math.radians((start + end) / 2)
        text_r = arc_radius + max(8, int(12 * ref / _REF_W))
        text_x = int(pv[0] + text_r * math.cos(mid_angle_rad))
        text_y = int(pv[1] - text_r * math.sin(mid_angle_rad))
        cv2.putText(frame, f"{angle_deg:.0f}", (text_x, text_y),
                    cv2.FONT_HERSHEY_SIMPLEX, font_sc, color, thickness, cv2.LINE_AA)


def _draw_velocity_bar(frame, velocity, w, h, ref):
    """Draw a vertical velocity indicator bar on the right edge."""
    def sx(v):
        return max(1, int(v * ref / _REF_W))

    bar_w = sx(12)
    bar_h = sx(120)
    bar_margin = sx(15)
    bar_x = w - bar_w - bar_margin
    bar_y_center = sx(80)

    overlay = frame.copy()
    cv2.rectangle(overlay,
                  (bar_x, bar_y_center - bar_h // 2),
                  (bar_x + bar_w, bar_y_center + bar_h // 2),
                  (50, 50, 50), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    cv2.line(frame,
             (bar_x, bar_y_center),
             (bar_x + bar_w, bar_y_center),
             (200, 200, 200), max(1, sx(1)))

    max_vel = 0.5  # time-normalized velocity range
    fill_ratio = max(-1.0, min(1.0, velocity / max_vel))
    fill_pixels = int(fill_ratio * (bar_h // 2))

    if fill_pixels > 0:
        cv2.rectangle(frame,
                      (bar_x + 1, bar_y_center),
                      (bar_x + bar_w - 1, bar_y_center + fill_pixels),
                      (60, 76, 231), -1)
    elif fill_pixels < 0:
        cv2.rectangle(frame,
                      (bar_x + 1, bar_y_center + fill_pixels),
                      (bar_x + bar_w - 1, bar_y_center),
                      (0, 230, 118), -1)
