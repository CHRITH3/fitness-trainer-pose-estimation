from pathlib import Path
import json

import app as app_module


RETAINED_ROUTES = ['/', '/dashboard', '/profile', '/video_analysis', '/video_analysis?mode=trampoline']
REMOVED_ENDPOINTS = [
    ('GET', '/video_feed'),
    ('POST', '/stop_camera'),
    ('POST', '/start_exercise'),
    ('POST', '/stop_exercise'),
    ('GET', '/get_status'),
    ('GET', '/exercises'),
    ('POST', '/api/profile/update'),
    ('POST', '/api/video/analyze_frame'),
]


def test_retained_routes_return_200_and_use_trampoline_copy():
    client = app_module.app.test_client()
    for route in RETAINED_ROUTES:
        response = client.get(route)
        assert response.status_code == 200, route
        html = response.get_data(as_text=True)
        assert '蹦床' in html or '视频分析' in html
        assert 'Fitness Trainer' not in html
        assert 'Select Exercise' not in html


def test_removed_fitness_endpoints_return_404():
    client = app_module.app.test_client()
    for method, route in REMOVED_ENDPOINTS:
        response = getattr(client, method.lower())(route)
        assert response.status_code == 404, f'{method} {route}'


def test_video_analysis_defaults_to_trampoline_only():
    client = app_module.app.test_client()
    response = client.get('/video_analysis')
    html = response.get_data(as_text=True)
    assert response.status_code == 200
    assert 'data-mode="trampoline"' in html
    assert 'Trampoline Mode' not in html
    assert 'Fitness Mode' not in html
    assert 'Select Exercise' not in html


def test_video_upload_rejects_missing_or_non_trampoline_type(tmp_path):
    client = app_module.app.test_client()

    response = client.post('/api/video/upload', data={}, content_type='multipart/form-data')
    assert response.status_code == 400
    assert response.get_json()['error'] == 'No video file provided'

    video_bytes = (tmp_path / 'sample.mp4')
    video_bytes.write_bytes(b'not-a-real-video-but-type-check-precedes-open')
    with video_bytes.open('rb') as fh:
        response = client.post(
            '/api/video/upload',
            data={'exercise_type': 'fitness', 'video': (fh, 'sample.mp4')},
            content_type='multipart/form-data',
        )
    assert response.status_code == 400
    assert response.get_json()['error'] == 'Only trampoline uploads are supported'


def test_llm_analysis_route_still_exists_and_returns_streaming_error_for_unknown_video():
    client = app_module.app.test_client()
    response = client.get('/api/video/llm_analysis/unknown-video-id')
    assert response.status_code == 200
    assert response.mimetype == 'text/event-stream'
    body = response.get_data(as_text=True)
    assert 'Video ID not found' in body


def test_score_route_exists_and_returns_json_error_for_unknown_video():
    client = app_module.app.test_client()
    response = client.post('/api/video/score/unknown-video-id', json={'selected_jump_numbers': list(range(1, 11))})
    assert response.status_code == 404
    assert response.get_json()['status'] == 'not_found'


def test_llm_fast_model_error_still_returns_quality_result(monkeypatch):
    video_id = 'video-with-score'
    app_module.video_analyses[video_id] = {
        'mode': 'trampoline',
        'status': 'completed',
        'progress': 100,
        'reps': 10,
        'form_score': 100,
        'avg_form_score': 100,
        'grade': '--',
        'state': 'COMPLETED',
        'feedback': '',
        'completed_jumps': [
            {'jump_number': i, 'action': 'Tuck', 'flight_frames': 30, 'is_intermediate': False}
            for i in range(1, 11)
        ],
        'fps': 30.0,
        'total_frames': 300,
        'resolution': '640x480',
        'score': {
            'status': 'ready',
            'components': {'D': 5.0, 'E': 20.0, 'T': 10.0, 'H': 10.0, 'P': 0.0, 'total': 45.0},
            'selected_jump_numbers': list(range(1, 11)),
            'deductions': [],
        },
    }

    monkeypatch.setattr('trampoline.llm_service.resolve_api_key', lambda: 'test-key')
    monkeypatch.setattr('trampoline.llm_service.resolve_models', lambda: ('fast', 'quality'))
    monkeypatch.setattr('trampoline.llm_service.stream_llm_analysis', lambda report, model=None: iter(['[ERROR] LLM 调用失败: APIConnectionError: Connection error.']))
    monkeypatch.setattr('trampoline.llm_service.run_llm_analysis_sync', lambda report, model=None, timeout=90: '## 整体表现\n高质量\n## 主要问题\n无\n## 逐跳点评\n第1跳 稳定\n## 改进建议\n保持')

    client = app_module.app.test_client()
    response = client.get(f'/api/video/llm_analysis/{video_id}')
    body = response.get_data(as_text=True)
    events = [
        json.loads(line.removeprefix('data: '))
        for line in body.splitlines()
        if line.startswith('data: ')
    ]

    assert any(event['type'] == 'fast_error' for event in events)
    fast_error = [event for event in events if event['type'] == 'fast_error'][0]
    assert fast_error['provider'] == 'deepseek'
    assert fast_error['fast_model'] == 'fast'
    assert 'APIConnectionError' in fast_error['fast_error']
    assert '代理' in fast_error['hint']
    done = [event for event in events if event['type'] == 'done'][-1]
    assert done['source'] == 'quality'
    assert done['sections']['整体表现'] == '高质量'


def test_llm_both_models_connection_errors_return_actionable_hint(monkeypatch):
    video_id = 'video-with-llm-errors'
    app_module.video_analyses[video_id] = {
        'mode': 'trampoline',
        'status': 'completed',
        'progress': 100,
        'reps': 10,
        'form_score': 100,
        'avg_form_score': 100,
        'grade': '--',
        'state': 'COMPLETED',
        'feedback': '',
        'completed_jumps': [
            {'jump_number': i, 'action': 'Tuck', 'flight_frames': 30, 'is_intermediate': False}
            for i in range(1, 11)
        ],
        'fps': 30.0,
        'total_frames': 300,
        'resolution': '640x480',
        'score': {
            'status': 'ready',
            'components': {'D': 5.0, 'E': 20.0, 'T': 10.0, 'H': 10.0, 'P': 0.0, 'total': 45.0},
            'selected_jump_numbers': list(range(1, 11)),
            'deductions': [],
        },
    }

    monkeypatch.setattr('trampoline.llm_service.resolve_api_key', lambda: 'test-key')
    monkeypatch.setattr('trampoline.llm_service.resolve_models', lambda: ('deepseek-v4-flash', 'deepseek-v4-pro'))
    monkeypatch.setattr('trampoline.llm_service.stream_llm_analysis', lambda report, model=None: iter(['[ERROR] LLM 调用失败: APIConnectionError: Connection error.']))
    monkeypatch.setattr('trampoline.llm_service.run_llm_analysis_sync', lambda report, model=None, timeout=90: '[ERROR] LLM 调用失败: APIConnectionError: Connection error.')

    client = app_module.app.test_client()
    response = client.get(f'/api/video/llm_analysis/{video_id}')
    body = response.get_data(as_text=True)
    events = [
        json.loads(line.removeprefix('data: '))
        for line in body.splitlines()
        if line.startswith('data: ')
    ]
    final_error = [event for event in events if event['type'] == 'error'][-1]

    assert final_error['provider'] == 'deepseek'
    assert final_error['fast_model'] == 'deepseek-v4-flash'
    assert final_error['quality_model'] == 'deepseek-v4-pro'
    assert 'APIConnectionError' in final_error['message']
    assert '出口网络' in final_error['hint']


def test_retained_frontend_has_no_deleted_fitness_endpoint_references():
    retained_sources = {
        'templates/index.html': Path('templates/index.html').read_text(encoding='utf-8'),
        'templates/dashboard.html': Path('templates/dashboard.html').read_text(encoding='utf-8'),
        'templates/profile.html': Path('templates/profile.html').read_text(encoding='utf-8'),
        'templates/video_analysis.html': Path('templates/video_analysis.html').read_text(encoding='utf-8'),
        'static/js/video_analysis.js': Path('static/js/video_analysis.js').read_text(encoding='utf-8'),
    }
    forbidden = [
        '/video_feed',
        '/stop_camera',
        '/start_exercise',
        '/stop_exercise',
        '/get_status',
        '/exercises',
        '/api/profile/update',
        '/api/video/analyze_frame',
    ]
    for name, content in retained_sources.items():
        for token in forbidden:
            assert token not in content, f'{token} leaked into {name}'
