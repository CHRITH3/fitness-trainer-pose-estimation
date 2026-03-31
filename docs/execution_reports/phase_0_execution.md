# Phase 0 Execution Report

## Step Identification

- Task: `tra_demo_v1`
- Run: `tra_demo_v1_20260326T161644Z_7b2xufi`
- Step: `S1`
- Title: `Phase 0 foundation for single-person TRA demo`

## Summary of Work

- Added an isolated `trampoline/` package with shared schema models and a `python -m trampoline.cli doctor` entrypoint.
- Added the `GET /trampoline` Flask shell page, repository sample/fixture conventions, and a navigation entry so the trampoline demo coexists with the current exercise app.
- Added Phase 0 test scaffolding, focused tests, and a GitHub Actions workflow for `ruff` and `pytest`.
- Solved two repo-coexistence issues: limited `pytest` collection to `tests/` so the legacy `test_engine.py` script does not become part of CI, and used a low-noise `ruff.toml` baseline so lint can pass without unrelated cleanups.

## Files Changed

- `requirements.txt`
- `requirements-dev.txt`
- `pytest.ini`
- `ruff.toml`
- `app.py`
- `templates/index.html`
- `templates/video_analysis.html`
- `templates/dashboard.html`
- `templates/profile.html`
- `templates/trampoline.html`
- `static/css/trampoline.css`
- `trampoline/__init__.py`
- `trampoline/schema.py`
- `trampoline/pipeline.py`
- `trampoline/rules_tra.py`
- `trampoline/features.py`
- `trampoline/bounce_segmenter.py`
- `trampoline/cli.py`
- `docs/adr/0001_tra_demo_scope.md`
- `docs/execution_reports/phase_0_execution.md`
- `samples/tra_demo/manifest.json`
- `samples/tra_demo/sample01.mp4`
- `fixtures/trampoline/README.md`
- `fixtures/trampoline/sample01/routine_analysis.expected.json`
- `tests/conftest.py`
- `tests/e2e/README.md`
- `tests/e2e/trampoline/test_page_smoke.py`
- `tests/unit/trampoline/test_schema.py`
- `tests/unit/trampoline/test_cli_doctor.py`
- `tests/unit/trampoline/test_sample_manifest.py`
- `.github/workflows/lint_and_test.yml`

## Commands Executed

- `python -m pip install -r requirements-dev.txt`
- `python -c "import trampoline; print(trampoline.__file__)"`
- `python -c "from trampoline.schema import RoutineAnalysis; print(bool(RoutineAnalysis.model_json_schema()))"`
- `python -m trampoline.cli doctor`
- `python -c "import json; print(json.load(open('samples/tra_demo/manifest.json'))['videos'][0]['id'])"`
- `python -m flask --app app routes | grep trampoline`
- `pytest tests/e2e/trampoline/test_page_smoke.py -q`
- `pytest tests/unit/trampoline/test_schema.py -q`
- `pytest tests/unit/trampoline/test_cli_doctor.py -q`
- `pytest tests/unit/trampoline/test_sample_manifest.py -q`
- `pytest --collect-only`
- `pytest -q`
- `ruff check .`

## Verification Results

- `python -c "import trampoline; print(trampoline.__file__)"` succeeded and printed the package path.
- `RoutineAnalysis.model_json_schema()` returned `True`.
- `python -m trampoline.cli doctor` exited `0` and reported `flask`, `pydantic`, `mediapipe`, `samples`, and `artifacts` as `ok`.
- `python -m flask --app app routes | grep trampoline` reported `GET /trampoline`.
- Targeted smoke/contract tests passed:
  - `tests/e2e/trampoline/test_page_smoke.py`
  - `tests/unit/trampoline/test_schema.py`
  - `tests/unit/trampoline/test_cli_doctor.py`
  - `tests/unit/trampoline/test_sample_manifest.py`
- `pytest --collect-only` collected `8` tests from `tests/` only.
- `pytest -q` passed with `8 passed`.
- `ruff check .` passed with `All checks passed!`.

## Logs / Artifacts

- Planned output root for future trampoline runs: `artifacts/trampoline/`
- Sample manifest: `samples/tra_demo/manifest.json`
- Placeholder expected output: `fixtures/trampoline/sample01/routine_analysis.expected.json`
- Doctor evidence:
  - `mediapipe: ok`
  - `samples: ok`
  - `artifacts: ok`
- Route evidence:
  - `trampoline_demo  GET  /trampoline`

## Risks & Limitations

- `samples/tra_demo/sample01.mp4` is intentionally a placeholder file for contract testing only; Phase 1 should replace it with a real lightweight demo clip.
- Phase 0 adds a browser-equivalent Flask smoke test, not a full browser automation stack.
- Pipeline, feature extraction, and segmentation modules are scaffolds only in this step.
- Importing `app.py` in tests still pulls in the existing MediaPipe-oriented app module, so third-party runtime dependencies remain part of the smoke-test environment.

## Reproduction Guide

1. Install dependencies with `python -m pip install -r requirements-dev.txt`.
2. Run `python -m trampoline.cli doctor`.
3. Run `python -m flask --app app routes | grep trampoline`.
4. Run `pytest -q` and `ruff check .`.
