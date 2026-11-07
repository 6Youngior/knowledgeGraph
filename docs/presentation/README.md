# 期中汇报

[FinGraph-期中汇报.pdf](FinGraph-期中汇报.pdf) 共 18 页。正文为第 1—13 页，按选题与研究范围、当前进展、后续计划展开；第 14—18 页为关系定义、行情示例与计算方法、参考文献。讲稿见 [TALK.md](TALK.md)。

## 内容

| 页码 | 内容 |
|---|---|
| 1 | 封面 |
| 2—3 | 选题、知识组织问题、研究目标及当前数据范围 |
| 4—7 | 资料整理、实体关系模型、抽取流程与多源融合实例 |
| 8—10 | 原型演示、更新与日期案例、六段文本的初步抽取试验 |
| 11—13 | 现有问题、下一阶段评估设计及推进安排 |
| 14—18 | 关系定义、行情示例与计算方法、参考文献 |

期中已完成初始资料整理、图谱与原型、少量抽取试验和功能案例。独立标注评估、组织层级补充、连续多批更新实验列为后续工作。约 60 段语料和约 20 组事件—日期问题均为计划规模，尚未完成。

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
