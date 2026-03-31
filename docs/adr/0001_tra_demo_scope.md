# ADR 0001: 单人 TRA Demo 范围

## 状态

Accepted

## 背景

当前仓库已经包含基于 Flask + MediaPipe 的健身训练能力。为了落地轻量化蹦床 AI 裁判 Demo，需要把新业务放在独立的 `trampoline/` 模块中，与原有 exercise engine 并行存在，避免继续把蹦床逻辑塞进已有训练流程。

## 决策

v1.0 仅覆盖单人 TRA demo，目标是建立后续分析阶段可以稳定复用的基础契约：

- 单人 TRA 视频上传与 `/trampoline` 页面壳。
- 独立的 `trampoline/` Python 包、统一 schema、CLI 骨架。
- 样例数据 manifest、fixture 命名规范、基础自动化测试与 CI。
- 为后续 landmarks、分段、人工修正、导出产物预留稳定文件位。

## 明确不做

以下能力在本 ADR 中明确不做，避免 Phase 0 范围膨胀：

- 不做 D-score 计算。
- 不做 ToF 计算。
- 不做 SYN 评分。
- 不做 TUM 支持。
- 不做 DMT 支持。
- 不做官方总分聚合。
- 不做多人 routine、多人同步判读或多机位融合。

## 影响

- 新的蹦床实现应放在 `trampoline/`、`samples/tra_demo/`、`fixtures/trampoline/`、`tests/**/trampoline/` 这些旁路目录下。
- 原有 exercise 页面与视频分析页面继续保留；只有在导航中新增 trampoline demo 入口。
- 后续阶段默认基于 `RoutineAnalysis`、`JumpSegment`、`ManualOverride`、`AnalysisArtifactRef` 继续扩展，而不是重新定义数据契约。
