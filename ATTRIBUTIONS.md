# 来源与开源复用

## 汇报主题

实际采用 [sonnyhcl/beamerthemefdu](https://github.com/sonnyhcl/beamerthemefdu)，一个非官方的复旦大学 Beamer 主题，Apache-2.0。原始 `.sty`、许可证和上游说明均保留在 `docs/presentation/vendor-fdu/`，校名与校徽矢量资源位于 `resources/`。详情见 [THEME_NOTICE.md](docs/presentation/THEME_NOTICE.md)。

## 主要组件

| 组件 | 用途 | 许可证 |
|---|---|---|
| React / React DOM 18.3.1 | 界面与交互 | MIT |
| React Flow 12.12.1 | 图谱节点、连线与视图交互 | MIT |
| Apache ECharts 6.1.0 | 事件行情图 | Apache-2.0 |
| [Dagre](https://github.com/dagrejs/dagre) | 有向图的层次布局 | MIT |
| ZRender 6.1.0 | 图形渲染 | BSD-3-Clause |
| Lucide React 0.468.0 | 图标 | ISC |
| TanStack React Query | 请求缓存与状态刷新 | MIT |
| Vite 6.4.5 | 前端构建 | MIT |
| NetworkX 3.6.1 | 有向属性图与索引 | BSD-3-Clause |
| [Pi 1.5.2](https://github.com/earendil-works/pi) | Agent 会话、终端与 MCP 客户端 | MIT |
| [MCP Python SDK 1.30.0](https://github.com/modelcontextprotocol/python-sdk) | 金融研究 stdio 服务 | MIT |
| [open 10.2.0](https://github.com/sindresorhus/open) | 从终端打开研究网页 | MIT |
| PyMuPDF 1.27.2.3 / PyMuPDF4LLM 0.2.9 | 离线解析财报 PDF 与页码 | AGPL-3.0 或 Artifex 商业许可 |
| LangChain Text Splitters 1.1.3 | 按中文段落切分财报原文 | MIT |
| FastAPI / Pydantic / Uvicorn | 类型校验与本地 API | 以各包许可证为准 |

前端已打包依赖的许可证副本保存在 `visualization/licenses/`；Python 的实际安装版本保存在 `code/requirements-lock.txt`。

终端金色主题基于 Pi 的 dark theme 调整，沿用 MIT 许可；主题与许可说明位于 `code/agent/themes/`。

## 数据与素材

事实来源、提供方、原始链接、日期精度与短摘录均登记在 `data/sources.json` 和 `data/README.md`。行情缓存源于腾讯财经公开日线接口，原始响应及复权方式保留。事实与市场数据属于各自发布方，本项目记录来源并用于课程研究展示。

新增金融样本记录在 `data/finance/`：结构化财务、主营构成和日线通过 [AKShare](https://github.com/akfamily/akshare) 访问东方财富公开数据；年报来源为巨潮资讯及公司投资者关系网站。来源、访问工具版本、快照日期和适用范围见该目录的 `sources.json`、`disclosures.json` 和 `manifest.json`。AKShare 的开源许可不替代数据提供方的条款。

Demo 截图来自本项目真实运行界面；Schema、架构和路径图由本项目绘制。

## 设计参考

图谱布局参考 [React Flow 官方 Dagre 示例](https://reactflow.dev/examples/layout/dagre)，使用 React Flow 显示节点与连线，Dagre 排列实体。界面信息组织参考 [OpenBB Design System](https://github.com/OpenBB-finance/design-system)。行情汇报图由 Matplotlib 从随附缓存生成。
