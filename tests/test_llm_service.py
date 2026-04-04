"""
Tests for LLM service: report building, prompt generation, response segmentation.
"""

import pytest
from trampoline.llm_service import (
    AnalysisReport, build_prompt, clean_chunk, segment_response,
    get_cached, set_cached, resolve_api_key, resolve_models,
    run_llm_analysis_sync, _llm_cache,
)


@pytest.fixture
def mock_analysis():
    return {
        'reps': 5,
        'completed_jumps': [
            {'jump_number': 1, 'action': 'Straight', 'flight_frames': 20, 'is_intermediate': False},
            {'jump_number': 2, 'action': 'Tuck', 'flight_frames': 30, 'is_intermediate': False},
            {'jump_number': 3, 'action': 'Straddle', 'flight_frames': 35, 'is_intermediate': False},
            {'jump_number': 4, 'action': 'Tuck', 'flight_frames': 28, 'is_intermediate': False},
            {'jump_number': 5, 'action': 'Straight', 'flight_frames': 5, 'is_intermediate': True},
        ],
        'fps': 25,
        'total_frames': 500,
        'resolution': '1920x1080',
    }


class TestAnalysisReport:
    def test_from_video_analysis(self, mock_analysis):
        report = AnalysisReport.from_video_analysis(mock_analysis)
        assert report.total_jumps == 5
        assert report.duration_s == 20.0
        assert report.fps == 25
        assert report.resolution == '1920x1080'
        assert len(report.completed_jumps) == 5

    def test_action_distribution_excludes_intermediate(self, mock_analysis):
        report = AnalysisReport.from_video_analysis(mock_analysis)
        # Jump 5 is intermediate, should be excluded from distribution
        assert report.action_distribution == {'Straight': 1, 'Tuck': 2, 'Straddle': 1}

    def test_flight_duration_enrichment(self, mock_analysis):
        report = AnalysisReport.from_video_analysis(mock_analysis)
        assert report.completed_jumps[0]['flight_duration_s'] == 0.8  # 20/25
        assert report.completed_jumps[1]['flight_duration_s'] == 1.2  # 30/25

    def test_defaults_for_missing_fields(self):
        report = AnalysisReport.from_video_analysis({'reps': 0})
        assert report.total_jumps == 0
        assert report.fps == 30
        assert report.resolution == 'unknown'
        assert report.completed_jumps == []

    def test_extra_sections_default_empty(self, mock_analysis):
        report = AnalysisReport.from_video_analysis(mock_analysis)
        assert report.extra_sections == ""
        assert report.landing_points is None


class TestBuildPrompt:
    def test_returns_two_messages(self, mock_analysis):
        report = AnalysisReport.from_video_analysis(mock_analysis)
        messages = build_prompt(report)
        assert len(messages) == 2
        assert messages[0]['role'] == 'system'
        assert messages[1]['role'] == 'user'

    def test_system_prompt_contains_constraints(self, mock_analysis):
        report = AnalysisReport.from_video_analysis(mock_analysis)
        messages = build_prompt(report)
        system = messages[0]['content']
        assert '数据不足' in system
        assert '运动员' in system or '教练' in system
        assert '整体表现' in system
        assert '逐跳点评' in system

    def test_user_prompt_contains_data(self, mock_analysis):
        report = AnalysisReport.from_video_analysis(mock_analysis)
        messages = build_prompt(report)
        user = messages[1]['content']
        assert '总跳次: 5' in user
        assert 'Straight' in user
        assert 'Tuck' in user

    def test_extra_sections_included(self, mock_analysis):
        report = AnalysisReport.from_video_analysis(mock_analysis)
        report.extra_sections = "落点偏移: 左偏 5cm"
        messages = build_prompt(report)
        user = messages[1]['content']
        assert '落点偏移' in user


class TestCleanChunk:
    def test_empty_chunk(self):
        assert clean_chunk("") == ""
        assert clean_chunk(None) == ""

    def test_strips_nothing_for_normal_text(self):
        assert clean_chunk("hello") == "hello"

    def test_merges_consecutive_newlines(self):
        assert clean_chunk("\nworld", "hello\n") == "world"

    def test_preserves_single_newline(self):
        assert clean_chunk("world", "hello") == "world"


class TestSegmentResponse:
    def test_all_sections_present(self):
        text = "## 整体表现\n好\n## 主要问题\n无\n## 逐跳点评\n略\n## 改进建议\n加油"
        sections = segment_response(text)
        assert sections['整体表现'] == '好'
        assert sections['主要问题'] == '无'
        assert sections['逐跳点评'] == '略'
        assert sections['改进建议'] == '加油'

    def test_missing_section(self):
        text = "## 整体表现\n好\n## 改进建议\n加油"
        sections = segment_response(text)
        assert sections['整体表现'] == '好'
        assert sections['主要问题'] == ''
        assert sections['改进建议'] == '加油'

    def test_multiline_content(self):
        text = "## 整体表现\n第一行\n第二行\n## 主要问题\n无\n## 逐跳点评\n略\n## 改进建议\n加油"
        sections = segment_response(text)
        assert '第一行' in sections['整体表现']
        assert '第二行' in sections['整体表现']


class TestCache:
    def setup_method(self):
        _llm_cache.clear()

    def test_set_and_get(self):
        set_cached('test_id', 'full text', {'整体表现': '好'})
        cached = get_cached('test_id')
        assert cached is not None
        assert cached['full_text'] == 'full text'

    def test_miss_returns_none(self):
        assert get_cached('nonexistent') is None


class TestApiKeyResolution:
    def test_prefers_qwen_api_key(self, monkeypatch):
        monkeypatch.setenv('QWEN_API_KEY', 'qwen-key')
        monkeypatch.setenv('DASHSCOPE_API_KEY', 'dashscope-key')
        assert resolve_api_key() == 'qwen-key'

    def test_falls_back_to_dashscope_api_key(self, monkeypatch):
        monkeypatch.delenv('QWEN_API_KEY', raising=False)
        monkeypatch.setenv('DASHSCOPE_API_KEY', 'dashscope-key')
        assert resolve_api_key() == 'dashscope-key'

    def test_returns_empty_string_when_no_key_present(self, monkeypatch):
        monkeypatch.delenv('QWEN_API_KEY', raising=False)
        monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
        assert resolve_api_key() == ''


class TestResolveModels:
    def test_defaults(self, monkeypatch):
        monkeypatch.delenv('QWEN_FAST_MODEL', raising=False)
        monkeypatch.delenv('QWEN_MODEL', raising=False)
        fast, quality = resolve_models()
        assert fast == 'qwen-plus'
        assert quality == 'qwen3.6-plus-2026-04-02'

    def test_custom_env(self, monkeypatch):
        monkeypatch.setenv('QWEN_FAST_MODEL', 'custom-fast')
        monkeypatch.setenv('QWEN_MODEL', 'custom-quality')
        fast, quality = resolve_models()
        assert fast == 'custom-fast'
        assert quality == 'custom-quality'


class TestRunLlmAnalysisSync:
    def test_returns_error_without_api_key(self, monkeypatch, mock_analysis):
        monkeypatch.delenv('QWEN_API_KEY', raising=False)
        monkeypatch.delenv('DASHSCOPE_API_KEY', raising=False)
        report = AnalysisReport.from_video_analysis(mock_analysis)
        result = run_llm_analysis_sync(report)
        assert result.startswith('[ERROR]')
        assert 'API key' in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
