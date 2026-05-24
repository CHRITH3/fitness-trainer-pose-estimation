import pytest

from trampoline.score import ScoreSelectionError, compute_score


def make_jump(number, action="Tuck", frames=30, landing=None, intermediate=False):
    if landing is None:
        landing = {
            "bed_xy_m": [0.1, 0.1],
            "dist_from_center_m": 0.14,
            "confidence": 0.9,
        }
    return {
        "jump_number": number,
        "action": action,
        "flight_frames": frames,
        "landing": landing,
        "is_intermediate": intermediate,
    }


def make_analysis(jumps, fps=30.0):
    return {
        "completed_jumps": jumps,
        "fps": fps,
        "video_fps": fps,
        "reps": len(jumps),
    }


def test_compute_score_ready_for_exactly_ten_effective_jumps():
    analysis = make_analysis([make_jump(i) for i in range(1, 11)])

    score = compute_score(analysis)

    assert score["status"] == "ready"
    assert score["selected_jump_numbers"] == list(range(1, 11))
    assert score["components"]["D"] == pytest.approx(5.0)
    assert score["components"]["E"] == pytest.approx(20.0)
    assert score["components"]["T"] == pytest.approx(10.0)
    assert score["components"]["H"] == pytest.approx(10.0)
    assert score["components"]["P"] == pytest.approx(0.0)
    assert score["components"]["total"] == pytest.approx(45.0)
    assert len(score["deductions"]) == 10


def test_compute_score_requires_selection_when_more_than_ten_effective_jumps():
    analysis = make_analysis([make_jump(i) for i in range(1, 13)])

    score = compute_score(analysis)

    assert score["status"] == "selection_required"
    assert score["components"]["total"] is None
    assert score["default_selected_jump_numbers"] == list(range(1, 11))
    assert score["effective_jump_count"] == 12


def test_compute_score_uses_selected_ten_jump_numbers():
    jumps = [make_jump(i, action="Straight", frames=15 + i) for i in range(1, 13)]
    analysis = make_analysis(jumps, fps=30.0)

    score = compute_score(analysis, selected_jump_numbers=list(range(3, 13)))

    assert score["status"] == "ready"
    assert score["selected_jump_numbers"] == list(range(3, 13))
    assert score["components"]["D"] == pytest.approx(0.0)
    assert score["components"]["T"] == pytest.approx(sum((15 + i) / 30 for i in range(3, 13)))


def test_compute_score_rejects_selection_that_is_not_ten_jumps():
    analysis = make_analysis([make_jump(i) for i in range(1, 13)])

    with pytest.raises(ScoreSelectionError, match="Exactly 10"):
        compute_score(analysis, selected_jump_numbers=[1, 2, 3])


def test_compute_score_rejects_non_effective_jump_selection():
    analysis = make_analysis([
        *[make_jump(i) for i in range(1, 10)],
        make_jump(10, intermediate=True),
        make_jump(11),
    ])

    with pytest.raises(ScoreSelectionError, match="not effective jumps"):
        compute_score(analysis, selected_jump_numbers=list(range(1, 11)))


def test_compute_score_outputs_incomplete_for_less_than_ten_jumps():
    analysis = make_analysis([make_jump(i) for i in range(1, 7)])

    score = compute_score(analysis)

    assert score["status"] == "incomplete"
    assert score["selected_jump_numbers"] == list(range(1, 7))
    assert score["components"]["total"] is not None
    assert "辅助估计" in score["message"]


def test_compute_score_handles_missing_landing_and_unknown_action():
    jumps = [make_jump(i) for i in range(1, 10)]
    last_jump = make_jump(10, action="Unknown")
    last_jump.pop("landing")
    jumps.append(last_jump)
    analysis = make_analysis(jumps)

    score = compute_score(analysis)

    last = score["deductions"][-1]
    assert score["status"] == "ready"
    assert last["action"] == "Unknown"
    assert last["h_deduction"] == pytest.approx(0.3)
    assert last["e_deduction"] > 0
    assert any("缺少落点数据" in note for note in last["notes"])


def test_compute_score_no_effective_jumps_is_insufficient_data():
    analysis = make_analysis([make_jump(1, intermediate=True)])

    score = compute_score(analysis)

    assert score["status"] == "insufficient_data"
    assert score["components"]["total"] is None
    assert score["selected_jump_numbers"] == []
