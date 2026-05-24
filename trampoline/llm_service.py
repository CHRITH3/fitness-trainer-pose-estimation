"""
LLM Service — Builds structured analysis reports and streams LLM commentary.

Components:
  A. AnalysisReport dataclass — structured data from trampoline analysis
  B. build_prompt() — constructs OpenAI-compatible messages from report
  C. stream_llm_analysis() — streams LLM response chunks
  D. clean_chunk() / segment_response() — post-processing
"""

import os
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
    score: Optional[dict] = None
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
        landing_points = [j.get("landing") for j in enriched if j.get("landing")]

        return cls(
            total_jumps=analysis.get("reps", len(jumps)),
            duration_s=duration_s,
            fps=fps,
            resolution=analysis.get("resolution", "unknown"),
            completed_jumps=enriched,
            action_distribution=dist,
            landing_points=landing_points or None,
            score=analysis.get("score"),
        )


# ── B. Prompt Builder ──────────────────────────────────────────────

_SYSTEM_PROMPT = """\
你是一位专业的蹦床运动 AI 分析助手，面向运动员和教练提供技术分析。

## 回答规则
- 只能基于下方提供的结构化分析数据回答，不要猜测视频中未检测出的动作或问题
- 如果某方面数据不足以做出判断，请明确说明"数据不足"，不要编造
- 视觉量化评分中的 D 分是候选难度估计，E 分是可量化完成质量估计，不要表述为正式 FIG 裁判定分
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
        landing = j.get("landing")
        landing_text = ""
        if landing:
            xy = landing.get("bed_xy_m") or ["?", "?"]
            conf = landing.get("confidence", "?")
            zone = landing.get("zone", "?")
            landing_text = f" | 落点 ({xy[0]}, {xy[1]})m / {zone} / 置信度 {conf}"
        jump_lines.append(
            f"  第{j['jump_number']}跳: {j['action']} | "
            f"滞空 {j.get('flight_duration_s', '?')}秒 ({j.get('flight_frames', '?')}帧){inter}{landing_text}"
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

    if report.landing_points:
        user_content += "\n## 落点数据\n"
        for idx, landing in enumerate(report.landing_points, 1):
            xy = landing.get("bed_xy_m") or ["?", "?"]
            user_content += (
                f"- 落点{idx}: ({xy[0]}, {xy[1]})m | "
                f"区域 {landing.get('zone', '?')} | "
                f"距中心 {landing.get('dist_from_center_m', '?')}m | "
                f"置信度 {landing.get('confidence', '?')}\n"
            )

    if report.score:
        components = report.score.get("components") or {}
        user_content += "\n## 视觉量化评分\n"
        user_content += (
            f"- 评分状态: {report.score.get('status', '?')}\n"
            f"- 选中跳次: {report.score.get('selected_jump_numbers') or '未确认'}\n"
            f"- D 候选难度: {components.get('D')}\n"
            f"- E 完成估计: {components.get('E')}\n"
            f"- T 腾空时间: {components.get('T')}\n"
            f"- H 水平位移: {components.get('H')}\n"
            f"- P 附加罚分: {components.get('P')}\n"
            f"- 总分: {components.get('total')}\n"
        )
        summary = report.score.get("summary") or {}
        if summary:
            user_content += "- 评分说明: " + "；".join(str(v) for v in summary.values() if v) + "\n"
        deductions = report.score.get("deductions") or []
        if deductions:
            user_content += "- 逐跳评分依据:\n"
            for row in deductions:
                notes = "；".join(row.get("notes") or [])
                user_content += (
                    f"  第{row.get('jump_number')}跳 {row.get('action')}: "
                    f"D={row.get('difficulty')}, T={row.get('flight_s')}s, "
                    f"H扣={row.get('h_deduction')}, E扣={row.get('e_deduction')} | {notes}\n"
                )

    if report.extra_sections:
        user_content += f"\n## 补充数据\n{report.extra_sections}\n"

    return [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]


# ── C. LLM Streaming Client ───────────────────────────────────────

def _first_env(*names: str, default: str = "") -> str:
    """Return the first non-empty environment variable value."""
    for name in names:
        value = os.environ.get(name)
        if value:
            return value
    return default


def resolve_api_key() -> str:
    """Resolve the LLM API key from supported environment variables."""
    return _first_env(
        "DEEPSEEK_API_KEY",
        "DS_API_KEY",
        "QWEN_API_KEY",
        "DASHSCOPE_API_KEY",
    )


def resolve_base_url() -> str:
    """Resolve the OpenAI-compatible base URL for the active provider."""
    return _first_env(
        "DEEPSEEK_BASE_URL",
        "DS_BASE_URL",
        "QWEN_BASE_URL",
        default="https://api.deepseek.com",
    )


def resolve_models() -> tuple:
    """Return (fast_model, quality_model) from environment."""
    fast = _first_env(
        "DEEPSEEK_FAST_MODEL",
        "DS_FAST_MODEL",
        "QWEN_FAST_MODEL",
        default="deepseek-v4-flash",
    )
    quality = _first_env(
        "DEEPSEEK_MODEL",
        "DS_PRO_MODEL",
        "QWEN_MODEL",
        default="deepseek-v4-pro",
    )
    return fast, quality


def stream_llm_analysis(report: AnalysisReport, model: str = None, timeout: float = 60) -> Generator[str, None, None]:
    """Stream LLM analysis chunks. Yields text strings.

    Args:
        report: Structured analysis data.
        model: Model name override. Defaults to the configured quality model.
        timeout: API timeout in seconds.
    """
    try:
        import openai
    except ImportError:
        yield "\n\n[ERROR] openai 库未安装，请运行 pip install openai"
        return

    api_key = resolve_api_key()
    base_url = resolve_base_url()
    if model is None:
        _, model = resolve_models()

    if not api_key:
        yield "\n\n[ERROR] 未配置 LLM API key 环境变量（支持 DEEPSEEK_API_KEY / DS_API_KEY / QWEN_API_KEY / DASHSCOPE_API_KEY）"
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
    base_url = resolve_base_url()
    if model is None:
        _, model = resolve_models()

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


def clear_cached(video_id: str):
    """Remove cached LLM result for a video id."""
    _llm_cache.pop(video_id, None)
