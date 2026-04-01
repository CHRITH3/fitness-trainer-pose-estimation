"""
JumpDetector — Detects landing and takeoff events from per-frame landmarks.

Uses vertical velocity of center-of-mass (hip midpoint) and ankle position
to segment video into individual jumps. Velocity is time-normalized (per second)
and smoothed over a short window to prevent noise-induced false triggers.

Jump cycle (in image coords, y increases downward):
  contact → takeoff (v < threshold) → flight → landing (v crosses from + to 0/-) → contact

  Velocity profile:   ~0 → negative (ascending) → 0 (peak) → positive (descending) → 0 (landing) → ...
  Landing = velocity zero-crossing from positive (descending) to ≤0 (bed reversal)
  Takeoff = smoothed velocity drops below negative threshold (ascending fast)
"""

import csv
from collections import deque
from trampoline.config import (
    LANDMARK, VELOCITY_WINDOW, VELOCITY_SMOOTH_WINDOW,
    LANDING_VEL_THRESHOLD, TAKEOFF_VEL_THRESHOLD,
    MIN_JUMP_FRAMES, MIN_FLIGHT_FRAMES, ANKLE_Y_EMA_ALPHA,
    INTERMEDIATE_MAX_FLIGHT_FRAMES,
)


class JumpDetector:
    def __init__(self, fps: float = 30.0):
        self.fps = fps
        self._time_per_window = VELOCITY_WINDOW / fps

        # Circular buffer for finite-difference velocity
        self._com_y_buffer = deque(maxlen=VELOCITY_WINDOW + 1)

        # Velocity smoothing (moving average)
        self._velocity_history = deque(maxlen=VELOCITY_SMOOTH_WINDOW)
        self._prev_smoothed_velocity = 0.0

        # Ankle baseline via EMA
        self._ankle_y_ema = None

        # State — start in contact (person is on the bed at video start)
        self.phase = "contact"
        self.jump_count = 0

        # Frame tracking
        self._current_jump_start = 0
        self._flight_start = None

        # Completed jumps list
        self.jumps = []

        # Diagnostic log: list of dicts, one per processed frame
        self._diagnostic_log = []

    def process_frame(self, landmarks, frame_idx: int) -> dict:
        """
        Process one frame of landmark data.

        Args:
            landmarks: MediaPipe pose landmarks list (33 elements)
            frame_idx: actual video frame number (1-based)

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
            self._diagnostic_log.append({
                "frame": frame_idx, "time_s": frame_idx / self.fps,
                "com_y": None, "ankle_y": None,
                "velocity": None, "smoothed_velocity": None,
                "ankle_ema": self._ankle_y_ema, "phase": self.phase, "event": "",
            })
            return result

        result["com_y"] = com_y
        result["ankle_y"] = ankle_y

        # Update ankle EMA baseline
        if self._ankle_y_ema is None:
            self._ankle_y_ema = ankle_y
        else:
            self._ankle_y_ema = (1 - ANKLE_Y_EMA_ALPHA) * self._ankle_y_ema + ANKLE_Y_EMA_ALPHA * ankle_y

        # Push to velocity buffer
        self._com_y_buffer.append(com_y)

        if len(self._com_y_buffer) < VELOCITY_WINDOW + 1:
            self._diagnostic_log.append({
                "frame": frame_idx, "time_s": frame_idx / self.fps,
                "com_y": com_y, "ankle_y": ankle_y,
                "velocity": 0.0, "smoothed_velocity": 0.0,
                "ankle_ema": self._ankle_y_ema, "phase": self.phase, "event": "",
            })
            return result

        # Time-normalized raw velocity (normalized-y per second)
        delta_y = self._com_y_buffer[-1] - self._com_y_buffer[-1 - VELOCITY_WINDOW]
        raw_velocity = delta_y / self._time_per_window
        result["velocity"] = raw_velocity

        # Smoothed velocity (moving average)
        self._velocity_history.append(raw_velocity)
        smoothed = sum(self._velocity_history) / len(self._velocity_history)

        event = ""

        # --- LANDING detection ---
        # Smoothed velocity was positive (descending toward bed) and now crosses to ≤0
        # (bed reverses the motion → ascending)
        ankle_near_baseline = (
            self._ankle_y_ema is not None
            and ankle_y >= self._ankle_y_ema * 0.95
        )

        landing_reversal = (
            self._prev_smoothed_velocity > LANDING_VEL_THRESHOLD
            and smoothed <= 0
        )

        if landing_reversal and ankle_near_baseline and self.phase == "flight":
            if self._flight_start is not None:
                flight_duration = frame_idx - self._flight_start
                if flight_duration >= MIN_FLIGHT_FRAMES:
                    event = "landing"
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

        # --- TAKEOFF detection ---
        # Smoothed velocity drops below negative threshold (person ascending fast)
        if smoothed < TAKEOFF_VEL_THRESHOLD and self.phase == "contact":
            frames_since_landing = frame_idx - self._current_jump_start
            if frames_since_landing >= MIN_JUMP_FRAMES:
                event = "takeoff"
                result["event"] = "takeoff"
                self.phase = "flight"
                result["phase"] = "flight"
                self._flight_start = frame_idx

        self._prev_smoothed_velocity = smoothed

        # Record diagnostic row
        self._diagnostic_log.append({
            "frame": frame_idx, "time_s": round(frame_idx / self.fps, 3),
            "com_y": round(com_y, 4), "ankle_y": round(ankle_y, 4),
            "velocity": round(raw_velocity, 4), "smoothed_velocity": round(smoothed, 4),
            "ankle_ema": round(self._ankle_y_ema, 4), "phase": self.phase, "event": event,
        })

        return result

    def dump_diagnostics(self, path: str):
        """Write diagnostic log to CSV file."""
        if not self._diagnostic_log:
            return
        fieldnames = ["frame", "time_s", "com_y", "ankle_y", "velocity",
                       "smoothed_velocity", "ankle_ema", "phase", "event"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._diagnostic_log)
        print(f"Diagnostics written to {path} ({len(self._diagnostic_log)} rows)")

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
