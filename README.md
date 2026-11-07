# FinGraph

本项目是知识图谱课程期中项目，当前覆盖大模型行业相关股票。从模型发布、硬件适配、云服务接入等事件出发，将模型、产品、公司与证券连接起来，查询关联股票、产业角色及原文依据。

当前选取 DeepSeek-R1、Qwen3、GLM-5、MiniMax-M2.5 四个模型主题，覆盖智谱、MiniMax、阿里巴巴、腾讯控股、百度集团、中国电信、海光信息、摩尔线程，共 8 只 A 股、港股证券。

[汇报 PDF](docs/presentation/FinGraph-期中汇报.pdf) · [构建方法](docs/METHOD.md) · [数据说明](data/README.md)

## 演示

录像约 2 分 12 秒：以 GLM-5 为例查看关联路径与原文，补入 MTT S5000 的适配关系后，关联证券由 2 只增至 3 只；随后查看行情、导出简报，并按历史日期查询 DeepSeek-R1 的关联变化。

https://github.com/user-attachments/assets/ec6aabb3-9543-4a88-8c19-6920ac20c110

## 当前数据与方法

| 内容 | 范围 |
|---|---|
| 初始图谱 | 59 个实体、85 条关系、10 个产业事件 |
| 文本来源 | 41 条：33 条官方、公司及交易所资料，8 条媒体报道 |
| 行情数据 | 8 只股票与恒生指数、科创50，共 10 条序列、2448 行日线 |
| 时间范围 | 主要产业事件为 2025.01—2026.02；行情为 2024.12—2026.03 |

初始图谱由人工整理并核对来源。新增资料由 LLM 按预设的实体与关系类型抽取，经过实体对齐、原文与日期检查后，预览并确认入图。图谱使用 NetworkX 存储和查询，每条关系保留出处与原句。

查询区分模型研发、硬件适配和云服务接入，支持按资料公开日期回看关系。行情用于比较股票与基准在同一窗口内的表现。当前数据是围绕上述主题整理的有限样本，关联关系不直接代表投资收益。

## 运行

在项目根目录使用 Python 3.11：

```powershell
python -m pip install -r code/requirements-lock.txt
python code/app.py
```

打开 <http://127.0.0.1:8000>。仓库已包含前端构建产物；Windows 也可使用 `./start.ps1` 启动。

演示资料入图时，可选择界面中标注的“样例回放”。实时抽取可使用兼容 OpenAI 的 API：将 `.env.example` 复制为 `.env`，填写模型地址、密钥和名称；也支持本机已登录的 OpenCode。

修改前端时，使用 Node.js 安装依赖并重新构建：

```powershell
cd visualization
npm ci
npm run build
```

## 项目目录

```text
knowledgeGraph/
├── code/                       # 图谱、抽取、查询、行情与后端 API
├── data/                       # 初始图谱、来源摘录、抽取样例与行情
├── visualization/
│   ├── src/                    # React 前端源码
│   ├── dist/                   # 已构建的前端
│   └── FinGraph-demo.mp4        # 演示录像
├── docs/
│   ├── presentation/           # Beamer 源码、PDF、图表与讲稿
│   ├── results/                # 实验输出与检查记录
│   ├── METHOD.md               # 图谱构建与行情计算方法
│   └── VALIDATION.md           # 数据与功能检查说明
├── .env.example                # 模型配置示例
├── start.ps1                   # Windows 启动脚本
└── README.md
```

后端使用 FastAPI、NetworkX，前端使用 React、React Flow、Dagre 和 ECharts。汇报采用复旦大学开源 Beamer 主题，来源与许可证见 [ATTRIBUTIONS.md](ATTRIBUTIONS.md)。

## 检查与复现

```powershell
python data/build_dataset.py          # 从随附原始缓存离线重建数据
python code/audit_data.py
python -m unittest discover -s code -p 'test_*.py' -v
python code/validate_demo.py          # 检查 API，使用回放入图
```

浏览器检查、图表与录屏工具的依赖见 `code/requirements-dev.txt`。抽取预实验与局限见 [EXTRACTION_PILOT.md](docs/EXTRACTION_PILOT.md)，汇报讲稿见 [TALK.md](docs/presentation/TALK.md)。
