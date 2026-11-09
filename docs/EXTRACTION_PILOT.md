# 抽取预实验

使用 DeepSeek V4.1 Flash 对 6 段真实文本实际调用，提供当前实体目录，逐例核对指定模型与关系类型。文本及参考见 `data/extraction_eval.json`，模型输出见 [extraction_pilot.json](results/extraction_pilot.json)。范围外的正确关系不计为误报。

本次保留 6 段真实调用的输入和输出，逐例复核见 [extraction_review.json](results/extraction_review.json)。其中 4 条目标关系与原参考精确匹配，1 段共同提及负例未生成关系。Qwen3 的研发主体参考需要修订，单列复核，不计入当前性能结论。

Qwen3 原文明确写出 `Qwen team, Alibaba Cloud`，模型也保留了 `Alibaba Cloud`。旧参考使用阿里巴巴集团的实体 ID，混合了原文事实抽取与后续集团映射，不能据此判定抽取错误。旧报告中据此产生的 TP=4、FP=1、FN=1 及 P/R/F1=0.80 撤回作为性能评价；原报告保留用于追溯实际调用，不修改模型原始输出，也不直接改报为全部正确。

当前汇报用百度千帆接入 DeepSeek-R1 展示有原文支持的关系，用 Qwen3 基准对比展示共同提及时不生成关系。下一轮在固定且复核过的标注标准下开展独立评估。评测输入已标记待复核案例，脚本会在发起任何模型调用前检查并停止，避免继续沿用该参考计分。

研发例最初采用“发布并开源”的句子，审查后改用明确的研发原句，仅重跑该例。初版输出保存在 [extraction_pilot_initial.json](results/extraction_pilot_initial.json)，其余 5 例沿用实际调用结果。

当前为少量、定向的初步核对，没有独立多人标注或开放实体发现测试，不能据此概括总体抽取性能。本次期中未开展 LLM/RAG 对比。
