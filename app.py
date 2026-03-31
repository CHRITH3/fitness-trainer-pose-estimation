# CRITICAL: Set environment variables BEFORE any TensorFlow/MediaPipe imports
import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TF_NUM_INTEROP_THREADS"] = "1"
os.environ["TF_NUM_INTRAOP_THREADS"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"  # Suppress TF warnings

from flask import Flask, Response, jsonify, redirect, render_template, request, send_file, session, url_for
import cv2
import json
import threading
import time
import sys
import traceback
import logging
import uuid
import numpy as np
from pathlib import Path
from werkzeug.utils import secure_filename

from trampoline.bed_calibration import create_bed_calibration, load_calibration, save_calibration
from trampoline.bounce_segmenter import segment_analysis_dir
from trampoline.exporter import export_analysis_bundle
from trampoline.pipeline import (
    list_analysis_outputs,
    load_analysis_output,
    load_segmentation_payload,
    merge_segment_overrides,
    persist_label_override,
    persist_timeline_overrides,
    resolve_analysis_dir,
    resolve_repo_path,
    analyze_video,
    load_overrides_artifact,
)
from trampoline.schema import JumpSegment

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
TRAMPOLINE_UPLOAD_DIR = Path(UPLOAD_FOLDER) / "trampoline"
TRAMPOLINE_ARTIFACTS_DIR = Path("artifacts") / "trampoline"
TRAMPOLINE_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
TRAMPOLINE_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
trampoline_analyses = {}
trampoline_analyses_lock = threading.Lock()

# Video upload limits
MAX_VIDEO_SIZE_MB = 50  # Max 50MB video
MAX_VIDEO_DURATION_SEC = 120  # Max 2 minutes

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
    return render_template('video_analysis.html')


def get_trampoline_upload_dir() -> Path:
    """Return the upload directory used by the trampoline demo."""

    upload_dir = Path(app.config.get("TRAMPOLINE_UPLOAD_DIR", TRAMPOLINE_UPLOAD_DIR))
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_trampoline_artifacts_dir() -> Path:
    """Return the artifacts directory used by the trampoline demo."""

    artifacts_dir = Path(app.config.get("TRAMPOLINE_ARTIFACTS_DIR", TRAMPOLINE_ARTIFACTS_DIR))
    artifacts_dir.mkdir(parents=True, exist_ok=True)
    return artifacts_dir


def _load_timeline_payload(analysis_dir: Path) -> dict:
    """Load automatic and merged jump timeline data for one analysis directory."""

    segmentation = load_segmentation_payload(analysis_dir)
    overrides = load_overrides_artifact(analysis_dir)
    auto_segments = [
        JumpSegment.model_validate(item)
        for item in (segmentation or {}).get("jump_segments", [])
    ]
    merged_segments, manual_overrides = merge_segment_overrides(auto_segments, overrides)
    return {
        "segmentation": segmentation,
        "jump_segments": [segment.model_dump(mode="json") for segment in merged_segments],
        "manual_overrides": [override.model_dump(mode="json") for override in manual_overrides],
    }


def _build_trampoline_status_payload(analysis_id: str) -> dict:
    """Return one app-facing status payload for a trampoline analysis."""

    with trampoline_analyses_lock:
        job = dict(trampoline_analyses.get(analysis_id, {}))

    analysis_dir = resolve_analysis_dir(get_trampoline_artifacts_dir(), analysis_id)
    result = None
    if analysis_dir.is_dir():
        try:
            result = load_analysis_output(analysis_dir)
        except FileNotFoundError:
            result = None

    status = job.get("status", "done" if result else "missing")
    payload = {
        "analysis_id": analysis_id,
        "status": status,
        "source_video": job.get("source_video") or (result["source_video"] if result else None),
        "message": job.get("message", ""),
        "error": job.get("error"),
        "result": result,
    }
    return payload


def _run_trampoline_analysis_job(analysis_id: str) -> None:
    """Background worker for the Phase 1 trampoline analysis flow."""

    with trampoline_analyses_lock:
        job = trampoline_analyses.get(analysis_id)
        if not job:
            return
        job["status"] = "running"
        source_video = Path(job["source_video"])

    output_dir = resolve_analysis_dir(get_trampoline_artifacts_dir(), analysis_id)

    try:
        analyze_video(
            video_path=source_video,
            output_dir=output_dir,
            landmarks_only=True,
            analysis_id=analysis_id,
        )
        result = load_analysis_output(output_dir)
        with trampoline_analyses_lock:
            job = trampoline_analyses.get(analysis_id, {})
            job["status"] = "done"
            job["message"] = "Analysis completed."
            job["result"] = result
    except Exception as exc:  # pragma: no cover - exercised via route tests
        with trampoline_analyses_lock:
            job = trampoline_analyses.get(analysis_id, {})
            job["status"] = "failed"
            job["error"] = str(exc)
            job["message"] = "Analysis failed."


def _build_trampoline_bootstrap(analysis_id) -> dict:
    """Assemble initial page state for `/trampoline`."""

    artifacts_dir = get_trampoline_artifacts_dir()
    analyses = list_analysis_outputs(artifacts_dir)
    selected_analysis_id = analysis_id or (analyses[-1]["analysis_id"] if analyses else None)
    selected_result = None
    if selected_analysis_id:
        status_payload = _build_trampoline_status_payload(selected_analysis_id)
        selected_result = status_payload.get("result")

    sample_video = Path("samples/tra_demo/sample01.mp4")
    return {
        "selected_analysis_id": selected_analysis_id,
        "selected_result": selected_result,
        "analyses": analyses,
        "sample_video": str(sample_video),
    }


@app.route('/trampoline')
def trampoline_demo():
    """Single-person trampoline demo shell."""

    analysis_id = request.args.get("analysis_id")
    return render_template(
        'trampoline.html',
        bootstrap=_build_trampoline_bootstrap(analysis_id),
    )


@app.route('/api/trampoline/upload', methods=['POST'])
def trampoline_upload_video():
    """Upload one trampoline demo video and register an analysis id."""

    if 'video' not in request.files:
        return jsonify({'success': False, 'error': 'No video file provided'}), 400

    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    filename = secure_filename(video_file.filename)
    suffix = Path(filename).suffix.lower() or ".mp4"
    analysis_id = f"{Path(filename).stem or 'analysis'}-{uuid.uuid4().hex[:8]}"
    upload_path = get_trampoline_upload_dir() / f"{analysis_id}{suffix}"
    video_file.save(upload_path)

    with trampoline_analyses_lock:
        trampoline_analyses[analysis_id] = {
            "status": "uploaded",
            "source_video": str(upload_path),
            "message": "Upload complete. Ready to analyze.",
        }

    return jsonify(
        {
            'success': True,
            'analysis_id': analysis_id,
            'status': 'uploaded',
            'source_video': str(upload_path),
        }
    )


@app.route('/api/trampoline/analyze', methods=['POST'])
def trampoline_analyze_video():
    """Queue one uploaded video for Phase 1 landmark extraction."""

    payload = request.get_json(silent=True) or {}
    analysis_id = payload.get("analysis_id")
    if not analysis_id:
        return jsonify({'success': False, 'error': 'analysis_id is required'}), 400

    with trampoline_analyses_lock:
        job = trampoline_analyses.get(analysis_id)
        if not job:
            return jsonify({'success': False, 'error': 'Unknown analysis_id'}), 404
        if job.get("status") in {"queued", "running"}:
            return jsonify({'success': True, 'analysis_id': analysis_id, 'status': job["status"]}), 202
        job["status"] = "queued"
        job["message"] = "Analysis queued."

    worker = threading.Thread(target=_run_trampoline_analysis_job, args=(analysis_id,))
    worker.daemon = True
    worker.start()

    return jsonify({'success': True, 'analysis_id': analysis_id, 'status': 'queued'}), 202


@app.route('/api/trampoline/status/<analysis_id>')
def trampoline_analysis_status(analysis_id: str):
    """Report current job status and include result payload once available."""

    payload = _build_trampoline_status_payload(analysis_id)
    if payload["status"] == "missing":
        return jsonify({'success': False, 'error': 'Analysis not found'}), 404
    payload["success"] = True
    return jsonify(payload)


@app.route('/api/trampoline/result/<analysis_id>')
def trampoline_analysis_result(analysis_id: str):
    """Load one existing analysis result from disk."""

    payload = _build_trampoline_status_payload(analysis_id)
    if not payload.get("result"):
        return jsonify({'success': False, 'error': 'Analysis result not found'}), 404
    return jsonify({'success': True, **payload})


@app.route('/api/trampoline/export/<analysis_id>')
def trampoline_export_bundle(analysis_id: str):
    """Create and download the Phase 4 export bundle for one analysis."""

    analysis_dir = resolve_analysis_dir(get_trampoline_artifacts_dir(), analysis_id)
    if not analysis_dir.is_dir():
        return jsonify({'success': False, 'error': 'Analysis directory not found'}), 404

    try:
        exported = export_analysis_bundle(analysis_dir=analysis_dir)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    return send_file(
        Path(exported["bundle_zip"]),
        mimetype="application/zip",
        as_attachment=True,
        download_name=f"{analysis_id}_analysis_bundle.zip",
    )


@app.route('/api/trampoline/calibration/<analysis_id>', methods=['GET', 'POST'])
def trampoline_calibration(analysis_id: str):
    """Persist or fetch bed calibration for one analysis directory."""

    analysis_dir = resolve_analysis_dir(get_trampoline_artifacts_dir(), analysis_id)
    if not analysis_dir.is_dir():
        return jsonify({'success': False, 'error': 'Analysis directory not found'}), 404

    if request.method == 'GET':
        calibration = load_calibration(analysis_dir)
        return jsonify(
            {
                'success': True,
                'analysis_id': analysis_id,
                'calibration': calibration.model_dump(mode="json") if calibration else None,
            }
        )

    payload = request.get_json(silent=True) or {}
    corners = payload.get("corners")
    if not isinstance(corners, dict):
        return jsonify({'success': False, 'error': 'corners must be provided'}), 400

    frames_meta = load_analysis_output(analysis_dir)["frames_meta"]
    calibration = create_bed_calibration(
        corners=corners,
        frame_width=int(frames_meta["width"]),
        frame_height=int(frames_meta["height"]),
    )
    save_calibration(calibration, analysis_dir)
    segmentation_payload = None
    try:
        segmentation_payload = segment_analysis_dir(analysis_dir)
    except FileNotFoundError:
        segmentation_payload = None

    with trampoline_analyses_lock:
        job = trampoline_analyses.setdefault(analysis_id, {})
        job["result"] = load_analysis_output(analysis_dir)

    return jsonify(
        {
            'success': True,
            'analysis_id': analysis_id,
            'calibration': calibration.model_dump(mode="json"),
            'segmentation': segmentation_payload,
        }
    )


@app.route('/api/trampoline/segment/<analysis_id>', methods=['POST'])
def trampoline_segment_analysis(analysis_id: str):
    """Generate automatic jump segmentation for one analysis directory."""

    analysis_dir = resolve_analysis_dir(get_trampoline_artifacts_dir(), analysis_id)
    if not analysis_dir.is_dir():
        return jsonify({'success': False, 'error': 'Analysis directory not found'}), 404

    try:
        segmentation = segment_analysis_dir(analysis_dir)
        result = load_analysis_output(analysis_dir)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    return jsonify(
        {
            'success': True,
            'analysis_id': analysis_id,
            'segmentation': segmentation,
            'result': result,
        }
    )


@app.route('/api/trampoline/overrides/<analysis_id>', methods=['GET', 'POST'])
def trampoline_timeline_overrides(analysis_id: str):
    """Fetch or persist manual jump timeline overrides."""

    analysis_dir = resolve_analysis_dir(get_trampoline_artifacts_dir(), analysis_id)
    if not analysis_dir.is_dir():
        return jsonify({'success': False, 'error': 'Analysis directory not found'}), 404

    if request.method == 'GET':
        timeline = _load_timeline_payload(analysis_dir)
        return jsonify({'success': True, 'analysis_id': analysis_id, **timeline})

    payload = request.get_json(silent=True) or {}
    jump_rows = payload.get("jump_segments")
    if not isinstance(jump_rows, list):
        return jsonify({'success': False, 'error': 'jump_segments must be provided'}), 400

    try:
        jump_segments = [JumpSegment.model_validate(item) for item in jump_rows]
        overrides = persist_timeline_overrides(analysis_dir, jump_segments)
        result = load_analysis_output(analysis_dir)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    with trampoline_analyses_lock:
        job = trampoline_analyses.setdefault(analysis_id, {})
        job["result"] = result

    return jsonify(
        {
            'success': True,
            'analysis_id': analysis_id,
            'overrides': overrides.model_dump(mode="json"),
            'result': result,
        }
    )


@app.route('/api/trampoline/labels/<analysis_id>', methods=['POST'])
def trampoline_label_overrides(analysis_id: str):
    """Persist one manual label override for the selected jump."""

    analysis_dir = resolve_analysis_dir(get_trampoline_artifacts_dir(), analysis_id)
    if not analysis_dir.is_dir():
        return jsonify({'success': False, 'error': 'Analysis directory not found'}), 404

    payload = request.get_json(silent=True) or {}
    jump_id = payload.get("jump_id")
    override_label = payload.get("override_label")
    override_note = payload.get("override_note")
    if not isinstance(jump_id, str) or not jump_id.strip():
        return jsonify({'success': False, 'error': 'jump_id is required'}), 400
    if override_label not in {None, "tuck", "pike", "straight"}:
        return jsonify({'success': False, 'error': 'override_label must be tuck, pike, straight, or null'}), 400
    if override_note is not None and not isinstance(override_note, str):
        return jsonify({'success': False, 'error': 'override_note must be a string when provided'}), 400

    try:
        labels = persist_label_override(
            analysis_dir,
            jump_id=jump_id.strip(),
            override_label=override_label,
            override_note=(override_note or "").strip() or None,
        )
        result = load_analysis_output(analysis_dir)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    with trampoline_analyses_lock:
        job = trampoline_analyses.setdefault(analysis_id, {})
        job["result"] = result

    return jsonify(
        {
            'success': True,
            'analysis_id': analysis_id,
            'labels': labels.model_dump(mode="json"),
            'result': result,
        }
    )


@app.route('/api/trampoline/video/<analysis_id>')
def trampoline_source_video(analysis_id: str):
    """Serve the source video for one analysis."""

    payload = _build_trampoline_status_payload(analysis_id)
    source_video = payload.get("source_video")
    if not source_video:
        return jsonify({'success': False, 'error': 'Video not found'}), 404
    video_path = resolve_repo_path(source_video)
    if not video_path.is_file():
        video_path = Path(source_video)
    if not video_path.is_file():
        return jsonify({'success': False, 'error': 'Video not found'}), 404
    return send_file(video_path, mimetype="video/mp4")

@app.route('/api/video/upload', methods=['POST'])
def upload_video():
    """Upload video for analysis"""
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
    
    # Check video duration
    cap = cv2.VideoCapture(filepath)
    if cap.isOpened():
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        frame_count = cap.get(cv2.CAP_PROP_FRAME_COUNT)
        duration = frame_count / fps
        cap.release()
        
        if duration > MAX_VIDEO_DURATION_SEC:
            os.remove(filepath)  # Delete the uploaded file
            return jsonify({
                'success': False,
                'error': f'Video çok uzun! Max {MAX_VIDEO_DURATION_SEC} saniye, yüklenen: {duration:.0f} saniye'
            })
    
    # Initialize analysis state
    video_analyses[video_id] = {
        'status': 'processing',
        'progress': 0,
        'filepath': filepath,
        'exercise_type': exercise_type,
        'reps': 0,
        'form_score': 100,
        'avg_form_score': 100,
        'grade': 'A',
        'state': 'READY',
        'feedback': '',
        'engine': ExerciseEngine(),
        'total_frames': 0,
        'processed_frames': 0
    }
    
    # Load exercise into engine (not used in subprocess mode, but keep for status)
    video_analyses[video_id]['engine'].set_exercise(exercise_type)
    
    # Start background processing using subprocess
    thread = threading.Thread(target=process_video_subprocess, args=(video_id,))
    thread.daemon = True
    thread.start()
    
    return jsonify({
        'success': True,
        'video_id': video_id,
        'message': 'Video uploaded, processing started'
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
            analysis['error'] = f"Subprocess failed: {stderr.decode()}"
            logger.error(f"Subprocess error: {stderr.decode()}")
        
        # Cleanup JSON file (keep processed video for download)
        try:
            if os.path.exists(output_json_path):
                os.remove(output_json_path)
            # Delete original video (keep processed one)
            if os.path.exists(analysis['filepath']):
                os.remove(analysis['filepath'])
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
        'error': analysis.get('error'),  # 加上这一行
        'has_processed_video': has_processed_video,
        'processed_video_url': f'/api/video/processed/{video_id}' if has_processed_video else None
    })

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
        'feedback': analysis.get('feedback', '') if analysis else ''
    })

if __name__ == '__main__':
    try:
        # List available exercises on startup
        exercises = get_available_exercises()
        logger.info(f"Available exercises: {exercises}")
        
        logger.info("Starting the Flask application on http://127.0.0.1:5000")
        print("=" * 50)
        print("🏋️ FITNESS TRAINER WITH POSE ESTIMATION")
        print("=" * 50)
        print(f"📋 Available exercises: {len(exercises)}")
        for ex in exercises:
            print(f"   • {ex}")
        print("-" * 50)
        print("🌐 Open http://127.0.0.1:5000 in your browser")
        print("=" * 50)
        app.run(debug=False, threaded=False, use_reloader=False)
    except Exception as e:
        logger.error(f"Failed to start application: {e}")
        traceback.print_exc()
