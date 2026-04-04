"""
LLM Service — Builds structured analysis reports and streams LLM commentary.

Components:
  A. AnalysisReport dataclass — structured data from trampoline analysis
  B. build_prompt() — constructs OpenAI-compatible messages from report
  C. stream_llm_analysis() — streams LLM response chunks
  D. clean_chunk() / segment_response() — post-processing
"""

import os
import json
import time
import dataclasses
from collections import Counter
from typing import Generator, Optional


# ── A. AnalysisReport ──────────────────────────────────────────────

@dataclasses.dataclass
class AnalysisReport:
    """Structured trampoline analysis result. Extensible for future features."""
    total_jumps: int
    duration_s: float
    fps: float
    resolution: str
    completed_jumps: list           # [{jump_number, action, flight_frames, flight_duration_s, is_intermediate}]
    action_distribution: dict       # {"Straight": 3, "Tuck": 2, ...}

    # Future-extensible (default None)
    landing_points: Optional[list] = None
    form_scores: Optional[list] = None
    rotation_data: Optional[list] = None
    extra_sections: str = ""

    @classmethod
    def from_video_analysis(cls, analysis: dict) -> "AnalysisReport":
        """Build report from video_analyses[video_id] dict."""
        jumps = analysis.get("completed_jumps", [])
        fps = analysis.get("fps", 30)
        total_frames = analysis.get("total_frames", 0)
        duration_s = round(total_frames / fps, 1) if fps > 0 else 0

        # Enrich jumps with flight_duration_s
        enriched = []
        for j in jumps:
            enriched.append({
                **j,
                "flight_duration_s": round(j.get("flight_frames", 0) / fps, 2) if fps > 0 else 0,
            })

        # Action distribution (excluding intermediate bounces)
        real_jumps = [j for j in jumps if not j.get("is_intermediate")]
        dist = dict(Counter(j.get("action", "Unknown") for j in real_jumps))

        return cls(
            total_jumps=analysis.get("reps", len(jumps)),
            duration_s=duration_s,
            fps=fps,
            resolution=analysis.get("resolution", "unknown"),
            completed_jumps=enriched,
            action_distribution=dist,
        )


# ── B. Prompt Builder ──────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的蹦床运动 AI 分析助手，面向运动员和教练提供技术分析。

## 回答规则
- 只能基于下方提供的结构化分析数据回答，不要猜测视频中未检测出的动作或问题
- 如果某方面数据不足以做出判断，请明确说明"数据不足"，不要编造
- 语气专业但友好，面向运动员或教练

## 输出格式
必须严格使用以下四个 markdown 标题，不要增减或改名：

## 整体表现
（2-3 句话概述本次训练的整体情况）

## 主要问题
（列出数据中反映的主要问题，如果没有明显问题则说明表现良好）

## 逐跳点评
（逐跳分析，包含动作名称、滞空时间、简要评价）

## 改进建议
（基于数据给出具体、可操作的改进建议）\
"""


def build_prompt(report: AnalysisReport) -> list:
    """Construct OpenAI-compatible messages list from AnalysisReport."""
    # Format per-jump table
    jump_lines = []
    for j in report.completed_jumps:
        inter = "（中间直跳）" if j.get("is_intermediate") else ""
        jump_lines.append(
            f"  第{j['jump_number']}跳: {j['action']} | "
            f"滞空 {j.get('flight_duration_s', '?')}秒 ({j.get('flight_frames', '?')}帧){inter}"
        )

    # Format action distribution
    dist_str = ", ".join(f"{k}: {v}次" for k, v in report.action_distribution.items()) or "无数据"

    user_content = f"""\
## 视频基本信息
- 总跳次: {report.total_jumps}
- 视频时长: {report.duration_s}秒
- 帧率: {report.fps:.0f}fps
- 分辨率: {report.resolution}

## 动作分布
{dist_str}

## 逐跳详情
{chr(10).join(jump_lines) if jump_lines else "无跳跃数据"}
"""

    if report.extra_sections:
        user_content += f"\n## 补充数据\n{report.extra_sections}\n"

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ── C. LLM Streaming Client ───────────────────────────────────────

def resolve_api_key() -> str:
    """Resolve the DashScope/Qwen API key from supported environment variables."""
    return (
        os.environ.get("QWEN_API_KEY")
        or os.environ.get("DASHSCOPE_API_KEY")
        or ""
    )


def resolve_models() -> tuple:
    """Return (fast_model, quality_model) from environment."""
    fast = os.environ.get("QWEN_FAST_MODEL", "qwen-plus")
    quality = os.environ.get("QWEN_MODEL", "qwen3.6-plus-2026-04-02")
    return fast, quality


def stream_llm_analysis(report: AnalysisReport, model: str = None, timeout: float = 60) -> Generator[str, None, None]:
    """Stream LLM analysis chunks. Yields text strings.

    Args:
        report: Structured analysis data.
        model: Model name override. Defaults to QWEN_MODEL env var.
        timeout: API timeout in seconds.
    """
    try:
        import openai
    except ImportError:
        yield "\n\n[ERROR] openai 库未安装，请运行 pip install openai"
        return

    api_key = resolve_api_key()
    base_url = os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if model is None:
        model = os.environ.get("QWEN_MODEL", "qwen3.6-plus-2026-04-02")

    if not api_key:
        yield "\n\n[ERROR] 未配置 QWEN_API_KEY 或 DASHSCOPE_API_KEY 环境变量"
        return

    messages = build_prompt(report)

    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=True,
        )
        for chunk in stream:
            if chunk.choices and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        yield f"\n\n[ERROR] LLM 调用失败: {type(e).__name__}: {e}"


def run_llm_analysis_sync(report: AnalysisReport, model: str = None, timeout: float = 90) -> str:
    """Run LLM analysis synchronously (non-streaming). Returns full text or error string."""
    try:
        import openai
    except ImportError:
        return "[ERROR] openai 库未安装"

    api_key = resolve_api_key()
    base_url = os.environ.get("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1")
    if model is None:
        model = os.environ.get("QWEN_MODEL", "qwen3.6-plus-2026-04-02")

    if not api_key:
        return "[ERROR] 未配置 API key"

    messages = build_prompt(report)

    try:
        client = openai.OpenAI(api_key=api_key, base_url=base_url, timeout=timeout)
        response = client.chat.completions.create(
            model=model,
            messages=messages,
            stream=False,
        )
        return response.choices[0].message.content or ""
    except Exception as e:
        return f"[ERROR] LLM 调用失败: {type(e).__name__}: {e}"


# ── D. Response Cleaning & Segmentation ────────────────────────────

def clean_chunk(chunk: str, prev_chunk: str = "") -> str:
    """Clean a single streaming chunk. Returns empty string if chunk should be skipped."""
    if not chunk:
        return ""
    # Merge consecutive newlines at chunk boundary
    if prev_chunk.endswith("\n") and chunk.startswith("\n"):
        chunk = chunk.lstrip("\n")
    return chunk


_SECTION_HEADINGS = ["整体表现", "主要问题", "逐跳点评", "改进建议"]


def segment_response(full_text: str) -> dict:
    """Split LLM response by ## headings into structured sections."""
    sections = {h: "" for h in _SECTION_HEADINGS}

    # Normalize: ensure all ## headings are preceded by newline
    normalized = full_text.replace("\n## ", "\n\n## ")
    parts = normalized.split("## ")

    for part in parts:
        for heading in _SECTION_HEADINGS:
            if part.startswith(heading):
                content = part[len(heading):].strip()
                sections[heading] = content
                break

    return sections


# ── Cache ──────────────────────────────────────────────────────────

_llm_cache: dict = {}  # video_id -> {"full_text": str, "sections": dict, "timestamp": float}
_CACHE_TTL = 1800  # 30 minutes


def get_cached(video_id: str) -> Optional[dict]:
    """Get cached LLM result if available and fresh."""
    entry = _llm_cache.get(video_id)
    if entry and (time.time() - entry["timestamp"]) < _CACHE_TTL:
        return entry
    if entry:
        del _llm_cache[video_id]
    return None


def set_cached(video_id: str, full_text: str, sections: dict):
    """Cache LLM result."""
    _llm_cache[video_id] = {
        "full_text": full_text,
        "sections": sections,
        "timestamp": time.time(),
    }
