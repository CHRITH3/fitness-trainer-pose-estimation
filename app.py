# CRITICAL: Set environment variables BEFORE any TensorFlow/MediaPipe imports
import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TF_NUM_INTEROP_THREADS"] = "1"
os.environ["TF_NUM_INTRAOP_THREADS"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"  # Suppress TF warnings

from flask import Flask, render_template, Response, request, jsonify, session, redirect, url_for
import cv2
import threading
import time
import sys
import traceback
import logging
import uuid
import json
import base64
from datetime import datetime, timezone
import numpy as np

# Set up logging
logging.basicConfig(level=logging.DEBUG, 
                   format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                   handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Import attempt with error handling
try:
    from pose_estimation.estimation import PoseEstimator
    # NEW: Import Exercise Engine
    from exercises.engine import ExerciseEngine
    from exercises.loader import get_available_exercises, get_exercise_info
    from utils.draw_text_with_background import draw_text_with_background
    logger.info("Successfully imported pose estimation modules")
except ImportError as e:
    logger.error(f"Failed to import required modules: {e}")
    traceback.print_exc()
    sys.exit(1)

# Try to import WorkoutLogger with fallback
try:
    from db.workout_logger import WorkoutLogger
    workout_logger = WorkoutLogger()
    logger.info("Successfully initialized workout logger")
except ImportError:
    logger.warning("WorkoutLogger import failed, creating dummy class")
    
    class DummyWorkoutLogger:
        def __init__(self):
            pass
        def log_workout(self, *args, **kwargs):
            return {}
        def get_recent_workouts(self, *args, **kwargs):
            return []
        def get_weekly_stats(self, *args, **kwargs):
            return {}
        def get_exercise_distribution(self, *args, **kwargs):
            return {}
        def get_user_stats(self, *args, **kwargs):
            return {'total_workouts': 0, 'total_exercises': 0, 'streak_days': 0}
    
    workout_logger = DummyWorkoutLogger()

logger.info("Setting up Flask application")
app = Flask(__name__)
app.secret_key = 'fitness_trainer_secret_key'  # Required for sessions

# Global variables
camera = None
output_frame = None
lock = threading.Lock()
exercise_running = False
exercise_engine = ExerciseEngine()  # NEW: Global exercise engine
current_exercise_type = None
exercise_goal = 0
sets_completed = 0
sets_goal = 0
workout_start_time = None

# FPS tracking
fps_counter = 0
fps_start_time = time.time()
current_fps = 0

# Video analysis storage
UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
video_analyses = {}  # Store ongoing video analyses

# Video upload limits
MAX_VIDEO_SIZE_MB = 50  # Max 50MB video
MAX_VIDEO_DURATION_SEC = 120  # Max 2 minutes
TRAMPOLINE_PENDING_TTL_SECONDS = 60 * 60  # 1 hour for abandoned calibration jobs

TRAMPOLINE_CORNER_ORDER = ["front_left", "front_right", "back_right", "back_left"]


def _extract_first_frame_b64(filepath):
    cap = cv2.VideoCapture(filepath)
    try:
        if not cap.isOpened():
            return None, None, "Could not open video file"
        ok, frame = cap.read()
        if not ok:
            return None, None, "Could not read first video frame"
        ok_enc, buffer = cv2.imencode('.png', frame)
        if not ok_enc:
            return None, None, "Could not encode first video frame"
        encoded = base64.b64encode(buffer).decode('ascii')
        image_size = {"width": int(frame.shape[1]), "height": int(frame.shape[0])}
        return encoded, image_size, None
    finally:
        cap.release()


def _canonicalize_corners(corners, image_size=None):
    from trampoline.bed_tracker import validate_corners
    normalized = validate_corners(corners, image_size=image_size)
    return [{"name": p["name"], "x": round(float(p["x"]), 3), "y": round(float(p["y"]), 3)} for p in normalized]


def _corners_equal(a, b):
    if not a or not b or len(a) != len(b):
        return False
    for pa, pb in zip(a, b):
        if pa.get('name') != pb.get('name'):
            return False
        if abs(float(pa.get('x', 0)) - float(pb.get('x', 0))) > 1e-3:
            return False
        if abs(float(pa.get('y', 0)) - float(pb.get('y', 0))) > 1e-3:
            return False
    return True


def _normalize_trampoline_calibrations(data, image_size=None):
    from trampoline.bed_tracker import normalize_calibrations

    image_tuple = (int(image_size['width']), int(image_size['height'])) if image_size else None
    if data.get('calibrations') is not None:
        raw = data.get('calibrations')
    else:
        raw = [{
            'frame_index': 0,
            'time_s': 0.0,
            'corners_px': data.get('corners') or [],
        }]
    normalized = normalize_calibrations(raw, image_size=image_tuple)
    return [
        {
            'frame_index': int(item['frame_index']),
            'time_s': item.get('time_s'),
            'corners_px': _canonicalize_corners(item['corners_px']),
        }
        for item in normalized
    ]


def _calibrations_equal(a, b):
    if not a or not b or len(a) != len(b):
        return False
    for ca, cb in zip(a, b):
        if int(ca.get('frame_index', -1)) != int(cb.get('frame_index', -2)):
            return False
        ta, tb = ca.get('time_s'), cb.get('time_s')
        if ta is not None and tb is not None and abs(float(ta) - float(tb)) > 1e-3:
            return False
        if not _corners_equal(ca.get('corners_px'), cb.get('corners_px')):
            return False
    return True


def _corners_sidecar_path(video_id):
    return os.path.join(UPLOAD_FOLDER, f"{video_id}_corners.json")



def _remove_video_artifacts(video_id, analysis, include_processed=False):
    """Best-effort cleanup for uploaded videos, sidecars, and optional outputs."""
    paths = [analysis.get('filepath'), _corners_sidecar_path(video_id)]
    if include_processed:
        paths.extend([
            analysis.get('processed_video'),
            os.path.join(UPLOAD_FOLDER, f"{video_id}_results.json"),
            os.path.join(UPLOAD_FOLDER, f"{video_id}_processed.mp4"),
        ])
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as exc:
                logger.warning(f"Cleanup could not remove {path}: {exc}")


def cleanup_expired_pending_trampoline_uploads(now=None):
    """Expire abandoned trampoline uploads that never reached subprocess processing."""
    now = now or time.time()
    expired = []
    for video_id, analysis in list(video_analyses.items()):
        if analysis.get('mode') != 'trampoline':
            continue
        if analysis.get('status') not in ('uploaded_pending_calibration', 'calibration_rejected'):
            continue
        age = now - float(analysis.get('created_at', now))
        if age < TRAMPOLINE_PENDING_TTL_SECONDS:
            continue
        _remove_video_artifacts(video_id, analysis, include_processed=True)
        analysis.update({
            'status': 'expired',
            'state': 'EXPIRED',
            'progress': 0,
            'feedback': 'Pending trampoline calibration expired; please upload again',
            'error': 'Pending trampoline calibration expired',
            'filepath': None,
        })
        expired.append(video_id)
    return expired

def initialize_camera():
    global camera
    if camera is None:
        try:
            print("[INFO] Attempting to initialize camera...")
            camera = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # Use DirectShow backend for better compatibility
            if not camera.isOpened():
                raise Exception("Camera could not be opened. Please check your device.")
            # Optimize camera settings
            camera.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
            camera.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
            camera.set(cv2.CAP_PROP_FPS, 30)
            print("[INFO] Camera initialized successfully.")
        except Exception as e:
            print(f"[ERROR] Failed to initialize camera: {e}")
            camera = None
    return camera

def release_camera():
    global camera
    if camera is not None:
        camera.release()
        camera = None

# Global pose estimator - ONLY ONE instance, created lazily when needed
_pose_estimator = None
_pose_estimator_lock = threading.Lock()

def get_pose_estimator():
    """Get or create the single PoseEstimator instance"""
    global _pose_estimator
    with _pose_estimator_lock:
        if _pose_estimator is None:
            _pose_estimator = PoseEstimator()
        return _pose_estimator

def generate_frames():
    global output_frame, lock, exercise_running, exercise_engine
    global exercise_goal, sets_completed, sets_goal
    global fps_counter, fps_start_time, current_fps

    # NO PoseEstimator here - only create when exercise starts
    pose_estimator = None

    # Initialize camera when video feed starts
    if not initialize_camera():
        print("[ERROR] Camera initialization failed. Exiting frame generation.")
        return

    while True:
        if camera is None:
            if not initialize_camera():
                time.sleep(0.1)
                continue

        success, frame = camera.read()
        if not success:
            print("[WARNING] Failed to read frame from camera. Retrying...")
            retry_count = 0
            while retry_count < 3 and not success:
                time.sleep(0.1)  # Short delay before retry
                success, frame = camera.read()
                retry_count += 1
                print(f"[DEBUG] Retry {retry_count}: Frame read {'successful' if success else 'failed'}.)")

            if not success:
                print("[ERROR] Unable to read frame after multiple retries. Check camera connection.")
                break

        # FPS calculation
        fps_counter += 1
        elapsed = time.time() - fps_start_time
        if elapsed >= 1.0:
            current_fps = fps_counter / elapsed
            fps_counter = 0
            fps_start_time = time.time()

        # Only process frames if an exercise is running
        if exercise_running and exercise_engine.exercise:
            # Lazy load pose estimator only when needed
            if pose_estimator is None:
                pose_estimator = get_pose_estimator()

            # Process with pose estimation
            results = pose_estimator.estimate_pose(frame, exercise_engine.exercise_name)

            if results.pose_landmarks:
                # NEW: Use Exercise Engine to process frame
                result = exercise_engine.process_frame(frame, results.pose_landmarks.landmark)

                if result["success"]:
                    # Draw status overlay
                    exercise_engine.draw_status_overlay(frame, exercise_goal, sets_goal, sets_completed)

                    # Draw Form Score
                    exercise_engine.draw_form_score(frame)

                    # Check if rep goal is reached for current set
                    current_counter = exercise_engine.get_counter()
                    if current_counter >= exercise_goal:
                        sets_completed += 1
                        exercise_engine.reset()

                        # Check if all sets are completed
                        if sets_completed >= sets_goal:
                            exercise_running = False
                            # Final form score display
                            avg_score = exercise_engine.exercise.avg_form_score if exercise_engine.exercise else 0
                            draw_text_with_background(frame, f"WORKOUT COMPLETE! Avg Score: {avg_score}", 
                                                    (frame.shape[1]//2 - 200, frame.shape[0]//2),
                                                    cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), (0, 200, 0), 2)
                        else:
                            draw_text_with_background(frame, f"SET {sets_completed} COMPLETE! Rest for 30 sec", 
                                                    (frame.shape[1]//2 - 200, frame.shape[0]//2),
                                                    cv2.FONT_HERSHEY_DUPLEX, 1.0, (255, 255, 255), (0, 0, 200), 2)
        else:
            # Display welcome message if no exercise is running
            cv2.putText(frame, "Select an exercise to begin", (frame.shape[1]//2 - 180, frame.shape[0]//2),
                       cv2.FONT_HERSHEY_DUPLEX, 0.8, (255, 255, 255), 1)
            
            # Show available exercises
            exercises = get_available_exercises()
            cv2.putText(frame, f"Available: {len(exercises)} exercises", (frame.shape[1]//2 - 120, frame.shape[0]//2 + 40),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, (200, 200, 200), 1)
        
        # Display FPS
        cv2.putText(frame, f"FPS: {current_fps:.1f}", (frame.shape[1] - 100, 30),
                   cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 1)
                
        # Encode the frame in JPEG format
        with lock:
            output_frame = frame.copy()
            
        # Yield the frame in byte format
        ret, buffer = cv2.imencode('.jpg', output_frame)
        frame = buffer.tobytes()
        yield (b'--frame\r\n'
               b'Content-Type: image/jpeg\r\n\r\n' + frame + b'\r\n')

@app.route('/')
def index():
    """Home page with exercise selection"""
    logger.info("Rendering index page")
    try:
        return render_template('index.html')
    except Exception as e:
        logger.error(f"Error rendering index: {e}")
        return f"Error rendering template: {str(e)}", 500

@app.route('/dashboard')
def dashboard():
    """Dashboard page with workout statistics"""
    logger.info("Rendering dashboard page")
    try:
        # Get data for the dashboard
        recent_workouts = workout_logger.get_recent_workouts(5)
        weekly_stats = workout_logger.get_weekly_stats()
        exercise_distribution = workout_logger.get_exercise_distribution()
        user_stats = workout_logger.get_user_stats()
        
        # Format workouts for display
        formatted_workouts = []
        for workout in recent_workouts:
            formatted_workouts.append({
                'date': workout['date'],
                'exercise': workout['exercise_type'].replace('_', ' ').title(),
                'sets': workout['sets'],
                'reps': workout['reps'],
                'duration': f"{workout['duration_seconds'] // 60}:{workout['duration_seconds'] % 60:02d}"
            })
        
        # Calculate total workouts this week
        weekly_workout_count = sum(day['workout_count'] for day in weekly_stats.values())
        
        return render_template('dashboard.html',
                              recent_workouts=formatted_workouts,
                              weekly_workouts=weekly_workout_count,
                              total_workouts=user_stats['total_workouts'],
                              total_exercises=user_stats['total_exercises'],
                              streak_days=user_stats['streak_days'])
    except Exception as e:
        logger.error(f"Error in dashboard: {e}")
        traceback.print_exc()
        return f"Error loading dashboard: {str(e)}", 500

@app.route('/video_feed')
def video_feed():
    """Video streaming route"""
    return Response(generate_frames(),
                   mimetype='multipart/x-mixed-replace; boundary=frame')

@app.route('/stop_camera', methods=['POST'])
def stop_camera():
    """Stop and release camera"""
    global exercise_running
    exercise_running = False
    release_camera()
    logger.info("Camera stopped and released")
    return jsonify({'success': True})

@app.route('/start_exercise', methods=['POST'])
def start_exercise():
    """Start a new exercise based on user selection"""
    global exercise_running, exercise_engine, current_exercise_type
    global exercise_goal, sets_completed, sets_goal
    global workout_start_time
    
    data = request.json
    exercise_type = data.get('exercise_type')
    sets_goal = int(data.get('sets', 3))
    exercise_goal = int(data.get('reps', 10))
    
    # Initialize camera if not already done
    initialize_camera()
    
    # Reset counters
    sets_completed = 0
    workout_start_time = time.time()
    
    # NEW: Use Exercise Engine to load exercise from YAML
    available = get_available_exercises()
    if exercise_type not in available:
        return jsonify({'success': False, 'error': f'Invalid exercise type. Available: {available}'})
    
    # Load exercise
    if not exercise_engine.set_exercise(exercise_type):
        return jsonify({'success': False, 'error': f'Failed to load exercise: {exercise_type}'})
    
    current_exercise_type = exercise_type
    
    # Start the exercise
    exercise_running = True
    
    logger.info(f"Started exercise: {exercise_type}, goal: {exercise_goal} reps x {sets_goal} sets")
    
    return jsonify({
        'success': True,
        'exercise': exercise_type,
        'info': get_exercise_info(exercise_type)
    })

@app.route('/stop_exercise', methods=['POST'])
def stop_exercise():
    """Stop the current exercise and log the workout"""
    global exercise_running, exercise_engine, current_exercise_type
    global workout_start_time, sets_completed, exercise_goal, sets_goal
    
    if exercise_running and exercise_engine.exercise:
        # Calculate duration
        duration = int(time.time() - workout_start_time) if workout_start_time else 0
        
        # Get final form score
        avg_form_score = exercise_engine.exercise.avg_form_score
        
        # Log the workout
        current_counter = exercise_engine.get_counter()
        workout_logger.log_workout(
            exercise_type=current_exercise_type,
            sets=sets_completed + (1 if current_counter > 0 else 0),
            reps=exercise_goal,
            duration_seconds=duration
        )
        
        logger.info(f"Workout stopped. Avg form score: {avg_form_score}")
    
    exercise_running = False
    return jsonify({'success': True})

@app.route('/get_status', methods=['GET'])
def get_status():
    """Return current exercise status"""
    global exercise_engine, sets_completed, exercise_goal, sets_goal, exercise_running
    
    status = {
        'exercise_running': exercise_running,
        'current_reps': exercise_engine.get_counter() if exercise_engine.exercise else 0,
        'current_set': sets_completed + 1 if exercise_running else 0,
        'total_sets': sets_goal,
        'rep_goal': exercise_goal
    }
    
    # Add form score if exercise is running
    if exercise_running and exercise_engine.exercise:
        ex_status = exercise_engine.get_status()
        status['form_score'] = ex_status.get('form_score', 100)
        status['avg_form_score'] = ex_status.get('avg_form_score', 100)
        status['form_grade'] = ex_status.get('form_grade', 'A')
    
    return jsonify(status)

@app.route('/exercises', methods=['GET'])
def list_exercises():
    """Return list of all available exercises"""
    exercises = get_available_exercises()
    exercises_info = {ex: get_exercise_info(ex) for ex in exercises}
    return jsonify({
        'exercises': exercises,
        'info': exercises_info,
        'count': len(exercises)
    })

@app.route('/profile')
def profile():
    """User profile page"""
    # Default user data (would come from database in production)
    user = {
        'name': '',
        'initials': 'FT',
        'title': 'Amateur Athlete',
        'joined': 'January 2026',
        'age': None,
        'gender': None,
        'height': None,
        'weight': None
    }
    
    # Calculate stats from workout logger
    stats = {
        'total_workouts': 0,
        'total_reps': 0,
        'total_minutes': 0,
        'streak': 0,
        'weekly_workouts': 0,
        'today_reps': 0,
        'avg_form_score': 85
    }
    
    # Try to get stats from workout logger
    try:
        workout_stats = workout_logger.get_dashboard_stats()
        stats['total_workouts'] = workout_stats.get('total_workouts', 0)
        stats['streak'] = workout_stats.get('streak_days', 0)
        stats['weekly_workouts'] = workout_stats.get('weekly_workouts', 0)
        
        # Get total reps from recent workouts
        recent = workout_logger.get_recent_workouts(100)
        stats['total_reps'] = sum(w.get('reps', 0) for w in recent)
        stats['total_minutes'] = sum(w.get('duration', 0) for w in recent)
    except Exception as e:
        logger.warning(f"Could not load workout stats: {e}")
    
    # Get favorite exercises
    favorites = []
    try:
        exercise_stats = workout_logger.get_exercise_stats()
        favorites = [
            {'name': ex['exercise'].replace('_', ' ').title(), 'count': ex['count']}
            for ex in exercise_stats[:5]
        ]
    except Exception as e:
        logger.warning(f"Could not load favorites: {e}")
    
    # Settings defaults
    settings = {
        'notifications': True,
        'dark_mode': False,
        'sounds': True,
        'units': 'metric'
    }
    
    # Calculate progress percentages for goals
    stats['weekly_progress'] = min(100, int((stats['weekly_workouts'] / 5) * 100))
    stats['reps_progress'] = min(100, int((stats['today_reps'] / 50) * 100))
    stats['form_progress'] = min(100, stats['avg_form_score'])
    
    return render_template('profile.html', 
                          user=user, 
                          stats=stats, 
                          favorites=favorites,
                          settings=settings)

@app.route('/api/profile/update', methods=['POST'])
def update_profile():
    """Update user profile - API endpoint"""
    try:
        data = request.get_json()
        # In a real app, this would save to a database
        # For now, we just acknowledge the update
        return jsonify({'success': True, 'message': 'Profile updated'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

# ============================================
# VIDEO ANALYSIS ROUTES
# ============================================

@app.route('/video_analysis')
def video_analysis():
    """Video analysis page"""
    return render_template('video_analysis.html', mode=request.args.get('mode', 'fitness'))

@app.route('/api/video/upload', methods=['POST'])
def upload_video():
    """Upload video for analysis"""
    cleanup_expired_pending_trampoline_uploads()
    if 'video' not in request.files:
        return jsonify({'success': False, 'error': 'No video file provided'})
    
    video_file = request.files['video']
    exercise_type = request.form.get('exercise_type')
    
    if not exercise_type:
        return jsonify({'success': False, 'error': 'No exercise type specified'})
    
    if video_file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'})
    
    # Check file size (in memory before saving)
    video_file.seek(0, 2)  # Seek to end
    file_size = video_file.tell()
    video_file.seek(0)  # Seek back to start
    
    max_size_bytes = MAX_VIDEO_SIZE_MB * 1024 * 1024
    if file_size > max_size_bytes:
        return jsonify({
            'success': False, 
            'error': f'Video çok büyük! Max {MAX_VIDEO_SIZE_MB}MB, yüklenen: {file_size / (1024*1024):.1f}MB'
        })
    
    # Generate unique ID
    video_id = str(uuid.uuid4())
    
    # Save video
    filename = f"{video_id}_{video_file.filename}"
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    video_file.save(filepath)
    
    # Check video duration / metadata
    fps = 30.0
    frame_count = 0
    cap = cv2.VideoCapture(filepath)
    if cap.isOpened():
        fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        duration = frame_count / max(fps, 1e-6)
        cap.release()

        if duration > MAX_VIDEO_DURATION_SEC:
            os.remove(filepath)  # Delete the uploaded file
            return jsonify({
                'success': False,
                'error': f'Video çok uzun! Max {MAX_VIDEO_DURATION_SEC} saniye, yüklenen: {duration:.0f} saniye'
            })
    
    # Initialize analysis state
    is_trampoline = (exercise_type == "trampoline")

    initial_status = 'uploaded_pending_calibration' if is_trampoline else 'processing'
    video_analyses[video_id] = {
        'mode': 'trampoline' if is_trampoline else 'fitness',
        'status': initial_status,
        'progress': 0,
        'filepath': filepath,
        'exercise_type': exercise_type,
        'reps': 0,
        'form_score': 100,
        'avg_form_score': 100,
        'grade': 'A' if not is_trampoline else '--',
        'state': 'PENDING_CALIBRATION' if is_trampoline else 'READY',
        'feedback': 'Awaiting bed corner calibration' if is_trampoline else '',
        'engine': None if is_trampoline else ExerciseEngine(),
        'total_frames': int(frame_count or 0),
        'processed_frames': 0,
        'video_fps': float(fps or 30.0),
        'current_action': '--',
        'completed_jumps': [],
        'corner_order': TRAMPOLINE_CORNER_ORDER if is_trampoline else None,
        'corners': None,
        'started': False,
        'created_at': time.time(),
    }

    # Load exercise into engine (not used in subprocess mode, but keep for status)
    if not is_trampoline and video_analyses[video_id]['engine']:
        video_analyses[video_id]['engine'].set_exercise(exercise_type)

    if is_trampoline:
        first_frame_b64, image_size, frame_error = _extract_first_frame_b64(filepath)
        if frame_error:
            video_analyses[video_id]['status'] = 'error'
            video_analyses[video_id]['error'] = frame_error
            return jsonify({'success': False, 'error': frame_error})
        video_analyses[video_id]['image_size'] = image_size
        logger.info(f"Trampoline video uploaded pending calibration: {video_id}")
        return jsonify({
            'success': True,
            'video_id': video_id,
            'status': 'uploaded_pending_calibration',
            'message': 'Video uploaded; bed corner calibration required',
            'first_frame_b64': first_frame_b64,
            'first_frame_image': f"data:image/png;base64,{first_frame_b64}",
            'image_size': image_size,
            'corner_order': TRAMPOLINE_CORNER_ORDER,
            'video_fps': float(fps or 30.0),
            'total_frames': int(frame_count or 0),
        })

    # Start background processing using subprocess for non-trampoline mode
    thread = threading.Thread(target=process_video_subprocess, args=(video_id,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'video_id': video_id,
        'message': 'Video uploaded, processing started'
    })


@app.route('/api/video/trampoline/start', methods=['POST'])
def start_trampoline_analysis():
    """Start trampoline analysis after pre-analysis bed keyframe calibration."""
    cleanup_expired_pending_trampoline_uploads()
    data = request.get_json(silent=True) or {}
    video_id = data.get('video_id')

    analysis = video_analyses.get(video_id)
    if not analysis:
        return jsonify({'success': False, 'status': 'not_found', 'error': 'Video ID not found'}), 404
    if analysis.get('mode') != 'trampoline':
        return jsonify({'success': False, 'error': 'This endpoint is only for trampoline videos'}), 400

    image_size = analysis.get('image_size')
    image_tuple = (int(image_size['width']), int(image_size['height'])) if image_size else None

    status = analysis.get('status')
    existing_calibrations = analysis.get('calibrations')
    if status == 'completed':
        return jsonify({
            'success': True,
            'video_id': video_id,
            'status': 'completed',
            'message': 'Analysis already completed',
            'processed_video_url': f'/api/video/processed/{video_id}' if analysis.get('processed_video') else None,
        })
    if status == 'processing':
        try:
            requested = _normalize_trampoline_calibrations(data, analysis.get('image_size'))
        except Exception:
            requested = None
        if requested and _calibrations_equal(existing_calibrations, requested):
            return jsonify({
                'success': True,
                'video_id': video_id,
                'status': status,
                'message': 'Analysis already started',
            })
        return jsonify({'success': False, 'status': status, 'error': 'Analysis already started with different calibrations'}), 409

    if status not in ('uploaded_pending_calibration', 'calibration_rejected'):
        return jsonify({'success': False, 'status': status, 'error': 'Video is not ready for calibration start'}), 400

    try:
        calibrations = _normalize_trampoline_calibrations(data, analysis.get('image_size'))
    except Exception as e:
        analysis['status'] = 'calibration_rejected'
        analysis['state'] = 'CALIBRATION_REJECTED'
        analysis['error'] = str(e)
        analysis['feedback'] = str(e)
        return jsonify({'success': False, 'status': 'calibration_rejected', 'error': str(e)}), 400

    first = calibrations[0]
    sidecar = {
        'schema_version': 2,
        'video_id': video_id,
        'exercise_type': 'trampoline',
        'frame_index': first['frame_index'],
        'time_s': first.get('time_s'),
        'image_size': analysis.get('image_size'),
        'corner_order': TRAMPOLINE_CORNER_ORDER,
        'corners_px': first['corners_px'],
        'calibrations': calibrations,
        'bed_dimensions_m': {'width': 4.28, 'length': 2.14},
        'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    }
    sidecar_path = _corners_sidecar_path(video_id)
    tmp_path = f"{sidecar_path}.tmp"
    with open(tmp_path, 'w') as f:
        json.dump(sidecar, f)
    os.replace(tmp_path, sidecar_path)

    analysis['corners'] = first['corners_px']
    analysis['calibrations'] = calibrations
    analysis['status'] = 'processing'
    analysis['state'] = 'PROCESSING'
    analysis['feedback'] = f"Processing trampoline video with {len(canonical_calibrations)} calibration(s)"
    analysis['error'] = None
    analysis['started'] = True

    thread = threading.Thread(target=process_video_subprocess, args=(video_id,))
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'video_id': video_id,
        'status': 'processing',
        'message': 'Trampoline analysis started',
        'calibration_count': len(calibrations),
    })

def process_video_subprocess(video_id):
    """Process video in a separate subprocess to avoid memory issues"""
    import subprocess
    import json
    
    logger.info(f"Starting video processing (subprocess) for {video_id}")
    
    analysis = video_analyses.get(video_id)
    if not analysis:
        logger.error(f"Analysis not found for {video_id}")
        return
    
    analysis['status'] = 'processing'
    
    # Output paths
    output_json_path = os.path.join(UPLOAD_FOLDER, f"{video_id}_results.json")
    output_video_path = os.path.join(UPLOAD_FOLDER, f"{video_id}_processed.mp4")
    
    try:
        # Run video processor in subprocess WITH output video
        cmd = [
            sys.executable,  # Use same Python interpreter
            'video_processor.py',
            analysis['filepath'],
            analysis['exercise_type'],
            output_json_path,
            output_video_path  # NEW: Output video with skeleton overlay
        ]
        
        logger.info(f"Running subprocess: {' '.join(cmd)}")
        
        # Start subprocess - capture output for debugging
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,  # Combine stderr with stdout
            cwd=os.path.dirname(os.path.abspath(__file__)),
            text=True,
            bufsize=1
        )
        
        # Monitor progress by reading output JSON periodically
        while process.poll() is None:
            # Read any available output
            try:
                line = process.stdout.readline()
                if line:
                    logger.info(f"[Subprocess] {line.strip()}")
            except:
                pass
            
            time.sleep(0.3)
            try:
                if os.path.exists(output_json_path):
                    with open(output_json_path, 'r') as f:
                        results = json.load(f)
                    analysis['progress'] = results.get('progress', 0)
                    analysis['reps'] = results.get('reps', 0)
                    analysis['form_score'] = results.get('form_score', 100)
                    analysis['avg_form_score'] = results.get('avg_form_score', 100)
                    analysis['grade'] = results.get('grade', 'A')
                    analysis['state'] = results.get('state', 'UNKNOWN')
                    analysis['feedback'] = results.get('feedback', '')
                    # Trampoline-specific fields
                    if results.get('mode') == 'trampoline':
                        analysis['current_action'] = results.get('current_action', '--')
                        analysis['completed_jumps'] = results.get('completed_jumps', [])
            except:
                pass
        
        # Process finished - read final results
        stdout, stderr = process.communicate()

        if process.returncode == 0 and os.path.exists(output_json_path):
            with open(output_json_path, 'r') as f:
                results = json.load(f)

            analysis['progress'] = 100

            if results.get('error'):
                analysis['status'] = 'error' # 先判断子进程结果里有没有错误
                analysis['error'] = results['error']
                analysis['reps'] = results.get('reps', 0)
                analysis['form_score'] = results.get('form_score', 0)
                analysis['avg_form_score'] = results.get('avg_form_score', 0)
                analysis['grade'] = results.get('grade', 'F')
                analysis['state'] = results.get('state', 'ERROR')
                analysis['feedback'] = results.get('feedback', results['error'])
            else:
                analysis['status'] = results.get('status', 'completed')
                analysis['reps'] = results.get('reps', 0)
                analysis['form_score'] = results.get('form_score', 100)
                analysis['avg_form_score'] = results.get('avg_form_score', 100)
                analysis['grade'] = results.get('grade', 'A')
                analysis['state'] = results.get('state', 'COMPLETED')
                analysis['feedback'] = results.get('feedback', '')

            # Trampoline-specific final fields
            if results.get('mode') == 'trampoline':
                analysis['current_action'] = results.get('current_action', '--')
                analysis['completed_jumps'] = results.get('completed_jumps', [])

            # Video metadata for LLM report
            analysis['fps'] = results.get('fps', 30)
            analysis['total_frames'] = results.get('total_frames', 0)
            analysis['resolution'] = results.get('resolution', 'unknown')
            
            # Get actual output video path from results (extension may have changed)
            actual_output_video = results.get('output_video', output_video_path)
            if actual_output_video and os.path.exists(actual_output_video):
                analysis['processed_video'] = actual_output_video
            elif os.path.exists(output_video_path):
                analysis['processed_video'] = output_video_path
            else:
                # Try .avi extension as fallback
                avi_path = output_video_path.rsplit('.', 1)[0] + '.avi'
                if os.path.exists(avi_path):
                    analysis['processed_video'] = avi_path
                else:
                    analysis['processed_video'] = None
            
            if results.get('error'):
                analysis['status'] = 'error'
                analysis['error'] = results['error']
            
            logger.info(f"Video processing completed: {analysis['reps']} reps, output: {output_video_path}")
        else:
            analysis['status'] = 'error'
            err_text = stderr or stdout or f"Subprocess exited with code {process.returncode}"
            analysis['error'] = f"Subprocess failed: {err_text}"
            logger.error(f"Subprocess error: {err_text}")
        
        # Cleanup JSON file (keep processed video for download)
        try:
            if os.path.exists(output_json_path):
                os.remove(output_json_path)
            # Delete original video and calibration sidecar (keep processed one)
            _remove_video_artifacts(video_id, analysis, include_processed=False)
        except Exception as e:
            logger.warning(f"Cleanup error: {e}")
            
    except Exception as e:
        logger.error(f"Subprocess error: {e}")
        analysis['status'] = 'error'
        analysis['error'] = str(e)

@app.route('/api/video/processed/<video_id>', methods=['GET'])
def get_processed_video(video_id):
    """Serve the processed video with skeleton overlay"""
    from flask import send_file
    
    analysis = video_analyses.get(video_id)
    
    if not analysis:
        return jsonify({'error': 'Video ID not found'}), 404
    
    processed_video = analysis.get('processed_video')
    if not processed_video or not os.path.exists(processed_video):
        return jsonify({'error': 'Processed video not ready'}), 404
    
    # Determine MIME type based on extension
    if processed_video.endswith('.avi'):
        mimetype = 'video/x-msvideo'
    elif processed_video.endswith('.webm'):
        mimetype = 'video/webm'
    else:
        mimetype = 'video/mp4'
    
    return send_file(processed_video, mimetype=mimetype, as_attachment=False)

@app.route('/api/video/status/<video_id>', methods=['GET'])
def get_video_status(video_id):
    """Get video analysis status"""
    cleanup_expired_pending_trampoline_uploads()
    analysis = video_analyses.get(video_id)
    
    if not analysis:
        return jsonify({'status': 'not_found', 'error': 'Video ID not found'})
    
    # Check if processed video is ready
    has_processed_video = False
    if analysis.get('processed_video') and os.path.exists(analysis.get('processed_video', '')):
        has_processed_video = True
    
    return jsonify({
        'status': analysis['status'],
        'progress': analysis['progress'],
        'reps': analysis['reps'],
        'form_score': analysis['form_score'],
        'avg_form_score': analysis['avg_form_score'],
        'grade': analysis['grade'],
        'state': analysis['state'],
        'feedback': analysis['feedback'],
        'error': analysis.get('error'),
        'has_processed_video': has_processed_video,
        'processed_video_url': f'/api/video/processed/{video_id}' if has_processed_video else None,
        'mode': analysis.get('mode', 'fitness'),
        'current_action': analysis.get('current_action', '--'),
        'completed_jumps': analysis.get('completed_jumps', []),
    })

@app.route('/api/video/llm_analysis/<video_id>', methods=['GET'])
def llm_analysis(video_id):
    """Stream LLM analysis of trampoline video results via SSE."""
    import json as _json

    def sse_message(payload):
        def generate_once():
            yield f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"

        return Response(
            generate_once(),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'}
        )

    analysis = video_analyses.get(video_id)

    if not analysis:
        return sse_message({'type': 'error', 'message': 'Video ID not found'})
    if analysis.get('mode') != 'trampoline':
        return sse_message({'type': 'error', 'message': 'LLM analysis only available for trampoline mode'})
    if analysis.get('status') != 'completed':
        return sse_message({'type': 'error', 'message': 'Video analysis not yet complete'})

    try:
        from trampoline.llm_service import (
            AnalysisReport, stream_llm_analysis, run_llm_analysis_sync,
            clean_chunk, segment_response, get_cached, set_cached,
            resolve_api_key, resolve_models,
        )
    except ImportError as e:
        return sse_message({'type': 'error', 'message': f'LLM service not available: {e}'})

    api_key = resolve_api_key()
    if not api_key:
        return sse_message({'type': 'error', 'message': 'QWEN_API_KEY or DASHSCOPE_API_KEY not configured'})

    # Check cache
    cached = get_cached(video_id)
    if cached:
        def cached_gen():
            yield f"data: {_json.dumps({'type': 'done', 'sections': cached['sections'], 'full_text': cached['full_text']}, ensure_ascii=False)}\n\n"
        return Response(cached_gen(), mimetype='text/event-stream',
                        headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    report = AnalysisReport.from_video_analysis(analysis)

    def generate():
        import threading
        fast_model, quality_model = resolve_models()

        # Shared state for quality model background thread
        quality_result = {"text": None, "error": None, "done": False}

        def run_quality():
            try:
                text = run_llm_analysis_sync(report, model=quality_model, timeout=90)
                if text.startswith("[ERROR]"):
                    quality_result["error"] = text
                else:
                    quality_result["text"] = text
            except Exception as e:
                quality_result["error"] = str(e)
            finally:
                quality_result["done"] = True

        # Start quality model in background
        quality_thread = threading.Thread(target=run_quality, daemon=True)
        quality_thread.start()

        # Stream fast model to frontend
        fast_full_text = ""
        prev_chunk = ""

        try:
            for raw_chunk in stream_llm_analysis(report, model=fast_model):
                cleaned = clean_chunk(raw_chunk, prev_chunk)
                if cleaned:
                    fast_full_text += cleaned
                    yield f"data: {_json.dumps({'type': 'chunk', 'text': cleaned}, ensure_ascii=False)}\n\n"
                    prev_chunk = cleaned

            # Fast model done
            yield f"data: {_json.dumps({'type': 'fast_done'}, ensure_ascii=False)}\n\n"

            # Wait for quality model (max 120s)
            quality_thread.join(timeout=120)

            # Prefer quality model result, fallback to fast
            if quality_result.get("text"):
                final_text = quality_result["text"]
                source = "quality"
            elif fast_full_text and not fast_full_text.startswith("[ERROR]"):
                final_text = fast_full_text
                source = "fast_fallback"
            else:
                yield f"data: {_json.dumps({'type': 'error', 'message': '两个模型均调用失败'}, ensure_ascii=False)}\n\n"
                return

            sections = segment_response(final_text)
            set_cached(video_id, final_text, sections)
            yield f"data: {_json.dumps({'type': 'done', 'sections': sections, 'full_text': final_text, 'source': source}, ensure_ascii=False)}\n\n"

        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            yield f"data: {_json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype='text/event-stream',
                    headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

@app.route('/api/video/analyze_frame', methods=['POST'])
def analyze_video_frame():
    """Analyze a single frame from video (real-time overlay)"""
    if 'frame' not in request.files:
        return jsonify({'success': False, 'error': 'No frame provided'})
    
    video_id = request.form.get('video_id')
    analysis = video_analyses.get(video_id)
    
    if not analysis:
        return jsonify({'success': False, 'error': 'Video ID not found'})
    
    # DISABLED: This endpoint creates new PoseEstimator which causes memory issues
    # Video analysis is handled by subprocess instead
    return jsonify({
        'success': False, 
        'error': 'Real-time frame analysis disabled. Use subprocess-based video analysis instead.',
        'reps': analysis.get('reps', 0) if analysis else 0,
        'form_score': analysis.get('form_score', 100) if analysis else 100,
        'grade': analysis.get('grade', 'A') if analysis else 'A',
        'state': analysis.get('state', 'PROCESSING') if analysis else 'PROCESSING',
        'feedback': analysis.get('feedback', '') if analysis else '',
        'current_action': analysis.get('current_action', '--') if analysis else '--'
    })

if __name__ == '__main__':
    try:
        # List available exercises on startup
        exercises = get_available_exercises()
        logger.info(f"Available exercises: {exercises}")
        
        logger.info("Starting the Flask application on http://127.0.0.1:5000")
        print("=" * 50)
        print("FITNESS TRAINER WITH POSE ESTIMATION")
        print("=" * 50)
        print(f"Available exercises: {len(exercises)}")
        for ex in exercises:
            print(f"   - {ex}")
        print("-" * 50)
        print("Trampoline mode: /video_analysis?mode=trampoline")
        print("-" * 50)
        print("Open http://127.0.0.1:5000 in your browser")
        print("=" * 50)
        app.run(debug=False, threaded=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        traceback.print_exc()
