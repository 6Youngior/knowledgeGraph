# 开发与验证

## 本地环境

在仓库根目录运行 `fingraph.cmd -Setup`，依赖会安装到 `.venv/` 与 `code/agent/node_modules/`。模型配置放在 `.env`；Pi 的设置、会话和用量数据库放在 `.fingraph/`。这些目录不会进入 Git。

启动器仅加载项目的金融工具和扩展。Pi 包保持原样，通过官方扩展接口定制 FinGraphAgent 界面，未修改依赖中的品牌配置。

当前终端使用 Pi 原生的 OpenCode Go provider。`.env` 中的 `LLM_API_KEY` 在子进程内映射为 `OPENCODE_API_KEY`；`LLM_BASE_URL` 用于 Web 的兼容 API 抽取接口。接入说明见 [OpenCode Go 的 Pi 文档](https://opencode.ai/docs/console/harnesses/pi/)。

```powershell
.\fingraph.cmd -Check
.\fingraph.cmd
```

使用指定的 Python 创建项目环境：

```powershell
.\fingraph.cmd -Setup -Python C:\path\to\python.exe
```

## 检查

以下检查使用本地数据、合成测试数据和本地 HTTP 服务，不调用付费模型：

```powershell
.\.venv\Scripts\python.exe -m unittest discover -s code -p "test_*.py" -v
npm test --prefix code/agent
```

Python 检查包括实际 MCP stdio 连接、图谱证据与时间过滤、财务字段和可复现导入。Node 检查包括 Pi 扩展、事件链接及预算不足时的真实 Pi 请求取消；浏览器打开函数在单元测试中使用替身。

一次真实模型对话可使用：

```powershell
.\fingraph.cmd -Prompt "GLM-5 发布关联哪些上市公司？给出具体关系和来源。"
```

这条命令会消耗模型额度。用量记在 `.fingraph/usage.sqlite`，包括接口报告的 token；请求没有返回用量时保留预留额度。`FINGRAPH_LLM_TEST_TOKEN_LIMIT` 控制项目累计测试上限，每次研究最多进行六轮模型请求。

## 前端

```powershell
npm ci --prefix visualization
npm run build --prefix visualization
```

构建结果由 FastAPI 提供，默认端口 `8017`。默认打开量化研究页；事件图谱保留独立入口及 `/?event=event%3Aglm5-release` 链接。

## Qlib 量化实验

查看仓库内已有排序与回测不需要 Qlib。重新训练时，使用独立的项目内环境，避免将量化依赖加入终端和 API 的基础环境：

```powershell
.\.venv\Scripts\python.exe -m venv .fingraph/quant-env
.\.fingraph\quant-env\Scripts\python.exe -m pip install -r code/requirements-quant.txt -c code/requirements-quant-lock.txt
```

锁定文件记录本次 Windows / Python 3.11 的依赖版本。该环境使用 CPU，模型不调用 LLM。

采集 38 只 A 股的原始、前复权日线和沪深 300：

```powershell
.\.venv\Scripts\python.exe code/collect_prices.py --universe data/universe.json --output .fingraph/market/ai-a-share --start 2021-01-01 --end 2026-11-12
```

采集器最多发起 80 次请求、接收约 40 MB 响应，并记录累计用量；匹配日期、身份和哈希的已有文件可直接复用。使用其他日期范围时选择新的输出目录，以保留旧实验快照。

```powershell
.\.fingraph\quant-env\Scripts\python.exe code/run_quant.py --source .fingraph/market/ai-a-share --output .fingraph/quant/baseline
.\.fingraph\quant-env\Scripts\python.exe -m unittest discover -s code -p "test_quant_data.py" -v
```

运行生成 Qlib 二进制行情、LightGBM 文本模型、预测与回测 CSV，以及 `result.json`。数据适配校验哈希、OHLC、原始与复权日历、成交量单位；测试额外检查停牌日历、价格还原与标签跨段隔离。三组模拟净值均核对实际 Qlib 账户余额。

当前发布的 `data/quant/baseline.json` 是本轮检查后的 `result.json`，`quant_research` MCP 工具及 `/api/quant` 读取同一个文件。重新训练保存在本地，核验后再更新发布文件。区间、结果与实验限制见 [data/quant/](../data/quant/)。

## 金融数据

`data/finance/` 提供五家公司的初始金融样本。`manifest.json` 记录文件哈希、数量、快照日期和单位；原始年报保留官方链接与校验信息，不将 PDF 二进制放入这个数据包。

- 财务指标保留报告期、披露日、采集日和可用日；当前聚合快照不按旧披露日回填历史。
- A 股中报和三季报的收入、利润为累计值。主营构成中的毛利率为小数比例，财务指标中的毛利率为百分比。
- 港股报价使用港币，不代表财务报表也使用港币。样本中阿里巴巴和腾讯的财务金额为人民币。
- 原始披露与聚合指标分别记录，查询时应核对它们对应的报告期。

从标准化采集目录导入：

```powershell
.\.venv\Scripts\python.exe code/import_finance.py --input <采集目录> --output data/finance
```

输入格式包括财务、主营、行情、指数 CSV，披露 JSONL、来源目录和采集 manifest，具体字段及合成输入见 `code/test_finance.py`。导入验证日期、单位、重复记录和披露文件哈希，输出按固定顺序生成。

## 财报采集与知识抽取

`data/universe.json` 定义 40 家公司的研究范围。巨潮采集器只收集 A 股完整年报与中报，保存公告标识、公开日期、原始 PDF、哈希及请求记录。港股语料沿用公司官方报告，当前不由该采集器自动下载。

```powershell
.\.venv\Scripts\python.exe -m pip install -r code/requirements-data.txt
.\.venv\Scripts\python.exe code/collect_disclosures.py --universe data/universe.json --output .fingraph/disclosures --limit 80 --per-kind 1 --delay 0.5
```

全文解析复用 PyMuPDF，按 PDF 页码记录原文；LangChain 的文本切分器生成带页内偏移的片段。默认提取文字，可选 PyMuPDF4LLM Markdown；扫描件尚未加入 OCR。文档、页数和片段分开计数，重复正文只算一份文档。

```powershell
.\.venv\Scripts\python.exe -m pip install -r code/requirements-documents.txt -c code/requirements-lock.txt
.\.venv\Scripts\python.exe code/prepare_documents.py --input .fingraph/disclosures/metadata.jsonl --output .fingraph/corpus/reports --limit 100
.\.venv\Scripts\python.exe code/catalog_documents.py --inputs .fingraph/corpus/reports --output .fingraph/catalog
.\.venv\Scripts\python.exe code/extract_corpus.py plan --inputs .fingraph/corpus/reports --output .fingraph/extraction/plan.json --limit 8
```

以上命令不调用模型。执行下列 `run` 才产生模型用量，串行处理并共用项目 token 账本；已有同一请求的结果可复用。默认遇错停止，`--continue-invalid` 可跳过无效候选，接口错误仍停止。

```powershell
.\.venv\Scripts\python.exe code/extract_corpus.py run --plan .fingraph/extraction/plan.json --output .fingraph/extraction
```

结果先保存在 `results/`，不自动入图。检查原文主语、关系含义和日期后，在审核 JSON 中逐项填写 `file`、文件 `sha256`、`decision`、`reviewer`、`note` 和允许入图的 `relation_ids`。校验引文能定位只是必要条件，不能代替语义审核。

```powershell
.\.venv\Scripts\python.exe code/extract_corpus.py ingest --results .fingraph/extraction/results --review .fingraph/extraction/review.json
```

入图写入本地 `data/runtime/`，重复执行不增加同一事实。MCP 检测图谱和来源文件变化后刷新，`entity_relations` 返回公司、产品或模型的一跳关系及出处。仓库内已发布首轮审核后的 22 条关系证据，其中 1 条补充已有事实，因此新增关系为 21 条。[审核记录](../data/corpus/extraction_review.json)是开发样本记录，没有作为独立测试集评分。

2023 年披露批次沿用同一流程，实际采集的 75 份文件中选取 72 份原始年报、中报，排除 3 份更正版本；与现有资料合并后共 168 份去重文档。首批 8 段历史文本审核采用 29 条关系证据，新增 22 条事实。片段选择优先主营业务章节，并排除风险讨论及财务表中指向该章节的引用，避免关键词较多的无关段落排在前面。

## 时间与实验

MCP 会话绑定一个研究日期，模型不能在工具参数中改写它。对没有历史归档的网页，当前正文的观察日期晚于截止日时，正文和关联证据不会返回。金融指标与复权行情也按快照可用日期过滤。

定期报告已保留固定 PDF 与披露日期，普通网页仍有较多 2026 年 11 月采集的当前版本。模型事件发生时的适配资料、上市确认与行情版本还需补齐；固定 Git 提交时间也不直接作为首次公开时间。Web 原型提供资料日期筛选，终端的 `/time`、历史会话隔离及结果验证页面尚未发布。

后续实验共用模型、原始资料、研究时点及相近预算，分别评估普通 Agent、RAG Agent 与图谱增强 Agent。问答正确性、证据支持、抽取质量及预测结果分别报告，不以功能测试数代替模型效果。
