# 期中汇报

[FinGraph-期中汇报.pdf](FinGraph-期中汇报.pdf) 共 19 页。正文为第 1—15 页，依次介绍选题与范围、数据与方法、抽取初试、应用案例和后续工作；第 16—19 页为参考资料。讲稿见 [TALK.md](TALK.md)。

## 内容

| 页码 | 内容 |
|---|---|
| 1 | 封面 |
| 2—3 | 选题、知识组织问题、研究目标及当前数据范围 |
| 4—6 | 资料来源、图谱规模、现有实体关系模型与构建流程 |
| 7 | 六段文本的初试结果与 Qwen3 主体层级差异 |
| 8—10 | GLM-5 多源融合、原型演示及更新与历史查询结果 |
| 11—12 | 组织归属扩展方案与 Qwen3 验证计划 |
| 13—15 | 后续实施安排、优化方向与拟扩展的关系定义 |
| 16—19 | 行情示例与计算方法、参考文献 |

期中已完成初始资料整理、图谱与原型、少量抽取试验和功能案例。组织归属完善、独立标注评估和连续更新实验列入后续工作。约 60 段语料和约 20 组事件—日期问题均为计划规模，具体安排见讲稿。

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
