# Lab 4：结果、LLM 与安全扩展流

## 这个 Lab 的目标

前 3 个 Lab 你已经看到了：

- 主链路如何启动；
- 前端如何驱动交互；
- 后端和算法如何生成结构化结果。

这一节要解决最后两个关键问题：

1. **这些结果是怎样回到页面上的？**
2. **如果以后要扩展这个项目，怎样做才不容易把原有功能改坏？**

完成后，你至少应该能解释：

- `/api/video/status/<video_id>` 为什么是运行态结果契约；
- `video_analysis_helpers.js` 为什么代表“加法式扩展”的前端写法；
- `trampoline/llm_service.py` 怎样把结构化结果变成流式 AI 分析；
- 一个安全的小扩展应该先找契约、先看测试，而不是直接改页面。

## 本 Lab 切的是哪条垂直切片

本节切的是最后一段结果输出流：

```text
video_processor / analyzer 产出结构化结果
-> app.py 通过 /api/video/status/<video_id> 暴露运行态与结果态字段
-> 前端 helper 决定统计区显示什么
-> video_analysis.js 把状态、报告、落点图、AI 区拼起来
-> /api/video/llm_analysis/<video_id> 通过 SSE 输出 AI 文本分析
-> 学习者据此设计一个安全扩展练习
```

## 先看 `/api/video/status/<video_id>`

看：

- `app.py` 中的 `get_video_status(...)`
- `tests/test_trampoline_api.py` 中的 `test_status_exposes_additive_runtime_fields`
- `tests/test_trampoline_api.py` 中的 `test_sync_analysis_from_results_preserves_runtime_seam`

### 为什么这个接口很重要

因为它不是简单的“进度查询接口”，而是：

- 前端运行态数据的总出口；
- 页面统计区、落点图、报告区的数据来源；
- 处理过程中和处理完成后都要依赖的结果契约。

它返回的字段包括：

- `status`
- `progress`
- `reps`
- `current_action`
- `completed_jumps`
- `phase`
- `current_flight_frames`
- `current_flight_duration_s`
- `latest_landing`
- `landings`
- `fps`
- `video_fps`
- 以及处理后视频相关字段

这些字段里，有一部分是后来**加法式扩展**出来的。

### 什么叫“加法式扩展”

意思是：

- 不把旧字段推翻重做；
- 在旧契约上新增更细的信息；
- 老前端还能工作；
- 新前端可以逐步消费更多字段。

这在工程里很稳，因为它比“整个返回结构推倒重来”更不容易造成回归。

## 够用语法 / 结构提醒：先能读懂“结果对象”和“流式输出”

这一节你会反复遇到几种结构：

- JSON 字段
  - 例如 `status`、`completed_jumps`、`latest_landing`。
  - 你可以把它们理解成“接口协议里的字段表”。
- `AnalysisReport`
  - 这是把分析结果重新整理成一份更适合给 LLM 使用的数据结构。
  - 先不用纠结高级写法，先把它理解成“专门给 AI 解读层准备的一份结构化报告”。
- `yield`
  - 这是 Python 里很值得认识的关键字。
  - 在这里你可以把它先理解成：**不要一次性把整段结果全吐出来，而是一小段一小段往外送**。
  - 这和串口分段输出的感觉很像。
- SSE
  - 可以先理解成“浏览器保持连接，边收到内容边显示”的机制。
- helper 纯函数
  - 输入一包状态数据；
  - 输出一包“页面该怎么显示”的结果；
  - 中间尽量不直接改 DOM。

如果你先把“结构化结果”和“流式分段输出”这两件事分开看，这一层就会清楚很多。

## `video_analysis_helpers.js`：为什么它这么值得学

看：

- `static/js/video_analysis_helpers.js`
- `tests/test_video_analysis_ui_helpers.mjs`

这里最值得学的是：

- `resolveCompactStats(...)`

它负责做一类非常典型的 UI 决策：

- 当前有实时 flight 数据，就显示实时值；
- 当前没有有效实时值，就回退到最近一次有效跳；
- 当前没有有效 landing，就不要乱显示垃圾值。

### 为什么这体现了“加法式扩展”

因为它没有要求后端必须彻底换返回结构，而是：

- 在已有结果上，多用一些新增字段；
- 前端自己把“当前值”和“最近一次有效值”整合起来。

这就是很典型的：

- **后端加法扩展**
- **前端渐进消费**

### 这对你以后扩展项目有什么启发

如果以后你要新增一个显示字段，优先想：

- 能不能在旧结构上加；
- 能不能先通过 helper 层消化；
- 能不能先不破坏旧页面逻辑。

## `video_analysis.js`：把结果真正拼回页面

看：

- `static/js/video_analysis.js`

在这个 Lab 里重点看这些职责：

- 轮询 `/api/video/status/<video_id>`；
- 调 `updateStats(...)`；
- 调 `showTrampolineReport(...)`；
- 维护落点图、反馈区、终端日志区；
- 在合适时机开启 AI 分析。

### 你要学的不是“所有细节”，而是拼装思路

也就是说，这个文件告诉你：

- 后端只负责给结构化数据；
- 真正决定页面各块如何联动的，是前端主流程文件；
- helper 负责收敛规则；
- 主流程文件负责把规则应用到页面。

## `trampoline/llm_service.py`：结构化结果如何变成 AI 文本分析

看：

- `trampoline/llm_service.py`
- `app.py` 中的 `llm_analysis(...)`
- `tests/test_llm_service.py`

### 这层在系统里做什么

它不是重新跑一遍视频算法，而是做：

1. 从结构化分析结果构建 `AnalysisReport`；
2. 生成适合 LLM 的 prompt；
3. 调用模型；
4. 把模型输出切成前端能消费的 section；
5. 用 SSE 流式把结果发给前端。

### 为什么它是一条独立输出链

因为：

- `/api/video/status` 负责结构化、稳定、程序可消费的数据；
- `/api/video/llm_analysis` 负责把这些数据转换成面向人的解释文本。

这两者的职责不同，所以不应该混在一个接口里。

## 安全扩展应该怎么做

这一节最重要的，不是学“怎么加一个新面板”，而是学：

> **以后你自己改项目时，怎样不容易把项目改坏。**

推荐顺序：

1. 先找契约
   - 这个改动属于哪一层？
   - 是 status 返回字段？
   - 是 helper 规则？
   - 还是 LLM 文本输出？
2. 先看或先补测试
   - 现有测试能不能保护你要改的地方？
   - 如果不能，先补一个最小检查点。
3. 再小步实现
   - 不要一下改三层；
   - 优先做加法式扩展。
4. 再验证
   - 先跑相关测试；
   - 再看手工效果。
5. 最后写文档/旁读
   - 说明为什么这样改；
   - 说明影响了哪些契约。

## 学习重点

### 学习重点 1：`/api/video/status` 是运行态结果契约

它不是“只是状态”，而是前端显示的事实来源。

### 学习重点 2：helper 层是控制 UI 复杂度的重要手段

把“如何选当前值 / 最近有效值”这种规则放到 helper 层，可以让页面主逻辑更稳定。

### 学习重点 3：LLM 是解释层，不是检测层

LLM 不重新识别动作，它消费的是前面算法层已经产出的结构化结果。

### 学习重点 4：扩展项目时，优先做加法式扩展

- 新字段尽量加，不尽量重构旧结构；
- 先保证老前端还能工作；
- 再让新页面逐渐消费更多数据。

## MCU C 视角下怎么理解这一层

可以这样类比：

- `/api/video/status` 新增字段
  - ≈ 在旧协议上增加可选寄存器，旧读法仍然要兼容
- `video_analysis_helpers.js`
  - ≈ 把协议解析和显示规则收敛到一个中间层
- SSE 流式输出
  - ≈ 串口分段发送数据，前端边收边显示，而不是整包等到最后
- LLM service
  - ≈ 高层解释模块，不直接碰底层采样

## 动手练习

### 练习 1：画结果输出路径

请你自己画出下面这条链：

- `video_processor.py`
- `app.py` status route
- `video_analysis_helpers.js`
- `video_analysis.js`
- `trampoline/llm_service.py`
- 前端 AI 面板

并说明：

- 哪一层负责结构化数据；
- 哪一层负责解释文本；
- 哪一层负责页面展示。

### 练习 2：设计一个小扩展但不要实现

例如你可以设计：

- 新增一个 display-only 的状态字段；
- 或者给统计区新增一个更清楚的文案；
- 或者给 helper 增加一个更稳的 fallback 规则。

请你写出：

- 你会改哪些文件；
- 会影响哪个契约；
- 先跑/先补哪些测试；
- 怎么确认这是“加法式扩展”而不是破坏式重构。

### 练习 3：解释为什么 `status` 和 `llm_analysis` 不能合并

试着自己写一段说明，回答：

- 结构化结果和解释文本的使用场景有什么不同；
- 为什么它们应该是两条输出链；
- 如果强行合并会带来什么问题。

## 强制检查点

```bash
python -m pytest tests/test_trampoline_api.py -v
python -m pytest tests/test_llm_service.py -v
node tests/test_video_analysis_ui_helpers.mjs
```

### 这些检查点分别在保护什么

- `tests/test_trampoline_api.py`
  - status/runtime seam、upload/start/status 契约是否仍然正确。
- `tests/test_llm_service.py`
  - AnalysisReport、prompt、section 切分、API key/model 解析等 LLM 层契约是否仍然成立。
- `tests/test_video_analysis_ui_helpers.mjs`
  - compact stats / latest-valid fallback 逻辑是否仍然可靠。

## 旁读 / 背景材料

这一节适合回看这些文档，但它们仍然只是旁读：

- `trampoline/docs/2026-04-03-LLM解释层集成.md`
- `trampoline/docs/2026-04-04-双模型并行AI分析.md`
- `trampoline/docs/2026-04-19-回归与模块化.md`
- `trampoline/docs/2026-04-20-视频页改版.md`

阅读目标不是“把它们当教程”，而是：

- 看看当前结构为什么会演进成现在这样；
- 理解某些 helper、字段、面板是怎么一步步加出来的。

## 自检问题

1. 为什么 `/api/video/status` 可以看成运行态结果契约？
2. `video_analysis_helpers.js` 为什么能降低 UI 复杂度？
3. 为什么 LLM service 不是检测层的一部分？
4. 什么叫“加法式扩展”？
5. 如果你要新增一个字段，为什么应该先找相关测试？
6. 为什么 dated docs 适合当背景材料，而不适合当主学习路线？

如果这些问题你已经能答清楚，你就已经从“看懂现有项目”迈到了“开始具备安全扩展能力”的阶段。
