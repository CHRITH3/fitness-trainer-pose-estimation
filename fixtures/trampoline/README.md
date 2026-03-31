# Trampoline Fixture Conventions

This directory stores repository fixtures for the single-person TRA demo.

## Naming

- Sample videos live in `samples/tra_demo/` and use IDs such as `sample01`.
- Matching expected outputs live in `fixtures/trampoline/<sample_id>/`.
- Golden JSON files should use descriptive names such as `routine_analysis.expected.json`, `segmentation.expected.json`, or `landmarks.expected.jsonl`.
- Derived run artifacts belong in `artifacts/trampoline/<analysis_id>/` and should not be committed.

## Phase 0 Notes

- `samples/tra_demo/sample01.mp4` is a placeholder contract file only.
- Future phases should replace placeholder media with a real lightweight demo sample while keeping the same manifest and fixture layout.
