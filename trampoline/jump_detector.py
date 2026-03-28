"""
JumpDetector — Detects landing and takeoff events from per-frame landmarks.

Uses vertical velocity of center-of-mass (hip midpoint) and ankle position
to segment video into individual jumps.
"""

from collections import deque
from trampoline.config import (
    LANDMARK, VELOCITY_WINDOW, LANDING_VEL_THRESHOLD, TAKEOFF_VEL_THRESHOLD,
    MIN_JUMP_FRAMES, MIN_FLIGHT_FRAMES, CONTACT_ANKLE_Y_RATIO,
    INTERMEDIATE_MAX_FLIGHT_FRAMES,
)


class JumpDetector:
    def __init__(self, fps: float = 30.0):
        self.fps = fps

        # Circular buffers for velocity estimation
        self._com_y_buffer = deque(maxlen=VELOCITY_WINDOW + 1)

        # Running tracker for ankle-y range
        self._ankle_y_min = None
        self._ankle_y_max = None

        # State
        self.phase = "unknown"          # "unknown", "contact", "flight"
        self._prev_velocity = 0.0
        self.jump_count = 0

        # Frame tracking
        self._current_jump_start = None # frame idx of last landing
        self._flight_start = None       # frame idx of last takeoff
        self._frame_count = 0

        # Completed jumps list
        self.jumps = []

        # Per-jump flight frame count (for intermediate detection)
        self._flight_frame_count = 0

    def process_frame(self, landmarks, frame_idx: int) -> dict:
        """
        Process one frame of landmark data.

        Args:
            landmarks: MediaPipe pose landmarks list (33 elements with .x, .y, .visibility)
            frame_idx: current frame number (1-based)

        Returns:
            dict with keys: event, phase, com_y, velocity, ankle_y, jump_count
        """
        self._frame_count = frame_idx
        result = {
            "event": None,
            "phase": self.phase,
            "com_y": 0.0,
            "velocity": 0.0,
            "ankle_y": 0.0,
            "jump_count": self.jump_count,
        }

        # Compute center-of-mass y (average of hip y values, normalized 0..1)
        com_y = self._compute_com_y(landmarks)
        ankle_y = self._compute_ankle_y(landmarks)

        if com_y is None or ankle_y is None:
            # Landmarks not visible — hold state
            return result

        result["com_y"] = com_y
        result["ankle_y"] = ankle_y

        # Update ankle range tracker
        if self._ankle_y_min is None:
            self._ankle_y_min = ankle_y
            self._ankle_y_max = ankle_y
        else:
            self._ankle_y_min = min(self._ankle_y_min, ankle_y)
            self._ankle_y_max = max(self._ankle_y_max, ankle_y)

        # Push to velocity buffer
        self._com_y_buffer.append(com_y)

        if len(self._com_y_buffer) < VELOCITY_WINDOW + 1:
            # Not enough data yet
            return result

        # Finite-difference velocity (positive = descending in image coords)
        velocity = (self._com_y_buffer[-1] - self._com_y_buffer[-1 - VELOCITY_WINDOW]) / VELOCITY_WINDOW
        result["velocity"] = velocity

        # Track flight frames
        if self.phase == "flight":
            self._flight_frame_count += 1

        # --- Event detection ---
        ankle_near_max = (
            self._ankle_y_max > self._ankle_y_min
            and ankle_y >= self._ankle_y_max * CONTACT_ANKLE_Y_RATIO
        )

        # LANDING: velocity was negative (ascending) and crosses to positive/zero
        # AND ankle near max
        velocity_reversal_down = (
            self._prev_velocity < -LANDING_VEL_THRESHOLD
            and velocity >= 0
        )

        if velocity_reversal_down and ankle_near_max and self.phase == "flight":
            if self._flight_start is not None:
                flight_duration = frame_idx - self._flight_start
                if flight_duration >= MIN_FLIGHT_FRAMES:
                    # Valid landing
                    result["event"] = "landing"
                    self.jump_count += 1
                    result["jump_count"] = self.jump_count

                    is_intermediate = flight_duration <= INTERMEDIATE_MAX_FLIGHT_FRAMES
                    self.jumps.append({
                        "jump_number": self.jump_count,
                        "start_frame": self._current_jump_start or 0,
                        "end_frame": frame_idx,
                        "flight_start": self._flight_start,
                        "flight_end": frame_idx,
                        "flight_frames": flight_duration,
                        "is_intermediate": is_intermediate,
                        "action": "Unknown",  # filled later by analyzer
                    })

            self.phase = "contact"
            result["phase"] = "contact"
            self._current_jump_start = frame_idx
            self._flight_start = None
            self._flight_frame_count = 0

        # TAKEOFF: velocity drops below threshold while in contact
        # (person is ascending fast enough to leave the bed)
        ascending_fast = velocity < TAKEOFF_VEL_THRESHOLD

        if ascending_fast and self.phase in ("contact", "unknown"):
            frames_since_landing = (
                frame_idx - self._current_jump_start
                if self._current_jump_start is not None
                else MIN_JUMP_FRAMES + 1  # allow first takeoff
            )
            if frames_since_landing >= MIN_JUMP_FRAMES:
                result["event"] = "takeoff"
                self.phase = "flight"
                result["phase"] = "flight"
                self._flight_start = frame_idx
                self._flight_frame_count = 0

        # Bootstrap: if still unknown and we see upward motion, treat as flight
        if self.phase == "unknown" and velocity < TAKEOFF_VEL_THRESHOLD:
            self.phase = "flight"
            result["phase"] = "flight"
            self._flight_start = frame_idx
            self._flight_frame_count = 0

        # Bootstrap: if still unknown and ankle near max with downward motion,
        # treat as contact
        if self.phase == "unknown" and ankle_near_max and velocity >= 0:
            self.phase = "contact"
            result["phase"] = "contact"
            self._current_jump_start = frame_idx

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
