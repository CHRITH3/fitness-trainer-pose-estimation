# 单人 TRA 轻量化蹦床 AI 裁判 Demo TODO

## 说明

* 文档用途：用于规划和跟踪项目落地的分阶段任务。
* 任务拆分原则：每条 TODO 尽量控制在 0.5～1 人日内完成，优先拆成可以独立提交、独立验收、独立回滚的小任务。
* 标签说明（方括号标签）：

  * `[repo]` 仓库结构 / 分支 / 配置
  * `[core]` 核心业务 / 核心库 / 协议实现
  * `[daemon]` 守护进程 / 后台服务（本项目 v1.0 预计不单独拆分）
  * `[app]` GUI / Web 应用（本项目指 Flask 页面、前端交互、页面路由）
  * `[cli]` 命令行工具 / 离线分析入口
  * `[agent]` Guest 或远端 agent（本项目 v1.0 预计不使用）
  * `[test]` 自动化测试 / CI / E2E 脚本
  * `[doc]` 文档 / 设计记录 / README
  * `[algo]` 视觉算法 / 时序规则 / 特征计算
  * `[data]` 样例数据 / 标注基线 / 测试夹具

---

## Phase 0：基础准备与架构对齐（约 12 项）

### 目标（Goals）

* 在原仓库内旁路出独立的 `trampoline/` 业务模块，避免继续把蹦床逻辑塞进原有 exercise engine。
* 明确 v1.0 范围：只做单人 TRA demo，暂不实现 D-score、ToF、SYN、TUM、DMT、官方总分。
* 建立统一的数据模型、样例数据目录和最小测试骨架，为后续分段、判读、导出提供稳定契约。

### 阶段性交付成果（Deliverables）

* 存在 `docs/adr/0001_tra_demo_scope.md`，写明范围、排除项、阶段目标。
* 存在可导入的 `trampoline/` Python 包，以及 `python -m trampoline.cli doctor` 入口。
* 存在 `GET /trampoline` 页面壳和导航入口。
* 存在 `trampoline/schema.py`、`samples/tra_demo/manifest.json`、`tests/unit/`、`tests/e2e/` 的基础骨架。

### TODO

1. [doc][repo] 新建 `docs/adr/0001_tra_demo_scope.md`，明确本项目仅覆盖单人 TRA demo，列出 v1.0 必做项与明确不做项。

   * 验证：执行 `grep -E "单人 TRA|不做|D-score|ToF|SYN|TUM|DMT" docs/adr/0001_tra_demo_scope.md`，确认范围和排除项均可检索到。

2. [core][repo] 新建 `trampoline/` Python 包，预留 `schema.py`、`pipeline.py`、`cli.py`、`rules_tra.py`、`features.py`、`bounce_segmenter.py` 等文件位。

   * 验证：执行 `python -c "import trampoline; print(trampoline.__file__)"`，确认包可被解释器导入。

3. [core] 在 `trampoline/schema.py` 中定义统一数据模型，至少包含 `RoutineAnalysis`、`JumpSegment`、`ManualOverride`、`AnalysisArtifactRef`。

   * 验证：执行 `python -c "from trampoline.schema import RoutineAnalysis; print(bool(RoutineAnalysis.model_json_schema()))"`，确认 schema 可导出。

4. [app] 在 Flask 中注册 `GET /trampoline` 路由，新增页面壳和导航入口，页面先展示“上传视频 / 结果区域 / 时间轴占位”三块空容器。

   * 验证：执行 `flask routes | grep trampoline`，并启动服务后访问 `http://127.0.0.1:5000/trampoline`，确认页面可打开。

5. [cli] 新建 `python -m trampoline.cli doctor` 命令，检查 Python 依赖、MediaPipe 依赖、样例数据目录、写权限目录是否就绪。

   * 验证：执行 `python -m trampoline.cli doctor`，确认退出码为 `0`，且输出包含 `mediapipe`、`samples`、`artifacts` 三项检查结果。

6. [data][repo] 新建 `samples/tra_demo/manifest.json` 与 `fixtures/trampoline/README.md`，统一样例视频、标定文件、预期输出 fixture 的命名规则。

   * 验证：执行 `python -c "import json; print(json.load(open('samples/tra_demo/manifest.json'))['videos'][0]['id'])"`，确认 manifest 可被解析。

7. [test][repo] 建立 `pytest`、`ruff`、`playwright` 基础骨架，补齐 `pytest.ini`、`tests/unit/`、`tests/e2e/`、`requirements-dev.txt` 或等价开发依赖文件。

   * 验证：执行 `pytest --collect-only` 和 `ruff check .`，确认测试目录可被收集、lint 可运行。

8. [test][app] 新增 `tests/e2e/trampoline/test_page_smoke.py`，验证 `GET /trampoline` 可返回 200，页面包含 `upload-panel`、`timeline-panel`、`detail-panel` 三个占位元素。

   * 验证：执行 `pytest tests/e2e/trampoline/test_page_smoke.py -q`，预期通过。

9. [test][core] 新增 `tests/unit/trampoline/test_schema.py`，验证 `RoutineAnalysis`、`JumpSegment`、`ManualOverride` 的必填字段、默认值、非法值拒绝逻辑。

   * 验证：执行 `pytest tests/unit/trampoline/test_schema.py -q`，预期通过。

10. [test][cli] 新增 `tests/unit/trampoline/test_cli_doctor.py`，覆盖第 5 条中的 `doctor` 命令正常路径和缺失样例目录路径。

    * 验证：执行 `pytest tests/unit/trampoline/test_cli_doctor.py -q`，预期通过。

11. [test][data] 新增 `tests/unit/trampoline/test_sample_manifest.py`，校验 `samples/tra_demo/manifest.json` 中声明的文件在仓库内都存在且扩展名合法。

    * 验证：执行 `pytest tests/unit/trampoline/test_sample_manifest.py -q`，预期通过。

12. [test][repo] 新建 GitHub Actions 工作流 `/.github/workflows/lint_and_test.yml`，至少跑 `ruff check .` 和 `pytest -q`。

    * 验证：推送到测试分支后，确认 `lint_and_test` 工作流在 CI 中被触发，且能完成收集与执行。

---

## Phase 1：视频分析基线与床面标定（约 12 项）

### 目标（Goals）

* 基于 Phase 0 的脚手架，接入单视频离线分析链路，能稳定产出帧级 landmarks 结果。
* 用户可以完成床面四角标定，并把标定结果持久化到分析产物目录。
* 页面上可以看到骨架、床面边界和中心线叠加预览，为后续分段和落点分析准备坐标系。

### 阶段性交付成果（Deliverables）

* 存在 `trampoline/pipeline.py`，可输出 `artifacts/trampoline/<analysis_id>/landmarks.jsonl` 与 `frames_meta.json`。
* 存在 `python -m trampoline.cli analyze --landmarks-only` 离线命令。
* 存在床面标定保存/读取接口，以及 `calibration.json` 持久化文件。
* `/trampoline` 页面可完成“上传视频 → 查看预览 → 手动标定 → 重载后保留标定”。

### TODO

1. [core][algo] 在 `trampoline/pipeline.py` 中封装 MediaPipe Pose VIDEO 模式，输出逐帧 `timestamp_ms`、关键点坐标、visibility 到 `landmarks.jsonl`。

   * 验证：执行 `python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --landmarks-only`，确认生成 `landmarks.jsonl` 且首尾帧都有时间戳。

2. [core] 生成 `frames_meta.json`，记录源视频路径、帧率、总帧数、宽高、帧索引与时间戳映射关系。

   * 验证：检查 `artifacts/trampoline/sample01/frames_meta.json`，确认包含 `fps`、`frame_count`、`width`、`height` 四个字段。

3. [cli] 新增 `python -m trampoline.cli analyze` 命令，支持 `--video`、`--out`、`--landmarks-only` 参数，作为后续各阶段的统一离线入口。

   * 验证：执行 `python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --landmarks-only`，确认退出码为 `0`。

4. [app] 在 `/trampoline` 页面接入视频上传、分析任务提交和状态轮询，至少支持“上传样例视频后触发 landmarks 分析”。

   * 验证：启动服务后上传 `samples/tra_demo/sample01.mp4`，确认页面状态从 `queued/running` 变为 `done`，并出现分析结果预览。

5. [core][algo] 新建 `trampoline/bed_calibration.py`，实现床面四角点到归一化床面坐标的透视变换，并保存为 `calibration.json`。

   * 验证：完成一次标定后检查 `artifacts/trampoline/sample01/calibration.json`，确认包含四角点、中心点和归一化变换参数。

6. [app] 在预览区域叠加骨架、床面边界和中心十字线，支持读取已有 `calibration.json` 自动复现标定效果。

   * 验证：刷新 `/trampoline` 页面并重新打开同一个分析结果，确认床面边界和中心线仍能正确显示。

7. [test][core] 新增 `tests/integration/trampoline/test_pipeline_smoke.py`，覆盖第 1 条中的 landmarks 产出链路，确认样例视频可生成非空 `landmarks.jsonl`。

   * 验证：执行 `pytest tests/integration/trampoline/test_pipeline_smoke.py -q`，预期通过。

8. [test][core] 新增 `tests/unit/trampoline/test_frames_meta.py`，覆盖第 2 条中的帧索引与时间戳映射，校验首帧、尾帧和随机帧的映射一致性。

   * 验证：执行 `pytest tests/unit/trampoline/test_frames_meta.py -q`，预期通过。

9. [test][cli] 新增 `tests/integration/trampoline/test_cli_analyze.py`，覆盖第 3 条中的 `analyze --landmarks-only` 命令，检查退出码和产物目录结构。

   * 验证：执行 `pytest tests/integration/trampoline/test_cli_analyze.py -q`，预期通过。

10. [test][app] 新增 `tests/e2e/trampoline/test_upload_and_status.py`，覆盖第 4 条中的“上传视频 → 任务完成”主链路。

    * 验证：执行 `pytest tests/e2e/trampoline/test_upload_and_status.py -q`，预期通过。

11. [test][core] 新增 `tests/unit/trampoline/test_bed_calibration.py`，覆盖第 5 条中的透视变换与 `calibration.json` 序列化/反序列化逻辑。

    * 验证：执行 `pytest tests/unit/trampoline/test_bed_calibration.py -q`，预期通过。

12. [test][app] 新增 `tests/e2e/trampoline/test_overlay_persistence.py`，覆盖第 6 条中的叠加显示与标定持久化效果。

    * 验证：执行 `pytest tests/e2e/trampoline/test_overlay_persistence.py -q`，预期通过。

---

## Phase 2：跳次分割与可交互时间轴（约 12 项）

### 目标（Goals）

* 基于 Phase 1 的 `landmarks.jsonl` 和 `calibration.json`，自动完成 routine 的 jump 分割。
* 页面底部可显示按 jump 切分的可交互时间轴，支持定位、边界微调、split、merge。
* 自动分段结果与人工修正可以合并存储、重复加载，形成后续动作判读的稳定输入。

### 阶段性交付成果（Deliverables）

* 存在 `trampoline/bounce_segmenter.py`，可输出 `segmentation.json`。
* 存在 `python -m trampoline.cli segment` 命令。
* `/trampoline` 页面存在可交互 jump timeline，并能驱动视频 seek。
* 存在 `overrides.json`，页面刷新后仍能保留人工边界修正结果。

### TODO

1. [core][algo] 在 `trampoline/bounce_segmenter.py` 中实现纵向时序信号预处理，基于 hip/ankle 轨迹提取 contact candidate 与 apex candidate。

   * 验证：执行 `python -m trampoline.cli segment --analysis-dir artifacts/trampoline/sample01`，确认日志中能输出非零数量的 `contact_candidates` 和 `apex_candidates`。

2. [core][algo] 实现 jump state machine 和多信号融合分段逻辑，输出每跳的 `start_ms`、`takeoff_ms`、`apex_ms`、`landing_ms`、`end_ms`。

   * 验证：检查 `artifacts/trampoline/sample01/segmentation.json`，确认 jump 列表按时间升序排列，且每跳都有上述关键时刻字段。

3. [core] 在统一 schema 中补齐 `JumpSegment` 的人工修正字段，并实现自动结果与 `overrides.json` 的合并策略。

   * 验证：手工写入一条边界修正后重新加载分析结果，确认页面读到的是合并后的边界而不是被自动结果覆盖。

4. [cli] 新增 `python -m trampoline.cli segment` 命令，支持基于已存在的 `landmarks.jsonl` 和 `calibration.json` 生成 `segmentation.json`。

   * 验证：执行 `python -m trampoline.cli segment --analysis-dir artifacts/trampoline/sample01`，确认退出码为 `0` 且生成 `segmentation.json`。

5. [app] 在 `/trampoline` 页面实现 jump timeline 渲染，支持点击 jump block 后视频 seek 到该 jump 的 `start_ms`。

   * 验证：在页面点击第 2 个或第 3 个 jump block，确认视频播放头和当前帧指示器同步跳转。

6. [app] 实现 jump 边界微调、split、merge 和保存操作，并将人工修正写入 `overrides.json`。

   * 验证：手动执行一次“向后微调边界 2 帧”和一次 `split/merge`，刷新页面后确认结果仍保留。

7. [test][core] 新增 `tests/unit/trampoline/test_contact_signal.py`，覆盖第 1 条中的信号预处理和 contact/apex candidate 提取，包含噪声样本与缺帧样本。

   * 验证：执行 `pytest tests/unit/trampoline/test_contact_signal.py -q`，预期通过。

8. [test][core] 新增 `tests/integration/trampoline/test_segmentation_golden.py`，覆盖第 2 条中的主分段逻辑，对 `sample01` 固定 jump 数和关键时间顺序做 golden 校验。

   * 验证：执行 `pytest tests/integration/trampoline/test_segmentation_golden.py -q`，预期通过。

9. [test][core] 新增 `tests/unit/trampoline/test_override_merge.py`，覆盖第 3 条中的覆盖优先级、幂等重载和重复保存不漂移逻辑。

   * 验证：执行 `pytest tests/unit/trampoline/test_override_merge.py -q`，预期通过。

10. [test][cli] 新增 `tests/integration/trampoline/test_cli_segment.py`，覆盖第 4 条中的 `segment` 命令输出结构和错误参数处理。

    * 验证：执行 `pytest tests/integration/trampoline/test_cli_segment.py -q`，预期通过。

11. [test][app] 新增 `tests/e2e/trampoline/test_timeline_seek.py`，覆盖第 5 条中的“点击 jump → 视频 seek → 当前 jump 高亮”交互。

    * 验证：执行 `pytest tests/e2e/trampoline/test_timeline_seek.py -q`，预期通过。

12. [test][app] 新增 `tests/e2e/trampoline/test_timeline_edit_persistence.py`，覆盖第 6 条中的边界微调、split、merge、保存、刷新后的持久化。

    * 验证：执行 `pytest tests/e2e/trampoline/test_timeline_edit_persistence.py -q`，预期通过。

---

## Phase 3：姿态特征、动作判读与标签修正（约 12 项）

### 目标（Goals）

* 基于 Phase 2 的 jump 边界，对每个 jump 输出稳定的 `tuck / pike / straight` 自动标签。
* 规则实现只覆盖单人 TRA demo 所需的 body-shape 判读，明确采用“飞行中段 + 最低难度形态”的简化策略。
* 页面右侧可查看判读依据、角度摘要、置信度，并允许人工覆盖自动标签。

### 阶段性交付成果（Deliverables）

* 存在 `trampoline/features.py`、`trampoline/rules_tra.py`，可输出 `features.jsonl` 与 `labels.json`。
* 每个 jump 都有自动标签、置信度、判定原因和低可见性 fallback 信息。
* `/trampoline` 页面存在 jump 详情面板，可显示角度摘要、自动标签和人工覆盖入口。
* 人工标签覆盖可持久化，并参与导出结果。

### TODO

1. [core][algo] 在 `trampoline/features.py` 中实现关键角度计算，至少包含 `trunk_thigh_angle`、`thigh_shank_angle`，并过滤低 visibility 关键点。

   * 验证：执行 `python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --steps features`，确认生成 `features.jsonl` 且包含两类角度字段。

2. [core][algo] 实现按 jump 的飞行相位归一化，抽取飞行中段分析窗口，避免用离床和触床瞬间帧直接判类。

   * 验证：检查 `features.jsonl` 或调试输出，确认每个 jump 都有 `flight_phase` 和 `is_mid_flight_window` 标记。

3. [core][algo] 实现 `tuck / pike / straight` 分类器，支持阈值配置、低可见性降级和最小置信度输出。

   * 验证：执行完整分析后检查 `labels.json`，确认每个 jump 至少包含 `auto_label`、`confidence`、`source` 字段。

4. [core] 在 `trampoline/rules_tra.py` 中实现“飞行中段 + 最低难度形态”规则，输出可解释的 `decision_reason` 与 `fallback_reason`。

   * 验证：检查 `labels.json` 中任意一跳，确认可看到 `decision_reason`，低可见性样本可看到 `fallback_reason`。

5. [app] 在页面右侧实现 jump 详情面板，展示当前 jump 的自动标签、置信度、关键角度摘要和判定原因。

   * 验证：点击不同 jump block，确认右侧详情面板内容跟随切换，且标签和摘要同步更新。

6. [app] 实现人工标签覆盖与原因备注，支持“覆盖为 tuck / pike / straight”和“清除覆盖”两种操作。

   * 验证：在页面将某一跳标签手工改为其他形态并保存，刷新后确认覆盖值和备注仍存在。

7. [test][core] 新增 `tests/unit/trampoline/test_angles.py`，覆盖第 1 条中的角度计算逻辑，使用可手算的 landmark fixture 做精确断言。

   * 验证：执行 `pytest tests/unit/trampoline/test_angles.py -q`，预期通过。

8. [test][core] 新增 `tests/unit/trampoline/test_shape_classifier.py`，覆盖第 2～4 条中的相位窗口、分类阈值、低可见性 fallback 和 decision reason。

   * 验证：执行 `pytest tests/unit/trampoline/test_shape_classifier.py -q`，预期通过。

9. [test][core] 新增 `tests/integration/trampoline/test_label_golden.py`，对已标注的 sample jump fixture 做 golden 校验，保证 `tuck / pike / straight` 输出稳定。

   * 验证：执行 `pytest tests/integration/trampoline/test_label_golden.py -q`，预期通过。

10. [test][app] 新增 `tests/e2e/trampoline/test_jump_detail_panel.py`，覆盖第 5 条中的“切换 jump → 详情面板更新 → 视频与时间轴联动”交互。

    * 验证：执行 `pytest tests/e2e/trampoline/test_jump_detail_panel.py -q`，预期通过。

11. [test][app] 新增 `tests/e2e/trampoline/test_label_override_persistence.py`，覆盖第 6 条中的人工标签覆盖、刷新后持久化和清除覆盖逻辑。

    * 验证：执行 `pytest tests/e2e/trampoline/test_label_override_persistence.py -q`，预期通过。

12. [test][core] 新增 `tests/integration/trampoline/test_label_contract.py`，校验 `features.jsonl`、`labels.json` 的字段契约与 UI 读取键名一致，覆盖第 1～6 条结果产物的兼容性。

    * 验证：执行 `pytest tests/integration/trampoline/test_label_contract.py -q`，预期通过。

---

## Phase 4：落点辅助判读、异常标记与 v1.0 收口（约 12 项）

### 目标（Goals）

* 基于 Phase 2 和 Phase 3 的分析结果，为每个 jump 提供归一化落点和简化水平位移辅助信息。
* 增加 demo 级别的异常 flag：`single_leg`、`out_of_bed`、`final_out_bounce`、`final_stable_3s`。
* 形成一键导出和一键验收能力，达到可演示、可回归、可交付的 v1.0 状态。

### 阶段性交付成果（Deliverables）

* 存在 `landing.json`、`summary.md`、`analysis_bundle.zip` 等导出产物。
* `/trampoline` 页面可显示落点热图、center deviation 摘要和 routine flag。
* 存在 `python -m trampoline.cli export` 命令，支持导出分析结果包。
* 存在 `scripts/check_v1_acceptance.sh`，可以一条命令跑完整条样例回归链路。

### TODO

1. [core][algo] 新建 `trampoline/landing.py`，实现落点提取规则：脚落点优先，前/后/坐落时允许以 hip 位置作为 fallback，并统一映射到归一化床面坐标。

   * 验证：执行完整分析后检查 `artifacts/trampoline/sample01/landing.json`，确认每跳包含 `landing_x_norm`、`landing_y_norm`、`landing_source`。

2. [core][algo] 实现简化的 center deviation / zone summary 计算逻辑，只做 demo 级辅助信息，不输出官方 H-score。

   * 验证：检查 `summary.md` 或 `landing.json`，确认存在 `center_deviation`、`zone` 或等价字段。

3. [core][algo] 实现 routine / jump 异常 flag：`single_leg`、`out_of_bed`、`final_out_bounce`、`final_stable_3s`。

   * 验证：对包含异常片段的 fixture 或裁剪样例运行分析，确认 `labels.json` 或 `summary.md` 中出现对应 flag。

4. [cli] 新增 `python -m trampoline.cli export` 命令，输出 `analysis.json`、`summary.md`、`overlays/`、`analysis_bundle.zip`。

   * 验证：执行 `python -m trampoline.cli export --analysis-dir artifacts/trampoline/sample01`，确认导出目录和 zip 文件都生成成功。

5. [app] 在 `/trampoline` 页面实现落点热图、summary panel 和导出按钮，能够下载 `analysis_bundle.zip`。

   * 验证：在页面完成一次分析后，确认 summary panel 可见，点击导出按钮能下载到 zip 文件。

6. [doc][repo] 完成 v1.0 文档收口，更新 `README.md`、新增 `docs/v1_release_checklist.md` 和 `docs/demo_script.md`，写明运行方式、限制项、演示步骤。

   * 验证：执行 `grep -E "安装|运行|限制|演示" README.md docs/v1_release_checklist.md docs/demo_script.md`，确认关键章节齐全。

7. [test][core] 新增 `tests/unit/trampoline/test_landing.py`，覆盖第 1 条中的 feet/hip 选择逻辑、归一化坐标边界和非法点拒绝。

   * 验证：执行 `pytest tests/unit/trampoline/test_landing.py -q`，预期通过。

8. [test][core] 新增 `tests/unit/trampoline/test_flags.py`，覆盖第 2～3 条中的 zone summary、`single_leg`、`out_of_bed`、`final_out_bounce`、`final_stable_3s`。

   * 验证：执行 `pytest tests/unit/trampoline/test_flags.py -q`，预期通过。

9. [test][cli] 新增 `tests/integration/trampoline/test_cli_export.py`，覆盖第 4 条中的 `export` 命令，校验 bundle 结构、文件数和关键字段。

   * 验证：执行 `pytest tests/integration/trampoline/test_cli_export.py -q`，预期通过。

10. [test][app] 新增 `tests/e2e/trampoline/test_summary_and_export.py`，覆盖第 5 条中的热图显示、summary panel 展示和导出下载。

    * 验证：执行 `pytest tests/e2e/trampoline/test_summary_and_export.py -q`，预期通过。

11. [test][repo] 在 CI 中新增 sample-analysis smoke job，串行执行 `ruff check .`、`pytest -q`、`python -m trampoline.cli analyze`、`segment`、`export`。

    * 验证：推送到测试分支后，确认 CI 中 sample-analysis job 能跑通并保留导出产物作为 artifact。

12. [test][repo] 新建 `scripts/check_v1_acceptance.sh`，串联样例视频从分析、分段、标签、落点、导出到结果检查的完整验收路径，覆盖第 1～5 条的集成能力。

    * 验证：执行 `bash scripts/check_v1_acceptance.sh samples/tra_demo/sample01.mp4`，预期退出码为 `0`，并输出 `PASS` 与产物路径列表。

---

## v1.0 完成判定

* `bash scripts/check_v1_acceptance.sh samples/tra_demo/sample01.mp4` 可以稳定通过。
* `/trampoline` 页面可完成：上传视频 → 标定 → 自动分段 → 时间轴修正 → 自动 body-shape 判读 → 人工覆盖 → 查看落点和 summary → 导出结果。
* 项目文档明确写清范围与限制：仅单人 TRA demo，不宣称官方评分，不包含 D-score / ToF / SYN / TUM / DMT。
* 至少有一条样例视频具备可重复的 golden regression 结果。
