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

构建结果由 FastAPI 提供，默认端口 `8017`。`/web` 将最近研究的事件传给页面，例如 `/?event=event%3Aglm5-release`。

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

输入格式包括财务、主营、行情、指数 CSV，披露 JSONL、来源目录和采集 manifest，具体字段及合成输入见 `code/test_finance.py`。导入验证日期、单位、重复记录和披露文件哈希，输出按固定顺序生成。批量金融采集工具仍待整理，不将本地采集缓存当成发布依赖。

## 时间与实验

MCP 会话绑定一个研究日期，模型不能在工具参数中改写它。对没有历史归档的网页，当前正文的观察日期晚于截止日时，正文和关联证据不会返回。金融指标与复权行情也按快照可用日期过滤。

现有资料的正文版本主要采集于 2026 年 11 月，早期历史查询可能没有可用证据。Web 原型的资料日期筛选与完整历史预测是不同功能；终端的 `/time`、历史会话隔离及结果验证页面尚未发布。

后续实验共用模型、原始资料、研究时点及相近预算，分别评估普通 Agent、RAG Agent 与图谱增强 Agent。问答正确性、证据支持、抽取质量及预测结果分别报告，不以功能测试数代替模型效果。
