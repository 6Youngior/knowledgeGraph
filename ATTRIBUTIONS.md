# 来源与开源复用

## 汇报主题

实际采用 [sonnyhcl/beamerthemefdu](https://github.com/sonnyhcl/beamerthemefdu)，一个非官方的复旦大学 Beamer 主题，Apache-2.0。原始 `.sty`、许可证和上游说明均保留在 `docs/presentation/vendor-fdu/`，校名与校徽矢量资源位于 `resources/`。详情见 [THEME_NOTICE.md](docs/presentation/THEME_NOTICE.md)。

## 主要组件

| 组件 | 用途 | 许可证 |
|---|---|---|
| React / React DOM 18.3.1 | 界面与交互 | MIT |
| Apache ECharts 5.6.0 | 图谱与事件行情 | Apache-2.0 |
| [Dagre](https://github.com/dagrejs/dagre) | 有向图的层次布局 | MIT |
| ZRender 5.6.1 | 图形渲染 | BSD-3-Clause |
| Lucide React 0.468.0 | 图标 | ISC |
| TanStack React Query | 请求缓存与状态刷新 | MIT |
| Vite 6.4.5 | 前端构建 | MIT |
| NetworkX 3.6.1 | 有向属性图与索引 | BSD-3-Clause |
| FastAPI / Pydantic / Uvicorn | 类型校验与本地 API | 以各包许可证为准 |

前端已打包依赖的许可证副本保存在 `visualization/licenses/`；Python 的实际安装版本保存在 `code/requirements-lock.txt`。

## 数据与素材

事实来源、提供方、原始链接、日期精度与短摘录均登记在 `data/sources.json` 和 `data/README.md`。行情缓存源于腾讯财经公开日线接口，原始响应及复权口径保留。事实与市场数据属于各自发布方，本项目记录来源并用于课程研究展示。

Demo 截图来自本项目真实运行界面；Schema、架构和路径图由本项目绘制。

## 设计参考

图谱布局参考 [React Flow 官方 Dagre 示例](https://reactflow.dev/examples/layout/dagre)，在 ECharts 中使用 Dagre 排列实体。界面信息组织参考 [OpenBB Design System](https://github.com/OpenBB-finance/design-system)。行情汇报图由 Matplotlib 从随附缓存生成。
