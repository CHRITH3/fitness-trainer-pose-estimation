# 蹦床视频分析项目学习路线图

## 这份学习包是给谁准备的

这套材料是给**只有嵌入式 C 语言开发基础**、但希望最终能**独立开发这个项目**的人准备的。

这里的“独立开发”不是指：

- 会把项目跑起来
- 会改几行文案
- 会跟着提示修一个 bug

而是指你最终能做到：

1. 看懂当前项目的真实主链路；
2. 解释前端、后端、视频处理、算法、AI 分析为什么这样分层；
3. 从零搭出一个“简化版但结构正确”的同类项目；
4. 在当前真实仓库上做小步扩展，并知道怎么验证不把旧功能改坏；
5. 逐步具备独立设计类似视频分析项目的能力。

## 为什么这套材料不是教材式写法

你已经明确说过：**不要教材式**。

所以这里不会按“先学完 HTML，再学完 CSS，再学完 JS，再学完 Flask”这种顺序讲。那种写法的缺点是：

- 容易学了很多概念，却不知道它们在项目里到底干什么；
- 很容易把注意力放在语法细节，而不是系统为什么这样工作；
- 学到后面会发现：项目真正难的是“模块怎么接起来”，不是单条语句怎么写。

这套材料采用的是：

> **沿着真实运行链路学习，用最少够用的语法解释去支撑理解。**

也就是说，先看系统怎么流动，再看每一层用什么代码表达它。

## 这套项目的真实运行主线

你在学习时，必须先把下面这条真实链路刻在脑子里：

```text
/api/video/upload
-> uploaded_pending_calibration
-> 标定采集 / 提交
-> /api/video/trampoline/start
-> processing
-> /api/video/status/<video_id>
-> 页面报告 / 落点 / 处理后视频
-> /api/video/llm_analysis/<video_id>
```

这一点非常重要，因为这个项目**不是**“上传视频后立刻直接分析完成”的结构。

上传成功后，后端会先把状态置成：

- `uploaded_pending_calibration`

这意味着：

- 视频文件已经收到了；
- 首帧也已经提取出来了；
- 但系统还不能正式分析；
- 因为它还缺少一个关键输入：**床面标定**。

如果你忽略这一步，你就会把这个项目学歪。因为真实产品不是“直接上传→直接出结果”，而是“**先上传，再标定，再开始处理**”。

## 两阶段学习模型

### 阶段一：先学最小但不失真的真实链路

目标不是一上来理解所有细节，而是先把这条主链路跑通、讲清楚：

- 上传
- 待标定
- 标定提交
- 启动分析
- 轮询状态
- 展示结果

这一阶段会故意简化复杂度，比如：

- 只看一个关键帧；
- 不先深挖床面跟踪的所有数学细节；
- 不先展开完整动作分类规则；
- 只讲完成这条链路所必须理解的前后端协作。

但它**不会**删掉真实架构里的关键门槛，也就是：

- 标定不是可选项；
- 轮询不是装饰；
- 状态接口不是附属品；
- `/api/video/trampoline/start` 不是多余接口。

### 阶段二：进入真实仓库深挖与扩展

当你已经能解释主链路后，才进入真实项目的各层细节：

- 前端页面和标定 UI 是怎样配合的；
- `video_processor.py` 为什么要单独做一个处理入口；
- `TrampolineAnalyzer`、`JumpDetector`、`ActionClassifier`、`BedTracker`、`overlay` 各自负责什么；
- `/api/video/status` 和 `/api/video/llm_analysis` 为什么是两条不同的结果输出链；
- 如果以后要新增一个字段、一个面板、一个小功能，应该先看哪里、先补什么测试。

## 这 4 个 Lab 的学习顺序

### Lab 1：最小真实主链路

文件：`lab-1-real-seam-minimal.md`

你会学到：

- 为什么上传后不是直接完成分析；
- `uploaded_pending_calibration` 这个状态到底意味着什么；
- 标定为什么是必须的前置门槛；
- `/api/video/trampoline/start` 和 `/api/video/status/<video_id>` 在主链路中的职责。

完成后，你应该能手工画出这条状态流。

### Lab 2：前端标定与页面交互流

文件：`lab-2-frontend-calibration-flow.md`

你会学到：

- 模板里的 `id` 为什么是一种契约；
- `video_analysis.js` 怎样驱动上传、轮询、展示；
- `trampoline_calibration_ui.js` 为什么要单独拆出来；
- `trampoline_calibration_geometry.js` 为什么负责坐标换算；
- 页面上的“看起来是一块 UI”的东西，实际是如何由多个 JS 模块协作的。

完成后，你应该能解释一个按钮点击是怎样一路传到后端接口上的。

### Lab 3：处理流程与算法协作流

文件：`lab-3-processing-and-algorithm-flow.md`

你会学到：

- 为什么需要 `video_processor.py` 这个处理入口；
- `TrampolineAnalyzer` 为什么像一个总调度器；
- `JumpDetector` 为什么最适合用状态机思路理解；
- `BedTracker` 为什么是坐标和落点分析的基础；
- `ActionClassifier` 和 `overlay` 为什么不能和主检测逻辑混成一团。

完成后，你应该能追踪“一跳”怎样从视频帧一路变成结构化结果。

### Lab 4：结果、LLM 与安全扩展流

文件：`lab-4-results-llm-and-extension.md`

你会学到：

- `/api/video/status/<video_id>` 为什么是运行态结果契约；
- 前端的 compact stats / fallback 为什么是“加法式扩展”；
- `trampoline/llm_service.py` 怎样把结构化结果变成 AI 分析；
- 如果以后你要扩项目，为什么要先找契约、先补测试，再实现。

完成后，你应该能设计一个“小而安全”的扩展练习，而不是盲改页面或接口。

## 为什么这里要把测试当作检查点

这套材料里，**测试不是最后才跑的东西**，而是每个 Lab 的检查点。

因为对 MCU C 背景的人来说，测试最像：

- 上电自检；
- 接口连通性检查；
- 协议回归检查；
- 状态机行为是否仍符合预期。

你可以把它理解成：

> **如果一个 Lab 讲完了，但对应测试你完全不知道在保护什么，那说明你其实还没真正理解这一层。**

例如：

- `tests/test_app_route_contract.py`
  - 保护保留页面和 API 路由是否还存在；
- `tests/test_trampoline_api.py`
  - 保护 upload / pending calibration / start / status 的契约；
- `tests/test_trampoline_frontend_contract.py`
  - 保护前端页面结构和关键脚本接线；
- `tests/test_trampoline_calibration_ui.mjs`
  - 保护标定 UI 状态机；
- `tests/test_trampoline.py`
  - 保护跳次检测和动作分类核心逻辑；
- `tests/test_bed_tracker.py`
  - 保护床面映射、标定与跟踪；
- `tests/test_llm_service.py`
  - 保护结果到 AI 文本分析这一层。

## MCU C → Web / Python 的常用桥接类比

为了减少你进入 Web/Python 项目时的陌生感，可以先用下面这套类比：

- Flask route
  - ≈ 串口命令 / 协议命令处理入口
- 页面上的按钮事件监听
  - ≈ 回调函数 / 中断响应入口
- DOM `id`
  - ≈ 接线端口编号，名字对不上就接不通
- `/api/video/status` 轮询
  - ≈ 周期性读取状态寄存器
- `uploaded_pending_calibration`
  - ≈ 设备进入“待校准”状态，主流程还不能继续
- `video_processor.py`
  - ≈ 后台任务或协处理工作线程
- `JumpDetector`
  - ≈ 事件驱动状态机
- `BedTracker`
  - ≈ 传感器标定 + 坐标换算层
- SSE 流式输出
  - ≈ 串口分段输出，不是一次性整块返回

这些类比不是为了把 Web 强行说成 MCU，而是帮你快速抓住“职责”和“边界”。

## 第一次读这些文件时，几个高频语法先这样理解

这一节不是系统语法课，只是帮你先跨过“看代码像天书”的第一道坎。

- HTML 标签
  - 可以先理解成“页面上的零件”。
  - 例如 `<button>` 是按钮，`<div>` 更像一个容器。
- `id` 和 `class`
  - `id="video-player"`：更像**唯一接线点**，JS 常用它精确抓节点。
  - `class="stat-card"`：更像**一组同类零件的样式标签**，CSS 常用它批量设外观。
- CSS 选择器
  - `#video-player` 表示“选中这个 id”。
  - `.stat-card` 表示“选中这一类节点”。
- JavaScript 里的 `const` / `let`
  - `const`：这个变量名后续不再重新指向别的东西。
  - `let`：后面还可能改。
- JavaScript 里的对象和数组
  - `{ status: 'processing', progress: 42 }`：对象，像一包“带字段名的数据”。
  - `[1, 2, 3]`：数组，像按顺序排好的数据表。
- JavaScript 里的 `addEventListener('click', ...)`
  - 可以先理解成“给这个按钮注册点击回调”。
- JavaScript 里的 `async` / `await`
  - 让“发请求、等返回”这种异步流程写起来更像顺序代码。
- JavaScript 里的 `?.` / `??`
  - `a?.b`：如果 `a` 不存在，就不要继续报错往下取。
  - `x ?? y`：如果 `x` 是空值，就退回用 `y`。
- Python 里的 `def`
  - 定义函数。
- Python 里的 `class`
  - 把“数据 + 操作这些数据的方法”打包到一起。
- Python 里的字典和列表
  - `{"status": "processing"}`：字典，像带字段名的数据包。
  - `[jump1, jump2]`：列表，像按顺序存放的一组记录。
- JSON
  - 可以把它理解成“前后端之间传递字段化数据的通用格式”。
  - 它长得很像 Python 字典 / JS 对象，但它是跨语言传输格式。

你不用先把这些定义背下来。更重要的是：

> **每次在真实文件里看到它们时，先判断它是在描述“结构”、还是在描述“行为”。**

- HTML / CSS 更偏结构和外观；
- JS 更偏页面交互和状态推进；
- Python 更偏后端流程、数据组织和算法协作。

## 旁读 / 背景材料怎么用

项目里已经有很多很好的 dated docs，例如：

- `trampoline/docs/2026-04-17-床面标定落点MVP.md`
- `trampoline/docs/2026-04-18-关键帧标定.md`
- `trampoline/docs/2026-04-18-关键帧补标.md`
- `trampoline/docs/2026-04-18-标定漂移修复.md`
- `trampoline/docs/2026-04-19-回归与模块化.md`
- `trampoline/docs/2026-04-20-视频页改版.md`

这些文档很值得读，但它们的定位是：

- **旁读**
- **背景材料**
- **为什么当前代码会长成这样**

而不是主学习路线。

你应该先完成当前 learning 路线，再把这些 dated docs 当成“设计演进说明”去补充理解。

## 紧凑版能力自测 rubric

### Level 1：能跑、能指出入口

你能说出：

- 页面入口在哪里；
- 上传接口在哪里；
- 状态接口在哪里；
- 主要 JS 文件分别负责什么。

### Level 2：能讲清主链路

你能完整讲出：

- upload → pending calibration → start → status → result/LLM

并说明每一步为什么存在。

### Level 3：能解释模块边界

你能解释：

- 为什么标定 UI 要拆成独立模块；
- 为什么算法要拆成 detector / classifier / tracker / overlay；
- 为什么 status 和 llm 是两条不同的输出链。

### Level 4：能安全做小扩展

你能做到：

- 明确一个改动会影响哪些文件；
- 找到相关测试；
- 先补或先读检查点；
- 小步实现后验证没有回归。

### Level 5：能独立重建类似项目

你能从零规划出：

- 页面
- Flask API
- 上传 / 待标定 / 启动分析 / 状态轮询
- 基础视频处理
- 基础姿态识别
- 基础结果展示
- 可选 AI 分析

并知道应该如何分层，不会把所有逻辑堆在一个文件里。

## 使用建议

最推荐的使用方式是：

1. 按顺序读 README 和 4 个 Lab；
2. 每完成一个 Lab，就跑对应 checkpoint；
3. 自己手工画状态图、模块图、数据流；
4. 再回头看 dated docs 做旁读；
5. 最后再尝试设计一个小扩展练习。

如果你照这个顺序走，你学到的不只是这个项目本身，还会学到：

- 一个真实 Web + Python + 视频分析项目是怎么拆层的；
- 为什么“契约”和“状态机”思维在 Web 项目里同样重要；
- 怎样从“看得懂”走到“自己能做出来”。
