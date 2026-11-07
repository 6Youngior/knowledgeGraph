# 抽取预实验

使用 DeepSeek V4.1 Flash 对 6 段真实文本实际调用，提供当前实体目录，逐例核对指定模型与关系类型。文本及参考见 `data/extraction_eval.json`，模型输出见 [extraction_pilot.json](results/extraction_pilot.json)。范围外的正确关系不计为误报。

5 条参考目标关系中有 4 条精确匹配。另 1 段为基准比较中的共同提及负例，没有生成目标关系。按精确三元组核对，TP=4、FP=1、FN=1，P/R/F1 均为 0.80。

未匹配例是 Qwen3 的研发主体：模型输出了研发关系，但保留 `Alibaba Cloud` 为独立公司；参考采用阿里巴巴集团的实体 ID。该差异反映当前组织层级映射不足，后续需要分别表示业务单位和上市集团。

研发例最初采用“发布并开源”的句子，审查后改用明确的研发原句，仅重跑该例。初版输出保存在 [extraction_pilot_initial.json](results/extraction_pilot_initial.json)，其余 5 例沿用实际调用结果。

当前为少量、定向的初步核对，没有独立多人标注或开放实体发现测试，不能据此概括总体抽取性能。本次期中未开展 LLM/RAG 对比。
