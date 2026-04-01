"""
ActionClassifier — Tuck / Pike / Straight / Straddle classification with hysteresis.

Only active during the flight phase. Uses shoulder-hip-knee (trunk-thigh)
and hip-knee-ankle (thigh-shin) angles averaged across both sides,
plus leg spread ratio (ankle distance / hip width) for straddle detection.
"""

import math
from enum import Enum
from collections import Counter

from trampoline.config import (
    LANDMARK, TRUNK_THIGH_ENTER, TRUNK_THIGH_EXIT,
    THIGH_SHIN_ENTER, THIGH_SHIN_EXIT, STRAIGHT_THRESHOLD,
    UNKNOWN_FALLBACK_FRAMES,
    STRADDLE_LEG_SPREAD_ENTER, STRADDLE_LEG_SPREAD_EXIT, TOGETHER_THRESHOLD,
)


class ActionState(Enum):
    UNKNOWN = "Unknown"
    STRAIGHT = "Straight"
    PIKE = "Pike"
    TUCK = "Tuck"
    STRADDLE = "Straddle"


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


def _distance(a, b) -> float:
    """Euclidean distance between two 2D points."""
    return math.sqrt((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2)


class ActionClassifier:
    def __init__(self):
        self.state = ActionState.UNKNOWN
        self.invalid_frame_count = 0
        self._phase = "contact"
        self._per_jump_classifications = []
        self.trunk_thigh_angle = 0.0
        self.thigh_shin_angle = 0.0
        self.leg_spread_ratio = 0.0

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
        """
        if self._phase != "flight":
            return ActionState.UNKNOWN

        trunk_thigh = self._compute_trunk_thigh_angle(landmarks, frame_shape)
        thigh_shin = self._compute_thigh_shin_angle(landmarks, frame_shape)
        leg_spread = self._compute_leg_spread_ratio(landmarks, frame_shape)

        if trunk_thigh is None or thigh_shin is None:
            self.invalid_frame_count += 1
            if self.invalid_frame_count >= UNKNOWN_FALLBACK_FRAMES:
                self.state = ActionState.UNKNOWN
                self.invalid_frame_count = 0
            self._per_jump_classifications.append(self.state)
            return self.state

        self.trunk_thigh_angle = trunk_thigh
        self.thigh_shin_angle = thigh_shin
        self.leg_spread_ratio = leg_spread if leg_spread is not None else 0.0

        new_state = self._apply_hysteresis(trunk_thigh, thigh_shin, leg_spread)
        self.state = new_state
        self._per_jump_classifications.append(new_state)
        return new_state

    def get_jump_action(self) -> ActionState:
        """Determine dominant action via majority vote on mid-flight 60% frames."""
        valid = [s for s in self._per_jump_classifications if s != ActionState.UNKNOWN]
        if not valid:
            return ActionState.UNKNOWN
        n = len(valid)
        trim = n // 5  # 20% from each end
        if trim > 0 and n > 4:
            valid = valid[trim : n - trim]
        counts = Counter(valid)
        return counts.most_common(1)[0][0]

    def _apply_hysteresis(self, trunk_thigh: float, thigh_shin: float,
                          leg_spread: float = None) -> ActionState:
        """Apply hysteresis FSM transitions with straddle support."""

        # --- Straddle check first (overrides angle-based classification) ---
        if leg_spread is not None:
            if self.state == ActionState.STRADDLE:
                # Exit straddle only when legs come together
                if leg_spread < STRADDLE_LEG_SPREAD_EXIT:
                    # Fall through to angle-based classification below
                    pass
                else:
                    self.invalid_frame_count = 0
                    return ActionState.STRADDLE
            else:
                # Enter straddle when legs spread wide
                if leg_spread > STRADDLE_LEG_SPREAD_ENTER:
                    self.invalid_frame_count = 0
                    return ActionState.STRADDLE

        # --- Angle-based classification (tuck/pike/straight) ---
        # These require legs together (leg_spread < TOGETHER_THRESHOLD if available)
        legs_together = (leg_spread is None or leg_spread < TOGETHER_THRESHOLD)

        if self.state == ActionState.UNKNOWN or self.state == ActionState.STRADDLE:
            if trunk_thigh > STRAIGHT_THRESHOLD:
                self.invalid_frame_count = 0
                return ActionState.STRAIGHT
            elif trunk_thigh <= TRUNK_THIGH_ENTER and legs_together:
                self.invalid_frame_count = 0
                if thigh_shin <= THIGH_SHIN_ENTER:
                    return ActionState.TUCK
                else:
                    return ActionState.PIKE
            else:
                self.invalid_frame_count += 1
                if self.invalid_frame_count >= UNKNOWN_FALLBACK_FRAMES:
                    self.invalid_frame_count = 0
                return ActionState.UNKNOWN

        elif self.state == ActionState.STRAIGHT:
            if trunk_thigh <= TRUNK_THIGH_ENTER and legs_together:
                self.invalid_frame_count = 0
                if thigh_shin <= THIGH_SHIN_ENTER:
                    return ActionState.TUCK
                else:
                    return ActionState.PIKE
            else:
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

    def _compute_leg_spread_ratio(self, landmarks, frame_shape) -> float:
        """
        Compute leg spread = ankle distance / hip width.
        Returns None if landmarks not visible.
        A ratio of ~1.0 means legs at hip width (normal standing).
        Ratio > 1.8 indicates straddle position.
        """
        h, w = frame_shape
        l_ankle = landmarks[LANDMARK["left_ankle"]]
        r_ankle = landmarks[LANDMARK["right_ankle"]]
        l_hip = landmarks[LANDMARK["left_hip"]]
        r_hip = landmarks[LANDMARK["right_hip"]]

        if (l_ankle.visibility < 0.3 or r_ankle.visibility < 0.3 or
                l_hip.visibility < 0.3 or r_hip.visibility < 0.3):
            return None

        ankle_dist = _distance([l_ankle.x * w, l_ankle.y * h],
                               [r_ankle.x * w, r_ankle.y * h])
        hip_width = _distance([l_hip.x * w, l_hip.y * h],
                              [r_hip.x * w, r_hip.y * h])

        if hip_width < 1:
            return None

        return ankle_dist / hip_width
