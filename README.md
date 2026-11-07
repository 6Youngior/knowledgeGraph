# FinGraph

知识图谱课程期中项目，选题为“股票量化情报——多源市场信息融合与投资研究系统”。

当前研究 AI 产业事件与上市公司的关联。系统把模型发布、硬件适配、云服务接入、公司及上市资料组织为知识图谱，用于查询关联证券、查看原文、按公开日期回看关系，并比较事件后的行情。

## 演示

关系查询、适配公告入图、历史日期筛选及研究简报导出，时长 2 分 12 秒。

https://github.com/user-attachments/assets/ec6aabb3-9543-4a88-8c19-6920ac20c110

## 数据范围

| 内容 | 当前范围 |
|---|---|
| 模型主题 | DeepSeek-R1、Qwen3、GLM-5、MiniMax-M2.5 |
| 图谱 | 59 个实体、85 条关系、10 个事件、8 只证券 |
| 文本来源 | 41 条：33 条官方、公司及交易所资料，8 条媒体报道 |
| 行情 | 8 只股票与恒生指数、科创50，10 条序列、2448 行日线 |
| 时间 | 主要产业事件为 2025.01—2026.02；行情为 2024.12—2026.03 |

详细来源、证券清单和日期说明见 [data/README.md](data/README.md)。初始图谱由人工整理并核对来源；新资料使用 LLM 抽取，经过类型、实体和引用检查后预览入图。

## 运行

Python 3.11 环境下：

```powershell
python -m pip install -r code/requirements-lock.txt
python code/app.py
```

打开 <http://127.0.0.1:8000>。仓库包含已构建的前端；本机也可直接运行 `./start.ps1`。

重新构建前端需要 Node.js：

```powershell
cd visualization
npm ci
npm run build
```

实时抽取支持兼容 OpenAI 的 API，将 `.env.example` 复制为 `.env` 后填写模型配置。也可使用本机已登录的 OpenCode。未配置模型时，可用界面中明确标注的回放样例演示更新。

## 主要操作

1. 选择 GLM-5 发布事件，查看智谱和阿里巴巴的不同关联路径，点击关系查看来源与原句。
2. 选择历史日期，检查哪些关系在当时已有资料支持。
3. 导入 MTT S5000 适配公告中暂未录入的事实，预览后入图；GLM-5 的关联证券由 2 只变为 3 只，新增摩尔线程。
4. 查看证券与基准的同窗口行情，下载包含关系和来源的研究简报。

关系查询区分模型研发、硬件适配与云服务接入，行业分类不用于推导合作。行情用于描述性比较，未进行因果识别。构建方法见 [docs/METHOD.md](docs/METHOD.md)。

## 汇报与演示

- [汇报 PDF](docs/presentation/FinGraph-期中汇报.pdf)
- [Beamer 源码与编译说明](docs/presentation/README.md)
- [讲稿与现场操作顺序](docs/presentation/TALK.md)
- [下载演示录像](visualization/FinGraph-demo.mp4)

汇报依次介绍选题、数据范围、图谱构建、阶段结果与后续计划。使用复旦大学开源 Beamer 主题，主题及依赖来源见 [ATTRIBUTIONS.md](ATTRIBUTIONS.md)。

## 重建与检查

```powershell
python data/build_dataset.py          # 从随附原始行情离线重建
python code/audit_data.py
python -m unittest discover -s code -p 'test_*.py' -v
python code/validate_demo.py          # API 检查，使用回放
```

图表、浏览器检查和录屏另需 `code/requirements-dev.txt`。实时抽取核对可运行 `python code/evaluate_extraction.py`；当前 6 段文本的预实验与局限见 [docs/EXTRACTION_PILOT.md](docs/EXTRACTION_PILOT.md)。检查记录见 [docs/VALIDATION.md](docs/VALIDATION.md)。

| 目录 | 内容 |
|---|---|
| `code/` | 图谱、抽取、查询、行情及 API，验证与导出脚本 |
| `data/` | 事实、来源摘录、抽取样例、行情原始响应与 CSV |
| `visualization/` | React/React Flow/ECharts 前端、构建产物及录像 |
| `docs/presentation/` | Beamer 源码、PDF、图表、主题及讲稿 |
| `docs/results/` | 抽取输出、数据审计和功能检查结果 |
