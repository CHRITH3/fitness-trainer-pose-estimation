"""
Tests for trampoline jump detection and action classification.
Uses synthetic landmark data to verify algorithms without MediaPipe.
"""

import math
import pytest
from unittest.mock import MagicMock
from trampoline.jump_detector import JumpDetector
from trampoline.action_classifier import ActionClassifier, ActionState, _angle_between
from trampoline.analyzer import TrampolineAnalyzer
import trampoline.config as cfg
import numpy as np


def make_landmark(x, y, visibility=0.9):
    """Create a mock MediaPipe landmark."""
    lm = MagicMock()
    lm.x = x
    lm.y = y
    lm.visibility = visibility
    return lm


def make_landmarks_at_y(com_y, ankle_y, trunk_thigh_deg=170, thigh_shin_deg=170):
    """
    Create a 33-element landmark list with specified com/ankle y positions
    and approximate body angles.
    """
    landmarks = [make_landmark(0.5, 0.5) for _ in range(33)]

    # Hips at com_y
    landmarks[23] = make_landmark(0.45, com_y)  # left hip
    landmarks[24] = make_landmark(0.55, com_y)  # right hip

    # Ankles at ankle_y
    landmarks[27] = make_landmark(0.45, ankle_y)  # left ankle
    landmarks[28] = make_landmark(0.55, ankle_y)  # right ankle

    # Position shoulders and knees to approximate the desired angles
    # trunk_thigh = angle at hip (shoulder-hip-knee)
    # thigh_shin = angle at knee (hip-knee-ankle)

    # For simplicity: place shoulder above hip, knee below hip, ankle below knee
    shoulder_offset = 0.15  # above hip
    knee_y = com_y + 0.1
    landmarks[11] = make_landmark(0.45, com_y - shoulder_offset)  # left shoulder
    landmarks[12] = make_landmark(0.55, com_y - shoulder_offset)  # right shoulder

    # Adjust knee x to set trunk_thigh angle
    if trunk_thigh_deg < 160:
        # Move knee forward to reduce angle
        knee_x_offset = 0.1 * (160 - trunk_thigh_deg) / 90
        landmarks[25] = make_landmark(0.45 + knee_x_offset, knee_y)
        landmarks[26] = make_landmark(0.55 + knee_x_offset, knee_y)
    else:
        landmarks[25] = make_landmark(0.45, knee_y)
        landmarks[26] = make_landmark(0.55, knee_y)

    return landmarks


class TestAngleBetween:
    def test_straight_line(self):
        # 180 degrees: a, b, c in a line
        angle = _angle_between([0, 0], [1, 0], [2, 0])
        assert abs(angle - 180.0) < 1.0

    def test_right_angle(self):
        angle = _angle_between([0, 1], [0, 0], [1, 0])
        assert abs(angle - 90.0) < 1.0

    def test_acute_angle(self):
        angle = _angle_between([1, 1], [0, 0], [1, 0])
        assert abs(angle - 45.0) < 1.0


class TestJumpDetector:
    def test_initial_state(self):
        jd = JumpDetector(fps=30.0)
        assert jd.phase == "contact"
        assert jd.jump_count == 0
        assert len(jd.jumps) == 0

    def test_detects_phase_from_motion(self):
        """Feed descending then ascending motion, verify phase transitions."""
        jd = JumpDetector(fps=30.0)

        # Descending phase (contact): com_y increasing, ankle_y near max
        for i in range(20):
            com_y = 0.5 + i * 0.005  # descending (y increasing)
            ankle_y = 0.7 + i * 0.003
            landmarks = make_landmarks_at_y(com_y, ankle_y)
            jd.process_frame(landmarks, i + 1)

        # After enough frames, should be in contact phase
        assert jd.phase == "contact"

    def test_full_jump_cycle(self):
        """Simulate: contact → takeoff → flight → landing → contact.

        Velocity extremum detection:
          - Takeoff = ascending velocity peak (most negative smoothed velocity)
          - Landing = descending velocity peak (most positive smoothed velocity)
        """
        jd = JumpDetector(fps=30.0)
        frame = 0

        # Phase 1: Static on bed (contact)
        for i in range(10):
            frame += 1
            com_y = 0.6
            ankle_y = 0.8
            jd.process_frame(make_landmarks_at_y(com_y, ankle_y), frame)

        # Phase 2: Accelerating upward (velocity increasingly negative)
        for i in range(8):
            frame += 1
            speed = (i + 1) * 0.005  # accelerating
            com_y = 0.6 - sum(range(1, i + 2)) * 0.005
            ankle_y = com_y + 0.2
            jd.process_frame(make_landmarks_at_y(com_y, ankle_y), frame)

        # Phase 3: Decelerating upward (velocity still negative but decreasing magnitude)
        # This is where takeoff should be detected (ascending velocity peak)
        for i in range(8):
            frame += 1
            speed = 0.04 - (i + 1) * 0.004  # decelerating
            com_y -= max(0.001, speed)
            ankle_y = com_y + 0.2
            jd.process_frame(make_landmarks_at_y(com_y, ankle_y), frame)

        # Should be in flight after takeoff
        assert jd.phase == "flight", f"Expected flight, got {jd.phase}"

        # Phase 4: Peak and descent — velocity goes from ~0 to positive (accelerating down)
        peak_com_y = com_y
        for i in range(10):
            frame += 1
            speed = (i + 1) * 0.004  # accelerating downward
            com_y = peak_com_y + sum(range(1, i + 2)) * 0.004
            ankle_y = com_y + 0.2
            jd.process_frame(make_landmarks_at_y(com_y, ankle_y), frame)

        # Phase 5: Decelerating descent (velocity positive but decreasing)
        # This is where landing should be detected (descending velocity peak)
        for i in range(8):
            frame += 1
            speed = 0.04 - (i + 1) * 0.004
            com_y += max(0.001, speed)
            ankle_y = com_y + 0.2
            jd.process_frame(make_landmarks_at_y(com_y, ankle_y), frame)

        # Phase 6: Bed reversal — velocity goes negative again
        for i in range(5):
            frame += 1
            com_y -= (i + 1) * 0.003
            ankle_y = com_y + 0.2
            jd.process_frame(make_landmarks_at_y(com_y, ankle_y), frame)

        # Should have detected landing
        assert jd.jump_count >= 1, f"Expected >=1 jump, got {jd.jump_count}"

    def test_missing_landmarks_handled(self):
        """Landmarks with low visibility should not crash."""
        jd = JumpDetector(fps=30.0)
        landmarks = [make_landmark(0.5, 0.5, visibility=0.1) for _ in range(33)]
        result = jd.process_frame(landmarks, 1)
        assert result["event"] is None
        assert result["phase"] == "contact"


class TestActionClassifier:
    def test_initial_state(self):
        ac = ActionClassifier()
        assert ac.state == ActionState.UNKNOWN

    def test_contact_phase_returns_unknown(self):
        ac = ActionClassifier()
        ac.set_phase("contact")
        landmarks = make_landmarks_at_y(0.5, 0.7, trunk_thigh_deg=90, thigh_shin_deg=90)
        result = ac.classify_frame(landmarks, (480, 640))
        assert result == ActionState.UNKNOWN

    def test_straight_classification(self):
        """With large angles (straight body), should classify as Straight."""
        ac = ActionClassifier()
        ac.set_phase("flight")

        # Create landmarks that form straight body (large angles)
        landmarks = [make_landmark(0.5, 0.5) for _ in range(33)]
        # Straight body: shoulder, hip, knee, ankle all roughly in line vertically
        landmarks[11] = make_landmark(0.5, 0.2)  # left shoulder
        landmarks[12] = make_landmark(0.5, 0.2)  # right shoulder
        landmarks[23] = make_landmark(0.5, 0.4)  # left hip
        landmarks[24] = make_landmark(0.5, 0.4)  # right hip
        landmarks[25] = make_landmark(0.5, 0.6)  # left knee
        landmarks[26] = make_landmark(0.5, 0.6)  # right knee
        landmarks[27] = make_landmark(0.5, 0.8)  # left ankle
        landmarks[28] = make_landmark(0.5, 0.8)  # right ankle

        result = ac.classify_frame(landmarks, (480, 640))
        assert result == ActionState.STRAIGHT

    def test_tuck_classification(self):
        """With small trunk-thigh and thigh-shin angles, should classify as Tuck."""
        ac = ActionClassifier()
        ac.set_phase("flight")

        landmarks = [make_landmark(0.5, 0.5) for _ in range(33)]
        # Tuck: knees pulled to chest
        # Shoulder above hip, knee close to chest, ankle near hip
        landmarks[11] = make_landmark(0.5, 0.3)   # left shoulder
        landmarks[12] = make_landmark(0.5, 0.3)   # right shoulder
        landmarks[23] = make_landmark(0.5, 0.45)  # left hip
        landmarks[24] = make_landmark(0.5, 0.45)  # right hip
        landmarks[25] = make_landmark(0.6, 0.35)  # left knee (pulled up and forward)
        landmarks[26] = make_landmark(0.6, 0.35)  # right knee
        landmarks[27] = make_landmark(0.55, 0.45) # left ankle (near hip)
        landmarks[28] = make_landmark(0.55, 0.45) # right ankle

        result = ac.classify_frame(landmarks, (480, 640))
        # Should be Pike or Tuck (depends on exact geometry)
        assert result in (ActionState.TUCK, ActionState.PIKE)

    def test_hysteresis_prevents_flickering(self):
        """Once in STRAIGHT, shouldn't immediately switch at boundary."""
        ac = ActionClassifier()
        ac.set_phase("flight")

        # First classify as straight (large angles)
        straight_lm = [make_landmark(0.5, 0.5) for _ in range(33)]
        straight_lm[11] = make_landmark(0.5, 0.2)
        straight_lm[12] = make_landmark(0.5, 0.2)
        straight_lm[23] = make_landmark(0.5, 0.4)
        straight_lm[24] = make_landmark(0.5, 0.4)
        straight_lm[25] = make_landmark(0.5, 0.6)
        straight_lm[26] = make_landmark(0.5, 0.6)
        straight_lm[27] = make_landmark(0.5, 0.8)
        straight_lm[28] = make_landmark(0.5, 0.8)

        ac.classify_frame(straight_lm, (480, 640))
        assert ac.state == ActionState.STRAIGHT

        # Classify again with same landmarks — should stay STRAIGHT
        result = ac.classify_frame(straight_lm, (480, 640))
        assert result == ActionState.STRAIGHT

    def test_unknown_fallback_after_invalid_frames(self):
        """After N frames with no visible landmarks, should fall back to UNKNOWN."""
        ac = ActionClassifier()
        ac.set_phase("flight")

        # First get into STRAIGHT state
        straight_lm = [make_landmark(0.5, 0.5) for _ in range(33)]
        straight_lm[11] = make_landmark(0.5, 0.2)
        straight_lm[12] = make_landmark(0.5, 0.2)
        straight_lm[23] = make_landmark(0.5, 0.4)
        straight_lm[24] = make_landmark(0.5, 0.4)
        straight_lm[25] = make_landmark(0.5, 0.6)
        straight_lm[26] = make_landmark(0.5, 0.6)
        straight_lm[27] = make_landmark(0.5, 0.8)
        straight_lm[28] = make_landmark(0.5, 0.8)
        ac.classify_frame(straight_lm, (480, 640))

        # Feed invisible landmarks
        invisible_lm = [make_landmark(0.5, 0.5, visibility=0.1) for _ in range(33)]
        for _ in range(cfg.UNKNOWN_FALLBACK_FRAMES + 1):
            ac.classify_frame(invisible_lm, (480, 640))

        assert ac.state == ActionState.UNKNOWN

    def test_majority_vote(self):
        ac = ActionClassifier()
        ac._per_jump_classifications = [
            ActionState.STRAIGHT, ActionState.STRAIGHT, ActionState.PIKE,
            ActionState.STRAIGHT, ActionState.UNKNOWN
        ]
        assert ac.get_jump_action() == ActionState.STRAIGHT

    def test_majority_vote_all_unknown(self):
        ac = ActionClassifier()
        ac._per_jump_classifications = [ActionState.UNKNOWN, ActionState.UNKNOWN]
        assert ac.get_jump_action() == ActionState.UNKNOWN

    def test_phase_reset_on_contact(self):
        ac = ActionClassifier()
        ac.set_phase("flight")
        ac.state = ActionState.TUCK
        ac.set_phase("contact")
        assert ac.state == ActionState.UNKNOWN

    def test_straddle_classification(self):
        """With legs spread wide, should classify as Straddle."""
        ac = ActionClassifier()
        ac.set_phase("flight")

        landmarks = [make_landmark(0.5, 0.5) for _ in range(33)]
        # Straight body but legs spread wide
        landmarks[11] = make_landmark(0.5, 0.2)   # left shoulder
        landmarks[12] = make_landmark(0.5, 0.2)   # right shoulder
        landmarks[23] = make_landmark(0.48, 0.4)  # left hip
        landmarks[24] = make_landmark(0.52, 0.4)  # right hip
        landmarks[25] = make_landmark(0.5, 0.6)   # left knee
        landmarks[26] = make_landmark(0.5, 0.6)   # right knee
        # Ankles spread very wide (much wider than hip width)
        landmarks[27] = make_landmark(0.2, 0.8)   # left ankle — far left
        landmarks[28] = make_landmark(0.8, 0.8)   # right ankle — far right

        result = ac.classify_frame(landmarks, (480, 640))
        assert result == ActionState.STRADDLE

    def test_straddle_hysteresis(self):
        """Once in straddle, shouldn't exit until legs come together past exit threshold."""
        ac = ActionClassifier()
        ac.set_phase("flight")

        # Enter straddle
        straddle_lm = [make_landmark(0.5, 0.5) for _ in range(33)]
        straddle_lm[11] = make_landmark(0.5, 0.2)
        straddle_lm[12] = make_landmark(0.5, 0.2)
        straddle_lm[23] = make_landmark(0.48, 0.4)
        straddle_lm[24] = make_landmark(0.52, 0.4)
        straddle_lm[25] = make_landmark(0.5, 0.6)
        straddle_lm[26] = make_landmark(0.5, 0.6)
        straddle_lm[27] = make_landmark(0.2, 0.8)
        straddle_lm[28] = make_landmark(0.8, 0.8)

        ac.classify_frame(straddle_lm, (480, 640))
        assert ac.state == ActionState.STRADDLE

        # Still straddle (same landmarks)
        result = ac.classify_frame(straddle_lm, (480, 640))
        assert result == ActionState.STRADDLE


class TestTrampolineAnalyzer:
    def test_initial_state(self):
        ta = TrampolineAnalyzer(fps=30.0)
        status = ta.get_status()
        assert status["counter"] == 0
        assert status["current_action"] == "Unknown"
        assert status["form_score"] == 100

    def test_process_frame_returns_expected_keys(self):
        ta = TrampolineAnalyzer(fps=30.0)
        landmarks = make_landmarks_at_y(0.5, 0.7)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        result = ta.process_frame(frame, landmarks)

        assert "jump_count" in result
        assert "current_action" in result
        assert "phase" in result
        assert "velocity" in result
        assert "completed_jumps" in result

    def test_process_many_frames_no_crash(self):
        """Process 100 frames of synthetic data without crashing."""
        ta = TrampolineAnalyzer(fps=30.0)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        for i in range(100):
            t = i / 30.0
            # Sinusoidal bounce
            com_y = 0.5 + 0.1 * math.sin(2 * math.pi * t)
            ankle_y = 0.7 + 0.08 * math.sin(2 * math.pi * t)
            landmarks = make_landmarks_at_y(com_y, ankle_y)
            result = ta.process_frame(frame, landmarks)

        assert result["jump_count"] >= 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

class TestTrampolineLandingIntegration:
    def test_landing_payload_uses_existing_landing_event(self):
        class FakeTracker:
            def __init__(self):
                self.calls = []

            def landing_payload(self, ankle_px, ankle_visibility=1.0):
                self.calls.append((ankle_px, ankle_visibility))
                return {
                    "bed_xy_m": [2.0, 1.0],
                    "norm_xy": [0.5, 0.5],
                    "zone": "center",
                    "dist_from_center_m": 0.0,
                    "confidence": 0.42,
                }

        tracker = FakeTracker()
        ta = TrampolineAnalyzer(fps=30.0, bed_tracker=tracker)
        ta.jump_detector.jump_count = 1
        ta.jump_detector.jumps = [{"flight_frames": 12, "is_intermediate": False}]
        ta.jump_detector.process_frame = MagicMock(return_value={
            "event": "landing",
            "phase": "contact",
            "velocity": 0.2,
            "com_y": 0.5,
            "ankle_y": 0.7,
        })
        landmarks = make_landmarks_at_y(0.5, 0.7)
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = ta.process_frame(frame, landmarks, frame_idx=10)

        assert result["jump_count"] == 1
        assert ta.completed_jumps[0]["landing"]["confidence"] == 0.42
        assert tracker.calls, "landing payload should be computed only from landing event path"

    def test_landing_mapping_failure_preserves_jump_result(self):
        class FailingTracker:
            def landing_payload(self, ankle_px, ankle_visibility=1.0):
                raise RuntimeError("mapping failed")

        ta = TrampolineAnalyzer(fps=30.0, bed_tracker=FailingTracker())
        ta.jump_detector.jump_count = 1
        ta.jump_detector.jumps = [{"flight_frames": 12, "is_intermediate": False}]
        ta.jump_detector.process_frame = MagicMock(return_value={
            "event": "landing",
            "phase": "contact",
            "velocity": 0.2,
            "com_y": 0.5,
            "ankle_y": 0.7,
        })
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        result = ta.process_frame(frame, make_landmarks_at_y(0.5, 0.7), frame_idx=10)

        assert result["jump_count"] == 1
        assert "landing" not in ta.completed_jumps[0]
