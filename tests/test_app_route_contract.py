from pathlib import Path

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
