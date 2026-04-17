"""
TrampolineAnalyzer — Orchestrates JumpDetector + ActionClassifier.

Drop-in replacement for ExerciseEngine when processing trampoline videos.
Compatible interface: process_frame(frame, landmarks, frame_idx) and get_status().
"""

from trampoline.jump_detector import JumpDetector
from trampoline.action_classifier import ActionClassifier, ActionState
from trampoline.config import LANDMARK


class TrampolineAnalyzer:
    def __init__(self, fps: float = 30.0, bed_tracker=None):
        self.fps = fps
        self.bed_tracker = bed_tracker
        self.jump_detector = JumpDetector(fps)
        self.action_classifier = ActionClassifier()
        self.completed_jumps = []
        self._current_action = ActionState.UNKNOWN

    def process_frame(self, frame, landmarks, frame_idx: int = None) -> dict:
        """
        Process one video frame.

        Args:
            frame: video frame (numpy array)
            landmarks: MediaPipe pose landmarks list
            frame_idx: actual video frame number (1-based). If None, uses internal counter.
        """
        if frame_idx is None:
            frame_idx = len(self.jump_detector._com_y_buffer) + 1

        frame_shape = frame.shape[:2]  # (height, width)

        # Step 1: Jump detection
        detection = self.jump_detector.process_frame(landmarks, frame_idx)

        # Step 2: Handle phase transitions
        if detection["event"] == "takeoff":
            self.action_classifier.set_phase("flight")
            self.action_classifier.reset_jump()

        elif detection["event"] == "landing":
            # Finalize the just-completed jump
            action = self.action_classifier.get_jump_action()
            self.action_classifier.set_phase("contact")

            # Update the last jump entry with the classified action
            if self.jump_detector.jumps:
                self.jump_detector.jumps[-1]["action"] = action.value

            jump_entry = {
                "jump_number": self.jump_detector.jump_count,
                "action": action.value,
                "flight_frames": self.jump_detector.jumps[-1]["flight_frames"] if self.jump_detector.jumps else 0,
                "is_intermediate": self.jump_detector.jumps[-1]["is_intermediate"] if self.jump_detector.jumps else False,
            }
            landing = self._compute_landing_payload(frame, landmarks)
            if landing is not None:
                jump_entry["landing"] = landing

            self.completed_jumps.append(jump_entry)

        # Step 3: Classify during flight
        if detection["phase"] == "flight":
            self._current_action = self.action_classifier.classify_frame(landmarks, frame_shape)
        else:
            self._current_action = ActionState.UNKNOWN

        return {
            "success": True,
            "jump_count": self.jump_detector.jump_count,
            "current_action": self._current_action.value,
            "phase": detection["phase"],
            "velocity": detection["velocity"],
            "com_y": detection["com_y"],
            "ankle_y": detection["ankle_y"],
            "trunk_thigh_angle": self.action_classifier.trunk_thigh_angle,
            "thigh_shin_angle": self.action_classifier.thigh_shin_angle,
            "completed_jumps": self.completed_jumps,
        }

    def _compute_landing_payload(self, frame, landmarks):
        """Attach landing data from the current BedTracker without changing jump segmentation."""
        if self.bed_tracker is None or landmarks is None:
            return None
        try:
            h, w = frame.shape[:2]
            left = landmarks[LANDMARK["left_ankle"]]
            right = landmarks[LANDMARK["right_ankle"]]
            left_vis = float(getattr(left, "visibility", 0.0))
            right_vis = float(getattr(right, "visibility", 0.0))
            total_vis = left_vis + right_vis
            if total_vis > 1e-6:
                x_norm = (left.x * left_vis + right.x * right_vis) / total_vis
                y_norm = (left.y * left_vis + right.y * right_vis) / total_vis
                ankle_visibility = min(1.0, max(0.0, total_vis / 2.0))
            else:
                x_norm = (left.x + right.x) / 2.0
                y_norm = (left.y + right.y) / 2.0
                ankle_visibility = 0.0

            ankle_px = (float(x_norm) * w, float(y_norm) * h)
            payload = self.bed_tracker.landing_payload(ankle_px, ankle_visibility=ankle_visibility)
            payload["ankle_px"] = [round(ankle_px[0], 1), round(ankle_px[1], 1)]
            return payload
        except Exception:
            # Landing enrichment must never break the existing jump result.
            return None

    def get_status(self) -> dict:
        return {
            "counter": self.jump_detector.jump_count,
            "current_state": self._current_action.value,
            "form_score": 100,
            "avg_form_score": 100,
            "form_grade": "--",
            "feedback": "",
            "current_action": self._current_action.value,
            "completed_jumps": self.completed_jumps,
        }

    def dump_diagnostics(self, path: str):
        """Write jump detection diagnostics CSV."""
        self.jump_detector.dump_diagnostics(path)
