# 演示录像

[FinGraph-demo.mp4](FinGraph-demo.mp4) 为 2 分 12 秒的真实界面操作录屏，1920×1080、25 fps、H.264，无音轨。抽取演示明确选择“样例回放”，使用已保存的模型输出。

录像分为四段：

1. 查询 GLM-5 的关联证券，打开研发关系的原文与来源。
2. 导入 MTT S5000 适配公告，对齐已有实体，核对后入图；证券由两只增至三只。
3. 查看智谱与恒生指数的同窗口行情，导出带引用的研究简报。
4. 查看 DeepSeek-R1 在不同历史日期的资料积累。

[封面](FinGraph-demo-cover.png) 取自视频首帧。录制脚本等待页面与图谱完整显示，再截去浏览器初始化片段；首帧会与就绪页面截图比较。

## 重新录制

启动后端，安装 code/requirements-dev.txt 中的依赖，并确保 Edge 与 ffmpeg 可用。在项目根目录运行：

    python visualization/record_demo.py

脚本操作实际页面，仅在底部加入字幕和鼠标指针；录制前后恢复初始图谱。MP4 与本机 WebM 使用相同起点，WebM 不提交到 Git。

检查记录见 [video_validation.json](../docs/results/video_validation.json)。
