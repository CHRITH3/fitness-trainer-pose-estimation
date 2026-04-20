# AGENTS.md

This file provides guidance to Codex when working with code in this repository.

## Project Overview

This repository is now a **trampoline-only** video analysis project.

**Current product surface:**
- trampoline video upload and direct-on-video calibration
- jump segmentation and action classification
- processed-video playback
- SSE-based LLM analysis
- placeholder shells for `/`, `/dashboard`, and `/profile`

**Tech stack:** Python/Flask backend, vanilla HTML/CSS/JS frontend, MediaPipe 0.10.9 for pose estimation, OpenCV for video processing, imageio-ffmpeg for H.264 encoding, openai SDK for Qianwen-compatible LLM integration (`QWEN_API_KEY` / `DASHSCOPE_API_KEY`).

## Commands

```bash
# Run the web app (serves on http://127.0.0.1:5000)
python app.py

# Run core trampoline tests
python -m pytest tests/test_trampoline.py -v
python -m pytest tests/test_trampoline_api.py -v
python -m pytest tests/test_bed_tracker.py -v
python -m pytest tests/test_trampoline_frontend_contract.py -v
python -m pytest tests/test_app_route_contract.py -v
python -m pytest tests/test_llm_service.py -v
node tests/test_trampoline_calibration_ui.mjs
node tests/test_video_analysis_ui_helpers.mjs

# Standalone video analysis
python video_processor.py <video_path> trampoline <output_json> [output_video]
```

## Architecture

### Flask app

- **`app.py`** — Flask server and route contract
  - retained pages: `/`, `/dashboard`, `/profile`, `/video_analysis`
  - retained APIs: trampoline upload / start / status / processed / llm_analysis
  - no legacy non-trampoline routes remain in the intended end state

### Trampoline module

- **`trampoline/analyzer.py`** — orchestrates jump detection + action classification
- **`trampoline/jump_detector.py`** — takeoff / landing segmentation
- **`trampoline/action_classifier.py`** — jump action classification
- **`trampoline/bed_tracker.py`** — trampoline bed calibration, tracking, landing mapping
- **`trampoline/overlay.py`** — video overlay rendering
- **`trampoline/llm_service.py`** — builds analysis report + streams Qianwen-compatible SSE output

### Frontend video-analysis modules

- **`static/js/trampoline_calibration_ui.js`** — direct-on-video calibration controller and keyframe workflow
- **`static/js/video_analysis_helpers.js`** — compact stats / latest-valid-jump fallback helpers
- **`static/js/video_analysis.js`** — trampoline video-analysis page controller, polling, report, landing map, and AI panel wiring

### Video processing flow

`video_processor.py` is kept as the stable subprocess entrypoint. It is now expected to process **trampoline-only** jobs.

Flow:
1. `/api/video/upload`
2. pending calibration
3. `/api/video/trampoline/start`
4. subprocess analysis via `video_processor.py`
5. polling via `/api/video/status/<id>`
6. processed video / LLM analysis

## Notes

- Some historical notes may still mention the older mixed-product era; prefer the current trampoline-only route/API contract over older wording.
- MediaPipe is pinned to 0.10.9.
- Keep public URLs stable: `/`, `/dashboard`, `/profile`, `/video_analysis`.
- Placeholder dashboard/profile pages are intentional; they preserve future trampoline product expansion space.

## Workflow Conventions

- **Git 提交**：提交信息遵循仓库 Lore protocol，用提交正文记录约束、取舍、验证与风险
- **任务文档**：当任务会改变产品语义、架构约定或清理范围时，在 `trampoline/docs/` 目录下补充中文执行说明，命名规则为 `YYYY-MM-DD-≤10字中文任务简介.md`
- **AGENTS.md 同步**：当发生以下变更时，主动提醒用户是否需要更新 AGENTS.md：
  - 新增或删除核心模块/组件
  - 技术栈变化（换框架、升级有 breaking change 的依赖）
  - 构建/测试/运行命令改变
  - 重要的架构模式变化
