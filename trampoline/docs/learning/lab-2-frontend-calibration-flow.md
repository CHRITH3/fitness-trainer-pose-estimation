# Lab 2：前端标定与页面交互流

## 这个 Lab 的目标

在 Lab 1 里，你已经知道了系统主链路必须经过：

- upload
- pending calibration
- start
- status polling

这个 Lab 的目标，是让你进一步看清：

> **浏览器这一侧到底是怎么把这条链路驱动起来的。**

完成后，你至少应该能解释：

- 模板里的 `id` 为什么是一种契约；
- `video_analysis.js`、`trampoline_calibration_ui.js`、`trampoline_calibration_geometry.js` 为什么要分开；
- 一个按钮点击是怎样一路变成 API 请求的；
- 为什么“纯逻辑 helper”和“直接操作 DOM 的 controller”最好拆开。

## 本 Lab 切的是哪条垂直切片

本 Lab 切的不是“所有前端知识”，而是这一段真实切片：

```text
页面结构
-> 用户交互事件
-> 标定 UI 状态机
-> 几何坐标换算
-> API 请求
-> 状态轮询
-> 页面更新
```

也就是说，这一节不讲完整算法，而是讲：

- 页面如何把用户动作变成正确的数据流。

## 先看模板：`templates/video_analysis.html`

这份模板里有很多节点，但你不用全背。你只需要先抓住“主链路相关节点”。

重点看这些：

- 上传相关
  - `upload-area`
  - `video-input`
  - `browse-btn`
- 视频与标定层
  - `video-container`
  - `video-player`
  - `analysis-canvas`
  - `corner-marking-step`
- 标定控制
  - `add-calibration-frame`
  - `confirm-corners`
  - `delete-calibration`
  - `start-trampoline-analysis`
  - `calibration-list`
  - `keyframe-list`
- 状态与展示
  - `progress-fill`
  - `progress-text`
  - `stat-reps`
  - `stat-flight-time`
  - `stat-action`
  - `stat-landing`
  - `landing-map`
  - `report-content`
  - `feedback-log`
  - `llm-btn`
  - `llm-streaming-text`

## 够用语法 / 结构提醒：先能读懂 HTML、CSS、JS 是怎么连起来的

这里你只需要先掌握“够用”的几种写法：

- HTML 里的 `id`
  - 主要给 JS 精确定位节点用。
  - 例如 `id="start-trampoline-analysis"` 就像一个唯一接口名。
- HTML 里的 `class`
  - 主要给 CSS 设样式用。
  - 例如一个页面里可以有很多个 `class="stat-card"`。
- CSS 文件
  - `templates/video_analysis.html` 会引入 `static/css/style.css` 和 `static/css/video_analysis.css`。
  - 你可以先理解成：HTML 负责摆零件，CSS 负责这些零件看起来像什么。
- `document.getElementById(...)`
  - 表示“把页面里的某个节点抓出来”。
- `addEventListener('click', handler)`
  - 表示“这个按钮被点击时，执行这个回调函数”。
- `const` 和 `let`
  - `const` 更像“这名字后面不换绑”；
  - `let` 表示后面可能重新赋值。
- `async function ...` + `await fetch(...)`
  - 可以先理解成：发一个网络请求，并在代码阅读上“看起来像顺序等待结果”。
- `a?.b`
  - 安全取值，`a` 不存在时不要直接报错。
- `x ?? y`
  - 如果 `x` 为空，就退回用 `y`。

你读前端文件时，先反复问自己三个问题：

1. 这段代码是在抓 DOM，还是在改数据？
2. 这段代码是在绑定事件，还是在发请求？
3. 这段代码是在做纯逻辑判断，还是在直接改页面？

### 为什么要先看 `id`

因为在这个项目里，HTML 里的 `id` 不只是“起个名字”，它其实是一种接线点。

JS 代码会通过 `getElementById(...)` 去抓这些节点。

一旦名字对不上：

- 按钮点了没反应；
- 某块面板不更新；
- 整个流程直接断掉。

这就是为什么模板里的 `id` 本身就是一种契约。

## 主流程调度器：`static/js/video_analysis.js`

这个文件很大，但在本 Lab 里你要先用“职责”去看它，而不是用“行数”去吓自己。

它主要负责这些事：

1. 找到页面上的关键 DOM 节点；
2. 绑定上传、播放、重置、AI 分析等主按钮；
3. 发起 `/api/video/upload`；
4. 收到上传返回后进入待标定态；
5. 在分析开始后轮询 `/api/video/status/<video_id>`；
6. 把结果渲染到统计区、报告区、落点图、反馈区、AI 区。

所以你可以把它理解成：

- **页面总调度器**

它不该独自承担所有细节计算，不然就会变成一个越来越难维护的大文件。

## 标定控制器：`static/js/trampoline_calibration_ui.js`

这个文件的价值，在于它把“待标定阶段”从总流程里拆了出来。

它主要管：

- 进入 pending calibration 的初始化；
- 当前草稿帧；
- 四角点选择与重置；
- 当前标定的保存/删除；
- calibration 列表与 keyframe 列表；
- 点击“开始分析”时如何打包 payload 并发到 `/api/video/trampoline/start`。

### 为什么要拆出这个文件

因为“标定”本身就是一段小状态机：

- 当前是不是待标定；
- 当前是不是正在编辑某个关键帧；
- 当前已经点了几个角点；
- 当前草稿是不是可保存；
- 当前是否允许开始分析。

如果这些状态全塞回 `video_analysis.js`，主流程文件很快就会变得：

- 谁都能改；
- 变量相互污染；
- 出问题时难定位。

## 几何换算模块：`static/js/trampoline_calibration_geometry.js`

这个文件里没有“业务主流程”，它更像一组几何工具：

- `computeContainRect(...)`
- `displayToImagePoint(...)`
- `imageToDisplayPoint(...)`
- `frameIndexFromTime(...)`
- `buildCalibrationPayload(...)`

### 为什么要单独拆这个文件

因为这些逻辑有两个特点：

1. 它们偏数学/坐标换算；
2. 它们本身可以做成纯逻辑函数，比较适合单测。

例如：

- 页面上点击一个点，不等于视频原图中的像素点；
- 因为页面显示时可能有缩放、contain、黑边；
- 所以必须先算出“真实视频内容区”，再做坐标映射。

这跟 MCU 里“ADC 原始值 → 工程量”很像。

你不能直接把原始读数当物理量，必须先过一层换算函数。

## 纯逻辑 helper：`static/js/video_analysis_helpers.js`

这个文件主要体现的是：

- 有些页面逻辑，不该和 DOM 紧耦合；
- 如果能拆成纯逻辑 helper，就更容易测试，也更不容易在 UI 改版时被带崩。

最典型的是：

- `resolveCompactStats(...)`

它做的不是“画界面”，而是：

- 根据当前状态、历史 jump、最新 landing，决定统计区应该显示什么。

例如：

- 当前如果正在 flight，就优先显示实时数据；
- 如果当前没有有效实时值，就回退到最近一次有效跳的数据。

### 为什么这很重要

因为它能避免 UI 到处写一堆重复判断：

- 有值就显示 A
- 没值就显示 B
- 如果 phase 不是 flight 就显示 C

把这类规则收敛成纯逻辑，是很典型的“减耦合”做法。

## 前端状态机是怎样被驱动的

把这几个文件放在一起，你就能看到一个更清楚的分工：

- `templates/video_analysis.html`
  - 页面结构和接线点
- `video_analysis.js`
  - 页面总调度器
- `trampoline_calibration_ui.js`
  - 标定流程控制器
- `trampoline_calibration_geometry.js`
  - 几何换算工具箱
- `video_analysis_helpers.js`
  - 可复用的纯逻辑 helper

这套分工的好处是：

- 主流程不需要知道所有细节；
- 标定逻辑不需要掺进所有展示逻辑；
- 几何函数不需要依赖 DOM；
- 辅助显示规则可以直接用单测锁住。

## 学习重点

### 学习重点 1：HTML 的 `id` 是前端契约的一部分

前端不是“写个页面就行”，而是：

- 模板结构
- JS 获取节点
- 事件绑定
- 数据更新

这四件事必须对得上。

### 学习重点 2：总流程与子状态机分开，是为了降低复杂度

- `video_analysis.js` 负责全局流程；
- `trampoline_calibration_ui.js` 负责标定子流程；
- `trampoline_calibration_geometry.js` 负责坐标换算；
- `video_analysis_helpers.js` 负责纯逻辑规则。

这就是前端版的“模块边界”。

### 学习重点 3：能纯逻辑化的规则，尽量纯逻辑化

因为纯逻辑：

- 更容易测；
- 更少副作用；
- 更容易复用；
- UI 改版时更稳。

## MCU C 视角下怎么理解前端这层

可以这样类比：

- DOM `id`
  - ≈ 板子上的引脚编号 / 设备端口名
- `addEventListener(...)`
  - ≈ 注册中断或回调
- `video_analysis.js`
  - ≈ 应用层总控状态机
- `trampoline_calibration_ui.js`
  - ≈ 某个外设子模块的局部控制器
- `trampoline_calibration_geometry.js`
  - ≈ 数据换算函数库
- `video_analysis_helpers.js`
  - ≈ 不碰硬件寄存器、只处理规则的纯逻辑模块

如果你这样看，前端就不再只是“点网页”，而是一个事件驱动系统。

## 动手练习

### 练习 1：画一个前端模块职责图

请你自己画出这几个文件之间的关系：

- `templates/video_analysis.html`
- `video_analysis.js`
- `trampoline_calibration_ui.js`
- `trampoline_calibration_geometry.js`
- `video_analysis_helpers.js`

要求你能说出：

- 谁负责 DOM；
- 谁负责坐标；
- 谁负责状态；
- 谁负责纯逻辑。

### 练习 2：追踪一个按钮点击

从页面上的：

- `add-calibration-frame`

开始，追踪：

- 点击之后哪个 JS 函数被调用；
- 它会改哪些状态；
- 它为什么需要当前视频帧；
- 它后面怎样影响 UI。

### 练习 3：追踪一个角点点击的坐标流

请你追踪从鼠标点击开始，到最终变成图像坐标这一路数据：

- 浏览器显示坐标
- contain rect
- image point

并写一句话解释：

- 为什么不能直接把鼠标点的位置当原图坐标。

## 强制检查点

```bash
python -m pytest tests/test_trampoline_frontend_contract.py -v
node tests/test_trampoline_calibration_geometry.mjs
node tests/test_trampoline_calibration_ui.mjs
node tests/test_video_analysis_ui_helpers.mjs
```

### 这些检查点分别在保护什么

- `tests/test_trampoline_frontend_contract.py`
  - 页面结构、脚本加载和关键 `id` 是否仍然成立。
- `tests/test_trampoline_calibration_geometry.mjs`
  - 几何换算函数是否仍然正确。
- `tests/test_trampoline_calibration_ui.mjs`
  - 标定 UI 控制器的状态机是否仍然合理。
- `tests/test_video_analysis_ui_helpers.mjs`
  - 统计区 fallback 等纯逻辑规则是否仍然成立。

## 自检问题

1. 为什么 HTML `id` 可以看成一种契约？
2. 为什么 `video_analysis.js` 不应该把所有标定逻辑都包进去？
3. `trampoline_calibration_geometry.js` 为什么适合单独做成工具模块？
4. `video_analysis_helpers.js` 和 `trampoline_calibration_ui.js` 最大的区别是什么？
5. 为什么“纯逻辑 helper”通常更容易测试？
6. 如果一个按钮点了没反应，你会先查模板、事件绑定，还是先查算法？为什么？

如果这些问题里有明显答不清的地方，建议你先回头再看一遍文件职责图，再进入 Lab 3。
