"""
Trampoline-specific video overlay drawing.
Replaces draw_stats_overlay() when in trampoline mode.
All sizes scale proportionally to video dimensions.
"""

import cv2


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
_REF_H = 480


def _scale(value, frame_dim, ref_dim=_REF_W):
    """Scale a pixel value proportionally to frame size."""
    return max(1, int(value * frame_dim / ref_dim))


def draw_trampoline_overlay(frame, stats):
    """
    Draw trampoline analysis overlay on video frame.
    All dimensions scale with video resolution.
    """
    h, w = frame.shape[:2]
    # Use the shorter edge as scaling reference for consistent appearance
    ref = min(w, h)

    # Scaling helpers
    def sx(v):
        return max(1, int(v * ref / _REF_W))

    def font_scale(v):
        return v * ref / _REF_W

    margin = sx(15)
    box_w = sx(340)
    box_h = sx(200)
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

    # --- JUMPS count (large) ---
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

    # --- ACTION name (large, color-coded) ---
    action = stats.get("current_action", "Unknown")
    action_y = y_base + sx(65)
    action_color = ACTION_COLORS.get(action, ACTION_COLORS["Unknown"])
    cv2.putText(frame, "ACTION", (x, action_y - sx(8)),
                font, font_scale(0.5), (150, 150, 150), thickness_sm, cv2.LINE_AA)
    cv2.putText(frame, action.upper(), (x, action_y + sx(28)),
                font_bold, font_scale(1.2), action_color, thickness_lg, cv2.LINE_AA)

    # --- Angle debug info (small) ---
    angle_y = action_y + sx(55)
    trunk_thigh = stats.get("trunk_thigh_angle", 0)
    thigh_shin = stats.get("thigh_shin_angle", 0)
    if trunk_thigh > 0:
        cv2.putText(frame, f"T-T: {trunk_thigh:.0f}deg  T-S: {thigh_shin:.0f}deg",
                    (x, angle_y), font, font_scale(0.4), (180, 180, 180), thickness_sm, cv2.LINE_AA)

    # --- Velocity bar on right edge ---
    velocity = stats.get("velocity", 0)
    _draw_velocity_bar(frame, velocity, w, h, ref)

    return frame


def _draw_velocity_bar(frame, velocity, w, h, ref):
    """Draw a vertical velocity indicator bar on the right edge, scaled to resolution."""
    def sx(v):
        return max(1, int(v * ref / _REF_W))

    bar_w = sx(12)
    bar_h = sx(120)
    bar_margin = sx(15)
    bar_x = w - bar_w - bar_margin
    bar_y_center = sx(80)

    # Background
    overlay = frame.copy()
    cv2.rectangle(overlay,
                  (bar_x, bar_y_center - bar_h // 2),
                  (bar_x + bar_w, bar_y_center + bar_h // 2),
                  (50, 50, 50), -1)
    cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)

    # Center line
    cv2.line(frame,
             (bar_x, bar_y_center),
             (bar_x + bar_w, bar_y_center),
             (200, 200, 200), max(1, sx(1)))

    # Velocity fill (clamped to bar range)
    max_vel = 0.02
    fill_ratio = max(-1.0, min(1.0, velocity / max_vel))
    fill_pixels = int(fill_ratio * (bar_h // 2))

    if fill_pixels > 0:
        # Descending — red
        cv2.rectangle(frame,
                      (bar_x + 1, bar_y_center),
                      (bar_x + bar_w - 1, bar_y_center + fill_pixels),
                      (60, 76, 231), -1)
    elif fill_pixels < 0:
        # Ascending — green
        cv2.rectangle(frame,
                      (bar_x + 1, bar_y_center + fill_pixels),
                      (bar_x + bar_w - 1, bar_y_center),
                      (0, 230, 118), -1)
