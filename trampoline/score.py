"""Visual scoring helpers for trampoline video analysis.

The module produces an auxiliary DETHP score from the currently available
2D video-analysis result while leaving room for future 3D/realtime inputs.
"""

from __future__ import annotations

import math
from typing import Any, Dict, Iterable, List, Optional


REQUIRED_ROUTINE_JUMPS = 10
DIFFICULTY_BY_ACTION = {
    "Straight": 0.0,
    "Tuck": 0.5,
    "Pike": 0.5,
    "Straddle": 0.1,
    "Unknown": 0.0,
}


class ScoreSelectionError(ValueError):
    """Raised when the selected scoring jumps are invalid."""


def _finite_number(value: Any) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number


def _round_score(value: float) -> float:
    return round(float(value) + 1e-9, 2)


def _real_jumps(analysis: Dict[str, Any]) -> List[Dict[str, Any]]:
    jumps = analysis.get("completed_jumps") or []
    if not isinstance(jumps, list):
        return []
    return [jump for jump in jumps if isinstance(jump, dict) and not jump.get("is_intermediate")]


def _fps(analysis: Dict[str, Any]) -> float:
    fps = _finite_number(analysis.get("fps"))
    if fps is None:
        fps = _finite_number(analysis.get("video_fps"))
    return fps if fps and fps > 0 else 30.0


def _jump_number(jump: Dict[str, Any], fallback: int) -> int:
    number = _finite_number(jump.get("jump_number"))
    return int(number) if number is not None else fallback


def _select_jumps(
    real_jumps: List[Dict[str, Any]],
    selected_jump_numbers: Optional[Iterable[Any]],
) -> List[Dict[str, Any]]:
    if selected_jump_numbers is None:
        return real_jumps

    try:
        selected_numbers = [int(value) for value in selected_jump_numbers]
    except (TypeError, ValueError) as exc:
        raise ScoreSelectionError("selected_jump_numbers must be a list of jump numbers") from exc

    if len(selected_numbers) != REQUIRED_ROUTINE_JUMPS:
        raise ScoreSelectionError("Exactly 10 effective jumps must be selected for scoring")
    if len(set(selected_numbers)) != len(selected_numbers):
        raise ScoreSelectionError("Selected jump numbers must not contain duplicates")

    lookup = {
        _jump_number(jump, index + 1): jump
        for index, jump in enumerate(real_jumps)
    }
    missing = [number for number in selected_numbers if number not in lookup]
    if missing:
        raise ScoreSelectionError(f"Selected jump numbers are not effective jumps: {missing}")

    return [lookup[number] for number in selected_numbers]


def _flight_seconds(jump: Dict[str, Any], fps: float) -> Optional[float]:
    duration = _finite_number(jump.get("flight_duration_s"))
    if duration is not None:
        return duration
    frames = _finite_number(jump.get("flight_frames"))
    if frames is None or fps <= 0:
        return None
    return frames / fps


def _landing_distance(landing: Dict[str, Any]) -> Optional[float]:
    distance = _finite_number(landing.get("dist_from_center_m"))
    if distance is not None:
        return abs(distance)
    xy = landing.get("bed_xy_m")
    if isinstance(xy, (list, tuple)) and len(xy) >= 2:
        x = _finite_number(xy[0])
        y = _finite_number(xy[1])
        if x is not None and y is not None:
            return math.sqrt(x * x + y * y)
    return None


def _h_deduction(landing: Any) -> tuple[float, List[str], Optional[float]]:
    notes: List[str] = []
    if not isinstance(landing, dict):
        return 0.3, ["缺少落点数据，H 分按保守 0.3 扣分"], None

    confidence = _finite_number(landing.get("confidence"))
    distance = _landing_distance(landing)
    if distance is None:
        return 0.3, ["落点坐标不可用，H 分按保守 0.3 扣分"], None

    if distance <= 0.25:
        deduction = 0.0
        notes.append("落点接近中心区")
    elif distance <= 0.55:
        deduction = 0.1
        notes.append("落点轻度偏离中心")
    elif distance <= 0.85:
        deduction = 0.2
        notes.append("落点中度偏离中心")
    else:
        deduction = 0.3
        notes.append("落点明显偏离中心")

    if confidence is not None and confidence < 0.35:
        deduction = max(deduction, 0.2)
        notes.append("落点置信度较低")
    elif confidence is not None and confidence < 0.6:
        notes.append("落点置信度中等")

    return deduction, notes, distance


def _e_deduction(
    jump: Dict[str, Any],
    h_deduction: float,
    distance: Optional[float],
    flight_s: Optional[float],
    avg_flight_s: Optional[float],
) -> tuple[float, List[str]]:
    notes: List[str] = []
    deduction = 0.0

    action = jump.get("action") or "Unknown"
    if action == "Unknown":
        deduction += 0.3
        notes.append("动作识别为 Unknown，完成质量置信不足")

    if h_deduction >= 0.3:
        deduction += 0.2
        notes.append("落点明显偏移或缺失，影响完成质量估计")
    elif h_deduction >= 0.2:
        deduction += 0.1
        notes.append("落点中度偏移")

    if flight_s is None:
        deduction += 0.1
        notes.append("缺少腾空时间数据")
    elif avg_flight_s and avg_flight_s > 0 and abs(flight_s - avg_flight_s) / avg_flight_s > 0.22:
        deduction += 0.1
        notes.append("腾空时间相对整套波动较大")

    if distance is not None and distance > 1.1:
        deduction += 0.1
        notes.append("落点距离中心过远")

    if not notes:
        notes.append("当前可量化指标未发现明显完成扣分")

    return min(0.5, round(deduction, 2)), notes


def _difficulty(action: str) -> tuple[float, str]:
    value = DIFFICULTY_BY_ACTION.get(action, DIFFICULTY_BY_ACTION["Unknown"])
    if action in ("Tuck", "Pike"):
        return value, "按当前动作分类给出单周姿态候选难度，复杂翻转需人工确认"
    if action == "Straddle":
        return value, "按分腿跳辅助难度估计"
    if action == "Straight":
        return value, "直体过渡/基础跳不计入候选难度"
    return value, "动作未知，候选难度按 0 处理"


def _selection_required(real_jumps: List[Dict[str, Any]]) -> Dict[str, Any]:
    default_numbers = [
        _jump_number(jump, index + 1)
        for index, jump in enumerate(real_jumps[:REQUIRED_ROUTINE_JUMPS])
    ]
    return {
        "status": "selection_required",
        "message": "有效跳次超过 10 次，请确认用于评分的 10 跳",
        "selected_jump_numbers": [],
        "default_selected_jump_numbers": default_numbers,
        "effective_jump_count": len(real_jumps),
        "components": {"D": None, "E": None, "T": None, "H": None, "P": 0.0, "total": None},
        "deductions": [],
        "data_sources": _data_sources(),
    }


def _data_sources() -> Dict[str, Any]:
    return {
        "current": "2d_video_analysis",
        "difficulty": "action_classifier_candidate",
        "execution": "video_quantified_estimate",
        "time_of_flight": "jump_detector_frames",
        "horizontal_displacement": "bed_tracker_landing_projection",
        "penalty": "default_zero_not_entered",
        "reserved_inputs": ["pose3d_stream", "manual_penalty", "future_realtime"],
    }


def compute_score(
    analysis: Dict[str, Any],
    selected_jump_numbers: Optional[Iterable[Any]] = None,
) -> Dict[str, Any]:
    """Compute auxiliary DETHP score from a trampoline video-analysis object."""
    real_jumps = _real_jumps(analysis)
    if not real_jumps:
        return {
            "status": "insufficient_data",
            "message": "没有可评分的有效跳次",
            "selected_jump_numbers": [],
            "default_selected_jump_numbers": [],
            "effective_jump_count": 0,
            "components": {"D": None, "E": None, "T": None, "H": None, "P": 0.0, "total": None},
            "deductions": [],
            "data_sources": _data_sources(),
        }

    if selected_jump_numbers is None and len(real_jumps) > REQUIRED_ROUTINE_JUMPS:
        return _selection_required(real_jumps)

    fps = _fps(analysis)
    selected = _select_jumps(real_jumps, selected_jump_numbers)
    if selected_jump_numbers is None and len(selected) > REQUIRED_ROUTINE_JUMPS:
        selected = selected[:REQUIRED_ROUTINE_JUMPS]

    selected_numbers = [
        _jump_number(jump, index + 1)
        for index, jump in enumerate(selected)
    ]
    flight_values = [_flight_seconds(jump, fps) for jump in selected]
    valid_flights = [value for value in flight_values if value is not None]
    avg_flight_s = sum(valid_flights) / len(valid_flights) if valid_flights else None

    total_d = 0.0
    total_h_deduction = 0.0
    total_e_deduction = 0.0
    total_t = 0.0
    deduction_rows: List[Dict[str, Any]] = []

    for index, jump in enumerate(selected):
        action = jump.get("action") or "Unknown"
        difficulty, difficulty_note = _difficulty(action)
        flight_s = flight_values[index]
        landing = jump.get("landing")
        h_deduction, h_notes, distance = _h_deduction(landing)
        e_deduction, e_notes = _e_deduction(jump, h_deduction, distance, flight_s, avg_flight_s)

        total_d += difficulty
        total_h_deduction += h_deduction
        total_e_deduction += e_deduction
        if flight_s is not None:
            total_t += flight_s

        jump_number = _jump_number(jump, index + 1)
        deduction_rows.append({
            "jump_number": jump_number,
            "action": action,
            "difficulty": _round_score(difficulty),
            "difficulty_note": difficulty_note,
            "flight_s": None if flight_s is None else _round_score(flight_s),
            "h_deduction": _round_score(h_deduction),
            "e_deduction": _round_score(e_deduction),
            "landing_distance_m": None if distance is None else _round_score(distance),
            "notes": h_notes + e_notes,
        })

    p_score = 0.0
    d_score = _round_score(total_d)
    e_score = _round_score(max(0.0, 20.0 - total_e_deduction))
    t_score = _round_score(total_t)
    h_score = _round_score(max(0.0, 10.0 - total_h_deduction))
    total = _round_score(d_score + e_score + t_score + h_score - p_score)
    status = "ready" if len(selected) == REQUIRED_ROUTINE_JUMPS else "incomplete"
    message = (
        "已完成 10 跳视觉量化评分"
        if status == "ready"
        else f"当前仅有 {len(selected)} 个有效跳，评分为辅助估计"
    )

    return {
        "status": status,
        "message": message,
        "selected_jump_numbers": selected_numbers,
        "default_selected_jump_numbers": selected_numbers,
        "effective_jump_count": len(real_jumps),
        "components": {
            "D": d_score,
            "E": e_score,
            "T": t_score,
            "H": h_score,
            "P": p_score,
            "total": total,
        },
        "deductions": deduction_rows,
        "summary": {
            "difficulty_note": "D 分为当前动作识别候选难度，复杂翻转和转体需人工确认",
            "execution_note": "E 分为视频可量化完成质量估计，不替代正式完成裁判",
            "penalty_note": "P 分默认 0.0，尚未录入附加罚分",
        },
        "data_sources": _data_sources(),
    }
