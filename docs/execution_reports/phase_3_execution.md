# Phase 3 Execution Report

## Scope

Implemented TODO.md Phase 3 on top of the existing Phase 2 trampoline flow:

- Per-jump feature extraction in [`trampoline/features.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/trampoline/features.py)
- TRA body-shape classification and explainability in [`trampoline/rules_tra.py`](/home/chris4/workspace/from_git/fitness-trainer-pose-estimation/trampoline/rules_tra.py)
- `features.jsonl` and `labels.json` generation wired into the existing pipeline, CLI, and `analysis.json`
- `/trampoline` jump detail panel with label summary, angle summary, decision reason, fallback reason, and manual override controls
- Manual label override persistence with reload compatibility
- Phase 3 unit, integration, and app-level tests

## Approach

1. Extended the shared schema so one jump can carry:
   - automatic label data
   - resolved/manual label data
   - explainability strings
   - UI-ready feature summaries
2. Implemented per-frame feature extraction over the current merged jump timeline:
   - visibility-filtered angle extraction for `trunk_thigh_angle` and `thigh_shank_angle`
   - normalized flight phase per frame
   - mid-flight window flagging for classification
3. Implemented the simplified TRA rules pipeline:
   - classify per-frame shape candidates
   - resolve each jump using the mid-flight lowest-difficulty rule
   - emit `decision_reason`, `fallback_reason`, and confidence
4. Kept Phase 2 timeline behavior intact by generating Phase 3 artifacts from the same merged jump view used by the UI after overrides.
5. Added a dedicated label override endpoint so manual label changes persist into `labels.json`, `analysis.json`, and page reloads.

## Commands Executed

```bash
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "sports analysis detail panel timeline editor warm technical" --design-system -p "Trampoline Demo"
python3 .codex/skills/ui-ux-pro-max/scripts/search.py "forms feedback selection detail panel" --domain ux
pytest tests/unit/trampoline/test_schema.py tests/unit/trampoline/test_override_merge.py -q
python - <<'PY'
from pathlib import Path
from trampoline.pipeline import sync_phase3_artifacts, load_analysis_output
labels = sync_phase3_artifacts(Path('artifacts/trampoline/sample01'))
print(labels.model_dump(mode='json'))
result = load_analysis_output(Path('artifacts/trampoline/sample01'))
print(result['jump_segments'])
PY
python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --steps features
pytest tests/unit/trampoline/test_angles.py tests/unit/trampoline/test_shape_classifier.py tests/unit/trampoline/test_schema.py tests/unit/trampoline/test_override_merge.py -q
pytest tests/integration/trampoline/test_label_golden.py tests/integration/trampoline/test_label_contract.py tests/integration/trampoline/test_segmentation_golden.py tests/integration/trampoline/test_cli_segment.py -q
pytest tests/e2e/trampoline/test_jump_detail_panel.py tests/e2e/trampoline/test_label_override_persistence.py tests/e2e/trampoline/test_timeline_seek.py tests/e2e/trampoline/test_timeline_edit_persistence.py -q
pytest tests/unit/trampoline tests/integration/trampoline tests/e2e/trampoline -q
```

## Issues Solved

### 1. Phase 2 timeline tests started failing after Phase 3 auto-regeneration

`persist_timeline_overrides()` began calling Phase 3 generation automatically, which was correct for real analyses but broke older tests that intentionally only created segmentation fixtures. The fix was to regenerate Phase 3 artifacts only when `landmarks.jsonl` is present, preserving the Phase 2 contract for landmark-free fixtures.

### 2. Label data needed one stable source across CLI, API, and UI

If the label merge only happened in the Flask layer, `analysis.json` and CLI output would drift from the page payload. The fix was to centralize the write path in `sync_phase3_artifacts()` plus `sync_analysis_segments()`, so `features.jsonl`, `labels.json`, `analysis.json`, and `/api/trampoline/result/<id>` all expose the same jump-level label state.

## Verification Evidence

### Sample01 Phase 3 artifacts

- `artifacts/trampoline/sample01/features.jsonl`
- `artifacts/trampoline/sample01/labels.json`
- `artifacts/trampoline/sample01/analysis.json`

Observed sample01 auto labels:

```text
jump-001 -> pike (confidence 0.953)
jump-002 -> tuck (confidence 0.671)
```

Observed `features.jsonl` head:

```text
jump-001 frame 18 ts=750 trunk_thigh=131.552 thigh_shank=149.433 mid_window=False
jump-001 frame 19 ts=792 trunk_thigh=129.975 thigh_shank=149.645 mid_window=False
```

### Test coverage added

- `tests/unit/trampoline/test_angles.py`
- `tests/unit/trampoline/test_shape_classifier.py`
- `tests/integration/trampoline/test_label_golden.py`
- `tests/integration/trampoline/test_label_contract.py`
- `tests/e2e/trampoline/test_jump_detail_panel.py`
- `tests/e2e/trampoline/test_label_override_persistence.py`

### Verification result

- Targeted Phase 3 suites passed.
- Full trampoline suites passed: `32 passed`.

## Artifacts

- `artifacts/trampoline/sample01/features.jsonl`
- `artifacts/trampoline/sample01/labels.json`
- `artifacts/trampoline/sample01/analysis.json`
- `docs/execution_reports/phase_3_execution.md`

## Remaining Limitations

- Manual label overrides are keyed by `jump_id`, so if a later split/merge renumbers jumps, an existing label override may no longer attach to the same physical jump.
- The classifier is intentionally heuristic and tuned for the single-athlete TRA demo scope; it is not a competition-grade judging model.
