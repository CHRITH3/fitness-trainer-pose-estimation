from pathlib import Path
import re

import app as app_module


def test_trampoline_video_analysis_js_ids_exist_in_template():
    js = '\n'.join([
        Path('static/js/video_analysis.js').read_text(encoding='utf-8'),
        Path('static/js/trampoline_calibration_ui.js').read_text(encoding='utf-8'),
    ])
    html = Path('templates/video_analysis.html').read_text(encoding='utf-8')

    dynamic_ids = {'report-details-toggle'}
    js_ids = set(re.findall(r"getElementById\('([^']+)'\)", js)) - dynamic_ids
    html_ids = set(re.findall(r'id="([^"]+)"', html))

    missing = sorted(js_ids - html_ids)
    assert missing == [], f'JS references missing template ids: {missing}'


def test_trampoline_page_includes_direct_on_video_calibration_ui_and_scripts():
    client = app_module.app.test_client()
    response = client.get('/video_analysis?mode=trampoline')

    assert response.status_code == 200
    html = response.get_data(as_text=True)

    assert 'id="corner-marking-step"' in html
    assert 'id="add-calibration-frame"' in html
    assert 'id="start-trampoline-analysis"' in html
    assert 'id="calibration-list"' in html
    assert 'id="analysis-canvas"' in html
    assert 'id="corner-canvas"' not in html
    assert '直接在视频画面上' in html
    assert '当前分析范围' not in html
    assert '分析质量' not in html
    assert 'id="stat-flight-time"' in html
    assert 'id="stat-landing"' in html
    assert 'id="landing-map"' in html
    assert 'js/video_analysis_helpers.js' in html
    assert 'js/trampoline_calibration_geometry.js' in html
    assert 'js/trampoline_calibration_ui.js' in html
    assert 'js/video_analysis.js' in html


def test_trampoline_frontend_contract_uses_redesigned_workflow_and_hidden_compat_nodes():
    html = Path('templates/video_analysis.html').read_text(encoding='utf-8')
    js = Path('static/js/video_analysis.js').read_text(encoding='utf-8')
    css = Path('static/css/video_analysis.css').read_text(encoding='utf-8')

    assert '实时统计' not in html
    assert '过程反馈' not in html
    assert '分析报告' not in html
    assert 'id="stat-flight-time"' in html
    assert 'id="stat-landing"' in html
    assert 'id="show-calibration"' in html
    assert 'id="show-results"' in html
    assert 'id="sequence-action-breakdown"' in html
    assert 'id="sequence-duration"' in html
    assert 'class="panel flight-panel"' in html
    assert 'id="flight-chart"' in html
    assert 'id="download-report-btn"' in html
    assert 'id="llm-active-panel"' in html
    assert 'data-llm-section="整体表现"' in html
    assert 'data-llm-section="主要问题"' in html
    assert 'data-llm-section="逐跳点评"' in html
    assert 'data-llm-section="改进建议"' in html
    assert 'stat-score' not in html
    assert 'stat-grade' not in html
    assert 'stat-state' not in html
    assert 'showAnalysisSummary' in js
    assert 'setWorkflowTab' in js
    assert 'renderFlightChart' in js
    assert 'renderLlmSection' in js
    assert 'renderJumpDetailPanel' in js
    assert 'llmFullText' in js
    assert 'AI 分析\n------------------------------' in js
    assert '动作分布：${analysisResults.actionBreakdown}' in js
    assert 'report-details-toggle' not in js
    assert '.step-switch' in css
    assert '.sequence-summary' in css
    assert '.chart-line' in css
    assert '.flight-panel' in css
    assert '.llm-tabs' in css
    assert '.llm-active-panel' in css
    assert '.llm-jump-detail-popover' in css
    assert '#corner-canvas' not in css
    assert 'calibration-active #analysis-canvas' in css
