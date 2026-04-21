# Lab 1：最小但不失真的真实主链路

## 这个 Lab 的目标

这个 Lab 不是让你先学一堆语法，而是让你先建立一个**正确的系统骨架认知**。

完成这个 Lab 之后，你至少应该能回答：

- 为什么上传视频后没有立刻开始分析？
- `uploaded_pending_calibration` 是什么状态？
- 为什么还需要 `/api/video/trampoline/start`？
- 为什么页面要去轮询 `/api/video/status/<video_id>`？

如果这些问题回答不清楚，后面所有前端、算法、LLM 的学习都会变成“记文件名”，而不是“理解系统”。

## 本 Lab 切的是哪条真实系统切片

这次只切项目里最核心的一条纵向切片：

```text
用户选择视频
-> 前端调用 /api/video/upload
-> 后端保存视频并返回 uploaded_pending_calibration
-> 用户在页面上完成床面标定
-> 前端调用 /api/video/trampoline/start
-> 后端正式启动处理
-> 前端轮询 /api/video/status/<video_id>
-> 页面根据状态显示进度与结果
```

请注意，这条链路里最容易被初学者忽略的就是中间这一步：

- **待标定状态**

这个项目不是“上传完就开始算”，而是“上传完进入一个必须补全输入信息的中间状态”。

## 先看真实后端入口：`app.py`

优先读这些位置：

- `app.py` 中的 `/video_analysis`
- `app.py` 中的 `/api/video/upload`
- `app.py` 中的 `/api/video/trampoline/start`
- `app.py` 中的 `/api/video/status/<video_id>`
- `app.py` 中的 `TRAMPOLINE_CORNER_ORDER`

你先不要追所有辅助函数，先看主行为。

## 够用语法 / 结构提醒：先把 route 看懂

第一次看 `app.py` 时，你可以先只认下面几种结构：

- `@app.route('/api/video/upload', methods=['POST'])`
  - 这是 Flask 的路由装饰器。
  - 你可以把它理解成：**把下面这个函数注册成某个 URL 的处理入口**。
- `def upload_video():`
  - Python 用 `def` 定义函数。
  - 这里就是“这个接口被打到时，真正执行的处理函数”。
- `request.files` / `request.form`
  - 可以先理解成“从这次 HTTP 请求里取上传文件和表单字段”。
- `return jsonify({...}), 400`
  - `jsonify({...})` 表示把一包字段化数据返回给前端；
  - 后面的 `400` 是 HTTP 状态码，表示这次请求有输入问题。
- `video_analyses[video_id] = {...}`
  - 这表示：用 `video_id` 当键，把当前分析状态存进一个字典。
  - 你可以把它先想成“用编号索引一块状态表”。

你不用一开始把每一行都看懂，但至少要先看出：

- 哪一段是在**收输入**；
- 哪一段是在**改状态**；
- 哪一段是在**回 JSON 给前端**。

### 1. `/api/video/upload` 到底做了什么

这段逻辑并不是“上传视频并开始分析”，而是：

1. 检查有没有上传文件；
2. 检查 `exercise_type` 是否是 `trampoline`；
3. 检查文件大小、视频时长；
4. 保存视频文件；
5. 提取首帧；
6. 在 `video_analyses[video_id]` 里登记一条状态；
7. 把状态设置成：
   - `uploaded_pending_calibration`
8. 把首帧图像、尺寸、角点顺序等信息返回给前端。

也就是说，上传接口的任务不是“算结果”，而是：

> **把系统推进到“待标定、可继续下一步”的状态。**

### 2. 为什么必须有 `uploaded_pending_calibration`

因为后端只拿到视频还不够。

要做蹦床落点和床面相关分析，系统还缺一类输入：

- 床面四角在哪里

这跟嵌入式里很像：

- 你把传感器数据线接好了，设备也上电了；
- 但如果还没有校准参数，数据就不能直接当作有效工程量使用。

所以：

- 视频上传成功 ≠ 可以直接分析
- 上传成功 = 进入“待标定”状态

### 3. `/api/video/trampoline/start` 的职责

这个接口是“**把标定数据正式提交，并触发分析开始**”。

它会做这些事：

- 读取前端提交的标定信息；
- 规范化成内部统一格式；
- 写入 sidecar（角点/标定附属数据）；
- 把状态从待标定推进到 processing；
- 启动后续处理流程。

所以你可以把这两个接口分工理解成：

- `/api/video/upload`
  - 负责“上传 + 建立待标定上下文”
- `/api/video/trampoline/start`
  - 负责“补齐标定输入 + 正式启动处理”

这个拆分很值得学习，因为它让流程更稳定：

- 上传失败和标定失败可以分开处理；
- 前端也能明确知道当前是在“待标定”还是“处理中”。

## 前端怎么进入待标定状态

这一步先只追主线，不深追所有 JS 细节。

你要看：

- `templates/video_analysis.html`
- `static/js/video_analysis.js`
- `static/js/trampoline_calibration_ui.js`
- `static/js/trampoline_calibration_geometry.js`

### 1. 页面上哪些节点属于待标定流程

在 `templates/video_analysis.html` 里重点看这些 `id`：

- `video-container`
- `upload-area`
- `video-player`
- `analysis-canvas`
- `corner-marking-step`
- `add-calibration-frame`
- `confirm-corners`
- `delete-calibration`
- `start-trampoline-analysis`
- `calibration-list`
- `keyframe-list`
- `calibration-status-text`

这些节点不是随便命名的，它们共同组成了“待标定阶段”的前端契约。

### 2. `video_analysis.js` 在这里做什么

这个文件在主链路里主要承担：

- 接收文件；
- 调用 `/api/video/upload`；
- 拿到上传返回结果；
- 把视频页面切进待标定流程；
- 在后续分析启动后开始轮询 `/api/video/status/<video_id>`。

所以这个文件在本 Lab 里是“主流程调度器”。

### 3. `trampoline_calibration_ui.js` 在这里做什么

这个文件可以先把它理解成：

- **待标定状态机控制器**

它管的是：

- 当前草稿是什么；
- 当前选中了哪些角点；
- 标定列表怎么维护；
- 点击“开始分析”时如何把标定 payload 发给后端。

在这个 Lab 里，你不需要把每个函数细节都看懂，但你必须先知道：

- 页面“进入待标定”之后，不是 `video_analysis.js` 一个人在干活；
- 真实系统是由“主流程 JS” + “标定控制器 JS”共同驱动的。

## `/api/video/status/<video_id>` 为什么这么重要

很多初学者容易把这个接口想成“只是拿个进度条数值”。

其实它更重要的作用是：

- 告诉前端当前系统处于什么状态；
- 返回处理中的动态字段；
- 返回最终完成后页面展示所需的数据；
- 让前端不需要一直阻塞等待一次性结果。

你可以把它类比成：

- MCU 程序里周期性读取一个状态寄存器；
- 当前是不是空闲、运行中、出错、完成，都要通过状态读取来驱动 UI 或上层逻辑。

## 学习重点

### 学习重点 1：这个项目不是“单次请求完成一切”的结构

它是典型的**多阶段状态推进型系统**：

- upload
- pending calibration
- start
- processing
- completed / error

### 学习重点 2：待标定状态不是 UI 装饰，而是业务门槛

没有标定，就没有可用的床面坐标系统；
没有床面坐标系统，后续很多分析就没有稳定语义。

### 学习重点 3：接口拆分体现的是职责边界

- upload 负责收视频和建上下文；
- start 负责正式启动；
- status 负责输出运行态与结果态。

这是一种非常典型、非常值得学的工程拆法。

## MCU C 视角下怎么理解这条链路

你可以这样类比：

- `/api/video/upload`
  - ≈ 收到一条“初始化并装载数据”的命令
- `uploaded_pending_calibration`
  - ≈ 设备进入“待校准”状态
- 用户标定
  - ≈ 写入校准参数
- `/api/video/trampoline/start`
  - ≈ 发出“带完整参数正式启动任务”的命令
- `/api/video/status`
  - ≈ 周期性读状态寄存器

如果你从这个角度去看，这套 Web 系统就不会显得那么陌生。

## 动手练习

### 练习 1：手工画状态图

请你自己画出下面这些状态之间的流转：

- idle
- uploaded_pending_calibration
- processing
- completed
- error
- expired（如果你已经看到了过期清理逻辑，也可以补上）

要求你能回答：

- 哪个接口会让状态从 A 走到 B；
- 哪个接口只负责读状态，不负责改状态。

### 练习 2：画出这条主链路的消息流

请你手工画出：

- 浏览器
- Flask 后端
- 处理器 / 子流程

三者之间的消息流。

至少标出：

- upload request
- upload response
- start request
- status polling
- final results

### 练习 3：解释为什么不能把 upload 和 start 合并成一个接口

尝试自己写一段说明，回答：

- 为什么当前设计要分成两个接口；
- 如果合并会带来什么问题；
- 哪些错误处理会变得更难。

## 强制检查点

在继续往下学之前，至少先看懂下面这些测试在保护什么：

```bash
python -m pytest tests/test_app_route_contract.py -v
python -m pytest tests/test_trampoline_api.py -v
python -m pytest tests/test_trampoline_frontend_contract.py -v
node tests/test_trampoline_calibration_ui.mjs
```

### 这些检查点分别在保护什么

- `tests/test_app_route_contract.py`
  - 页面/路由是否还在，保留接口是否还可访问。
- `tests/test_trampoline_api.py`
  - upload、待标定、start、status 这条契约链是否正确。
- `tests/test_trampoline_frontend_contract.py`
  - 页面节点和脚本接线是否还满足标定流程要求。
- `tests/test_trampoline_calibration_ui.mjs`
  - 标定控制器的状态逻辑是否仍然成立。

## 自检问题

如果你已经完成这个 Lab，请试着不用看代码，回答下面这些问题：

1. 为什么 `/api/video/upload` 返回的不是“分析完成”？
2. `uploaded_pending_calibration` 到底代表什么？
3. `/api/video/trampoline/start` 为什么不是多余接口？
4. `/api/video/status/<video_id>` 为什么是主链路的一部分？
5. 如果有人把这个系统讲成“上传后直接分析”，哪里讲错了？
6. `trampoline_calibration_ui.js` 在主链路里扮演什么角色？

如果这 6 个问题里有 2 个以上答不清，建议你把本 Lab 再读一遍，再进入 Lab 2。
