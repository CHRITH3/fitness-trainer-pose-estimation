# Phase 4 Execution Report

## Scope

Implemented the remaining TODO.md Phase 4 work to close the repo into a lightweight single-person TRA demo v1:

- landing extraction in [`trampoline/landing.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/trampoline/landing.py)
- landing/summary fields merged into [`analysis.json`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/artifacts/trampoline/sample01/analysis.json)
- CLI export bundle generation in [`trampoline/exporter.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/trampoline/exporter.py) and [`trampoline/cli.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/trampoline/cli.py)
- `/trampoline` summary panel, landing heatmap, and bundle download path in [`templates/trampoline.html`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/templates/trampoline.html), [`static/js/trampoline.js`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/static/js/trampoline.js), and [`app.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/app.py)
- Phase 4 unit, integration, e2e, CI smoke, and one-command acceptance coverage
- v1 release/demo docs plus regenerated `sample01` golden artifacts

## Approach

1. Extended the shared schema so jump segments can optionally carry normalized landing coordinates, zones, jump flags, and routine summary data.
2. Added a Phase 4 artifact sync step after Phase 3 generation:
   - extract a landing point using feet first and hip fallback second
   - normalize the point into bed space using the saved calibration homography
   - derive `center_deviation`, `zone`, `single_leg`, `out_of_bed`, `final_out_bounce`, and `final_stable_3s`
   - persist `landing.json` and `summary.md`
3. Kept one canonical write path by merging landing data back into `analysis.json`, the API result payload, and the sample export bundle.
4. Built a deterministic export directory under `analysis_dir/export/` containing:
   - `analysis.json`
   - `summary.md`
   - `landing.json`
   - `overlays/preview_overlay.json`
   - `overlays/landing_heatmap.json`
   - `analysis_bundle.zip`
5. Closed the repo-level acceptance path with a shell script and a dedicated CI smoke job that runs lint, tests, analyze, segment, and export on `sample01`.

## Commands Executed

```bash
python -m py_compile trampoline/schema.py trampoline/landing.py trampoline/pipeline.py trampoline/exporter.py trampoline/cli.py app.py
ruff check trampoline/schema.py trampoline/landing.py trampoline/pipeline.py trampoline/exporter.py trampoline/cli.py app.py
pytest -q tests/unit/trampoline/test_landing.py tests/unit/trampoline/test_flags.py
pytest -q tests/integration/trampoline/test_cli_export.py
pytest -q tests/e2e/trampoline/test_summary_and_export.py
chmod +x scripts/check_v1_acceptance.sh
bash scripts/check_v1_acceptance.sh samples/tra_demo/sample01.mp4 sample01
ruff check .
pytest -q tests/unit/trampoline tests/integration/trampoline tests/e2e/trampoline
grep -E "安装|运行|限制|演示" README.md docs/v1_release_checklist.md docs/demo_script.md
```

## Issues Solved

### 1. Real sample landings fell slightly below the calibrated bed polygon

On `sample01`, the feet landmarks at landing sit a little below the manually calibrated rectangle, so the first implementation rejected them as invalid and produced `null` landing coordinates. The fix was to keep a small normalized safety margin and classify these as valid `out_of_bed` demo landings instead of discarding them.

### 2. Summary/export state could drift between CLI, API, and UI

If export generation assembled its own payload independently, the `/trampoline` page, `analysis.json`, and `analysis_bundle.zip` could expose different landing summaries. The fix was to centralize Phase 4 generation in `sync_phase4_artifacts()` and then reuse the same merged result from both Flask and CLI export flows.

## Verification Evidence

### Sample01 artifacts

- [`landing.json`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/artifacts/trampoline/sample01/landing.json)
- [`summary.md`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/artifacts/trampoline/sample01/summary.md)
- [`analysis.json`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/artifacts/trampoline/sample01/analysis.json)
- [`analysis_bundle.zip`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/artifacts/trampoline/sample01/export/analysis_bundle.zip)

Observed `sample01` Phase 4 summary:

```text
Jumps detected: 2
Landings mapped: 2
Mean center deviation: 0.648
Routine flags: final_out_bounce
Export bundle: artifacts/trampoline/sample01/export/analysis_bundle.zip
```

Observed exported files:

```text
artifacts/trampoline/sample01/export/analysis.json
artifacts/trampoline/sample01/export/analysis_bundle.zip
artifacts/trampoline/sample01/export/calibration.json
artifacts/trampoline/sample01/export/export_manifest.json
artifacts/trampoline/sample01/export/features.jsonl
artifacts/trampoline/sample01/export/frames_meta.json
artifacts/trampoline/sample01/export/labels.json
artifacts/trampoline/sample01/export/landing.json
artifacts/trampoline/sample01/export/overlays/landing_heatmap.json
artifacts/trampoline/sample01/export/overlays/preview_overlay.json
artifacts/trampoline/sample01/export/segmentation.json
artifacts/trampoline/sample01/export/summary.md
```

### Test coverage added

- [`tests/unit/trampoline/test_landing.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/tests/unit/trampoline/test_landing.py)
- [`tests/unit/trampoline/test_flags.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/tests/unit/trampoline/test_flags.py)
- [`tests/integration/trampoline/test_cli_export.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/tests/integration/trampoline/test_cli_export.py)
- [`tests/e2e/trampoline/test_summary_and_export.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/tests/e2e/trampoline/test_summary_and_export.py)
- [`scripts/check_v1_acceptance.sh`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/scripts/check_v1_acceptance.sh)
- [`.github/workflows/lint_and_test.yml`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/.github/workflows/lint_and_test.yml)

### Verification result

- `ruff check .` passed.
- `pytest -q tests/unit/trampoline tests/integration/trampoline tests/e2e/trampoline` passed with `39 passed`.
- `bash scripts/check_v1_acceptance.sh samples/tra_demo/sample01.mp4 sample01` exited `0` and printed `PASS`.
- `grep -E "安装|运行|限制|演示" README.md docs/v1_release_checklist.md docs/demo_script.md` returned the expected headings.

## Artifacts

- [`artifacts/trampoline/sample01/landing.json`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/artifacts/trampoline/sample01/landing.json)
- [`artifacts/trampoline/sample01/summary.md`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/artifacts/trampoline/sample01/summary.md)
- [`artifacts/trampoline/sample01/export/analysis_bundle.zip`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/artifacts/trampoline/sample01/export/analysis_bundle.zip)
- [`docs/v1_release_checklist.md`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/docs/v1_release_checklist.md)
- [`docs/demo_script.md`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/docs/demo_script.md)
- [`docs/execution_reports/phase_4_execution.md`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/docs/execution_reports/phase_4_execution.md)

## Remaining Limitations

- The landing heatmap is a lightweight demo visualization based on the nearest landing frame, not a frame-perfect contact detector.
- `final_stable_3s` depends on video tail duration after the last landing and will only appear when the clip actually contains that post-routine window.
- The export bundle ships JSON overlays rather than rendered image/video overlays, which is sufficient for demo handoff but still intentionally minimal.
