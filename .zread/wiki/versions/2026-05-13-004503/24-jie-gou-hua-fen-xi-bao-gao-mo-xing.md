**结构化分析报告模型**位于 AI 分析层的入口位置：它不直接识别动作、不调用视频处理算法，也不负责前端展示，而是把已经完成的视频分析结果转换为一个稳定、可解释、可传给 LLM 的 `AnalysisReport` 数据对象。这个页面只讨论该模型的字段、转换规则、数据边界和验证方式；SSE 流式返回与双模型调度请继续阅读 [SSE 流式返回、缓存与双模型分析](26-sse-liu-shi-fan-hui-huan-cun-yu-shuang-mo-xing-fen-xi)，提示词规则请继续阅读 [提示词构建与输出约束](25-ti-shi-ci-gou-jian-yu-shu-chu-yue-shu)。Sources: [llm_service.py](trampoline/llm_service.py#L18-L65), [app.py](app.py#L606-L705)

## 架构假设与验证结论

从第一性原理看，LLM 不应该直接消费视频处理过程中的临时状态，而应该消费一个**收敛后的结构化快照**；代码验证显示，`/api/video/llm_analysis/<video_id>` 只在视频记录存在、模式为 `trampoline`、状态为 `completed` 时继续执行，并在通过 API key 检查后调用 `AnalysisReport.from_video_analysis(analysis)` 构造报告对象。Sources: [app.py](app.py#L620-L655)

第二个假设是：报告模型应该只做**轻量派生与字段规整**，不重新计算跳次、动作类型或落点映射；代码验证显示，`from_video_analysis()` 读取 `completed_jumps`、`fps`、`total_frames`、`resolution`，只派生 `duration_s`、逐跳 `flight_duration_s`、动作分布和落点列表，没有调用动作分类器、跳次检测器或床面映射算法。Sources: [llm_service.py](trampoline/llm_service.py#L36-L65)

第三个假设是：报告模型需要对后续扩展保持开放，但当前页面只能记录已存在字段；代码验证显示，`AnalysisReport` 已声明 `landing_points`、`form_scores`、`rotation_data`、`extra_sections` 等可选字段，其中当前构造函数实际填充的是 `landing_points`，而 `extra_sections` 可由调用方追加补充文本。Sources: [llm_service.py](trampoline/llm_service.py#L20-L35), [tests/test_llm_service.py](tests/test_llm_service.py#L56-L60)

## 模型在 AI 分析层中的位置

`AnalysisReport` 是视频分析结果与 LLM 消息之间的**中间表示**：视频处理进程最终写入 `fps`、`video_fps`、`total_frames`、`resolution`、`completed_jumps`、`landings` 等结果字段；AI 分析端点读取内存中的 `analysis` 字典，并把它转换为 `AnalysisReport` 后再进入提示词构建与模型调用流程。Sources: [video_processor.py](video_processor.py#L313-L329), [app.py](app.py#L654-L655)

```mermaid
flowchart LR
    A[视频处理最终结果 analysis dict] --> B[AnalysisReport.from_video_analysis]
    B --> C[AnalysisReport 结构化报告]
    C --> D[build_prompt(report)]
    D --> E[LLM 调用与响应分段]

    A:::data
    C:::model
    E:::ai

    classDef data fill:#eef6ff,stroke:#4b83c4,color:#1f3552
    classDef model fill:#f1fff1,stroke:#4b9b57,color:#183f20
    classDef ai fill:#fff6e8,stroke:#d48a2a,color:#4a2a00
```

上图表达的是该模型的责任边界：`AnalysisReport` 接收已经完成的分析字典，输出规范化后的报告对象；后续的 `build_prompt()` 会把报告对象转成 OpenAI-compatible 的 system/user messages，但这属于下一页 [提示词构建与输出约束](25-ti-shi-ci-gou-jian-yu-shu-chu-yue-shu) 的重点。Sources: [llm_service.py](trampoline/llm_service.py#L95-L147)

## 字段结构

`AnalysisReport` 当前是一个 `dataclasses.dataclass`，核心字段包括总跳次、视频时长、帧率、分辨率、逐跳结果和动作分布；这些字段构成 LLM 可读报告的最小稳定输入。Sources: [llm_service.py](trampoline/llm_service.py#L20-L29)

| 字段 | 类型 | 来源或构造方式 | 当前用途 |
|---|---:|---|---|
| `total_jumps` | `int` | 优先取 `analysis["reps"]`，缺失时使用 `len(completed_jumps)` | 表示本次训练总跳次 |
| `duration_s` | `float` | `round(total_frames / fps, 1)`，`fps <= 0` 时为 `0` | 表示视频时长 |
| `fps` | `float` | `analysis["fps"]`，默认 `30` | 用于换算滞空秒数 |
| `resolution` | `str` | `analysis["resolution"]`，默认 `"unknown"` | 表示视频分辨率 |
| `completed_jumps` | `list` | 在原始逐跳记录基础上追加 `flight_duration_s` | 支撑逐跳解读 |
| `action_distribution` | `dict` | 对非中间跳的 `action` 计数 | 表示动作分布 |
| `landing_points` | `Optional[list]` | 从含 `landing` 的逐跳记录中提取 | 支撑落点数据输入 |
| `extra_sections` | `str` | dataclass 默认空字符串 | 允许追加补充数据 |

Sources: [llm_service.py](trampoline/llm_service.py#L20-L65)

## 从视频结果到报告对象的转换规则

转换入口是 `AnalysisReport.from_video_analysis(cls, analysis)`，它从 `analysis` 字典读取 `completed_jumps`，并使用 `fps` 和 `total_frames` 计算视频时长；当缺少 `fps` 时默认使用 `30`，当缺少 `total_frames` 时默认使用 `0`。Sources: [llm_service.py](trampoline/llm_service.py#L36-L43)

逐跳记录会被复制并增强：每个 jump 字典保留原字段，同时新增 `flight_duration_s`，其计算方式为 `round(flight_frames / fps, 2)`；如果 `fps <= 0`，则滞空时长写为 `0`。Sources: [llm_service.py](trampoline/llm_service.py#L44-L50)

动作分布会排除 `is_intermediate` 为真值的中间跳，只统计真实动作跳；测试用例明确验证了第 5 跳为中间跳时，`Straight` 的统计不会把该中间跳计入分布。Sources: [llm_service.py](trampoline/llm_service.py#L52-L54), [tests/test_llm_service.py](tests/test_llm_service.py#L39-L42)

落点数据不是单独重新计算，而是从增强后的逐跳记录中提取已有 `landing` 字段；如果没有任何落点，`landing_points` 会保持为 `None`。Sources: [llm_service.py](trampoline/llm_service.py#L55-L65), [tests/test_llm_service.py](tests/test_llm_service.py#L56-L60)

## 上游数据契约

上游 `TrampolineAnalyzer` 在检测到 `landing` 事件时完成一条逐跳记录，字段包括 `jump_number`、`action`、`flight_frames`、`is_intermediate`，并在可计算时附加 `landing`；因此报告模型依赖的是已经稳定生成的逐跳结构，而不是帧级姿态点。Sources: [trampoline/analyzer.py](trampoline/analyzer.py#L44-L64)

`TrampolineAnalyzer` 返回的运行状态中也包含 `completed_jumps`、`latest_landing` 和 `landings`，而视频处理器在处理过程中把这些字段同步到 `results`，最终完成时再写入 `total_frames` 与 `resolution`。Sources: [trampoline/analyzer.py](trampoline/analyzer.py#L71-L86), [video_processor.py](video_processor.py#L274-L282), [video_processor.py](video_processor.py#L319-L329)

| 上游字段 | 生成位置 | 报告模型如何使用 |
|---|---|---|
| `reps` | 视频处理结果 | 映射为 `total_jumps` |
| `completed_jumps` | 分析器落地事件累计 | 映射并增强为报告逐跳列表 |
| `fps` | 视频读取阶段 | 用于 `duration_s` 与 `flight_duration_s` |
| `total_frames` | 视频读取阶段，最终写入 | 用于 `duration_s` |
| `resolution` | 视频处理最终结果 | 映射为报告分辨率 |
| `completed_jumps[i].landing` | 分析器落地载荷 | 提取为 `landing_points` |

Sources: [video_processor.py](video_processor.py#L129-L135), [video_processor.py](video_processor.py#L319-L329), [trampoline/analyzer.py](trampoline/analyzer.py#L53-L64)

## 下游消费方式

报告对象进入下游后，`build_prompt(report)` 会遍历 `report.completed_jumps` 生成逐跳文本，并在存在落点时拼接床面坐标、区域和置信度；这说明 `AnalysisReport` 的字段命名与结构直接决定了 LLM 输入数据的可读性。Sources: [llm_service.py](trampoline/llm_service.py#L95-L111)

动作分布会被格式化为 `"动作: 次数"` 的字符串；如果没有动作分布，则写入 `"无数据"`，从而避免空字典直接暴露给自然语言模型。Sources: [llm_service.py](trampoline/llm_service.py#L113-L128)

当 `landing_points` 存在时，下游提示词内容会追加“落点数据”段落，逐条输出床面坐标、区域、距中心距离和置信度；当 `extra_sections` 非空时，会追加“补充数据”段落。Sources: [llm_service.py](trampoline/llm_service.py#L130-L143)

## 默认值与容错边界

报告模型对缺失字段有明确默认值：缺少 `fps` 时使用 `30`，缺少 `resolution` 时使用 `"unknown"`，缺少 `completed_jumps` 时使用空列表；测试用例验证了只传入 `{"reps": 0}` 时这些默认值会生效。Sources: [llm_service.py](trampoline/llm_service.py#L39-L43), [tests/test_llm_service.py](tests/test_llm_service.py#L49-L55)

`duration_s` 和 `flight_duration_s` 都受 `fps` 控制，并在 `fps <= 0` 时退化为 `0`，这避免了除零错误；该逻辑只做数值保护，不改变上游跳次或动作分类结果。Sources: [llm_service.py](trampoline/llm_service.py#L40-L50)

## 可扩展点

`AnalysisReport` 已包含 `form_scores`、`rotation_data` 和 `extra_sections` 等字段，但当前 `from_video_analysis()` 只自动填充 `landing_points`，并不会自动构造评分或旋转数据；因此新增指标时，应先让上游结果结构稳定输出，再在报告转换层显式映射。Sources: [llm_service.py](trampoline/llm_service.py#L30-L35), [llm_service.py](trampoline/llm_service.py#L57-L65)

`extra_sections` 当前以字符串方式追加到用户消息中，测试用例验证了手动写入 `"落点偏移: 左偏 5cm"` 后，构建出的用户提示词会包含该补充内容；这是一种低结构化扩展口，但不替代正式字段建模。Sources: [llm_service.py](trampoline/llm_service.py#L141-L143), [tests/test_llm_service.py](tests/test_llm_service.py#L87-L93)

## 测试覆盖

测试集把报告模型的核心契约拆成三个方面：字段转换、动作分布过滤、滞空时长派生；`test_from_video_analysis()` 验证总跳次、时长、帧率、分辨率和逐跳数量，`test_action_distribution_excludes_intermediate()` 验证中间跳不计入动作分布，`test_flight_duration_enrichment()` 验证帧数到秒数的换算。Sources: [tests/test_llm_service.py](tests/test_llm_service.py#L30-L48)

提示词构建测试也间接保护了报告模型的下游可消费性：测试要求返回 system/user 两条消息，并确认用户内容包含总跳次和动作名称，说明报告字段必须能够稳定转化为 LLM 输入文本。Sources: [tests/test_llm_service.py](tests/test_llm_service.py#L62-L86)

## 阅读路径

如果你需要理解这个报告对象从哪里来，建议回到 [端到端架构与数据流](8-duan-dao-duan-jia-gou-yu-shu-ju-liu) 和 [独立视频处理进程设计](10-du-li-shi-pin-chu-li-jin-cheng-she-ji)；如果你已经关注 AI 层的下一步，应继续阅读 [提示词构建与输出约束](25-ti-shi-ci-gou-jian-yu-shu-chu-yue-shu) 和 [SSE 流式返回、缓存与双模型分析](26-sse-liu-shi-fan-hui-huan-cun-yu-shuang-mo-xing-fen-xi)。Sources: [llm_service.py](trampoline/llm_service.py#L95-L147), [app.py](app.py#L606-L705)