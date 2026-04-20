"""
Standalone trampoline video processor.

Runs in a separate process to avoid memory issues while producing:
- JSON analysis results for polling
- processed video with trampoline overlays
"""

import os
os.environ["TF_ENABLE_ONEDNN_OPTS"] = "0"
os.environ["OMP_NUM_THREADS"] = "1"
os.environ["TF_NUM_INTEROP_THREADS"] = "1"
os.environ["TF_NUM_INTRAOP_THREADS"] = "1"
os.environ["TF_CPP_MIN_LOG_LEVEL"] = "2"

import gc
import json
import sys

import cv2

try:
    import imageio
    IMAGEIO_AVAILABLE = True
    print('imageio available for H.264 output')
except ImportError:
    IMAGEIO_AVAILABLE = False
    print('imageio not available, using OpenCV for output')


def draw_skeleton(frame, landmarks):
    """Draw a simplified skeleton with highlighted joints."""
    h, w = frame.shape[:2]

    body_connections = [(11, 12), (11, 23), (12, 24), (23, 24)]
    arm_connections = [(11, 13), (13, 15), (12, 14), (14, 16)]
    leg_connections = [(23, 25), (25, 27), (24, 26), (26, 28)]

    def get_pos(idx):
        lm = landmarks.landmark[idx]
        return (int(lm.x * w), int(lm.y * h))

    def is_visible(idx):
        return landmarks.landmark[idx].visibility > 0.5

    def draw_line_with_glow(p1, p2, color, thickness=3):
        cv2.line(frame, p1, p2, (color[0] // 3, color[1] // 3, color[2] // 3), thickness + 4)
        cv2.line(frame, p1, p2, color, thickness)
        cv2.line(
            frame,
            p1,
            p2,
            (min(255, color[0] + 50), min(255, color[1] + 50), min(255, color[2] + 50)),
            max(1, thickness - 1),
        )

    for start, end in body_connections:
        if is_visible(start) and is_visible(end):
            draw_line_with_glow(get_pos(start), get_pos(end), (255, 200, 0), 3)
    for start, end in arm_connections:
        if is_visible(start) and is_visible(end):
            draw_line_with_glow(get_pos(start), get_pos(end), (0, 255, 100), 3)
    for start, end in leg_connections:
        if is_visible(start) and is_visible(end):
            draw_line_with_glow(get_pos(start), get_pos(end), (255, 100, 100), 3)

    for idx in [11, 12, 13, 14, 15, 16, 23, 24, 25, 26, 27, 28]:
        if is_visible(idx):
            pos = get_pos(idx)
            cv2.circle(frame, pos, 8, (50, 50, 50), -1)
            cv2.circle(frame, pos, 6, (0, 200, 100), -1)
            cv2.circle(frame, pos, 3, (255, 255, 255), -1)

    return frame


def process_video(video_path: str, exercise_type: str, output_json_path: str, output_video_path: str = None):
    """Process a trampoline video, draw overlay, and write incremental results."""
    import mediapipe as mp
    from trampoline.analyzer import TrampolineAnalyzer
    from trampoline.bed_tracker import BedTracker, load_corners_sidecar
    from trampoline.overlay import draw_angle_arcs, draw_trampoline_overlay

    results = {
        'status': 'processing',
        'progress': 0,
        'reps': 0,
        'form_score': 100,
        'avg_form_score': 100,
        'grade': '--',
        'state': 'READY',
        'feedback': '',
        'error': None,
        'output_video': output_video_path,
        'mode': 'trampoline',
        'current_action': '--',
        'completed_jumps': [],
    }

    def save_results():
        with open(output_json_path, 'w', encoding='utf-8') as f:
            json.dump(results, f)

    if exercise_type != 'trampoline':
        results['status'] = 'error'
        results['error'] = 'Only trampoline analysis is supported'
        save_results()
        print(results['error'])
        return

    cap = None
    out = None
    pose = None
    imageio_writer = None

    try:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            results['status'] = 'error'
            results['error'] = 'Could not open video file'
            save_results()
            return

        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS) or 30
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        print(f'Video: {width}x{height} @ {fps:.1f} fps, {total_frames} frames')

        if output_video_path:
            if not output_video_path.endswith('.mp4'):
                output_video_path = output_video_path.rsplit('.', 1)[0] + '.mp4'

            if IMAGEIO_AVAILABLE:
                try:
                    imageio_writer = imageio.get_writer(
                        output_video_path,
                        fps=fps,
                        codec='libx264',
                        pixelformat='yuv420p',
                        quality=8,
                        macro_block_size=1,
                    )
                    print(f'Using imageio/FFmpeg H.264 writer: {output_video_path}')
                except Exception as exc:
                    print(f'imageio writer init failed: {exc}, will use OpenCV')
                    imageio_writer = None

            if not imageio_writer:
                codecs_to_try = [('avc1', '.mp4'), ('H264', '.mp4'), ('XVID', '.avi'), ('mp4v', '.mp4')]
                for codec, ext in codecs_to_try:
                    try:
                        fourcc = cv2.VideoWriter_fourcc(*codec)
                        candidate_path = output_video_path.rsplit('.', 1)[0] + ext
                        out = cv2.VideoWriter(candidate_path, fourcc, fps, (width, height))
                        if out.isOpened():
                            output_video_path = candidate_path
                            print(f'Using OpenCV codec: {codec}')
                            break
                        out.release()
                        out = None
                    except Exception:
                        continue
                if not out:
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                    out = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))
                    print('Using fallback codec: mp4v')

            results['output_video'] = output_video_path
            print(f'Output video: {output_video_path}')

        mp_pose = mp.solutions.pose
        pose = mp_pose.Pose(
            static_image_mode=False,
            model_complexity=1,
            enable_segmentation=False,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        print('MediaPipe Pose initialized')

        video_id = os.path.basename(output_json_path).replace('_results.json', '')
        corners_json = os.path.join(os.path.dirname(output_json_path), f'{video_id}_corners.json')
        if not os.path.exists(corners_json):
            results['status'] = 'error'
            results['error'] = f'No trampoline corners sidecar found at {corners_json}'
            save_results()
            print(results['error'])
            return

        sidecar = load_corners_sidecar(corners_json, expected_video_id=video_id)
        bed_tracker = BedTracker.from_sidecar(sidecar)
        cap_peek = cv2.VideoCapture(video_path)
        ok_first, first_frame = cap_peek.read()
        cap_peek.release()
        if not ok_first:
            results['status'] = 'error'
            results['error'] = 'Could not read first frame for bed tracker initialization'
            save_results()
            print(results['error'])
            return
        bed_tracker.initialize(first_frame, frame_index=0)
        print(f'Bed tracker initialized from {corners_json}')

        analyzer = TrampolineAnalyzer(fps=fps, bed_tracker=bed_tracker)
        analyze_skip = max(1, int(fps / 15))
        print(f'Analyze skip: {analyze_skip} (analyzing at ~{fps / analyze_skip:.1f} fps)')

        current_stats = {
            'reps': 0,
            'form_score': 100,
            'grade': '--',
            'state': 'READY',
            'feedback': '',
            'jump_count': 0,
            'current_action': '--',
            'phase': 'unknown',
            'velocity': 0,
            'trunk_thigh_angle': 0,
            'thigh_shin_angle': 0,
            'bed_info': None,
            'latest_landing': None,
            'landings': [],
        }

        frame_count = 0
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break

            frame_count += 1
            results['progress'] = int((frame_count / max(total_frames, 1)) * 100)

            if analyzer.bed_tracker is not None:
                try:
                    current_stats['bed_info'] = analyzer.bed_tracker.update(frame, frame_index=frame_count)
                except Exception as exc:
                    current_stats['bed_info'] = {'success': False, 'message': str(exc)}

            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            pose_results = pose.process(rgb_frame)

            if pose_results.pose_landmarks:
                frame = draw_skeleton(frame, pose_results.pose_landmarks)
                draw_angle_arcs(frame, pose_results.pose_landmarks)

                if frame_count % analyze_skip == 0:
                    tramp_result = analyzer.process_frame(frame, pose_results.pose_landmarks.landmark, frame_count)
                    current_stats['reps'] = tramp_result['jump_count']
                    current_stats['jump_count'] = tramp_result['jump_count']
                    current_stats['current_action'] = tramp_result['current_action']
                    current_stats['phase'] = tramp_result['phase']
                    current_stats['velocity'] = tramp_result['velocity']
                    current_stats['trunk_thigh_angle'] = tramp_result['trunk_thigh_angle']
                    current_stats['thigh_shin_angle'] = tramp_result['thigh_shin_angle']
                    current_stats['state'] = tramp_result['current_action']
                    current_stats['feedback'] = f"Phase: {tramp_result['phase']}"
                    current_stats['bed_info'] = getattr(analyzer.bed_tracker, 'current_info', current_stats.get('bed_info'))
                    current_stats['landings'] = [j.get('landing') for j in tramp_result.get('completed_jumps', []) if j.get('landing')]
                    current_stats['latest_landing'] = current_stats['landings'][-1] if current_stats['landings'] else None

                    results['reps'] = tramp_result['jump_count']
                    results['current_action'] = tramp_result['current_action']
                    results['completed_jumps'] = tramp_result['completed_jumps']
                    results['state'] = tramp_result['current_action']
                    results['form_score'] = 100
                    results['avg_form_score'] = 100
                    results['grade'] = '--'
                    results['feedback'] = f"Phase: {tramp_result['phase']}"

                    if (frame_count // analyze_skip) % 30 == 0:
                        print(
                            f"[Frame {frame_count}] Jumps: {tramp_result['jump_count']}, "
                            f"Action: {tramp_result['current_action']}, Phase: {tramp_result['phase']}"
                        )

            frame = draw_trampoline_overlay(frame, current_stats, current_stats.get('bed_info'))

            if imageio_writer:
                imageio_writer.append_data(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
            elif out:
                out.write(frame)

            if frame_count % 15 == 0:
                save_results()

            del rgb_frame
            if frame_count % 100 == 0:
                gc.collect()

        if cap:
            cap.release()
        if pose:
            pose.close()

        results['reps'] = current_stats['reps']
        results['form_score'] = current_stats['form_score']
        results['avg_form_score'] = 100
        results['grade'] = current_stats['grade']
        results['state'] = 'COMPLETED'
        results['feedback'] = current_stats['feedback']
        results['fps'] = fps
        results['total_frames'] = total_frames
        results['resolution'] = f'{width}x{height}'
        results['current_action'] = current_stats.get('current_action', '--')
        results['completed_jumps'] = analyzer.completed_jumps

        diag_path = output_json_path.rsplit('.', 1)[0] + '_diagnostics.csv'
        analyzer.dump_diagnostics(diag_path)

        if imageio_writer:
            try:
                imageio_writer.close()
                print(f'H.264 video saved: {output_video_path}')
            except Exception as exc:
                print(f'Error closing imageio writer: {exc}')
        if out:
            out.release()

        gc.collect()
        results['status'] = 'completed'
        results['progress'] = 100

        print('=== FINAL RESULTS ===')
        print(f"Mode: {results.get('mode', 'trampoline')}")
        print(f"Jumps written to results: {results['reps']}")
        print(f"State: {results['state']}")
        print(f"Completed jumps: {len(analyzer.completed_jumps)}")
        for jump in analyzer.completed_jumps:
            print(
                f"  Jump {jump['jump_number']}: {jump['action']} "
                f"(flight={jump['flight_frames']}f, intermediate={jump['is_intermediate']})"
            )
        print('=====================')

        save_results()
        print(f'Completed: {frame_count} frames, {results["reps"]} jumps')
        if output_video_path:
            print(f'Output video saved: {output_video_path}')

    except Exception as exc:
        results['status'] = 'error'
        results['error'] = str(exc)
        save_results()
        print(f'Error: {exc}')
        import traceback
        traceback.print_exc()
    finally:
        if cap:
            try:
                cap.release()
            except Exception:
                pass
        if imageio_writer:
            try:
                imageio_writer.close()
            except Exception:
                pass
        if out:
            try:
                out.release()
            except Exception:
                pass
        if pose:
            try:
                pose.close()
            except Exception:
                pass
        gc.collect()


if __name__ == '__main__':
    if len(sys.argv) < 4:
        print('Usage: python video_processor.py <video_path> <exercise_type> <output_json_path> [output_video_path]')
        sys.exit(1)

    video_path = sys.argv[1]
    exercise_type = sys.argv[2]
    output_json_path = sys.argv[3]
    output_video_path = sys.argv[4] if len(sys.argv) > 4 else None
    process_video(video_path, exercise_type, output_json_path, output_video_path)
