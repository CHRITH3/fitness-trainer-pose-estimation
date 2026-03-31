# Trampoline Demo Script

## 演示前准备

1. 安装依赖: `python -m pip install -r requirements-dev.txt`
2. 生成或刷新样例产物: `bash scripts/check_v1_acceptance.sh samples/tra_demo/sample01.mp4`
3. 启动服务: `python app.py`

## 演示流程

1. 打开 `http://127.0.0.1:5000/trampoline`。
2. 说明这是单人 TRA demo，不是官方评分系统。
3. 选择已存在的 `sample01` 分析，或重新上传 `sample01.mp4`。
4. 展示标定矩形、自动分段、时间轴块和 Phase 3 label 详情。
5. 切到 Phase 4 summary panel，说明：
   - landing heatmap
   - center deviation / zone summary
   - routine flags `final_out_bounce` / `final_stable_3s`
6. 点击 `Download Export Bundle`，展示 zip 内的 `analysis.json`、`summary.md`、`landing.json`、`overlays/`。

## 运行兜底

- CLI analyze: `python -m trampoline.cli analyze --video samples/tra_demo/sample01.mp4 --out artifacts/trampoline/sample01 --landmarks-only`
- CLI segment: `python -m trampoline.cli segment --analysis-dir artifacts/trampoline/sample01`
- CLI export: `python -m trampoline.cli export --analysis-dir artifacts/trampoline/sample01`

## 限制说明

- 仅支持单人 TRA demo。
- 不输出 D-score、ToF、SYN、TUM、DMT。
- 落点热图和 flags 只是辅助判读，不是官方裁判结果。
