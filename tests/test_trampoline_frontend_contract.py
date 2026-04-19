from pathlib import Path
import re

import app as app_module


def test_trampoline_video_analysis_js_ids_exist_in_template():
    js = Path('static/js/video_analysis.js').read_text(encoding='utf-8')
    html = Path('templates/video_analysis.html').read_text(encoding='utf-8')

    js_ids = set(re.findall(r"getElementById\('([^']+)'\)", js))
    html_ids = set(re.findall(r'id="([^"]+)"', html))

    missing = sorted(js_ids - html_ids)
    assert missing == [], f'JS references missing template ids: {missing}'


def test_trampoline_page_includes_pending_calibration_ui_and_scripts():
    client = app_module.app.test_client()
    response = client.get('/video_analysis?mode=trampoline')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="corner-marking-step"' in html
    assert 'id="add-calibration-frame"' in html
    assert 'id="start-trampoline-analysis"' in html
    assert 'id="calibration-list"' in html
    assert 'js/trampoline_calibration_geometry.js' in html
    assert 'js/trampoline_calibration_ui.js' in html
    assert 'js/video_analysis.js' in html
