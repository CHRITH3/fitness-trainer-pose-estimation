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
MIN_DESCENT_VEL = 0.05            # minimum positive (descending) peak velocity to count as valid landing
MIN_ASCENT_VEL = -0.05            # minimum negative (ascending) peak velocity to count as valid takeoff
MIN_JUMP_FRAMES = 8               # minimum frames between two landings
MIN_FLIGHT_FRAMES = 4             # minimum airborne frames to count as a jump

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

# --- Mid-Flight Voting ---
FLIGHT_TRIM_RATIO = 0.2           # trim 20% from each end of flight frames for action voting

# --- Bed Tracking / Plane Calibration ---
BED_WIDTH_M = 4.28
BED_LENGTH_M = 2.14
BED_MAX_FEATURES = 200
BED_FEATURE_QUALITY = 0.01
BED_FEATURE_MIN_DISTANCE = 8
BED_LK_WIN_SIZE = (15, 15)
BED_LK_MAX_LEVEL = 3
BED_FB_THRESHOLD = 1.0
BED_RANSAC_REPROJ_THRESH = 3.0
BED_REDETECT_INLIER_RATIO = 0.5
BED_REDETECT_INTERVAL = 30
BED_MIN_TRACK_POINTS = 20
BED_CORNER_MIN_DISTANCE_PX = 5.0
BED_MIN_QUAD_AREA_PX = 100.0
BED_MIN_QUAD_AREA_RATIO = 0.01
BED_OFF_BED_CONFIDENCE_DECAY = 0.25
BED_CORNER_ORDER = ["front_left", "front_right", "back_right", "back_left"]

# --- Landing Zone Classification ---
ZONE_CENTER_RADIUS_M = 0.5
ZONE_MID_RADIUS_M = 1.0
ZONE_EDGE_MARGIN_M = 0.3

# --- Bed Tracking Trust / Re-localization ---
BED_ACCEPT_INLIER_RATIO = 0.35
BED_MAX_AREA_RATIO_CHANGE = 1.75
BED_MIN_AREA_RATIO_CHANGE = 0.45
BED_MAX_CENTER_SHIFT_RATIO = 0.25
BED_ORB_MAX_CENTER_SHIFT_RATIO = 0.65
BED_MAX_EDGE_SCALE_CHANGE = 2.5
BED_MIN_EDGE_SCALE_CHANGE = 0.35
BED_BOUNDS_MARGIN_RATIO = 0.20
BED_TRACKING_LOST_AFTER_FAILURES = 3
BED_TRUSTED_CONFIDENCE = 0.60
BED_LOW_CONFIDENCE = 0.30
BED_ORB_MAX_FEATURES = 500
BED_ORB_MIN_MATCHES = 8
BED_ORB_RELOCALIZE_INTERVAL = 30
BED_ORB_RELOCALIZE_ON_FAILURE = True
BED_KEYFRAME_TRANSITION_FRAMES = 20
BED_MANUAL_MAX_CENTER_SHIFT_RATIO = 0.45
BED_MARKER_LINE_MAX_LINES = 6
