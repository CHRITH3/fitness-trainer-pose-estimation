# 移植到 `trampolin_frontend_demo` 的建议

## 1. 页面路由与标签切换

- `/`：实时裁判页面；
- `/video_analysis`：离线视频分析页面；
- 两个页面的头部统一加入标签导航：
  - `实时裁判` → `/`
  - `离线视频分析` → `/video_analysis`

## 2. 保持原交互脚本需要的 ID，不重写业务主链路

原 `video_analysis.js` 已读取以下元素并绑定上传、轮询、标定和 LLM 流式事件，因此正式移植中建议保留 ID：

- 视频：`video-input`、`browse-btn`、`video-player`、`analysis-canvas`、`video-container`
- 控制：`play-btn`、`analyze-btn`、`stop-analysis-btn`、`reset-btn`
- 标定：`corner-marking-step`、`add-calibration-frame`、`delete-calibration`、`start-trampoline-analysis`、`calibration-list`、`corner-count`、`reset-corners`、`confirm-corners`、`keyframe-list`
- LLM：`llm-section`、`llm-btn`、`llm-streaming`、`llm-streaming-text`、`llm-cards`、`llm-toggle-raw`

建议只把这些 DOM 元素移动进新布局，并写一份新的 `video_analysis_redesign.css` 覆盖样式，而不是第一步就重构现有业务脚本。

## 3. 标定区域和动作序列区域复用一个工作区

新增外层容器：

```html
<section class="workflow-panel">
  <div id="corner-marking-step">...</div>
  <div id="sequence-step" class="hidden">...</div>
</section>
```

状态切换建议：

- 视频上传后：显示 `corner-marking-step`；
- 开始分析后：可显示处理中占位；
- 分析完成后：隐藏 `corner-marking-step`，显示 `sequence-step`；
- 在 `sequence-step` 顶部永久保留“重新标定”按钮；
- 点击“重新标定”后回到原标定组件，重新提交 `/api/video/trampoline/start` 所需的 calibration 数据。

## 4. 删除“实时统计”，替换为“实时评分”

现有后端 `/api/video/status/<video_id>` 返回了 `reps`、`current_action`、`current_flight_duration_s`、`latest_landing`、`landings` 等字段。新评分卡需要进一步让 `video_processor.py` 输出评分结果，并在 `app.py` 的 `_sync_analysis_from_results()` 和 `get_video_status()` 中透传：

```json
{
  "score": {
    "D": 5.2,
    "E": 17.4,
    "T": 15.86,
    "total": 38.46,
    "deduction_total": 0.7,
    "deductions": [
      {"value": 0.3, "reason": "第4跳落点偏右", "type": "落点"}
    ]
  }
}
```

建议论文/界面中把自动计算的 E 分标注为“视觉量化估计”，避免表述为正式裁判判分替代。

## 5. 复用现有后端接口

界面改版不需要改变主流程接口：

- 上传视频：`POST /api/video/upload`
- 提交标定并开始分析：`POST /api/video/trampoline/start`
- 轮询状态：`GET /api/video/status/<video_id>`
- 获取处理视频：`GET /api/video/processed/<video_id>`
- AI 分析 SSE：`GET /api/video/llm_analysis/<video_id>`

重点是扩展状态响应中的评分字段，而不是重新做一套接口。

## 6. 推荐移植顺序

1. 建立新 HTML 网格布局和头部页面切换；
2. 把原 `video-player` 与 `analysis-canvas` 放入新左侧视频面板；
3. 将原 `corner-marking-step` 移到新的工作区；
4. 复用原标定脚本并验证四角点击、关键帧和开始分析功能；
5. 将原落点图 DOM 移到中上方并验证数据更新；
6. 将 LLM DOM 移到右侧大面板并验证 SSE；
7. 扩展后端评分字段，最后接入 D/E/T 展示和动作序列表。
