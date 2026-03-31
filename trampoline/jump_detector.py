"""
JumpDetector — Detects landing and takeoff events from per-frame landmarks.

Uses vertical velocity of center-of-mass (hip midpoint) and ankle position
to segment video into individual jumps. Velocity is time-normalized (per second).
"""

from collections import deque
from trampoline.config import (
    LANDMARK, VELOCITY_WINDOW, LANDING_VEL_THRESHOLD, TAKEOFF_VEL_THRESHOLD,
    MIN_JUMP_FRAMES, MIN_FLIGHT_FRAMES, ANKLE_Y_EMA_ALPHA,
    INTERMEDIATE_MAX_FLIGHT_FRAMES,
)


class JumpDetector:
    def __init__(self, fps: float = 30.0):
        self.fps = fps
        self._time_per_window = VELOCITY_WINDOW / fps  # seconds spanned by velocity window

        # Circular buffer for velocity estimation
        self._com_y_buffer = deque(maxlen=VELOCITY_WINDOW + 1)

        # Ankle baseline tracking via EMA (adapts per-jump, not all-time)
        self._ankle_y_ema = None          # exponential moving average of ankle y
        self._ankle_y_contact_max = None  # max ankle y observed during current contact phase

        # State — start in contact (person is on the bed at video start)
        self.phase = "contact"
        self._prev_velocity = 0.0
        self.jump_count = 0

        # Frame tracking
        self._current_jump_start = 0   # frame idx of last landing
        self._flight_start = None      # frame idx of last takeoff

        # Completed jumps list
        self.jumps = []

    def process_frame(self, landmarks, frame_idx: int) -> dict:
        """
        Process one frame of landmark data.

        Args:
            landmarks: MediaPipe pose landmarks list (33 elements)
            frame_idx: actual video frame number (1-based, from video_processor)

        Returns:
            dict with keys: event, phase, com_y, velocity, ankle_y, jump_count
        """
        result = {
            "event": None,
            "phase": self.phase,
            "com_y": 0.0,
            "velocity": 0.0,
            "ankle_y": 0.0,
            "jump_count": self.jump_count,
        }

        com_y = self._compute_com_y(landmarks)
        ankle_y = self._compute_ankle_y(landmarks)

        if com_y is None or ankle_y is None:
            return result

        result["com_y"] = com_y
        result["ankle_y"] = ankle_y

        # Update ankle EMA baseline
        if self._ankle_y_ema is None:
            self._ankle_y_ema = ankle_y
        else:
            self._ankle_y_ema = (1 - ANKLE_Y_EMA_ALPHA) * self._ankle_y_ema + ANKLE_Y_EMA_ALPHA * ankle_y

        # Track contact-phase ankle max (resets each landing)
        if self.phase == "contact":
            if self._ankle_y_contact_max is None:
                self._ankle_y_contact_max = ankle_y
            else:
                self._ankle_y_contact_max = max(self._ankle_y_contact_max, ankle_y)

        # Push to velocity buffer
        self._com_y_buffer.append(com_y)

        if len(self._com_y_buffer) < VELOCITY_WINDOW + 1:
            return result

        # Time-normalized velocity (normalized-y per second)
        delta_y = self._com_y_buffer[-1] - self._com_y_buffer[-1 - VELOCITY_WINDOW]
        velocity = delta_y / self._time_per_window
        result["velocity"] = velocity

        # --- LANDING detection ---
        # Velocity was strongly negative (ascending) and now crosses to >= 0 (descending)
        # AND ankle is near its baseline (person is low, near bed level)
        ankle_near_baseline = (
            self._ankle_y_ema is not None
            and ankle_y >= self._ankle_y_ema * 0.95
        )

        velocity_reversal_down = (
            self._prev_velocity < -LANDING_VEL_THRESHOLD
            and velocity >= 0
        )

        if velocity_reversal_down and ankle_near_baseline and self.phase == "flight":
            if self._flight_start is not None:
                flight_duration = frame_idx - self._flight_start
                if flight_duration >= MIN_FLIGHT_FRAMES:
                    result["event"] = "landing"
                    self.jump_count += 1
                    result["jump_count"] = self.jump_count

                    is_intermediate = flight_duration <= INTERMEDIATE_MAX_FLIGHT_FRAMES
                    self.jumps.append({
                        "jump_number": self.jump_count,
                        "start_frame": self._current_jump_start,
                        "end_frame": frame_idx,
                        "flight_start": self._flight_start,
                        "flight_end": frame_idx,
                        "flight_frames": flight_duration,
                        "is_intermediate": is_intermediate,
                        "action": "Unknown",
                    })

            self.phase = "contact"
            result["phase"] = "contact"
            self._current_jump_start = frame_idx
            self._flight_start = None
            # Reset contact-phase ankle tracker for next jump
            self._ankle_y_contact_max = ankle_y

        # --- TAKEOFF detection ---
        # Velocity drops below threshold (person ascending fast)
        ascending_fast = velocity < TAKEOFF_VEL_THRESHOLD

        if ascending_fast and self.phase == "contact":
            frames_since_landing = frame_idx - self._current_jump_start
            if frames_since_landing >= MIN_JUMP_FRAMES:
                result["event"] = "takeoff"
                self.phase = "flight"
                result["phase"] = "flight"
                self._flight_start = frame_idx

        self._prev_velocity = velocity
        return result

    def _compute_com_y(self, landmarks) -> float:
        """Average of left/right hip y (normalized 0..1)."""
        l_hip = landmarks[LANDMARK["left_hip"]]
        r_hip = landmarks[LANDMARK["right_hip"]]
        if l_hip.visibility < 0.3 and r_hip.visibility < 0.3:
            return None
        if l_hip.visibility >= 0.3 and r_hip.visibility >= 0.3:
            return (l_hip.y + r_hip.y) / 2
        return l_hip.y if l_hip.visibility >= 0.3 else r_hip.y

    def _compute_ankle_y(self, landmarks) -> float:
        """Average of left/right ankle y (normalized 0..1)."""
        l_ankle = landmarks[LANDMARK["left_ankle"]]
        r_ankle = landmarks[LANDMARK["right_ankle"]]
        if l_ankle.visibility < 0.3 and r_ankle.visibility < 0.3:
            return None
        if l_ankle.visibility >= 0.3 and r_ankle.visibility >= 0.3:
            return (l_ankle.y + r_ankle.y) / 2
        return l_ankle.y if l_ankle.visibility >= 0.3 else r_ankle.y
