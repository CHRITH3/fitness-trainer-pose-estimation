"""
Trampoline-specific video overlay drawing.
Replaces draw_stats_overlay() when in trampoline mode.
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


def draw_trampoline_overlay(frame, stats):
    """
    Draw trampoline analysis overlay on video frame.

    Args:
        frame: BGR numpy array
        stats: dict with keys from TrampolineAnalyzer:
            jump_count, current_action, phase, velocity,
            trunk_thigh_angle, thigh_shin_angle
    """
    h, w = frame.shape[:2]

    # Semi-transparent background box
    box_w, box_h = 340, 200
    margin = 15
    overlay = frame.copy()
    cv2.rectangle(overlay, (margin, margin), (margin + box_w, margin + box_h),
                  (30, 30, 30), -1)
    cv2.rectangle(overlay, (margin, margin), (margin + 5, margin + box_h),
                  (0, 200, 100), -1)
    cv2.addWeighted(overlay, 0.85, frame, 0.15, 0, frame)

    font = cv2.FONT_HERSHEY_SIMPLEX
    font_bold = cv2.FONT_HERSHEY_DUPLEX
    x = margin + 14
    y_base = margin + 35

    # --- JUMPS count (large) ---
    jump_count = stats.get("jump_count", stats.get("reps", 0))
    cv2.putText(frame, "JUMPS", (x, y_base - 8),
                font, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
    cv2.putText(frame, str(jump_count), (x, y_base + 28),
                font_bold, 1.4, (255, 255, 255), 2, cv2.LINE_AA)

    # --- PHASE indicator ---
    phase = stats.get("phase", "unknown")
    phase_x = x + 90
    phase_color = PHASE_COLORS.get(phase, PHASE_COLORS["unknown"])
    cv2.putText(frame, "PHASE", (phase_x, y_base - 8),
                font, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
    cv2.circle(frame, (phase_x + 8, y_base + 15), 6, phase_color, -1)
    cv2.putText(frame, phase.upper(), (phase_x + 22, y_base + 20),
                font, 0.6, phase_color, 2, cv2.LINE_AA)

    # --- ACTION name (large, color-coded) ---
    action = stats.get("current_action", "Unknown")
    action_y = y_base + 65
    action_color = ACTION_COLORS.get(action, ACTION_COLORS["Unknown"])
    cv2.putText(frame, "ACTION", (x, action_y - 8),
                font, 0.5, (150, 150, 150), 1, cv2.LINE_AA)
    cv2.putText(frame, action.upper(), (x, action_y + 28),
                font_bold, 1.2, action_color, 2, cv2.LINE_AA)

    # --- Angle debug info (small) ---
    angle_y = action_y + 55
    trunk_thigh = stats.get("trunk_thigh_angle", 0)
    thigh_shin = stats.get("thigh_shin_angle", 0)
    if trunk_thigh > 0:
        cv2.putText(frame, f"T-T: {trunk_thigh:.0f}deg  T-S: {thigh_shin:.0f}deg",
                    (x, angle_y), font, 0.4, (180, 180, 180), 1, cv2.LINE_AA)

    # --- Velocity bar on right edge ---
    velocity = stats.get("velocity", 0)
    _draw_velocity_bar(frame, velocity, w, h)

    return frame


def _draw_velocity_bar(frame, velocity, w, h):
    """Draw a vertical velocity indicator bar on the right edge."""
    bar_w = 12
    bar_h = 120
    bar_x = w - bar_w - 15
    bar_y_center = 80

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
             (200, 200, 200), 1)

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
