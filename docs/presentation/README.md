# 期中汇报

[FinGraph-期中汇报.pdf](FinGraph-期中汇报.pdf) 共 18 页。第 1—15 页介绍选题、数据、构建方法、阶段结果和后续计划；第 16—18 页列出关系定义、行情计算及主要来源。讲稿见 [TALK.md](TALK.md)。

## 内容

| 页码 | 内容 |
|---|---|
| 1—4 | 选题与任务、四个模型主题、八只证券、来源与行情范围 |
| 5—9 | 构建流程、实体与关系 Schema、抽取示例、跨来源融合、证券路径查询 |
| 10—14 | 原型演示、增量更新、日期查询、抽取的初步评估与行情观察 |
| 15 | 当前问题、下一步工作与预期产出 |
| 16—18 | 关系定义、行情计算方法和主要来源 |

方法以 GLM-5 适配公告为主要例子，分别说明新抽取事实、已有产品归属和证券映射。DeepSeek-R1 用于说明日期筛选的结果。

## 编译

需要 XeLaTeX、latexmk、微软雅黑和 Arial。在项目根目录运行：

    powershell -ExecutionPolicy Bypass -File docs/presentation/build.ps1

脚本更新查询结果并编译 main.tex，输出正式 PDF。更换图谱或行情后，先运行：

    python code/build_presentation_inputs.py
    python code/build_research_figures.py

页面源码在 sections/，实际截图和行情图在 generated/，由数据生成的查询结果在 derived/。编译临时文件在 build/，不提交到仓库。

## 主题

使用 [sonnyhcl/beamerthemefdu](https://github.com/sonnyhcl/beamerthemefdu) 的原生封面、蓝色标题栏、章节导航和三段页脚，保留淡校徽水印。主题原文件和 Apache-2.0 许可证位于 vendor-fdu/，配置说明见 [THEME_NOTICE.md](THEME_NOTICE.md)。

封面和 PDF 元数据不显示小组或成员姓名，页脚显示项目名称。
