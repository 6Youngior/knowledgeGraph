# 历史资料版本

本目录记录 DeepSeek-R1、Qwen3、GLM-5 的模型卡版本，以及智谱的港交所招股书和业绩公告。共 8 个来源地址、7 份独立正文；DeepSeek 的 GitHub 与 Hugging Face 版本正文相同。

| 文件 | 内容 |
|---|---|
| `sources.jsonl` | 来源、固定版本、日期依据与内容哈希 |
| `bodies.jsonl` | 独立正文及其对应的来源地址 |
| `manifest.json` | 数量和目录校验信息 |

固定提交能确认正文版本，但提交时间不等于首次公开时间。Git/Hugging Face 记录的 `available_at` 暂取版本日与官方发布日中的较晚者，标为 `release_date_assumption`，`eligible_for_strict_replay=false`。这些版本尚不能直接用于严格历史预测，也不声明日内公开时刻。

港交所公告按自身披露日期使用：2025-12-30 招股书中的上市日期是预期安排；2026-03-31 公告对实际上市的确认只能从后者披露日起使用，不能提前回填。

本目录只发布元数据。正文与 PDF 保存在本地缓存；历史原始行情仍需另行整理。
