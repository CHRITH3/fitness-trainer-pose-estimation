# 视频分析页 DETHP 真实评分改造方案

## Summary

将“视觉评分预留”改为真实评分区，后端新增 `trampoline/score.py` 作为独立评分模块，基于当前视频分析结果计算 `D/E/T/H/P + total`，并把 `score` 字段加入状态接口、AI 分析输入和报告下载。

当有效跳次超过 10 次时，不直接评分：前端默认预选前 10 个有效跳，用户可确认默认选择，或点击“修改评分跳次”在动作序列表格中勾选任意 10 跳后再计算评分。

## Key Changes

### 后端评分模块

- 新增 `trampoline/score.py`，提供 `compute_score(analysis, selected_jump_numbers=None)`。
- 输入使用当前 `completed_jumps`、`fps/video_fps`、`landing.bed_xy_m/norm_xy/confidence`、`action/is_intermediate`。
- 输出统一 `score` 字段：
  - `status`: `ready | selection_required | incomplete | insufficient_data`
  - `selected_jump_numbers`
  - `components`: `D/E/T/H/P/total`
  - `deductions`: 每跳 D 候选、E 扣分、H 扣分、T 秒数、数据置信说明
  - `data_sources`: 标明当前来自 2D 视频分析，保留 `pose3d_stream`、`manual_penalty`、`future_realtime` 接入口

### 评分规则第一版

- `T`: 选中 10 跳的 `flight_frames / fps` 求和，保留两位小数。
- `H`: 基于落点距中心距离估算扣分，满分 10；无落点或低置信度时给出说明并按保守扣分处理。
- `D`: 基于当前动作类别给候选难度，`Straight=0.0`、`Tuck/Pike=0.5`、`Straddle=0.1`、`Unknown=0.0`，明确标记为“动作识别候选难度，复杂翻转需人工确认”。
- `E`: 满分 20，按当前可量化数据做视频特化扣分：未知动作、过渡跳误入、低置信落点、落点明显偏移、腾空时间异常波动等产生扣分；不宣称替代裁判主观完成分。
- `P`: 第一版按用户选择默认 `0.0`，显示“未录入附加罚分”，结构中保留后续人工录入/实时流事件字段。
- `total = D + E + T + H - P`，最终保留两位小数。

### 后端接口

- `/api/video/status/<video_id>` 返回 `score`。
- 新增 `POST /api/video/score/<video_id>`，请求体为 `{ "selected_jump_numbers": [1,2,...] }`。
- 当有效跳次 `>10` 且未确认选择时，状态接口返回 `score.status="selection_required"`，不生成最终总分。
- 当有效跳次 `<=10` 时自动使用全部有效跳；少于 10 跳时标记 `incomplete`，仍输出辅助分和原因。

### 前端交互

- 评分卡标题改为“视觉量化评分”，展示 `D/E/T/H/P/总分`。
- 有效跳次超过 10 时，评分卡显示“默认前10跳待确认”和两个按钮：“确认评分”“修改评分跳次”。
- 点击“修改评分跳次”后，动作序列表格出现勾选框，默认勾选前 10 个有效跳；只有正好选择 10 跳时才允许提交评分。
- 评分完成后，评分卡渲染 DETHP、总分、扣分说明；下载报告加入评分明细。
- AI 分析按钮在需要选 10 跳时保持禁用，评分完成后启用，避免 AI 输入缺少最终评分。

### AI 输入

- `AnalysisReport.from_video_analysis()` 增加 `score`。
- `build_prompt()` 在用户数据中加入“视觉量化评分”段落，包含 DETHP、总分、选中跳次、扣分说明和评分局限。
- AI prompt 明确：只能基于评分字段和视频分析字段解释，不得把候选 D 分说成正式 FIG 裁判定分。

## Test Plan

- 新增 `tests/test_trampoline_score.py`：
  - 正好 10 个有效跳时可直接输出 DETHP 和总分。
  - 超过 10 个有效跳且未传选择时返回 `selection_required`。
  - 传入 10 个合法跳号时按选择计算。
  - 选择数量不是 10、包含不存在跳号、包含过渡跳时返回可解释错误。
  - 缺少落点、低置信落点、`Unknown` 动作、少于 10 跳均有稳定输出和扣分说明。
- 更新 API 测试：
  - 状态接口包含 `score`。
  - `POST /api/video/score/<video_id>` 能保存选中跳次并刷新分析对象中的 `score`。
  - AI report 构造能读取并输出评分段落。
- 更新前端契约测试：
  - 页面包含 `score-d/e/t/h/p/total`。
  - 包含评分确认和修改选择入口。
  - JS 包含评分拉取、10 跳勾选、提交评分、报告导出评分内容的逻辑。
- 回归验证：
  - `python -m pytest tests/test_trampoline_score.py -v`
  - `python -m pytest tests/test_trampoline_api.py -v`
  - `python -m pytest tests/test_llm_service.py -v`
  - `python -m pytest tests/test_trampoline_frontend_contract.py -v`
  - `node tests/test_video_analysis_ui_helpers.mjs`
  - `git diff --check`

## Assumptions

- 第一版 P 分按 `0.0` 处理，只展示“未录入附加罚分”，不做前端人工输入。
- 第一版 D/E 是“视频分析特化的视觉量化估计”，不宣称完全符合正式 FIG 裁判人工判分。
- 当前项目还没有稳定 3D 姿态输入；`score.py` 会在结构和函数参数中预留 3D/实时流数据入口，但本轮不实现实时流接入。
- 有效跳次定义为 `completed_jumps` 中 `is_intermediate != true` 的跳次。
- 超过 10 个有效跳时，默认预选前 10 个有效跳，但必须由用户确认或修改后才生成最终评分和启用 AI 分析。
