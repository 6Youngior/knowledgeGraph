# 期中汇报

[FinGraph-期中汇报.pdf](FinGraph-期中汇报.pdf) 共 16 页：第 1—13 页为汇报内容，第 14—16 页列出关系定义、行情口径与主要来源。

## 内容

1. 选题与研究问题
2. 初步数据范围
3. 知识图谱构建流程
4. 本体与关系设计
5. 知识抽取示例
6. 关联证券查询
7. 原型系统
8. 增量更新结果
9. 历史时点查询
10. 抽取预实验
11. 事件后的行情观察
12. 当前问题与后续计划

构建过程以 GLM-5 适配公告为主要例子；DeepSeek-R1 用于说明按公开日期查询的区别。现场讲解与操作顺序见 [TALK.md](TALK.md)。

## 编译

需要 XeLaTeX、latexmk、微软雅黑和 Arial。Windows 下在项目根目录运行：

```powershell
powershell -ExecutionPolicy Bypass -File docs/presentation/build.ps1
```

脚本更新 `derived/research.tex` 并编译 `main.tex`，输出正式 PDF。更换图谱或行情后，先运行：

```powershell
python code/build_presentation_inputs.py
python code/build_research_figures.py
```

源码按页面放在 `sections/`；`generated/` 保存实际界面截图、行情图和指标，`derived/` 保存从数据生成的查询结果。临时编译文件位于 `build/`，不提交到仓库。

主题为 [sonnyhcl/beamerthemefdu](https://github.com/sonnyhcl/beamerthemefdu)，Apache-2.0。原始文件与许可位于 `vendor-fdu/`，本地样式调整见 [THEME_NOTICE.md](THEME_NOTICE.md)。封面不显示小组或成员姓名。
