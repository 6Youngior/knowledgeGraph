# 检查记录

以下记录分别检查数据、系统功能、抽取输出和汇报文件。抽取性能与功能检查分开统计。

| 项目 | 结果 | 记录 |
|---|---|---|
| 数据规则 | 59 个实体、85 条关系、41 条来源；类型、日期与行情检查通过 | `results/data_audit.json` |
| 原文定位 | 85 条关系的 89 处引用均可定位 | `results/source_verification.json` |
| 单元检查 | 24 项通过，覆盖类型、时间、实体、上市日期与重复导入 | `results/unit_tests.json` |
| API | 20 项，覆盖事件、行情、回放入图、历史查询、简报与前端资源 | `results/api_validation.json` |
| 实时抽取 | 实际模型调用的原始输出和耗时 | `results/live_extraction.json` |
| 抽取预实验 | 6 段文本；5 条目标关系精确匹配 4 条，1 段共同提及负例未生成关系 | `results/extraction_pilot.json` |
| 浏览器操作 | 24 项：事件、日期、下载、入图与重复导入；窗口适配、连线与慢响应下的画面保持 | `results/browser_validation.json` |
| 汇报 PDF | 16 页，16:9；正文 11 页介绍选题、当前进展和后续工作，另 5 页为参考资料 | `results/pdf_validation.json` |
| 演示录像 | 1920×1080，H.264；元数据、解码与画面检查 | `results/video_validation.json` |

## 复查

```powershell
python -m unittest discover -s code -p 'test_*.py' -v
python code/audit_data.py
python code/validate_demo.py
python code/check_browser.py
python code/check_pdf.py
```

浏览器检查需要运行本地服务、Edge 与开发依赖，并会在前后重置 Demo。`python code/validate_demo.py --live` 会实际调用模型，另存输出。原文定位可用 `python code/verify_sources.py --browser` 访问原始网站复查。

## 适用范围

原文定位不代替关系语义核查。抽取预实验提供了实体目录，样例较少，详见 [EXTRACTION_PILOT.md](EXTRACTION_PILOT.md)。历史查询按已收集资料的日期重建，尚不是完整的历史网页版本库。行情计算方法见 [METHOD.md](METHOD.md)。
