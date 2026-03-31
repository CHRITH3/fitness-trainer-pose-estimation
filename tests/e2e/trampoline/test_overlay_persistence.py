from __future__ import annotations

from pathlib import Path

from app import app, trampoline_analyses
from trampoline.pipeline import analyze_video


PROJECT_ROOT = Path(__file__).resolve().parents[3]
SAMPLE_VIDEO = PROJECT_ROOT / "samples" / "tra_demo" / "sample01.mp4"


def test_overlay_persistence_for_existing_analysis(tmp_path: Path) -> None:
    analysis_id = "sample01"
    artifacts_dir = tmp_path / "artifacts"
    analysis_dir = artifacts_dir / analysis_id
    analyze_video(
        video_path=SAMPLE_VIDEO,
        output_dir=analysis_dir,
        landmarks_only=True,
        analysis_id=analysis_id,
    )

    app.config["TESTING"] = True
    app.config["TRAMPOLINE_UPLOAD_DIR"] = tmp_path / "uploads"
    app.config["TRAMPOLINE_ARTIFACTS_DIR"] = artifacts_dir
    trampoline_analyses.clear()
    client = app.test_client()

    calibration_payload = {
        "corners": {
            "top_left": {"x": 48, "y": 96},
            "top_right": {"x": 312, "y": 96},
            "bottom_right": {"x": 312, "y": 544},
            "bottom_left": {"x": 48, "y": 544},
        }
    }
    save_response = client.post(f"/api/trampoline/calibration/{analysis_id}", json=calibration_payload)
    save_json = save_response.get_json()

    assert save_response.status_code == 200
    assert save_json["success"] is True
    assert save_json["calibration"]["corners"]["top_left"]["x"] == 48.0

    result_response = client.get(f"/api/trampoline/result/{analysis_id}")
    result_json = result_response.get_json()
    assert result_response.status_code == 200
    assert result_json["result"]["calibration"]["center_point"]["x"] == 180.0

    page_response = client.get(f"/trampoline?analysis_id={analysis_id}")
    html = page_response.get_data(as_text=True)
    assert page_response.status_code == 200
    assert analysis_id in html
    assert '"top_left": {"x": 48.0, "y": 96.0}' in html
