# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

AI-powered fitness trainer web app that uses MediaPipe pose estimation for real-time exercise tracking with form scoring. Also includes a trampoline analysis module for jump detection and action classification.

**Tech stack:** Python/Flask backend, vanilla HTML/CSS/JS frontend, MediaPipe 0.10.9 for pose estimation, OpenCV for video processing, imageio-ffmpeg for H.264 encoding.

## Commands

```bash
# Run the web app (serves on http://127.0.0.1:5000)
python app.py

# Run exercise engine tests (custom test runner, not pytest)
python test_engine.py

# Run trampoline module tests (pytest)
pytest tests/test_trampoline.py -v

# Run a single trampoline test
pytest tests/test_trampoline.py::test_function_name -v

# Standalone video analysis
python video_processor.py <video_path> <exercise_type> <output_json> [output_video]
```

## Architecture

### Exercise Engine (FSM-based)

The core exercise system uses a **Finite State Machine** pattern: `START → DESCENT → ASCENT (rep counted) → START`.

- **`exercises/base_exercise.py`** — FSM core with three subclasses:
  - `BaseExercise` — standard repetition exercises (squat, push_up, etc.)
  - `BilateralExercise` — left/right tracking (bicep_curl, lunge, lateral_raise)
  - `DurationExercise` — time-based holds (plank, wall_sit)
- **`exercises/loader.py`** — Parses YAML definitions, validates configs, returns the correct subclass
- **`exercises/engine.py`** — High-level wrapper: `process_frame(frame, landmarks)` → runs FSM, calculates form score, renders overlays
- **`exercises/definitions/*.yaml`** — 18 exercise definitions. New exercises can be added as YAML without code changes

### Form Score System

Score 0-100 composed of: angle accuracy (40%), tempo compliance (30%), form feedback penalties (30%). Grades: A (90+), B (80+), C (70+), D (60+), F (<60).

### Trampoline Module

- **`trampoline/analyzer.py`** — Orchestrator, drop-in replacement for ExerciseEngine with same `process_frame()` interface
- **`trampoline/jump_detector.py`** — Detects takeoff/landing events from center-of-mass Y position
- **`trampoline/action_classifier.py`** — Classifies jump actions using trunk-thigh and thigh-shin angles
- **`trampoline/config.py`** — Thresholds and constants

### Web App Flow

`app.py` is the Flask server. Real-time tracking uses an MJPEG stream via `/video_feed` with a `generate_frames()` loop that runs MediaPipe + ExerciseEngine per frame. Video analysis uploads run `video_processor.py` as a subprocess and poll status via `/api/video/status/<id>`.

### Pose Estimation

`pose_estimation/estimation.py` wraps MediaPipe Pose. `pose_estimation/angle_calculation.py` provides angle math utilities. MediaPipe uses 33 body landmarks; the exercise engine maps named landmarks (e.g., `left_shoulder` → index 11) via `BaseExercise.LANDMARK_MAP`.

## YAML Exercise Definition Format

Each exercise YAML defines: `angles` (body points to track), `states` (FSM conditions on angle values), `counter` (which state transition counts a rep), `feedback` (form warnings), and `visualization` (skeleton overlay config). See any file in `exercises/definitions/` for examples.

## Notes

- Code comments are in Turkish; keep this convention when modifying existing code
- MediaPipe is pinned to 0.10.9 — newer versions have breaking API changes
- Camera and PoseEstimator are lazily initialized to reduce memory usage
- Frame processing uses a global `lock` for thread safety in the MJPEG stream
- `db/workout_logger.py` is currently a stub

## Workflow Conventions

- **Git 提交**：每完成一项任务立即提交一个 git commit，commit message 使用简略中文描述
- **任务文档**：每项任务完成后在 `trampoline/docs/` 目录下生成一份详细的任务执行说明文档，命名规则为 `YYYY-MM-DD-≤10字中文任务简介.md`
- **CLAUDE.md 同步**：当发生以下变更时，主动提醒用户是否需要更新 CLAUDE.md：
  - 新增或删除核心模块/组件
  - 技术栈变化（换框架、升级有 breaking change 的依赖）
  - 构建/测试/运行命令改变
  - 重要的架构模式变化
