"""
JumpDetector — Detects landing and takeoff events from per-frame landmarks.

Uses velocity extremum detection (not zero-crossing):
  - Landing = descending velocity starts decreasing (bed contact causes deceleration)
  - Takeoff = ascending velocity starts decreasing in magnitude (leaving bed)

Velocity is time-normalized (per second) and smoothed.
"""

import csv
from collections import deque
from trampoline.config import (
    LANDMARK, VELOCITY_WINDOW, VELOCITY_SMOOTH_WINDOW,
    MIN_DESCENT_VEL, MIN_ASCENT_VEL,
    MIN_JUMP_FRAMES, MIN_FLIGHT_FRAMES,
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
        self._prev_smoothed = 0.0
        self._prev_prev_smoothed = 0.0  # two-step history for extremum detection

        # State — start in contact
        self.phase = "contact"
        self.jump_count = 0

        # Track peak velocities for extremum detection
        self._descent_peak_vel = 0.0  # max positive velocity seen since last landing

        # Frame tracking
        self._current_jump_start = 0
        self._flight_start = None
        self._last_frame_idx = 0

        # Completed jumps list
        self.jumps = []

        # Diagnostic log
        self._diagnostic_log = []

    def current_flight_frames(self, frame_idx: int = None) -> int:
        """Return live flight frame count without changing phase or event semantics."""
        if self.phase != "flight" or self._flight_start is None:
            return 0
        current_frame = self._last_frame_idx if frame_idx is None else frame_idx
        return max(0, int(current_frame) - int(self._flight_start))

    def current_flight_duration_s(self, frame_idx: int = None) -> float:
        """Return live flight duration in seconds for status/UI rendering."""
        return self.current_flight_frames(frame_idx) / self.fps if self.fps else 0.0

    def process_frame(self, landmarks, frame_idx: int) -> dict:
        self._last_frame_idx = frame_idx
        result = {
            "event": None,
            "phase": self.phase,
            "com_y": 0.0,
            "velocity": 0.0,
            "ankle_y": 0.0,
            "jump_count": self.jump_count,
            "current_flight_frames": self.current_flight_frames(frame_idx),
            "current_flight_duration_s": self.current_flight_duration_s(frame_idx),
        }

        com_y = self._compute_com_y(landmarks)
        ankle_y = self._compute_ankle_y(landmarks)

        if com_y is None or ankle_y is None:
            self._diagnostic_log.append({
                "frame": frame_idx, "time_s": frame_idx / self.fps,
                "com_y": None, "ankle_y": None,
                "velocity": None, "smoothed_velocity": None,
                "phase": self.phase, "event": "",
            })
            return result

        result["com_y"] = com_y
        result["ankle_y"] = ankle_y

        self._com_y_buffer.append(com_y)

        if len(self._com_y_buffer) < VELOCITY_WINDOW + 1:
            self._diagnostic_log.append({
                "frame": frame_idx, "time_s": frame_idx / self.fps,
                "com_y": com_y, "ankle_y": ankle_y,
                "velocity": 0.0, "smoothed_velocity": 0.0,
                "phase": self.phase, "event": "",
            })
            return result

        # Time-normalized velocity
        delta_y = self._com_y_buffer[-1] - self._com_y_buffer[-1 - VELOCITY_WINDOW]
        raw_velocity = delta_y / self._time_per_window
        result["velocity"] = raw_velocity

        # Smoothed velocity
        self._velocity_history.append(raw_velocity)
        smoothed = sum(self._velocity_history) / len(self._velocity_history)

        event = ""

        # --- LANDING detection ---
        # Velocity was positive (descending) and starts decreasing → bed contact
        # prev_prev > prev > smoothed wouldn't work for a single-frame check,
        # so we detect: prev_smoothed was a local max (prev > prev_prev AND prev > smoothed)
        # AND prev_smoothed exceeded minimum descent velocity
        if self.phase == "flight":
            descent_peak = (
                self._prev_smoothed > self._prev_prev_smoothed
                and self._prev_smoothed > smoothed
                and self._prev_smoothed > MIN_DESCENT_VEL
            )
            if descent_peak:
                if self._flight_start is not None:
                    flight_duration = frame_idx - self._flight_start
                    if flight_duration >= MIN_FLIGHT_FRAMES:
                        event = "landing"
                        result["event"] = "landing"
                        self.jump_count += 1
                        result["jump_count"] = self.jump_count
                        result["current_flight_frames"] = flight_duration
                        result["current_flight_duration_s"] = flight_duration / self.fps if self.fps else 0.0

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
        # Velocity was negative (ascending) and starts increasing → leaving bed
        # prev_smoothed was a local min (prev < prev_prev AND prev < smoothed)
        # AND prev_smoothed exceeded minimum ascent velocity
        if self.phase == "contact":
            ascent_peak = (
                self._prev_smoothed < self._prev_prev_smoothed
                and self._prev_smoothed < smoothed
                and self._prev_smoothed < MIN_ASCENT_VEL
            )
            if ascent_peak:
                frames_since_landing = frame_idx - self._current_jump_start
                if frames_since_landing >= MIN_JUMP_FRAMES:
                    event = "takeoff"
                    result["event"] = "takeoff"
                    self.phase = "flight"
                    result["phase"] = "flight"
                    self._flight_start = frame_idx
                    result["current_flight_frames"] = 0
                    result["current_flight_duration_s"] = 0.0

        if self.phase == "flight" and result["event"] != "landing":
            result["current_flight_frames"] = self.current_flight_frames(frame_idx)
            result["current_flight_duration_s"] = self.current_flight_duration_s(frame_idx)
        elif self.phase == "contact" and result["event"] != "landing":
            result["current_flight_frames"] = 0
            result["current_flight_duration_s"] = 0.0

        self._prev_prev_smoothed = self._prev_smoothed
        self._prev_smoothed = smoothed

        # Diagnostic
        self._diagnostic_log.append({
            "frame": frame_idx, "time_s": round(frame_idx / self.fps, 3),
            "com_y": round(com_y, 4), "ankle_y": round(ankle_y, 4),
            "velocity": round(raw_velocity, 4), "smoothed_velocity": round(smoothed, 4),
            "phase": self.phase, "event": event,
        })

        return result

    def dump_diagnostics(self, path: str):
        """Write diagnostic log to CSV file."""
        if not self._diagnostic_log:
            return
        fieldnames = ["frame", "time_s", "com_y", "ankle_y", "velocity",
                       "smoothed_velocity", "phase", "event"]
        with open(path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(self._diagnostic_log)
        print(f"Diagnostics written to {path} ({len(self._diagnostic_log)} rows)")

    def _compute_com_y(self, landmarks) -> float:
        l_hip = landmarks[LANDMARK["left_hip"]]
        r_hip = landmarks[LANDMARK["right_hip"]]
        if l_hip.visibility < 0.3 and r_hip.visibility < 0.3:
            return None
        if l_hip.visibility >= 0.3 and r_hip.visibility >= 0.3:
            return (l_hip.y + r_hip.y) / 2
        return l_hip.y if l_hip.visibility >= 0.3 else r_hip.y

    def _compute_ankle_y(self, landmarks) -> float:
        l_ankle = landmarks[LANDMARK["left_ankle"]]
        r_ankle = landmarks[LANDMARK["right_ankle"]]
        if l_ankle.visibility < 0.3 and r_ankle.visibility < 0.3:
            return None
        if l_ankle.visibility >= 0.3 and r_ankle.visibility >= 0.3:
            return (l_ankle.y + r_ankle.y) / 2
        return l_ankle.y if l_ankle.visibility >= 0.3 else r_ankle.y
