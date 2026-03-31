# Trampoline Demo v1 Release Checklist

## 安装

- `python -m pip install -r requirements-dev.txt`
- `python -m trampoline.cli doctor`

## 运行

- `python app.py`
- `python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --landmarks-only`
- `python -m trampoline.cli segment --analysis-dir artifacts/trampoline/sample01`
- `python -m trampoline.cli export --analysis-dir artifacts/trampoline/sample01`
- `bash scripts/check_v1_acceptance.sh samples/tra_demo/sample01.mp4`

## 验收检查

- `artifacts/trampoline/sample01/landing.json` exists and each jump has `landing_x_norm`, `landing_y_norm`, `landing_source`, and `zone`.
- `artifacts/trampoline/sample01/summary.md` exists and includes center deviation plus routine flags.
- `artifacts/trampoline/sample01/export/analysis_bundle.zip` exists and contains `analysis.json`, `summary.md`, `landing.json`, and `overlays/`.
- `/trampoline` shows the summary panel, landing heatmap, and export button for a completed analysis.
- CI `sample-analysis` job runs lint, tests, the sample chain, and uploads the bundle artifact.

## 限制

- Single-person TRA demo only.
- No official judging claims.
- No D-score, ToF, SYN, TUM, or DMT.
- Landing zones are lightweight helper summaries, not H-score output.

## 演示出口

- Browser demo: `/trampoline`
- CLI demo: `python -m trampoline.cli export --analysis-dir artifacts/trampoline/sample01`
- One-command acceptance: `bash scripts/check_v1_acceptance.sh samples/tra_demo/sample01.mp4`
