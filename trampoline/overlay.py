"""
Trampoline-specific video overlay drawing.
Replaces draw_stats_overlay() when in trampoline mode.
All sizes scale proportionally to video dimensions.
"""

import math
import cv2
from trampoline.config import LANDMARK


# Action colors (BGR)
ACTION_COLORS = {
    "Straight": (0, 230, 118),     # green
    "Pike":     (255, 180, 0),     # blue-ish
    "Tuck":     (0, 200, 255),     # orange-ish
    "Unknown":  (140, 140, 140),   # gray
}

PHASE_COLORS = {
    "flight":  (0, 230, 118),   # green
    "contact": (0, 165, 255),   # orange
    "unknown": (140, 140, 140), # gray
}

# Reference resolution for scaling (720p)
_REF_W = 640


def draw_trampoline_overlay(frame, stats):
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
