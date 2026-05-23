# 蹦床 AI 裁判系统：离线视频分析 UI 预览

这是独立静态预览包，不需要 Flask、Python、OAK 或 YOLO 环境。

## 打开方法

1. 解压 ZIP；
2. 打开 `trampoline_video_analysis_ui_preview/index.html`；
3. 建议使用 Chrome / Edge 浏览器，浏览器窗口宽度不小于 1280 px。

## 可直接体验的交互

- 顶部“实时裁判 / 离线视频分析”切换入口样式；
- “选择本地视频”：可加载你电脑上的一个视频，仅在本地浏览器展示；
- “进入标定”：将底部主工作区切换为床面标定交互；
- 直接在左侧视频画面点击四个角点，或点击“加载演示角点”；
- “保存并开始分析”：演示标定完成后切换成动作序列；
- “重新标定”：从动作序列返回标定界面；
- “演示分析结果”：快速预览评分、落点、腾空时间曲线和 LLM 面板；
- “导出报告 / 保存结果”：导出演示 JSON。

## 文件结构

```text
trampoline_video_analysis_ui_preview/
├── index.html
├── README.md
├── MIGRATION_GUIDE.md
└── static/
    ├── css/video_analysis_redesign.css
    └── js/video_analysis_redesign.js
```

本预览包不修改你的 GitHub 仓库代码，用于先确认布局与交互逻辑。
