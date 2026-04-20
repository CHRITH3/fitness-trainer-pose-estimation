# 🤸 蹦床视频分析项目

一个基于 Flask + MediaPipe + OpenCV 的蹦床视频分析工具，当前聚焦于：
- 上传蹦床视频
- 床面关键帧标定
- 跳次分割与动作识别
- 处理后视频回放
- AI 文本分析

> 当前仓库围绕 `/video_analysis` 主链路展开，同时保留 `/`、`/dashboard`、`/profile` 作为后续页面入口，便于继续扩展蹦床训练相关能力。

---

## 当前能力

### 1. 蹦床视频分析主链路
- 上传蹦床视频并提取首帧
- 在分析前完成床面四角标定 / 关键帧补标
- 检测跳次、识别动作类型
- 输出处理后视频与诊断结果
- 对已完成分析的视频发起 AI 解读

### 2. 当前页面入口
- `/`：蹦床首页 / 实时页预留壳层
- `/dashboard`：蹦床看板占位页，保留图表容器
- `/profile`：蹦床训练档案占位页
- `/video_analysis`：蹦床视频分析主入口

### 3. 当前技术结构
- Flask 后端负责页面与 API
- `video_processor.py` 负责独立进程视频分析
- `trampoline/` 目录承载床面跟踪、跳次检测、动作识别、覆盖层与 LLM 服务
- 前端为原生 HTML/CSS/JS，无额外前端框架依赖

---

## 快速开始

### 1. 安装依赖

```bash
python -m venv venv
source venv/bin/activate  # Linux / Mac
# 或 venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

### 2. 启动项目

```bash
python app.py
```

### 3. 打开页面

访问：

```text
http://127.0.0.1:5000
```

---

## 主要路由

### 页面路由

| 路由 | 说明 |
|---|---|
| `/` | 蹦床首页 / 实时页预留壳层 |
| `/dashboard` | 蹦床仪表盘占位页 |
| `/profile` | 蹦床训练档案占位页 |
| `/video_analysis` | 蹦床视频分析主入口 |

### API 路由

| 路由 | 方法 | 说明 |
|---|---|---|
| `/api/video/upload` | POST | 上传蹦床视频；仅接受 `exercise_type=trampoline` |
| `/api/video/trampoline/start` | POST | 提交床面标定并启动分析 |
| `/api/video/status/<video_id>` | GET | 获取分析进度与结果摘要 |
| `/api/video/processed/<video_id>` | GET | 获取处理后视频 |
| `/api/video/llm_analysis/<video_id>` | GET | 对已完成分析的视频发起 AI SSE 分析 |

---

## 目录结构（当前重点）

```text
project-root/
├── app.py
├── video_processor.py
├── trampoline/
│   ├── analyzer.py
│   ├── bed_tracker.py
│   ├── jump_detector.py
│   ├── action_classifier.py
│   ├── overlay.py
│   ├── llm_service.py
│   └── docs/
├── templates/
│   ├── index.html
│   ├── dashboard.html
│   ├── profile.html
│   └── video_analysis.html
├── static/
│   ├── css/
│   └── js/
└── tests/
```

---

## 测试与验证

常用命令：

```bash
python -m pytest tests/test_app_route_contract.py -v
python -m pytest tests/test_trampoline_frontend_contract.py -v
python -m pytest tests/test_trampoline_api.py -v
python -m pytest tests/test_bed_tracker.py -v
python -m pytest tests/test_trampoline_overlay.py -v
python -m pytest tests/test_trampoline.py -v
python -m pytest tests/test_llm_service.py -v
node tests/test_trampoline_calibration_geometry.mjs
node tests/test_trampoline_calibration_ui.mjs
```

---

## AI 分析配置

若要启用 `/api/video/llm_analysis/<video_id>`，请设置：

```bash
export QWEN_API_KEY=your_key
# 或使用 DASHSCOPE_API_KEY
```

可选模型环境变量：

```bash
export QWEN_FAST_MODEL=qwen-plus
export QWEN_MODEL=qwen3.6-plus-2026-04-02
```

---

## 当前状态说明

- 当前可直接使用的重点是蹦床视频上传、标定、分析与 AI 解读主链路
- `/`、`/dashboard`、`/profile` 当前主要承担后续扩展入口与页面结构预留作用
- dashboard / profile 中保留的图表与卡片布局可继续承接训练数据、落点统计与档案信息
