"""API lifecycle tests for trampoline two-stage calibration."""

import io
import json
import os

import cv2
import numpy as np
import pytest

import app as app_module


@pytest.fixture(autouse=True)
def isolated_uploads(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "UPLOAD_FOLDER", str(tmp_path))
    app_module.video_analyses.clear()
    monkeypatch.setattr(app_module, "process_video_subprocess", lambda video_id: None)
    yield
    app_module.video_analyses.clear()


def make_video_bytes(tmp_path):
    path = tmp_path / "sample.mp4"
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), 5, (64, 64))
    for _ in range(5):
        writer.write(np.zeros((64, 64, 3), dtype=np.uint8))
    writer.release()
    return path.read_bytes()


def valid_corners():
    return [
        {"name": "front_left", "x": 5, "y": 55},
        {"name": "front_right", "x": 55, "y": 55},
        {"name": "back_right", "x": 55, "y": 5},
        {"name": "back_left", "x": 5, "y": 5},
    ]


def upload_trampoline(client, tmp_path):
    data = {
        "exercise_type": "trampoline",
        "video": (io.BytesIO(make_video_bytes(tmp_path)), "sample.mp4"),
    }
    response = client.post("/api/video/upload", data=data, content_type="multipart/form-data")
    payload = response.get_json()
    assert payload["success"]
    assert payload["status"] == "uploaded_pending_calibration"
    return payload["video_id"]


def test_trampoline_upload_returns_pending_calibration_contract_fields(tmp_path):
    client = app_module.app.test_client()
    data = {
        "exercise_type": "trampoline",
        "video": (io.BytesIO(make_video_bytes(tmp_path)), "sample.mp4"),
    }

    response = client.post("/api/video/upload", data=data, content_type="multipart/form-data")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["success"] is True
    assert payload["status"] == "uploaded_pending_calibration"
    assert payload["message"]
    assert payload["video_id"]
    assert payload["first_frame_image"].startswith("data:image/png;base64,")
    assert payload["first_frame_b64"]
    assert payload["image_size"] == {"width": 64, "height": 64}
    assert payload["video_fps"] == 5.0
    assert payload["total_frames"] == 5
    assert payload["corner_order"] == app_module.TRAMPOLINE_CORNER_ORDER


def test_trampoline_upload_start_and_processing_idempotency(tmp_path):
    client = app_module.app.test_client()
    video_id = upload_trampoline(client, tmp_path)

    response = client.post("/api/video/trampoline/start", json={"video_id": video_id, "corners": valid_corners()})
    payload = response.get_json()
    assert payload["success"]
    assert payload["status"] == "processing"
    assert os.path.exists(os.path.join(app_module.UPLOAD_FOLDER, f"{video_id}_corners.json"))

    duplicate = client.post("/api/video/trampoline/start", json={"video_id": video_id, "corners": valid_corners()})
    assert duplicate.get_json()["success"]

    changed = valid_corners()
    changed[0] = {**changed[0], "x": 8}
    conflict = client.post("/api/video/trampoline/start", json={"video_id": video_id, "corners": changed})
    assert conflict.status_code == 409


def test_completed_start_returns_existing_result_even_with_different_corners(tmp_path):
    client = app_module.app.test_client()
    video_id = upload_trampoline(client, tmp_path)
    client.post("/api/video/trampoline/start", json={"video_id": video_id, "corners": valid_corners()})
    app_module.video_analyses[video_id]["status"] = "completed"
    app_module.video_analyses[video_id]["processed_video"] = "processed.mp4"

    changed = valid_corners()
    changed[0] = {**changed[0], "x": 8}
    response = client.post("/api/video/trampoline/start", json={"video_id": video_id, "corners": changed})
    payload = response.get_json()
    assert response.status_code == 200
    assert payload["success"]
    assert payload["status"] == "completed"


def test_pending_trampoline_cleanup_expires_abandoned_upload(tmp_path):
    video_path = tmp_path / "orphan.mp4"
    sidecar_path = tmp_path / "orphan_corners.json"
    video_path.write_bytes(b"video")
    sidecar_path.write_text("{}")
    app_module.video_analyses["orphan"] = {
        "mode": "trampoline",
        "status": "uploaded_pending_calibration",
        "created_at": 0,
        "filepath": str(video_path),
    }

    expired = app_module.cleanup_expired_pending_trampoline_uploads(now=app_module.TRAMPOLINE_PENDING_TTL_SECONDS + 1)

    assert expired == ["orphan"]
    assert app_module.video_analyses["orphan"]["status"] == "expired"
    assert not video_path.exists()
    assert not sidecar_path.exists()


def test_multi_keyframe_start_writes_sorted_calibrations(tmp_path):
    client = app_module.app.test_client()
    video_id = upload_trampoline(client, tmp_path)
    later = valid_corners()
    later = [{**p, "x": p["x"] + 1, "y": p["y"] + 1} for p in later]

    response = client.post("/api/video/trampoline/start", json={
        "video_id": video_id,
        "calibrations": [
            {"frame_index": 30, "time_s": 1.0, "corners_px": later},
            {"frame_index": 0, "time_s": 0.0, "corners_px": valid_corners()},
        ],
    })

    payload = response.get_json()
    assert response.status_code == 200, payload
    assert payload["success"]
    assert payload["calibration_count"] == 2
    with open(os.path.join(app_module.UPLOAD_FOLDER, f"{video_id}_corners.json")) as f:
        sidecar = json.load(f)
    assert sidecar["schema_version"] == 2
    assert [c["frame_index"] for c in sidecar["calibrations"]] == [0, 30]


def test_duplicate_keyframe_rejected_without_processing(tmp_path):
    client = app_module.app.test_client()
    video_id = upload_trampoline(client, tmp_path)

    response = client.post("/api/video/trampoline/start", json={
        "video_id": video_id,
        "calibrations": [
            {"frame_index": 4, "corners_px": valid_corners()},
            {"frame_index": 4, "corners_px": valid_corners()},
        ],
    })

    payload = response.get_json()
    assert response.status_code == 400
    assert payload["status"] == "calibration_rejected"
    assert app_module.video_analyses[video_id]["status"] == "calibration_rejected"
