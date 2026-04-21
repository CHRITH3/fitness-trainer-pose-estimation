# Lab 3：处理流程与算法协作流

## 这个 Lab 的目标

前两个 Lab 你看到的是：

- 用户怎样上传、标定、启动分析；
- 页面怎样驱动前端交互。

这一节要进入后端与算法的核心：

> **标定后的视频，是怎样一步一步变成结构化蹦床分析结果的。**

完成后，你至少应该能解释：

- 为什么要有 `video_processor.py`；
- `TrampolineAnalyzer` 为什么像一个总调度器；
- `JumpDetector`、`BedTracker`、`ActionClassifier`、`overlay` 各自负责什么；
- 为什么这些模块不能简单糊成一个大类。

## 本 Lab 切的是哪条垂直切片

这一节切的是处理主线：

```text
/start 提交成功
-> 处理入口启动
-> 逐帧读取视频
-> 姿态识别 / landmarks
-> 床面跟踪与落点映射
-> 跳次检测
-> 动作分类
-> overlay 绘制
-> JSON 结果写回
```

这条线不是“讲某个算法原理”，而是讲：

- 在真实工程里，这些算法模块怎么协作。

## 先补一个“常量层”视角：`trampoline/config.py`

在进入主处理模块前，建议你顺手看一眼：

- `trampoline/config.py`

这个文件的价值在于，它把很多“阈值、尺寸、判定条件”集中放在一处，例如：

- `MIN_JUMP_FRAMES`
- `MIN_FLIGHT_FRAMES`
- `BED_WIDTH_M`
- `BED_LENGTH_M`

你可以先把它理解成：

- **算法层的可调参数表**

这很值得学习，因为它避免把各种魔法数字直接散落在业务逻辑里。

如果以后要调分析灵敏度，第一反应应该先问：

- 这是流程问题？
- 还是参数问题？

而不是直接去大改主逻辑。

## 够用语法 / 结构提醒：先能读懂 Python 模块是怎么协作的

读这几个 `.py` 文件时，先只认下面几种高频结构：

- 一个 `.py` 文件
  - 可以先理解成一个模块。
- `class TrampolineAnalyzer:`
  - 表示定义一个类。
  - 你可以先把类理解成“带状态的数据结构 + 一组处理方法”。
- `self`
  - 可以先理解成“当前这个对象自己”。
  - 如果你有 C 背景，可以把它类比成“当前实例指针”。
- `def process_video(...):`
  - 定义一个函数。
- 全大写常量名
  - 例如 `MIN_JUMP_FRAMES`、`BED_WIDTH_M`。
  - 通常表示配置值或不希望在运行中随意改动的常量。
- 返回字典 / 列表
  - 很多模块不会直接返回一个“最终 UI”，而是返回结构化数据，供别的层继续消费。

你读 Python 算法层时，先优先看出三件事：

1. 这个模块保存了什么状态；
2. 这个模块输入什么、输出什么；
3. 这个模块是在“做决策”、还是在“做换算”、还是在“做展示”。

## 为什么要有 `video_processor.py`

先看：

- `video_processor.py`

这个文件可以先把它理解成：

- **重任务 worker / 处理子流程入口**

它的特点是：

- 负责真正打开视频；
- 逐帧读取；
- 调用 MediaPipe Pose；
- 调 `TrampolineAnalyzer`；
- 写中间结果和最终结果；
- 可选输出处理后视频。

### 为什么不把这些都塞回 `app.py`

因为 Flask 的路由层更适合做：

- 收请求
- 校验输入
- 返回响应
- 管理状态

而不是去做长时间、重 CPU、逐帧的视频处理。

所以你可以把：

- `app.py`
  - 看成控制层 / 命令入口
- `video_processor.py`
  - 看成后台 worker

这跟嵌入式里“主控发任务给后台处理单元”很像。

## `TrampolineAnalyzer`：算法总调度器

看：

- `trampoline/analyzer.py`

这个类最大的价值，不是它单独算了什么，而是它把多层职责串了起来：

- `JumpDetector`
- `ActionClassifier`
- `BedTracker`（通过注入）
- landing payload 组装
- completed jumps 维护

你可以把它理解成：

- **算法应用层 orchestrator**

它本身不是最底层算法，但它定义了“处理一帧后，系统应该返回什么结构”。

### 它做了哪些关键事

1. 先让 `JumpDetector` 判断当前是 contact / flight，是否发生了 takeoff / landing；
2. 在 takeoff/landing 这些关键事件点上，驱动 `ActionClassifier` 的阶段切换；
3. 在 landing 时把动作和落点补进 jump 结果；
4. 返回一个统一的结果结构，给 `video_processor.py` 和状态接口消费。

## `JumpDetector`：为什么最适合用状态机思路理解

看：

- `trampoline/jump_detector.py`

如果你有 MCU C 背景，这个模块是全项目里最值得用状态机思维理解的部分之一。

它的核心成员包括：

- `phase`
- `jump_count`
- `_flight_start`
- `jumps`
- `current_flight_frames()`
- `current_flight_duration_s()`

### 它在干什么

它不是单纯“读一帧就给一个答案”，而是在做：

- 维护当前运动阶段；
- 看速度变化是否形成 takeoff / landing 事件；
- 在合适的时候确认一跳已经完成；
- 把每跳的帧数和边界记录下来。

所以它更像：

- **事件驱动状态机**

而不是普通数学函数。

### 为什么这很重要

因为“跳次”这种东西本来就不是单帧属性。

它必须依赖：

- 连续帧的变化；
- 当前阶段；
- 过去若干帧积累的速度/位置信息。

## `BedTracker`：为什么它是床面语义的基座

看：

- `trampoline/bed_tracker.py`

这个文件体量很大，但你在这个 Lab 不需要先把所有数学都弄懂。你要先抓住它在系统中的职责：

- 校验和接收标定；
- 维护当前床面四边形；
- 把像素点映射到床面坐标；
- 给 landing 生成结构化 payload。

### 为什么它不能和 `JumpDetector` 混在一起

因为“跳次分割”和“床面坐标映射”是两类不同问题：

- `JumpDetector`
  - 关心时间上的事件：什么时候起跳、什么时候落地；
- `BedTracker`
  - 关心空间上的几何：床面在哪里、脚落在哪。

如果把这两个模块强行揉在一起：

- 一边改跳次逻辑，容易误伤坐标逻辑；
- 一边改床面跟踪，容易影响事件判定层。

这就是为什么它必须独立。

## `ActionClassifier`：动作分类是独立层

看：

- `trampoline/action_classifier.py`

这个模块负责的是：

- 根据 landmarks 的角度关系判断是 Straight / Pike / Tuck / Straddle 等动作。

重点不是背所有阈值，而是理解：

- 它只在合适阶段工作；
- 它本质上是一个“根据几何特征做规则判定”的层；
- 它不负责决定 jump 是否发生。

也就是说：

- `JumpDetector` 决定“是不是一跳”；
- `ActionClassifier` 决定“这一跳是什么动作”。

这是很干净的职责边界。

## `overlay.py`：可视化层不是算法本体

看：

- `trampoline/overlay.py`

这里的 overlay 负责的是：

- 在视频上叠加统计、状态、床面、落点、辅助图形。

它的价值非常大，因为：

- 它能帮助用户理解结果；
- 它也能帮助开发者调试算法。

但你必须记住：

> overlay 是结果表达层，不是核心算法层。

换句话说：

- 如果 overlay 画错了，不等于 jump detector 算错了；
- 如果 overlay 样式变了，不应该改坏算法本身。

## 一跳是怎样穿过整个栈的

你最好用“一跳”来理解整条链路，而不是一次性看所有模块。

一跳大致会这样走：

1. `video_processor.py` 逐帧读取视频；
2. MediaPipe 给出当前 frame 的 landmarks；
3. `BedTracker` 根据当前 frame 更新床面几何；
4. `JumpDetector` 判断当前 phase、速度、事件；
5. 如果在 flight，`ActionClassifier` 累积动作判断；
6. 如果 landing 发生，`TrampolineAnalyzer` 生成一条完整 jump 结果；
7. `overlay.py` 根据当前 stats 和 bed_info 画到视频上；
8. 结果被写进 JSON，供 `/api/video/status` 和前端继续使用。

这条链路一旦讲通，整个算法层就不会再像“神秘黑盒”。

## 学习重点

### 学习重点 1：后端控制层和重处理层必须分开

- `app.py` 控制请求和状态；
- `video_processor.py` 做真正的视频重处理。

### 学习重点 2：算法模块最好按职责拆分

- 检测 jump 的模块
- 分类动作的模块
- 跟踪床面的模块
- 负责展示的模块

这不是“为了优雅”，而是为了避免维护时互相污染。

### 学习重点 3：状态机比单帧判断更重要

对于跳次检测来说，真正关键的是：

- 过去发生了什么；
- 当前处于什么 phase；
- 这次 event 会怎样影响下一步状态。

## MCU C 视角下怎么理解这一层

可以这样类比：

- `video_processor.py`
  - ≈ 后台任务 / 协处理器执行单元
- `TrampolineAnalyzer`
  - ≈ 上层调度器，把多个子模块串起来
- `JumpDetector`
  - ≈ 基于采样流的有限状态机
- `BedTracker`
  - ≈ 校准 + 坐标变换模块
- `ActionClassifier`
  - ≈ 在已知事件窗口内工作的规则判定器
- `overlay`
  - ≈ 调试与显示输出层，像逻辑分析仪/示波器界面

## 动手练习

### 练习 1：画处理层模块图

请你画出这几个模块的箭头关系：

- `app.py`
- `video_processor.py`
- `TrampolineAnalyzer`
- `JumpDetector`
- `ActionClassifier`
- `BedTracker`
- `overlay`

并说明：

- 哪些模块负责决策；
- 哪些模块负责变换；
- 哪些模块负责显示。

### 练习 2：手工追踪“一跳”

请你从 landmarks 输入开始，手工追踪一跳如何变成最终的 jump 记录。

至少写清：

- 谁决定 event；
- 谁决定 action；
- 谁决定 landing payload；
- 谁把它们合成统一结果。

### 练习 3：解释为什么 `BedTracker` 不能并入 `JumpDetector`

试着自己写一段解释，回答：

- 这两个模块分别在解决什么问题；
- 如果合并，会带来什么耦合风险；
- 为什么分开后更容易测试。

## 强制检查点

```bash
python -m pytest tests/test_trampoline.py -v
python -m pytest tests/test_bed_tracker.py -v
python -m pytest tests/test_trampoline_overlay.py -v
```

### 这些检查点分别在保护什么

- `tests/test_trampoline.py`
  - 跳次检测、动作分类、分析主流程是否仍然成立。
- `tests/test_bed_tracker.py`
  - 标定、几何映射、落点 payload、跟踪健壮性是否仍然成立。
- `tests/test_trampoline_overlay.py`
  - 结果叠加层和可视化辅助是否仍然保持约定行为。

## 自检问题

1. 为什么 `video_processor.py` 不应该直接并入 `app.py`？
2. 为什么 `TrampolineAnalyzer` 更像调度器而不是单一算法函数？
3. `JumpDetector` 和 `ActionClassifier` 的职责区别是什么？
4. `BedTracker` 为什么是空间语义的基础模块？
5. 为什么 overlay 不应该和核心算法绑死在一起？
6. 如果你要调试“落点不对”，你会先看哪个模块？为什么？

如果这些问题能答清楚，你就已经真正进入了这个项目的算法骨架层。
