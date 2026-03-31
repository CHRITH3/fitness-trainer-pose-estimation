# Phase 1 Execution Report

## Step Identification

- Task: `tra_demo_v1`
- Run: `tra_demo_v1_20260326T161644Z_7b2xufi`
- Step: `S2`
- Title: `Phase 1 video analysis baseline and bed calibration`

## Summary of Work

- Replaced the Phase 0 placeholder `samples/tra_demo/sample01.mp4` with a lightweight real local clip derived from `uploads/deadlift.mp4` so the offline landmark pipeline runs against an actual repo-local video.
- Implemented `trampoline/pipeline.py` as a real Phase 1 baseline using MediaPipe Pose and OpenCV, producing `landmarks.jsonl`, `frames_meta.json`, and `analysis.json` in a stable analysis directory.
- Added `trampoline/bed_calibration.py` with four-corner bed calibration persistence, perspective transforms, normalized mapping, and `calibration.json` save/load support.
- Extended `python -m trampoline.cli` with `analyze --video --out --landmarks-only` so the Phase 1 offline flow can be run directly from the command line.
- Added isolated Flask trampoline routes for upload, analyze, status polling, result loading, calibration save/load, and source-video preview without refactoring unrelated exercise flows.
- Replaced the `/trampoline` shell page with a working Phase 1 UI that can upload a video, trigger analysis, render a preview skeleton overlay, suggest/save calibration points, and reload persisted overlays for an existing analysis id.
- Added focused Phase 1 tests for pipeline smoke, frame metadata mapping, CLI analyze, upload/status flow, and overlay persistence.
- Solved two implementation issues during verification: Python 3.9 compatibility in `app.py` by removing PEP 604 union syntax from the new helper, and keeping MediaPipe runtime stable by using a short 72-frame sample clip.

## Files Changed

- `app.py`
- `templates/trampoline.html`
- `static/css/trampoline.css`
- `static/js/trampoline.js`
- `trampoline/pipeline.py`
- `trampoline/bed_calibration.py`
- `trampoline/cli.py`
- `samples/tra_demo/sample01.mp4`
- `tests/unit/trampoline/test_frames_meta.py`
- `tests/unit/trampoline/test_bed_calibration.py`
- `tests/integration/trampoline/test_pipeline_smoke.py`
- `tests/integration/trampoline/test_cli_analyze.py`
- `tests/e2e/trampoline/test_upload_and_status.py`
- `tests/e2e/trampoline/test_overlay_persistence.py`
- `docs/execution_reports/phase_1_execution.md`

## Commands Executed

- `python - <<'PY' ...` to inspect repo-local MP4 candidates in `uploads/`
- `python - <<'PY' ...` to probe MediaPipe pose detection on local sample candidates
- `python - <<'PY' ...` to regenerate `samples/tra_demo/sample01.mp4` from `uploads/deadlift.mp4`
- `pytest -q tests/unit/trampoline/test_frames_meta.py tests/unit/trampoline/test_bed_calibration.py`
- `pytest -q tests/integration/trampoline/test_pipeline_smoke.py tests/integration/trampoline/test_cli_analyze.py`
- `pytest -q tests/e2e/trampoline/test_page_smoke.py tests/e2e/trampoline/test_upload_and_status.py tests/e2e/trampoline/test_overlay_persistence.py`
- `pytest -q tests/unit/trampoline tests/integration/trampoline tests/e2e/trampoline`
- `pytest -q`
- `ruff check app.py trampoline tests/e2e/trampoline tests/integration/trampoline tests/unit/trampoline`
- `python -m trampoline.cli doctor`
- `python -m flask --app app routes | grep trampoline`
- `python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --landmarks-only`
- `python - <<'PY' ...` to save `artifacts/trampoline/sample01/calibration.json`
- `python - <<'PY' ...` to inspect `frames_meta.json`, `landmarks.jsonl`, and `calibration.json`

## Verification Results

- `pytest -q tests/unit/trampoline tests/integration/trampoline tests/e2e/trampoline` passed with `14 passed`.
- `pytest -q` passed with `14 passed`.
- `ruff check app.py trampoline tests/e2e/trampoline tests/integration/trampoline tests/unit/trampoline` passed with `All checks passed!`.
- `python -m trampoline.cli doctor` exited `0` and reported `flask`, `pydantic`, `mediapipe`, `samples`, and `artifacts` as `ok`.
- `python -m flask --app app routes | grep trampoline` reported:
  - `GET /trampoline`
  - `POST /api/trampoline/upload`
  - `POST /api/trampoline/analyze`
  - `GET /api/trampoline/status/<analysis_id>`
  - `GET /api/trampoline/result/<analysis_id>`
  - `GET, POST /api/trampoline/calibration/<analysis_id>`
  - `GET /api/trampoline/video/<analysis_id>`
- `python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --landmarks-only` exited `0` and produced:
  - `artifacts/trampoline/sample01/landmarks.jsonl`
  - `artifacts/trampoline/sample01/frames_meta.json`
  - `artifacts/trampoline/sample01/analysis.json`
- Artifact inspection confirmed:
  - `frame_count=72`
  - `fps=24.0`
  - `width=360`
  - `height=640`
  - `first_timestamp_ms=0`
  - `last_timestamp_ms=2958`
  - `first_has_landmarks=True`
  - `last_has_landmarks=True`
- Calibration inspection confirmed:
  - `artifacts/trampoline/sample01/calibration.json` exists
  - `corner_keys=['top_left', 'top_right', 'bottom_right', 'bottom_left']`
  - `center_point={'x': 180.0, 'y': 320.0}`
  - `bed_to_normalized` and `normalized_to_bed` are both 3x3 matrices

## Logs / Artifacts

- Sample analysis directory: `artifacts/trampoline/sample01/`
- Generated Phase 1 artifacts:
  - `artifacts/trampoline/sample01/analysis.json`
  - `artifacts/trampoline/sample01/landmarks.jsonl`
  - `artifacts/trampoline/sample01/frames_meta.json`
  - `artifacts/trampoline/sample01/calibration.json`
- Sample clip used for verification: `samples/tra_demo/sample01.mp4`
- Route evidence:
  - `trampoline_demo             GET        /trampoline`
  - `trampoline_upload_video     POST       /api/trampoline/upload`
  - `trampoline_analyze_video    POST       /api/trampoline/analyze`
  - `trampoline_analysis_status  GET        /api/trampoline/status/<analysis_id>`
  - `trampoline_analysis_result  GET        /api/trampoline/result/<analysis_id>`
  - `trampoline_calibration      GET, POST  /api/trampoline/calibration/<analysis_id>`
  - `trampoline_source_video     GET        /api/trampoline/video/<analysis_id>`
- Runtime note:
  - MediaPipe emitted `libEGL` loader warnings in this environment, but analysis and tests completed successfully and the generated artifacts were valid.

## Risks & Limitations

- The Phase 1 preview overlay is intentionally lightweight: it draws the first detected skeleton frame plus persisted calibration, not a per-frame animated overlay track yet.
- Analysis jobs are kept in process memory for the live Flask session; persisted artifacts survive reloads, but queued/running job state does not survive a process restart.
- The baseline uses MediaPipe Pose plus OpenCV only for offline landmarks and metadata; segmentation, jump timeline interaction, and routine logic remain Phase 2+ work.
- The saved calibration in the sample artifact directory uses a suggested rectangle for reproducible verification evidence, not a human-clicked annotation workflow.

## Reproduction Guide

1. Install dependencies with `python -m pip install -r requirements-dev.txt`.
2. Run `python -m trampoline.cli doctor`.
3. Generate the sample analysis with `python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --landmarks-only`.
4. Save a calibration into that directory or use the `/trampoline` page to upload, analyze, and persist calibration for a result.
5. Verify with `pytest -q tests/unit/trampoline tests/integration/trampoline tests/e2e/trampoline`.
