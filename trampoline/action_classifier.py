"""
ActionClassifier — Tuck / Pike / Straight classification with hysteresis.

Only active during the flight phase. Uses shoulder-hip-knee (trunk-thigh)
and hip-knee-ankle (thigh-shin) angles averaged across both sides.
"""

import math
from enum import Enum
from collections import Counter

from trampoline.config import (
    LANDMARK, TRUNK_THIGH_ENTER, TRUNK_THIGH_EXIT,
    THIGH_SHIN_ENTER, THIGH_SHIN_EXIT, STRAIGHT_THRESHOLD,
    UNKNOWN_FALLBACK_FRAMES,
)


class ActionState(Enum):
    UNKNOWN = "Unknown"
    STRAIGHT = "Straight"
    PIKE = "Pike"
    TUCK = "Tuck"


def _angle_between(a, b, c) -> float:
    """Compute angle at vertex b formed by points a-b-c. Returns degrees."""
    ba = [a[0] - b[0], a[1] - b[1]]
    bc = [c[0] - b[0], c[1] - b[1]]
    dot = ba[0] * bc[0] + ba[1] * bc[1]
    mag_ba = math.sqrt(ba[0] ** 2 + ba[1] ** 2)
    mag_bc = math.sqrt(bc[0] ** 2 + bc[1] ** 2)
    if mag_ba * mag_bc == 0:
        return 180.0
    cos_angle = max(-1.0, min(1.0, dot / (mag_ba * mag_bc)))
    return math.degrees(math.acos(cos_angle))


class ActionClassifier:
    def __init__(self):
        self.state = ActionState.UNKNOWN
        self.invalid_frame_count = 0
        self._phase = "contact"
        self._per_jump_classifications = []
        self.trunk_thigh_angle = 0.0
        self.thigh_shin_angle = 0.0

    def set_phase(self, phase: str):
        """Called when phase changes between 'flight' and 'contact'."""
        self._phase = phase
        if phase == "contact":
            self.state = ActionState.UNKNOWN
            self.invalid_frame_count = 0

    def reset_jump(self):
        """Reset per-jump classification buffer for a new jump."""
        self._per_jump_classifications = []

    def classify_frame(self, landmarks, frame_shape=(480, 640)) -> ActionState:
        """
        Classify one frame. Only active during flight phase.

        Args:
            landmarks: MediaPipe landmark list
            frame_shape: (height, width) for coordinate conversion

        Returns:
            Current ActionState
        """
        if self._phase != "flight":
            return ActionState.UNKNOWN

        trunk_thigh = self._compute_trunk_thigh_angle(landmarks, frame_shape)
        thigh_shin = self._compute_thigh_shin_angle(landmarks, frame_shape)

        if trunk_thigh is None or thigh_shin is None:
            self.invalid_frame_count += 1
            if self.invalid_frame_count >= UNKNOWN_FALLBACK_FRAMES:
                self.state = ActionState.UNKNOWN
                self.invalid_frame_count = 0
            self._per_jump_classifications.append(self.state)
            return self.state

        self.trunk_thigh_angle = trunk_thigh
        self.thigh_shin_angle = thigh_shin

        new_state = self._apply_hysteresis(trunk_thigh, thigh_shin)
        self.state = new_state
        self._per_jump_classifications.append(new_state)
        return new_state

    def get_jump_action(self) -> ActionState:
        """Determine dominant action for current jump via majority vote (ignoring UNKNOWN)."""
        valid = [s for s in self._per_jump_classifications if s != ActionState.UNKNOWN]
        if not valid:
            return ActionState.UNKNOWN
        counts = Counter(valid)
        return counts.most_common(1)[0][0]

    def _apply_hysteresis(self, trunk_thigh: float, thigh_shin: float) -> ActionState:
        """Apply hysteresis FSM transitions."""
        if self.state == ActionState.UNKNOWN:
            if trunk_thigh > STRAIGHT_THRESHOLD:
                self.invalid_frame_count = 0
                return ActionState.STRAIGHT
            elif trunk_thigh <= TRUNK_THIGH_ENTER:
                self.invalid_frame_count = 0
                if thigh_shin <= THIGH_SHIN_ENTER:
                    return ActionState.TUCK
                else:
                    return ActionState.PIKE
            else:
                # In dead zone — stay unknown
                self.invalid_frame_count += 1
                if self.invalid_frame_count >= UNKNOWN_FALLBACK_FRAMES:
                    self.invalid_frame_count = 0
                return ActionState.UNKNOWN

        elif self.state == ActionState.STRAIGHT:
            if trunk_thigh <= TRUNK_THIGH_ENTER:
                self.invalid_frame_count = 0
                if thigh_shin <= THIGH_SHIN_ENTER:
                    return ActionState.TUCK
                else:
                    return ActionState.PIKE
            else:
                # Stay STRAIGHT (above enter threshold — either in dead zone or above exit)
                self.invalid_frame_count = 0
                return ActionState.STRAIGHT

        elif self.state == ActionState.PIKE:
            if trunk_thigh > TRUNK_THIGH_EXIT:
                self.invalid_frame_count = 0
                return ActionState.STRAIGHT
            elif thigh_shin <= THIGH_SHIN_ENTER:
                self.invalid_frame_count = 0
                return ActionState.TUCK
            elif trunk_thigh <= TRUNK_THIGH_EXIT and thigh_shin > THIGH_SHIN_ENTER:
                # Stay PIKE
                self.invalid_frame_count = 0
                return ActionState.PIKE
            else:
                self.invalid_frame_count += 1
                if self.invalid_frame_count >= UNKNOWN_FALLBACK_FRAMES:
                    self.invalid_frame_count = 0
                    return ActionState.UNKNOWN
                return ActionState.PIKE

        elif self.state == ActionState.TUCK:
            if trunk_thigh > TRUNK_THIGH_EXIT:
                self.invalid_frame_count = 0
                return ActionState.STRAIGHT
            elif thigh_shin > THIGH_SHIN_EXIT:
                self.invalid_frame_count = 0
                return ActionState.PIKE
            elif trunk_thigh <= TRUNK_THIGH_EXIT and thigh_shin <= THIGH_SHIN_EXIT:
                # Stay TUCK
                self.invalid_frame_count = 0
                return ActionState.TUCK
            else:
                self.invalid_frame_count += 1
                if self.invalid_frame_count >= UNKNOWN_FALLBACK_FRAMES:
                    self.invalid_frame_count = 0
                    return ActionState.UNKNOWN
                return ActionState.TUCK

        return self.state

    def _compute_trunk_thigh_angle(self, landmarks, frame_shape) -> float:
        """Shoulder-Hip-Knee angle averaged across both sides."""
        h, w = frame_shape
        angles = []

        for side in ("left", "right"):
            shoulder = landmarks[LANDMARK[f"{side}_shoulder"]]
            hip = landmarks[LANDMARK[f"{side}_hip"]]
            knee = landmarks[LANDMARK[f"{side}_knee"]]

            if shoulder.visibility < 0.3 or hip.visibility < 0.3 or knee.visibility < 0.3:
                continue

            a = [shoulder.x * w, shoulder.y * h]
            b = [hip.x * w, hip.y * h]
            c = [knee.x * w, knee.y * h]
            angles.append(_angle_between(a, b, c))

        return sum(angles) / len(angles) if angles else None

    def _compute_thigh_shin_angle(self, landmarks, frame_shape) -> float:
        """Hip-Knee-Ankle angle averaged across both sides."""
        h, w = frame_shape
        angles = []

        for side in ("left", "right"):
            hip = landmarks[LANDMARK[f"{side}_hip"]]
            knee = landmarks[LANDMARK[f"{side}_knee"]]
            ankle = landmarks[LANDMARK[f"{side}_ankle"]]

            if hip.visibility < 0.3 or knee.visibility < 0.3 or ankle.visibility < 0.3:
                continue

            a = [hip.x * w, hip.y * h]
            b = [knee.x * w, knee.y * h]
            c = [ankle.x * w, ankle.y * h]
            angles.append(_angle_between(a, b, c))

        return sum(angles) / len(angles) if angles else None
