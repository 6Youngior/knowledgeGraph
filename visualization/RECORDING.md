# 演示录像

`FinGraph-demo.mp4` 为约 2 分 29 秒的实际操作录屏，1920×1080、25 fps，H.264，无音轨。字幕介绍所执行的操作；回放抽取在界面上明确标注。

录像依次展示 GLM-5 的关联证券与原文、历史日期筛选、适配公告入图、新增摩尔线程路径、行情和研究简报下载，最后查看 DeepSeek-R1 在不同日期的关联变化。

## 重新录制

先启动后端，安装 `code/requirements-dev.txt` 中的依赖，并确保本机可用 Edge 与 ffmpeg。在项目根目录运行：

```powershell
python visualization/record_demo.py
```

脚本在录制前后重置图谱，使用 Playwright 操作界面并保存录像，再用 ffmpeg 转为 MP4。原始 WebM 保留在本机，不提交到 Git 仓库。

视频元数据及检查记录见 [video_validation.json](../docs/results/video_validation.json)。
