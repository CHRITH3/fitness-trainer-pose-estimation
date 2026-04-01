"""
Trampoline analysis configuration — all thresholds and constants.
"""

# MediaPipe landmark indices
LANDMARK = {
    "nose": 0,
    "left_shoulder": 11,
    "right_shoulder": 12,
    "left_hip": 23,
    "right_hip": 24,
    "left_knee": 25,
    "right_knee": 26,
    "left_ankle": 27,
    "right_ankle": 28,
    "left_foot_index": 31,
    "right_foot_index": 32,
}

# --- Jump Detection ---
VELOCITY_WINDOW = 5               # frames for finite-difference velocity
VELOCITY_SMOOTH_WINDOW = 3        # frames for velocity moving average smoothing
LANDING_VEL_THRESHOLD = 0.01      # y-velocity reversal threshold (positive = descending)
TAKEOFF_VEL_THRESHOLD = -0.01     # negative = ascending
MIN_JUMP_FRAMES = 8               # minimum frames between two landings
MIN_FLIGHT_FRAMES = 4             # minimum airborne frames to count as a jump
ANKLE_Y_EMA_ALPHA = 0.05          # EMA decay for ankle baseline tracking

# --- Action Classification (hysteresis) ---
TRUNK_THIGH_ENTER = 132.0         # degrees: enter pike/tuck zone
TRUNK_THIGH_EXIT = 138.0          # degrees: exit back to straight
THIGH_SHIN_ENTER = 132.0          # degrees: enter tuck zone
THIGH_SHIN_EXIT = 138.0           # degrees: exit back to pike
STRAIGHT_THRESHOLD = 135.0        # primary boundary (reference)
UNKNOWN_FALLBACK_FRAMES = 6       # consecutive invalid frames before Unknown

# --- Straddle Detection ---
STRADDLE_LEG_SPREAD_ENTER = 1.8   # ankle_dist/hip_width ratio to enter straddle
STRADDLE_LEG_SPREAD_EXIT = 1.4    # ratio to exit straddle (hysteresis)
TOGETHER_THRESHOLD = 1.2          # legs considered "together" below this ratio

# --- Intermediate Bounce Detection ---
INTERMEDIATE_MAX_FLIGHT_FRAMES = 6
