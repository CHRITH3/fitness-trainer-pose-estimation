from __future__ import annotations

from pathlib import Path

import pytest

from trampoline.bed_calibration import (
    create_bed_calibration,
    load_calibration,
    save_calibration,
    transform_point,
)


def test_bed_calibration_transform_and_persistence(tmp_path: Path) -> None:
    corners = {
        "top_left": {"x": 100.0, "y": 200.0},
        "top_right": {"x": 300.0, "y": 210.0},
        "bottom_right": {"x": 320.0, "y": 420.0},
        "bottom_left": {"x": 90.0, "y": 410.0},
    }

    calibration = create_bed_calibration(
        corners=corners,
        frame_width=360,
        frame_height=640,
    )

    top_left_norm = transform_point(corners["top_left"], calibration.bed_to_normalized)
    bottom_right_norm = transform_point(corners["bottom_right"], calibration.bed_to_normalized)
    center_norm = transform_point(calibration.center_point, calibration.bed_to_normalized)

    assert top_left_norm.x == pytest.approx(0.0, abs=1e-4)
    assert top_left_norm.y == pytest.approx(0.0, abs=1e-4)
    assert bottom_right_norm.x == pytest.approx(1.0, abs=1e-4)
    assert bottom_right_norm.y == pytest.approx(1.0, abs=1e-4)
    assert center_norm.x == pytest.approx(0.5, abs=1e-3)
    assert center_norm.y == pytest.approx(0.5, abs=1e-3)

    saved_path = save_calibration(calibration, tmp_path / "sample01")
    loaded = load_calibration(tmp_path / "sample01")

    assert saved_path == Path(tmp_path / "sample01" / "calibration.json")
    assert loaded is not None
    assert loaded.center_point.x == pytest.approx(calibration.center_point.x)
    assert loaded.center_point.y == pytest.approx(calibration.center_point.y)
