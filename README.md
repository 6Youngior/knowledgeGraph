# FinGraph · 股票量化情报

本项目是知识图谱课程期中项目，当前覆盖大模型行业相关股票。从模型发布、硬件适配、云服务接入等事件出发，将模型、产品、公司与证券连接起来，查询关联股票、产业角色及原文依据。

## 汇报与演示

- **[期中汇报 PDF](docs/presentation/FinGraph-期中汇报.pdf)**：选题与范围、图谱构建、当前结果和后续计划；[讲稿与操作顺序](docs/presentation/TALK.md)。
- **[演示视频](visualization/FinGraph-demo.mp4)**：约 2 分 12 秒，展示关联路径、原文核查、资料入图、行情与历史日期查询。

https://github.com/user-attachments/assets/ec6aabb3-9543-4a88-8c19-6920ac20c110

## 当前进展

已围绕 DeepSeek-R1、Qwen3、GLM-5、MiniMax-M2.5 四个模型主题整理资料，覆盖 8 只 A 股和港股证券。

| 数据 | 当前规模 |
|---|---|
| 初始图谱 | 59 个实体、85 条关系、10 个产业事件 |
| 文本资料 | 41 项：官方、公司及交易所资料 33 项，媒体报道 8 项 |
| 行情数据 | 8 只股票与 2 项指数，2448 行日线，覆盖 2024.12—2026.03 |

初始图谱由人工整理。新增文本经 LLM 抽取、实体匹配和证据检查后，预览确认入图。查询区分模型研发、硬件适配和云服务接入，保留路径各步的原文、来源与公开日期。

在 GLM-5 演示中，补入 MTT S5000 适配资料后，关联证券由 2 只增至 3 只，重复输入不再增加记录。目前已完成少量抽取试验和功能案例；后续将补充组织归属关系，开展独立标注评估与连续更新实验。

[构建方法](docs/METHOD.md) · [数据说明](data/README.md) · [抽取初试](docs/EXTRACTION_PILOT.md)

## 项目目录

| 路径 | 内容 |
|---|---|
| [code/](code/) | 图谱构建、关系抽取、查询、行情与后端 API |
| [data/](data/) | 初始图谱、来源摘录、抽取样例与行情 |
| [visualization/](visualization/) | React 前端、构建产物与演示录像 |
| [docs/](docs/) | 构建方法、实验记录；Beamer 源码、PDF 与讲稿在 [presentation/](docs/presentation/) |

后端使用 FastAPI、NetworkX，前端使用 React、React Flow、Dagre 和 ECharts。

## 本地运行

在项目根目录使用 Python 3.11：

```powershell
python -m pip install -r code/requirements-lock.txt
python code/app.py
```

打开 [http://127.0.0.1:8000](http://127.0.0.1:8000)。仓库已包含前端构建产物；Windows 也可使用 `./start.ps1` 启动。

演示时可选择“样例回放”。实时抽取需将 `.env.example` 复制为 `.env`，填写兼容 OpenAI 的模型地址、密钥和名称；也支持本机已登录的 OpenCode。

<details>
<summary>前端开发与数据复现</summary>

修改前端后重新构建：

```powershell
cd visualization
npm ci
npm run build
```

在项目根目录重建数据与检查功能：

```powershell
python data/build_dataset.py          # 从随附原始缓存离线重建数据
python code/audit_data.py
python -m unittest discover -s code -p 'test_*.py' -v
python code/validate_demo.py          # 检查 API，使用回放入图
```

浏览器检查、图表与录屏工具的依赖见 `code/requirements-dev.txt`，检查说明见 [VALIDATION.md](docs/VALIDATION.md)。

</details>
