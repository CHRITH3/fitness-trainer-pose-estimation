# CRITICAL: Set environment variables BEFORE TensorFlow/MediaPipe imports
import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TF_NUM_INTEROP_THREADS"] = "1"
os.environ["TF_NUM_INTRAOP_THREADS"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

from flask import Flask, Response, jsonify, render_template, request, send_file
import base64
import cv2
import json
import logging
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'trampoline_analysis_secret_key'

UPLOAD_FOLDER = 'uploads'
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
video_analyses = {}

MAX_VIDEO_SIZE_MB = 50
MAX_VIDEO_DURATION_SEC = 120
TRAMPOLINE_PENDING_TTL_SECONDS = 60 * 60
TRAMPOLINE_CORNER_ORDER = ["front_left", "front_right", "back_right", "back_left"]


def _extract_first_frame_b64(filepath):
    cap = cv2.VideoCapture(filepath)
    try:
        if not cap.isOpened():
            return None, None, 'Could not open video file'
        ok, frame = cap.read()
        if not ok:
            return None, None, 'Could not read first video frame'
        ok_enc, buffer = cv2.imencode('.png', frame)
        if not ok_enc:
            return None, None, 'Could not encode first video frame'
        encoded = base64.b64encode(buffer).decode('ascii')
        image_size = {'width': int(frame.shape[1]), 'height': int(frame.shape[0])}
        return encoded, image_size, None
    finally:
        cap.release()


def _canonicalize_corners(corners, image_size=None):
    from trampoline.bed_tracker import validate_corners

    normalized = validate_corners(corners, image_size=image_size)
    return [
        {'name': p['name'], 'x': round(float(p['x']), 3), 'y': round(float(p['y']), 3)}
        for p in normalized
    ]


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


def _canonicalize_calibrations(calibrations, image_size=None):
    from trampoline.bed_tracker import validate_calibrations

    normalized = validate_calibrations(calibrations or [], image_size=image_size)
    canonical = []
    for item in normalized:
        entry = {
            'frame_index': int(item['frame_index']),
            'corners_px': _canonicalize_corners(item['corners_px'], image_size=image_size),
        }
        if item.get('time_s') is not None:
            entry['time_s'] = round(float(item['time_s']), 3)
        if item.get('label'):
            entry['label'] = str(item['label'])
        canonical.append(entry)
    return canonical


def _calibrations_equal(a, b):
    if not a or not b or len(a) != len(b):
        return False
    for ca, cb in zip(a, b):
        if int(ca.get('frame_index', -1)) != int(cb.get('frame_index', -1)):
            return False
        ta = ca.get('time_s')
        tb = cb.get('time_s')
        if ta is None and tb is None:
            pass
        elif ta is None or tb is None or abs(float(ta) - float(tb)) > 1e-3:
            return False
        if not _corners_equal(ca.get('corners_px') or [], cb.get('corners_px') or []):
            return False
    return True


def _normalize_trampoline_calibrations(payload, image_size=None):
    calibrations = payload.get('calibrations')
    if calibrations is None:
        corners = payload.get('corners')
        calibrations = [{
            'frame_index': 0,
            'time_s': 0.0,
            'corners_px': corners or [],
        }]
    return _canonicalize_calibrations(calibrations, image_size=image_size)


def _corners_sidecar_path(video_id):
    return os.path.join(UPLOAD_FOLDER, f'{video_id}_corners.json')


def _remove_video_artifacts(video_id, analysis, include_processed=False):
    paths = [analysis.get('filepath'), _corners_sidecar_path(video_id)]
    if include_processed:
        paths.extend([
            analysis.get('processed_video'),
            os.path.join(UPLOAD_FOLDER, f'{video_id}_results.json'),
            os.path.join(UPLOAD_FOLDER, f'{video_id}_processed.mp4'),
        ])
    for path in paths:
        if path and os.path.exists(path):
            try:
                os.remove(path)
            except OSError as exc:
                logger.warning('Cleanup could not remove %s: %s', path, exc)


def cleanup_expired_pending_trampoline_uploads(now=None):
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


def _dashboard_context():
    return {
        'summary_cards': [
            {'title': '视频分析流程', 'value': '已启用', 'note': '当前主线聚焦蹦床视频上传、标定与分析'},
            {'title': '实时页面', 'value': '预留', 'note': '首页保留为后续蹦床实时页开发入口'},
            {'title': '图表区域', 'value': '保留', 'note': '可继续承接落点分布、训练统计等模块'},
            {'title': '当前阶段', 'value': '占位态', 'note': '先稳定视频分析主链路，再逐步补齐看板能力'},
        ],
        'highlights': [
            '继续沿用 /dashboard 路由，便于后续保持入口稳定。',
            '保留图表容器，便于后续接入跳次、落点、动作稳定性等数据。',
            '当前页面聚焦蹦床训练数据展示方向，便于后续继续扩展。',
        ],
    }


def _profile_context():
    return {
        'athlete': {
            'name': '蹦床训练档案',
            'title': '占位页（后续接入真实用户信息）',
            'joined': '2026-04',
        },
        'cards': [
            {
                'title': '档案定位',
                'items': ['保留 /profile 页面结构', '后续可接入运动员资料、器材配置、训练偏好'],
            },
            {
                'title': '后续可复用模块',
                'items': ['训练目标卡片', '周计划提醒', '历史训练摘要'],
            },
            {
                'title': '当前状态',
                'items': ['当前页先承接档案信息布局', '后续可接入真实用户数据与同步逻辑'],
            },
        ],
    }


def _sync_analysis_from_results(analysis, results):
    field_defaults = {
        'progress': 0,
        'reps': 0,
        'form_score': 100,
        'avg_form_score': 100,
        'grade': '--',
        'state': 'UNKNOWN',
        'feedback': '',
        'current_action': '--',
        'completed_jumps': [],
        'phase': 'unknown',
        'current_flight_frames': 0,
        'current_flight_duration_s': 0.0,
        'latest_landing': None,
        'landings': [],
    }
    for field, default in field_defaults.items():
        analysis[field] = results.get(field, default)

    optional_fields = (
        'fps',
        'video_fps',
        'total_frames',
        'resolution',
        'phase',
        'current_flight_frames',
        'current_flight_duration_s',
        'latest_landing',
        'landings',
        'score',
        'score_selected_jump_numbers',
    )
    for field in optional_fields:
        if field in results:
            analysis[field] = results[field]


def _compute_analysis_score(analysis, selected_jump_numbers=None):
    from trampoline.score import ScoreSelectionError, compute_score

    selected = selected_jump_numbers
    if selected is None:
        selected = analysis.get('score_selected_jump_numbers')
    try:
        score = compute_score(analysis, selected_jump_numbers=selected)
    except ScoreSelectionError:
        raise
    analysis['score'] = score
    if score.get('selected_jump_numbers'):
        analysis['score_selected_jump_numbers'] = score['selected_jump_numbers']
    return score


def _score_for_status(analysis):
    if analysis.get('status') not in ('processing', 'completed'):
        return analysis.get('score')
    try:
        return _compute_analysis_score(analysis)
    except Exception as exc:
        logger.warning('Score computation failed: %s', exc)
        return {
            'status': 'insufficient_data',
            'message': f'评分计算失败：{exc}',
            'selected_jump_numbers': [],
            'default_selected_jump_numbers': [],
            'effective_jump_count': 0,
            'components': {'D': None, 'E': None, 'T': None, 'H': None, 'P': 0.0, 'total': None},
            'deductions': [],
        }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html', **_dashboard_context())


@app.route('/profile')
def profile():
    return render_template('profile.html', **_profile_context())


@app.route('/video_analysis')
def video_analysis():
    return render_template('video_analysis.html', mode='trampoline')


@app.route('/api/video/upload', methods=['POST'])
def upload_video():
    cleanup_expired_pending_trampoline_uploads()

    if 'video' not in request.files:
        return jsonify({'success': False, 'error': 'No video file provided'}), 400

    exercise_type = (request.form.get('exercise_type') or '').strip()
    if not exercise_type:
        return jsonify({'success': False, 'error': 'No exercise type specified'}), 400
    if exercise_type != 'trampoline':
        return jsonify({'success': False, 'error': 'Only trampoline uploads are supported'}), 400

    video_file = request.files['video']
    if video_file.filename == '':
        return jsonify({'success': False, 'error': 'No file selected'}), 400

    video_file.seek(0, 2)
    file_size = video_file.tell()
    video_file.seek(0)
    max_size_bytes = MAX_VIDEO_SIZE_MB * 1024 * 1024
    if file_size > max_size_bytes:
        return jsonify({
            'success': False,
            'error': f'Video too large. Max {MAX_VIDEO_SIZE_MB}MB, received {file_size / (1024 * 1024):.1f}MB',
        }), 400

    video_id = str(uuid.uuid4())
    filename = f'{video_id}_{video_file.filename}'
    filepath = os.path.join(UPLOAD_FOLDER, filename)
    video_file.save(filepath)

    fps = 30.0
    frame_count = 0
    cap = cv2.VideoCapture(filepath)
    try:
        if cap.isOpened():
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
            duration = frame_count / max(fps, 1e-6)
            if duration > MAX_VIDEO_DURATION_SEC:
                os.remove(filepath)
                return jsonify({
                    'success': False,
                    'error': f'Video too long. Max {MAX_VIDEO_DURATION_SEC}s, received {duration:.0f}s',
                }), 400
    finally:
        cap.release()

    first_frame_b64, image_size, frame_error = _extract_first_frame_b64(filepath)
    if frame_error:
        if os.path.exists(filepath):
            os.remove(filepath)
        return jsonify({'success': False, 'error': frame_error}), 400

    video_analyses[video_id] = {
        'mode': 'trampoline',
        'status': 'uploaded_pending_calibration',
        'progress': 0,
        'filepath': filepath,
        'exercise_type': 'trampoline',
        'reps': 0,
        'form_score': 100,
        'avg_form_score': 100,
        'grade': '--',
        'state': 'PENDING_CALIBRATION',
        'feedback': 'Awaiting bed corner calibration',
        'total_frames': int(frame_count or 0),
        'processed_frames': 0,
        'video_fps': float(fps or 30.0),
        'current_action': '--',
        'completed_jumps': [],
        'phase': 'pending_calibration',
        'current_flight_frames': 0,
        'current_flight_duration_s': 0.0,
        'latest_landing': None,
        'landings': [],
        'score': None,
        'score_selected_jump_numbers': None,
        'corner_order': TRAMPOLINE_CORNER_ORDER,
        'corners': None,
        'started': False,
        'created_at': time.time(),
        'image_size': image_size,
    }

    logger.info('Trampoline video uploaded pending calibration: %s', video_id)
    return jsonify({
        'success': True,
        'video_id': video_id,
        'status': 'uploaded_pending_calibration',
        'message': 'Video uploaded; bed corner calibration required',
        'first_frame_b64': first_frame_b64,
        'first_frame_image': f'data:image/png;base64,{first_frame_b64}',
        'image_size': image_size,
        'corner_order': TRAMPOLINE_CORNER_ORDER,
        'video_fps': float(fps or 30.0),
        'total_frames': int(frame_count or 0),
    })


@app.route('/api/video/trampoline/start', methods=['POST'])
def start_trampoline_analysis():
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
            requested = _normalize_trampoline_calibrations(data, image_size=image_tuple)
        except Exception:
            requested = None
        if requested and existing_calibrations and _calibrations_equal(existing_calibrations, requested):
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
        canonical_calibrations = _normalize_trampoline_calibrations(data, image_size=image_tuple)
    except Exception as e:
        analysis['status'] = 'calibration_rejected'
        analysis['state'] = 'CALIBRATION_REJECTED'
        analysis['error'] = str(e)
        analysis['feedback'] = str(e)
        return jsonify({'success': False, 'status': 'calibration_rejected', 'error': str(e)}), 400

    first_calibration = canonical_calibrations[0]
    sidecar = {
        'schema_version': 2,
        'video_id': video_id,
        'exercise_type': 'trampoline',
        'frame_index': int(first_calibration['frame_index']),
        'image_size': analysis.get('image_size'),
        'corner_order': TRAMPOLINE_CORNER_ORDER,
        'corners_px': first_calibration['corners_px'],
        'calibrations': canonical_calibrations,
        'bed_dimensions_m': {'width': 4.28, 'length': 2.14},
        'created_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
    }
    sidecar_path = _corners_sidecar_path(video_id)
    tmp_path = f'{sidecar_path}.tmp'
    with open(tmp_path, 'w', encoding='utf-8') as f:
        json.dump(sidecar, f)
    os.replace(tmp_path, sidecar_path)

    analysis['corners'] = list(first_calibration['corners_px'])
    analysis['calibrations'] = canonical_calibrations
    analysis['status'] = 'processing'
    analysis['state'] = 'PROCESSING'
    analysis['feedback'] = f'Processing trampoline video with {len(canonical_calibrations)} calibration(s)'
    analysis['error'] = None
    analysis['started'] = True
    analysis['score'] = None
    analysis['score_selected_jump_numbers'] = None

    thread = threading.Thread(target=process_video_subprocess, args=(video_id,))
    thread.daemon = True
    thread.start()

    return jsonify({
        'success': True,
        'video_id': video_id,
        'status': 'processing',
        'message': 'Trampoline analysis started',
        'calibration_count': len(canonical_calibrations),
    })


def process_video_subprocess(video_id):
    import subprocess

    logger.info('Starting video processing (subprocess) for %s', video_id)
    analysis = video_analyses.get(video_id)
    if not analysis:
        logger.error('Analysis not found for %s', video_id)
        return

    analysis['status'] = 'processing'
    output_json_path = os.path.join(UPLOAD_FOLDER, f'{video_id}_results.json')
    output_video_path = os.path.join(UPLOAD_FOLDER, f'{video_id}_processed.mp4')

    try:
        cmd = [
            sys.executable,
            'video_processor.py',
            analysis['filepath'],
            analysis['exercise_type'],
            output_json_path,
            output_video_path,
        ]
        logger.info('Running subprocess: %s', ' '.join(cmd))
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            text=True,
            bufsize=1,
        )

        while process.poll() is None:
            try:
                line = process.stdout.readline()
                if line:
                    logger.info('[Subprocess] %s', line.strip())
            except Exception:
                pass

            time.sleep(0.3)
            try:
                if os.path.exists(output_json_path):
                    with open(output_json_path, 'r', encoding='utf-8') as f:
                        results = json.load(f)
                    _sync_analysis_from_results(analysis, results)
            except Exception:
                pass

        stdout, stderr = process.communicate()
        if process.returncode == 0 and os.path.exists(output_json_path):
            with open(output_json_path, 'r', encoding='utf-8') as f:
                results = json.load(f)

            analysis['progress'] = 100
            analysis['status'] = results.get('status', 'completed')
            _sync_analysis_from_results(analysis, results)

            actual_output_video = results.get('output_video', output_video_path)
            if actual_output_video and os.path.exists(actual_output_video):
                analysis['processed_video'] = actual_output_video
            elif os.path.exists(output_video_path):
                analysis['processed_video'] = output_video_path
            else:
                avi_path = output_video_path.rsplit('.', 1)[0] + '.avi'
                analysis['processed_video'] = avi_path if os.path.exists(avi_path) else None

            if results.get('error'):
                analysis['status'] = 'error'
                analysis['error'] = results['error']

            logger.info('Video processing completed: %s jumps, output: %s', analysis['reps'], output_video_path)
        else:
            analysis['status'] = 'error'
            err_text = stderr or stdout or f'Subprocess exited with code {process.returncode}'
            analysis['error'] = f'Subprocess failed: {err_text}'
            logger.error('Subprocess error: %s', err_text)

        try:
            if os.path.exists(output_json_path):
                os.remove(output_json_path)
            _remove_video_artifacts(video_id, analysis, include_processed=False)
        except Exception as e:
            logger.warning('Cleanup error: %s', e)

    except Exception as e:
        logger.error('Subprocess error: %s', e)
        analysis['status'] = 'error'
        analysis['error'] = str(e)


@app.route('/api/video/processed/<video_id>', methods=['GET'])
def get_processed_video(video_id):
    analysis = video_analyses.get(video_id)
    if not analysis:
        return jsonify({'error': 'Video ID not found'}), 404

    processed_video = analysis.get('processed_video')
    if not processed_video or not os.path.exists(processed_video):
        return jsonify({'error': 'Processed video not ready'}), 404

    if processed_video.endswith('.avi'):
        mimetype = 'video/x-msvideo'
    elif processed_video.endswith('.webm'):
        mimetype = 'video/webm'
    else:
        mimetype = 'video/mp4'
    return send_file(processed_video, mimetype=mimetype, as_attachment=False)


@app.route('/api/video/status/<video_id>', methods=['GET'])
def get_video_status(video_id):
    cleanup_expired_pending_trampoline_uploads()
    analysis = video_analyses.get(video_id)
    if not analysis:
        return jsonify({'status': 'not_found', 'error': 'Video ID not found'})

    has_processed_video = False
    if analysis.get('processed_video') and os.path.exists(analysis.get('processed_video', '')):
        has_processed_video = True

    score = _score_for_status(analysis)

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
        'mode': 'trampoline',
        'current_action': analysis.get('current_action', '--'),
        'completed_jumps': analysis.get('completed_jumps', []),
        'phase': analysis.get('phase', 'unknown'),
        'current_flight_frames': analysis.get('current_flight_frames', 0),
        'current_flight_duration_s': analysis.get('current_flight_duration_s', 0.0),
        'latest_landing': analysis.get('latest_landing'),
        'landings': analysis.get('landings', []),
        'fps': analysis.get('fps'),
        'video_fps': analysis.get('video_fps'),
        'score': score,
    })


@app.route('/api/video/score/<video_id>', methods=['POST'])
def score_video(video_id):
    analysis = video_analyses.get(video_id)
    if not analysis:
        return jsonify({'success': False, 'status': 'not_found', 'error': 'Video ID not found'}), 404
    if analysis.get('mode') != 'trampoline':
        return jsonify({'success': False, 'error': 'Scoring only available for trampoline mode'}), 400
    if analysis.get('status') != 'completed':
        return jsonify({'success': False, 'error': 'Video analysis not yet complete'}), 400

    data = request.get_json(silent=True) or {}
    selected = data.get('selected_jump_numbers')
    try:
        score = _compute_analysis_score(analysis, selected_jump_numbers=selected)
    except Exception as exc:
        return jsonify({'success': False, 'error': str(exc)}), 400

    try:
        from trampoline.llm_service import clear_cached
        clear_cached(video_id)
    except Exception:
        pass

    return jsonify({'success': True, 'score': score})


@app.route('/api/video/llm_analysis/<video_id>', methods=['GET'])
def llm_analysis(video_id):
    import json as _json

    def sse_message(payload):
        def generate_once():
            yield f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"

        return Response(
            generate_once(),
            mimetype='text/event-stream',
            headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'},
        )

    analysis = video_analyses.get(video_id)
    if not analysis:
        return sse_message({'type': 'error', 'message': 'Video ID not found'})
    if analysis.get('mode') != 'trampoline':
        return sse_message({'type': 'error', 'message': 'LLM analysis only available for trampoline mode'})
    if analysis.get('status') != 'completed':
        return sse_message({'type': 'error', 'message': 'Video analysis not yet complete'})

    score = _score_for_status(analysis)
    if score and score.get('status') == 'selection_required':
        return sse_message({'type': 'error', 'message': '请先确认用于评分的 10 个有效跳次，再启动 AI 分析'})

    try:
        from trampoline.llm_service import (
            AnalysisReport,
            clean_chunk,
            get_cached,
            resolve_api_key,
            resolve_models,
            run_llm_analysis_sync,
            segment_response,
            set_cached,
            stream_llm_analysis,
        )
    except ImportError as e:
        return sse_message({'type': 'error', 'message': f'LLM service not available: {e}'})

    api_key = resolve_api_key()
    if not api_key:
        return sse_message({'type': 'error', 'message': 'LLM API key not configured'})

    cached = get_cached(video_id)
    if cached:
        def cached_gen():
            yield f"data: {_json.dumps({'type': 'done', 'sections': cached['sections'], 'full_text': cached['full_text']}, ensure_ascii=False)}\n\n"

        return Response(cached_gen(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    report = AnalysisReport.from_video_analysis(analysis)

    def generate():
        quality_result = {'text': None, 'error': None, 'done': False}
        fast_model, quality_model = resolve_models()

        def run_quality():
            try:
                text = run_llm_analysis_sync(report, model=quality_model, timeout=90)
                if text.startswith('[ERROR]'):
                    quality_result['error'] = text
                else:
                    quality_result['text'] = text
            except Exception as exc:
                quality_result['error'] = str(exc)
            finally:
                quality_result['done'] = True

        quality_thread = threading.Thread(target=run_quality, daemon=True)
        quality_thread.start()

        def llm_error_payload(message, *, stage='final', fast_error_text=None, quality_error_text=None):
            return {
                'type': 'error' if stage == 'final' else stage,
                'message': message,
                'provider': 'deepseek',
                'fast_model': fast_model,
                'quality_model': quality_model,
                'fast_error': fast_error_text,
                'quality_error': quality_error_text,
                'hint': 'DeepSeek API TLS/网络连接失败。请检查代理、出口网络或稍后重试。',
            }

        fast_full_text = ''
        fast_error = None
        prev_chunk = ''
        try:
            for raw_chunk in stream_llm_analysis(report, model=fast_model):
                cleaned = clean_chunk(raw_chunk, prev_chunk)
                if cleaned:
                    if cleaned.lstrip().startswith('[ERROR]'):
                        fast_error = cleaned.strip()
                        payload = llm_error_payload(
                            '快速模型连接失败，继续等待高质量分析结果',
                            stage='fast_error',
                            fast_error_text=fast_error,
                        )
                        yield f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"
                        break
                    fast_full_text += cleaned
                    yield f"data: {_json.dumps({'type': 'chunk', 'text': cleaned}, ensure_ascii=False)}\n\n"
                    prev_chunk = cleaned

            if not fast_error:
                yield f"data: {_json.dumps({'type': 'fast_done'}, ensure_ascii=False)}\n\n"
            quality_thread.join(timeout=120)

            if quality_result.get('text'):
                final_text = quality_result['text']
                source = 'quality'
            elif fast_full_text and not fast_full_text.startswith('[ERROR]'):
                final_text = fast_full_text
                source = 'fast_fallback'
            else:
                details = quality_result.get('error') or fast_error or '两个模型均调用失败'
                payload = llm_error_payload(
                    f'DeepSeek AI 分析失败：{details}',
                    fast_error_text=fast_error,
                    quality_error_text=quality_result.get('error'),
                )
                yield f"data: {_json.dumps(payload, ensure_ascii=False)}\n\n"
                return

            sections = segment_response(final_text)
            set_cached(video_id, final_text, sections)
            yield f"data: {_json.dumps({'type': 'done', 'sections': sections, 'full_text': final_text, 'source': source}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            logger.error('LLM analysis error: %s', exc)
            yield f"data: {_json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return Response(generate(), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})


if __name__ == '__main__':
    try:
        logger.info('Starting trampoline analysis app on http://127.0.0.1:5000')
        print('=' * 50)
        print('TRAMPOLINE VIDEO ANALYSIS')
        print('=' * 50)
        print('Routes: /  /dashboard  /profile  /video_analysis')
        print('Open http://127.0.0.1:5000 in your browser')
        print('=' * 50)
        app.run(debug=False, threaded=False, use_reloader=False)
    except Exception as exc:
        logger.error('Failed to start application: %s', exc)
        traceback.print_exc()
