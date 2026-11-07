"""Build FinGraph's auditable data package.

Only writes inside data/ (never data/runtime/). Usage:
    D:/anaconda3/envs/agent/python.exe -X utf8 data/build_dataset.py
"""
from __future__ import annotations

import csv
import argparse
import json
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from extended_dataset import (
    EXTRA_BENCHMARKS, EXTRA_EDGES, EXTRA_EVENTS, EXTRA_NODES, EXTRA_SAMPLES,
    EXTRA_SOURCES, EXTRA_STOCKS, EXTRACTION_EVAL,
)

DATA = Path(__file__).resolve().parent
RAW = DATA / "raw"
MARKET = DATA / "market"
RETRIEVED_AT = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

NODE_TYPES = {"Company", "Stock", "Model", "Product", "Industry", "Event"}
RELATION_SCHEMA = {
    "DEVELOPED_BY": ({"Model"}, {"Company"}),
    "LISTED_AS": ({"Company"}, {"Stock"}),
    "PRODUCES": ({"Company"}, {"Product"}),
    "SUPPORTS_MODEL": ({"Product"}, {"Model"}),
    "HOSTS_MODEL": ({"Product"}, {"Model"}),
    "RELEASED_MODEL": ({"Event"}, {"Model"}),
    "CONCERNS": ({"Event"}, NODE_TYPES - {"Industry"}),
    "BELONGS_TO": ({"Company", "Product", "Model"}, {"Industry"}),
    "UPSTREAM_OF": ({"Product"}, {"Product"}),
    "COOPERATES_WITH": ({"Company"}, {"Company"}),
    "INVESTS_IN": ({"Company"}, {"Company"}),
    "DEPLOYS": ({"Company"}, {"Model"}),
}
RELATION_LABELS = {
    "DEVELOPED_BY": "研发主体", "LISTED_AS": "上市证券", "PRODUCES": "提供产品",
    "SUPPORTS_MODEL": "技术适配", "HOSTS_MODEL": "推理服务接入", "RELEASED_MODEL": "发布模型", "CONCERNS": "事件涉及",
    "BELONGS_TO": "所属产业", "UPSTREAM_OF": "产品上游", "COOPERATES_WITH": "商业合作",
    "INVESTS_IN": "投资关系", "DEPLOYS": "模型接入",
}


def n(nid, label, ntype, aliases, description, source_ids, properties=None):
    return {"id": nid, "label": label, "type": ntype, "aliases": aliases,
            "description": description, "source_ids": source_ids,
            "properties": properties or {}}


def e(eid, source, target, rtype, source_ids, evidence, disclosed_at, group=None):
    return {"id": eid, "source": source, "target": target, "type": rtype,
            "label": RELATION_LABELS[rtype], "source_ids": source_ids,
            "evidence": evidence, "disclosed_at": disclosed_at,
            "relation_group": group or ("adaptation" if rtype == "SUPPORTS_MODEL" else
                                        "distribution" if rtype == "HOSTS_MODEL" else
                                        "industry" if rtype in {"BELONGS_TO", "UPSTREAM_OF"} else "direct")}


# ---------------------------------------------------------------- sources
SOURCES = [
    {"id": "src:zai-glm5", "title": "GLM-5: From Vibe Coding to Agentic Engineering",
     "url": "https://z.ai/blog/glm-5", "publisher": "Z.ai (智谱)", "published_at": "2026-02-12",
     "event_at": "2026-02-12", "source_type": "official_blog", "retrieved_at": RETRIEVED_AT,
     "date_basis": "official visible page header: 2026-02-12 · Research",
     "text": "We are launching GLM-5, targeting complex systems engineering and long-horizon agentic tasks. Scaling is still one of the most important ways to improve the intelligence efficiency of Artificial General Intelligence (AGI). Compared to GLM-4.5, GLM-5 scales from 355B parameters (32B active) to 744B parameters (40B active), and increases pre-training data from 23T to 28.5T tokens. GLM-5 also integrates DeepSeek Sparse Attention (DSA), significantly reducing deployment cost while preserving long-context capacity. …… GLM-4.5 is our first step for reasoning, coding, and agent, enabling the model to complete complex tasks. With GLM-5, we further enhance complex systems engineering and long-horizon agent capabilities. …… To this end, we developed slime, a novel asynchronous RL infrastructure that substantially improves training throughput and efficiency, enabling more fine-grained post-training iterations. …… GLM-5 is open-sourced on Hugging Face and ModelScope, with model weights released under the MIT License. GLM-5 is also available on developer platform api.z.ai and BigModel.cn, with compatibility with Claude Code and OpenClaw."},
    {"id": "src:bigmodel-glm5", "title": "GLM-5 - 智谱AI开放文档",
     "url": "https://docs.bigmodel.cn/cn/guide/models/text/glm-5", "publisher": "智谱 BigModel",
     "published_at": "", "event_at": "", "source_type": "official_docs",
     "retrieved_at": RETRIEVED_AT,
     "text": "GLM-5 是智谱的基座模型，面向 Agentic Engineering 打造，能够在复杂系统工程与长程 Agent 任务中提供可靠生产力。…… 参数规模扩展：从 355B（激活 32B）扩展至 744B（激活 40B），预训练数据从 23T 提升至 28.5T。…… 在 SWE-bench-Verified 和 Terminal Bench 2.0 中分别获得 77.8 和 56.2 的开源模型最高分数，性能表现超过 Gemini 3.0 Pro。"},
    {"id": "src:github-glm5", "title": "zai-org/GLM-5: GLM-5: From Vibe Coding to Agentic Engineering",
     "url": "https://github.com/zai-org/GLM-5", "publisher": "GitHub / Z.ai",
     "published_at": "", "event_at": "", "source_type": "code_repository",
     "retrieved_at": RETRIEVED_AT,
     "text": "GLM-5: From Vibe Coding to Agentic Engineering. Repository metadata: GitHub repository created 2026-02-09T08:17:02Z; Hugging Face model repository zai-org/GLM-5 created 2026-02-11T04:55:46Z. These timestamps are repository metadata, not a verified announcement time."},
    {"id": "src:mthreads-glm5", "title": "Day-0 支持｜摩尔线程 MTT S5000 率先完成对 GLM-5 的适配",
     "url": "https://www.mthreads.com/news/280", "publisher": "摩尔线程", "published_at": "2026-02-12",
     "event_at": "2026-02-12", "source_type": "official_news", "retrieved_at": RETRIEVED_AT,
     "text": "2月12日，智谱正式发布新一代大模型GLM-5。摩尔线程基于SGLang推理框架，在旗舰级AI训推一体全功能GPU MTT S5000上，Day-0完成了全流程适配与验证。…… MTT S5000是专为大模型训练、推理及高性能计算而设计的全功能GPU智算卡，基于第四代MUSA架构“平湖”打造。…… MUSA软件栈的敏捷性是实现Day-0适配的关键。基于MUSA架构的TileLang原生算子单元测试覆盖率已超过80%，使得绝大多数通用算子可直接复用，显著降低移植成本，并能快速跟进前沿模型结构与新特性演进。"},
    {"id": "src:mthreads-minimax", "title": "Day-0 支持｜摩尔线程完成 MiniMax M2.5 模型极速适配",
     "url": "https://www.mthreads.com/news/281", "publisher": "摩尔线程", "published_at": "2026-02-14",
     "event_at": "2026-02-14", "source_type": "official_news", "retrieved_at": RETRIEVED_AT,
     "text": "2月14日，摩尔线程在其旗舰级AI训推一体全功能GPU MTT S5000上，成功实现了对MiniMax新一代大模型MiniMax M2.5的Day-0极速适配。在此次适配工作中，摩尔线程技术团队依托MUSA软件栈强大的生态兼容性，基于高性能SGLang-MUSA推理引擎进行调优，成功在MTT S5000上实现了该模型的高性能推理。"},
    {"id": "src:minimax-m25", "title": "MiniMax M2.5: Built for Real-World Productivity.",
     "url": "https://www.minimax.io/news/minimax-m25", "publisher": "MiniMax", "published_at": "2026-02-12",
     "event_at": "2026-02-12", "source_type": "official_news", "retrieved_at": RETRIEVED_AT,
     "text": "Today we're introducing our latest model, MiniMax-M2.5. Extensively trained with reinforcement learning in hundreds of thousands of complex real-world environments, M2.5 is SOTA in coding, agentic tool use and search, office work, and a range of other economically valuable tasks, boasting scores of 80.2% in SWE-Bench Verified, 51.3% in Multi-SWE-Bench, and 76.3% in BrowseComp."},
    {"id": "src:minimax-m25-cn", "title": "MiniMax M2.5: 更快更强更智能，为真实世界生产力而生",
     "url": "https://www.minimax.cn/news/minimax-m25", "publisher": "MiniMax", "published_at": "2026-02-12",
     "event_at": "2026-02-12", "source_type": "official_news", "retrieved_at": RETRIEVED_AT,
     "text": "今天我们来介绍 MiniMax-M2.5。经过数十万个真实复杂环境中的大规模强化学习训练，M2.5 在编程、工具调用和搜索、办公等生产力场景都达到或者刷新了行业的 SOTA。M2.5 优化了模型对复杂任务的拆解能力和思考过程中 token 的消耗，使其能更快地完成复杂的 Agentic 任务，比如在 SWE-Bench Verified 的测试中，比上一个版本 M2.1 完成任务的速度快了 37%。M2.5 已经在 MiniMax Agent 中全面上线，带来最佳 Agentic 体验。"},
    {"id": "src:chinadaily-zhipu-ipo", "title": "“全球大模型第一股”来了！智谱港交所敲钟",
     "url": "https://cn.chinadaily.com.cn/a/202601/08/WS695f5b9da310942cc499a93e.html",
     "publisher": "中国日报网", "published_at": "2026-01-08", "event_at": "2026-01-08",
     "source_type": "news", "retrieved_at": RETRIEVED_AT,
     "text": "2026年1月8日，北京智谱华章科技股份有限公司（02513.HK）正式在香港联合交易所挂牌上市。…… 智谱首日开盘价120港元/股，盘中冲高，截至发稿最高触及130港元，较其发行价116.2港元上涨约12%，市值超570亿港元。…… 以每股116.20港元的发行价计算，智谱本次IPO募资总额超43亿港元。…… 2025年12月，智谱新一代基座模型GLM-4.7在模型综合能力榜单Artificial Analysis与权威编码榜单Code Arena中，均荣登开源模型与国产模型双料榜首。…… 智谱2019年由清华大学技术成果转化而来，专注通用人工智能（AGI）的研发，并坚持做让用户真正用得上的研究与技术。…… 其中编程订阅产品表现尤为突出，上线短时间内即实现过亿的年度经常性收入，并在海外开发者社群中快速渗透。"},
    {"id": "src:hkex-zhipu-prospectus", "title": "北京智譜華章科技股份有限公司 全球發售",
     "url": "https://www1.hkexnews.hk/listedco/listconews/sehk/2025/1230/2025123000018_c.pdf",
     "publisher": "香港交易所披露易", "published_at": "2025-12-30", "event_at": "2026-01-08",
     "source_type": "prospectus", "retrieved_at": RETRIEVED_AT,
     "text": "全球發售"},
    {"id": "src:sse-mthreads-ipo", "title": "关于摩尔线程智能科技（北京）股份有限公司人民币普通股股票科创板上市交易的公告",
     "url": "https://www.sse.com.cn/disclosure/announcement/listing/ipo/c/c_20251204_10800678.shtml",
     "publisher": "上海证券交易所", "published_at": "2025-12-04", "event_at": "2025-12-05",
     "source_type": "exchange_announcement", "retrieved_at": RETRIEVED_AT,
     "text": "上证公告（股票）[2025]35号 摩尔线程智能科技（北京）股份有限公司A股股票将在本所科创板上市交易。该公司A股股本为47002.8217万股，其中2938.2386万股于2025年12月5日起上市交易。证券简称为“摩尔线程”，证券代码为“688795”。"},
    {"id": "src:mthreads-ipo-news", "title": "股票代码 688795！摩尔线程正式挂牌科创板！",
     "url": "https://www.mthreads.com/news/266", "publisher": "摩尔线程", "published_at": "2025-12-05",
     "event_at": "2025-12-05", "source_type": "official_news", "retrieved_at": RETRIEVED_AT,
     "text": "2025年12月5日，摩尔线程智能科技（北京）股份有限公司（简称：摩尔线程，股票代码：688795.SH）正式在上海证券交易所科创板挂牌上市，成为中国首家登陆资本市场的全功能GPU企业。"},
    {"id": "src:alibaba-hkex-listing", "title": "Alibaba Group Listed on Main Board of HKEX",
     "url": "https://www.alibabagroup.com/en-US/document-1491198532105797632",
     "publisher": "Alibaba Group", "published_at": "2019-11-26", "event_at": "2019-11-26",
     "source_type": "company_press_release", "retrieved_at": RETRIEVED_AT,
     "text": "Hong Kong, China, November 26, 2019 - Alibaba Group Holding Limited (\"Alibaba\" or the \"Company\") (NYSE: BABA and HKEX: 9988) has officially listed on the main board of the Hong Kong Exchanges and Clearing Limited (HKEX) today, successfully going public in Hong Kong."},
    {"id": "src:acn-minimax-ipo", "title": "市值超800億 成功上市的MiniMax以「極致效率」重塑全球AGI新格局",
     "url": "https://www.acnnewswire.com/press-release/traditionalchinese/104546/",
     "publisher": "亚太商讯", "published_at": "2026-01-09", "event_at": "2026-01-09",
     "source_type": "press_release", "retrieved_at": RETRIEVED_AT,
     "text": "香港, 2026年1月9日 - (亞太商訊) - 1月9日，全球領先的通用人工智能科技公司——MiniMax（0100.HK）正式登陸港交所。"},
    {"id": "src:aliyun-glm5", "title": "glm-5 模型信息 - 大模型服务平台百炼",
     "url": "https://www.alibabacloud.com/help/zh/model-studio/glm-9", "publisher": "阿里云",
     "published_at": "", "event_at": "", "source_type": "official_docs", "retrieved_at": RETRIEVED_AT,
     "text": "GLM-5是面向Coding与Agent场景的新一代大模型，在复杂系统工程与长程任务中达到开源 SOTA，真实编程体验逼近 Claude Opus 级别；基于 744B 新基座、异步强化学习与稀疏注意力，实现从“写代码”到“写工程”的全面升级。…… glm-5模型的推理服务供应商为阿里云百炼。"},
    {"id": "src:aliyun-minimax", "title": "MiniMax-M2.5 模型信息 - 大模型服务平台百炼",
     "url": "https://www.alibabacloud.com/help/zh/model-studio/minimax-m2-5", "publisher": "阿里云",
     "published_at": "", "event_at": "", "source_type": "official_docs", "retrieved_at": RETRIEVED_AT,
     "text": "MiniMax-M2.5是MiniMax推出的旗舰级开源大模型，经过数十万个真实复杂环境中的大规模强化学习训练，M2.5 在编程、工具调用和搜索、办公等生产力场景都达到或者刷新了行业的 SOTA。…… MiniMax-M2.5模型的推理服务供应商为阿里云百炼。"},
    {"id": "src:mthreads-s5000", "title": "MTT S5000 - 摩尔线程",
     "url": "https://www.mthreads.com/product/S5000", "publisher": "摩尔线程",
     "published_at": "", "event_at": "", "source_type": "product_page", "retrieved_at": RETRIEVED_AT,
     "text": "MTT S5000是专为大模型训练、推理及高性能计算而设计的全功能GPU智算卡，基于第四代MUSA架构“平湖”打造。完整支持从FP8到FP64的全精度计算。"},
]

# ---------------------------------------------------------------- nodes
NODES = [
    n("company:zhipu", "智谱", "Company", ["Zhipu", "Z.ai", "北京智谱华章科技股份有限公司"],
      "中国通用大模型公司，GLM 系列研发方；2026-01-08 于港交所主板上市（02513.HK）。",
      ["src:chinadaily-zhipu-ipo", "src:zai-glm5"],
      {"ticker": "02513.HK", "market": "HK", "hq": "北京", "founded": "2019"}),
    n("company:mthreads", "摩尔线程", "Company",
      ["Moore Threads", "摩尔线程智能科技（北京）股份有限公司"],
      "中国全功能 GPU 企业，MTT S5000 与 MUSA 软件栈研发方；2025-12-05 于上交所科创板上市（688795.SH）。",
      ["src:sse-mthreads-ipo", "src:mthreads-glm5"],
      {"ticker": "688795.SH", "market": "SH", "hq": "北京", "founded": "2020"}),
    n("company:minimax", "MiniMax", "Company", ["MiniMax Group Inc.", "稀宇科技"],
      "中国全模态大模型公司，MiniMax-M2.5 研发方；2026-01-09 于港交所主板上市（00100.HK）。",
      ["src:acn-minimax-ipo", "src:minimax-m25-cn"],
      {"ticker": "00100.HK", "market": "HK", "hq": "上海"}),
    n("company:alibaba", "阿里巴巴", "Company", ["Alibaba", "Alibaba Group", "阿里巴巴集团"],
      "中国云计算与互联网公司，阿里云百炼平台运营方；港交所 09988.HK。",
      ["src:alibaba-hkex-listing", "src:aliyun-glm5"],
      {"ticker": "09988.HK", "market": "HK", "hq": "杭州"}),
    n("stock:02513.HK", "智谱 (02513.HK)", "Stock", ["02513.HK", "2513.HK", "智谱"],
      "智谱在港交所主板的上市证券，2026-01-08 开始交易。",
      ["src:chinadaily-zhipu-ipo", "src:hkex-zhipu-prospectus"],
      {"symbol": "02513.HK", "market": "HK", "currency": "HKD", "company_id": "company:zhipu",
       "company_name": "智谱", "listing_date": "2026-01-08", "ipo_price_hkd": 116.2}),
    n("stock:688795.SH", "摩尔线程-U (688795.SH)", "Stock", ["688795.SH", "688795", "摩尔线程"],
      "摩尔线程在上交所科创板的上市证券，2025-12-05 开始交易。",
      ["src:sse-mthreads-ipo", "src:mthreads-ipo-news"],
      {"symbol": "688795.SH", "market": "SH", "currency": "CNY", "company_id": "company:mthreads",
       "company_name": "摩尔线程", "listing_date": "2025-12-05"}),
    n("stock:00100.HK", "MINIMAX-W (00100.HK)", "Stock", ["00100.HK", "0100.HK", "MINIMAX-W"],
      "MiniMax 在港交所主板的上市证券，2026-01-09 开始交易。",
      ["src:acn-minimax-ipo"],
      {"symbol": "00100.HK", "market": "HK", "currency": "HKD", "company_id": "company:minimax",
       "company_name": "MiniMax", "listing_date": "2026-01-09"}),
    n("stock:09988.HK", "阿里巴巴-W (09988.HK)", "Stock", ["09988.HK", "9988.HK", "阿里巴巴-W"],
      "阿里巴巴在港交所主板的上市证券，2019-11-26 开始交易。",
      ["src:alibaba-hkex-listing"],
      {"symbol": "09988.HK", "market": "HK", "currency": "HKD", "company_id": "company:alibaba",
       "company_name": "阿里巴巴", "listing_date": "2019-11-26"}),
    n("model:glm5", "GLM-5", "Model", ["GLM5", "GLM-5"],
      "智谱 744B 总参数 / 40B 激活的开源基座模型，200K 上下文，面向 Agentic Engineering，MIT License。",
      ["src:zai-glm5", "src:bigmodel-glm5", "src:github-glm5"],
      {"parameters_total": "744B", "parameters_active": "40B", "context_window": 200000,
       "license": "MIT", "released_at": "2026-02-12", "hf_repo_created_at": "2026-02-11T04:55:46Z",
       "hf_repo_created_at_note": "仅仓库元数据，不是正式发布时间"}),
    n("model:glm47", "GLM-4.7", "Model", ["GLM4.7", "GLM-4.7"],
      "GLM-5 的前代基座模型，2025 年 12 月发布；官方以它作为 GLM-5 的主要对照基线。",
      ["src:chinadaily-zhipu-ipo", "src:zai-glm5"], {"released": "2025-12"}),
    n("model:minimax-m25", "MiniMax-M2.5", "Model", ["M2.5", "MiniMax M2.5", "MiniMax-M2.5"],
      "MiniMax 旗舰开源文本模型，主打编程、工具调用与 Agent 任务；SWE-Bench Verified 80.2%。",
      ["src:minimax-m25", "src:minimax-m25-cn"],
      {"swe_bench_verified": 0.802, "multi_swe_bench": 0.513, "browsecomp": 0.763, "released_at": "2026-02-12"}),
    n("model:minimax-m21", "MiniMax-M2.1", "Model", ["M2.1", "MiniMax M2.1"],
      "MiniMax-M2.5 的前代模型，官方发布文以 M2.1 作为速度与 token 效率对照。",
      ["src:minimax-m25-cn"], {"released": "2025"}),
    n("product:mtt-s5000", "MTT S5000", "Product", ["MTT S5000", "S5000"],
      "摩尔线程旗舰级 AI 训推一体全功能 GPU，基于第四代 MUSA 架构“平湖”，支持 FP8 到 FP64。",
      ["src:mthreads-glm5", "src:mthreads-s5000"],
      {"vendor": "摩尔线程", "architecture": "MUSA 平湖", "precision": "FP8-FP64"}),
    n("product:musa", "MUSA 软件栈", "Product", ["MUSA", "SGLang-MUSA"],
      "摩尔线程全栈软件平台，含驱动、算子库与 SGLang-MUSA 推理引擎。",
      ["src:mthreads-glm5"], {"vendor": "摩尔线程"}),
    n("product:zai", "Z.ai", "Product", ["Z.ai", "api.z.ai"],
      "智谱面向消费者与开发者的 AI 应用及 API 平台，GLM-5 上线渠道之一。",
      ["src:zai-glm5"], {"operator": "智谱"}),
    n("product:bigmodel", "BigModel.cn", "Product", ["BigModel", "bigmodel.cn", "智谱开放平台"],
      "智谱大模型开放平台，提供 GLM-5 API 与模型文档。",
      ["src:zai-glm5", "src:bigmodel-glm5"], {"operator": "智谱"}),
    n("product:glm-coding-plan", "GLM 编程订阅", "Product", ["GLM Coding Plan", "编程订阅"],
      "智谱编程订阅产品；据中国日报报道，上线短时间内实现过亿年度经常性收入。",
      ["src:chinadaily-zhipu-ipo"],
      {"operator": "智谱", "arr": "超过 1 亿元人民币（报道口径）"}),
    n("product:minimax-agent", "MiniMax Agent", "Product", ["MiniMax Agent"],
      "MiniMax 的 Agent 产品，M2.5 上线后集成 Office Skills 与专家套组。",
      ["src:minimax-m25-cn"], {"operator": "MiniMax"}),
    n("product:bailian", "阿里云百炼", "Product", ["百炼", "Model Studio", "阿里云百炼"],
      "阿里云一站式大模型服务平台；文档标注 GLM-5 与 MiniMax-M2.5 的推理服务供应商为阿里云百炼。",
      ["src:aliyun-glm5", "src:aliyun-minimax"],
      {"operator": "阿里云", "doc_retrieved_at": "2026-11-06"}),
    n("industry:foundation-model", "基础大模型", "Industry", [],
      "通用基座大模型的研发与开源供给。", ["src:zai-glm5", "src:minimax-m25"], {}),
    n("industry:gpu", "全功能 GPU", "Industry", [],
      "面向 AI 训练与推理的通用 GPU 算力硬件。", ["src:mthreads-glm5"], {}),
    n("industry:cloud-maas", "云 MaaS 平台", "Industry", [],
      "将第三方模型以 API 形式托管的云模型服务。", ["src:aliyun-glm5"], {}),
    n("industry:ai-agent", "AI Agent 应用", "Industry", [],
      "面向长程任务与工具调用的智能体应用层。",
      ["src:minimax-m25-cn", "src:zai-glm5"], {}),
    n("event:glm5-release", "GLM-5 发布", "Event", [],
      "智谱发布 744B 总参数的开源基座模型 GLM-5；中文资料记为 2026-02-12，Hugging Face 仓库创建于 2026-02-11T04:55:46Z。",
      ["src:zai-glm5", "src:bigmodel-glm5", "src:mthreads-glm5", "src:github-glm5"],
      {"timezone": "Asia/Shanghai", "utc_date": "2026-02-11", "local_date": "2026-02-12"}),
    n("event:minimax-m25-release", "MiniMax-M2.5 发布", "Event", [],
      "MiniMax 发布 M2.5，官方页面标注 2026.2.12；SWE-Bench Verified 80.2%，并强调低成本 Agent 推理。",
      ["src:minimax-m25", "src:minimax-m25-cn"], {"timezone": "Asia/Shanghai"}),
    n("event:mtt-minimax-adapt", "MTT S5000 完成 MiniMax-M2.5 Day-0 适配", "Event", [],
      "摩尔线程在 MTT S5000 上完成 MiniMax-M2.5 的 Day-0 极速适配，基于 SGLang-MUSA 与原生 FP8。",
      ["src:mthreads-minimax"], {"timezone": "Asia/Shanghai"}),
]

# ---------------------------------------------------------------- edges
EDGES = [
    e("rel:glm5-developed-by-zhipu", "model:glm5", "company:zhipu", "DEVELOPED_BY",
      ["src:bigmodel-glm5", "src:zai-glm5"], "GLM-5 是智谱的基座模型", "2026-02-12"),
    e("rel:glm47-developed-by-zhipu", "model:glm47", "company:zhipu", "DEVELOPED_BY",
      ["src:chinadaily-zhipu-ipo"], "2025年12月，智谱新一代基座模型GLM-4.7", "2026-01-08"),
    e("rel:minimax-m25-developed-by-minimax", "model:minimax-m25", "company:minimax", "DEVELOPED_BY",
      ["src:minimax-m25"], "Today we're introducing our latest model, MiniMax-M2.5.", "2026-02-12"),
    e("rel:minimax-m21-developed-by-minimax", "model:minimax-m21", "company:minimax", "DEVELOPED_BY",
      ["src:minimax-m21-github"], "Your name is MiniMax-M2.1 and is built by MiniMax.", "2026-11-07"),
    e("rel:zhipu-listed-as-02513", "company:zhipu", "stock:02513.HK", "LISTED_AS",
      ["src:chinadaily-zhipu-ipo"],
      "2026年1月8日，北京智谱华章科技股份有限公司（02513.HK）正式在香港联合交易所挂牌上市", "2026-01-08"),
    e("rel:mthreads-listed-as-688795", "company:mthreads", "stock:688795.SH", "LISTED_AS",
      ["src:sse-mthreads-ipo"], "证券简称为“摩尔线程”，证券代码为“688795”", "2025-12-04"),
    e("rel:minimax-listed-as-00100", "company:minimax", "stock:00100.HK", "LISTED_AS",
      ["src:acn-minimax-ipo"], "MiniMax（0100.HK）正式登陸港交所", "2026-01-09"),
    e("rel:alibaba-listed-as-09988", "company:alibaba", "stock:09988.HK", "LISTED_AS",
      ["src:alibaba-hkex-listing"], "NYSE: BABA and HKEX: 9988", "2019-11-26"),
    e("rel:mthreads-produces-s5000", "company:mthreads", "product:mtt-s5000", "PRODUCES",
      ["src:mthreads-glm5"], "MTT S5000是专为大模型训练、推理及高性能计算而设计的全功能GPU智算卡", "2026-02-12"),
    e("rel:mthreads-produces-musa", "company:mthreads", "product:musa", "PRODUCES",
      ["src:mthreads-glm5"], "MUSA软件栈的敏捷性是实现Day-0适配的关键", "2026-02-12"),
    e("rel:zhipu-produces-zai", "company:zhipu", "product:zai", "PRODUCES",
      ["src:zai-glm5"], "GLM-5 is also available on developer platform api.z.ai and BigModel.cn", "2026-11-06"),
    e("rel:zhipu-produces-bigmodel", "company:zhipu", "product:bigmodel", "PRODUCES",
      ["src:zai-glm5"], "GLM-5 is also available on developer platform api.z.ai and BigModel.cn", "2026-11-06"),
    e("rel:zhipu-produces-coding-plan", "company:zhipu", "product:glm-coding-plan", "PRODUCES",
      ["src:chinadaily-zhipu-ipo"],
      "编程订阅产品表现尤为突出，上线短时间内即实现过亿的年度经常性收入", "2026-01-08"),
    e("rel:minimax-produces-agent", "company:minimax", "product:minimax-agent", "PRODUCES",
      ["src:minimax-m25-cn"], "M2.5 已经在 MiniMax Agent 中全面上线", "2026-02-12"),
    e("rel:alibaba-produces-bailian", "company:alibaba", "product:bailian", "PRODUCES",
      ["src:aliyun-bailian-product"], "大模型服务平台百炼 - 大模型应用构建 - 阿里云", "2026-11-07"),
    e("rel:mtt-s5000-supports-minimax-m25", "product:mtt-s5000", "model:minimax-m25", "SUPPORTS_MODEL",
      ["src:mthreads-minimax"],
      "成功实现了对MiniMax新一代大模型MiniMax M2.5的Day-0极速适配", "2026-02-14", "adaptation"),
    e("rel:bailian-hosts-glm5", "product:bailian", "model:glm5", "HOSTS_MODEL",
      ["src:aliyun-glm5"], "glm-5模型的推理服务供应商为阿里云百炼", "2026-11-06", "distribution"),
    e("rel:bailian-hosts-minimax-m25", "product:bailian", "model:minimax-m25", "HOSTS_MODEL",
      ["src:aliyun-minimax"], "MiniMax-M2.5模型的推理服务供应商为阿里云百炼", "2026-11-06", "distribution"),
    e("rel:zhipu-belongs-to-foundation-model", "company:zhipu", "industry:foundation-model", "BELONGS_TO",
      ["src:chinadaily-zhipu-ipo"], "专注通用人工智能（AGI）的研发", "2026-01-08", "industry"),
    e("rel:minimax-belongs-to-foundation-model", "company:minimax", "industry:foundation-model", "BELONGS_TO",
      ["src:acn-minimax-ipo"], "全球領先的通用人工智能科技公司", "2026-01-09", "industry"),
    e("rel:mthreads-belongs-to-gpu", "company:mthreads", "industry:gpu", "BELONGS_TO",
      ["src:mthreads-glm5"], "全功能GPU", "2026-02-12", "industry"),
    e("rel:alibaba-belongs-to-cloud-maas", "company:alibaba", "industry:cloud-maas", "BELONGS_TO",
      ["src:aliyun-glm5"], "glm-5模型的推理服务供应商为阿里云百炼", "2026-11-06", "industry"),
    e("rel:glm5-release-released-model", "event:glm5-release", "model:glm5", "RELEASED_MODEL",
      ["src:mthreads-glm5"], "智谱正式发布新一代大模型GLM-5", "2026-02-12"),
    e("rel:glm5-release-concerns-zhipu", "event:glm5-release", "company:zhipu", "CONCERNS",
      ["src:mthreads-glm5"], "智谱正式发布新一代大模型GLM-5", "2026-02-12"),
    e("rel:minimax-release-released-model", "event:minimax-m25-release", "model:minimax-m25", "RELEASED_MODEL",
      ["src:minimax-m25-cn"], "今天我们来介绍 MiniMax-M2.5", "2026-02-12"),
    e("rel:minimax-release-concerns-minimax", "event:minimax-m25-release", "company:minimax", "CONCERNS",
      ["src:minimax-m25-cn"], "M2.5 已经在 MiniMax Agent 中全面上线", "2026-02-12"),
    e("rel:mtt-minimax-adapt-concerns-model", "event:mtt-minimax-adapt", "model:minimax-m25", "CONCERNS",
      ["src:mthreads-minimax"],
      "成功实现了对MiniMax新一代大模型MiniMax M2.5的Day-0极速适配", "2026-02-14"),
    e("rel:mtt-minimax-adapt-concerns-product", "event:mtt-minimax-adapt", "product:mtt-s5000", "CONCERNS",
      ["src:mthreads-minimax"], "旗舰级AI训推一体全功能GPU MTT S5000", "2026-02-14"),
    e("rel:mtt-minimax-adapt-concerns-company", "event:mtt-minimax-adapt", "company:mthreads", "CONCERNS",
      ["src:mthreads-minimax"], "摩尔线程在其旗舰级AI训推一体全功能GPU MTT S5000上", "2026-02-14"),
]

# ---------------------------------------------------------------- events
EVENTS = [
    {"id": "event:glm5-release", "title": "GLM-5 发布", "date": "2026-02-12",
     "event_at": "2026-02-12", "disclosed_at": "2026-02-12", "type": "MODEL_RELEASE",
     "summary": "智谱发布 744B 总参数的开源基座模型 GLM-5，面向复杂系统工程与长程 Agent 任务，重点提升编程、工具调用与端到端交付能力。",
     "entity_id": "model:glm5",
     "source_ids": ["src:zai-glm5", "src:bigmodel-glm5", "src:mthreads-glm5", "src:github-glm5"],
     "properties": {"timezone": "Asia/Shanghai", "date_note": "事件日期采用已公开官方新闻的 2026-02-12 口径；具体披露时刻未核验。"}},
    {"id": "event:minimax-m25-release", "title": "MiniMax-M2.5 发布", "date": "2026-02-12",
     "event_at": "2026-02-12", "disclosed_at": "2026-02-12", "type": "MODEL_RELEASE",
     "summary": "MiniMax 发布 M2.5，官方页面标注 2026.2.12；SWE-Bench Verified 80.2%，并强调低成本 Agent 推理。",
     "entity_id": "model:minimax-m25",
     "source_ids": ["src:minimax-m25", "src:minimax-m25-cn"],
     "properties": {"timezone": "Asia/Shanghai"}},
    {"id": "event:mtt-minimax-adapt", "title": "MTT S5000 完成 MiniMax-M2.5 Day-0 适配",
     "date": "2026-02-14", "event_at": "2026-02-14", "disclosed_at": "2026-02-14",
     "type": "PRODUCT_ADAPTATION",
     "summary": "摩尔线程在 MTT S5000 上完成 MiniMax-M2.5 的 Day-0 极速适配，基于 SGLang-MUSA 与原生 FP8。",
     "entity_id": "model:minimax-m25", "source_ids": ["src:mthreads-minimax"],
     "properties": {"timezone": "Asia/Shanghai"}},
]

# ---------------------------------------------------------------- extraction samples
SAMPLE1_TEXT = "2月12日，智谱正式发布新一代大模型GLM-5。摩尔线程基于SGLang推理框架，在旗舰级AI训推一体全功能GPU MTT S5000上，Day-0完成了全流程适配与验证。凭借MUSA架构广泛的算子覆盖与强大的生态兼容能力，摩尔线程成功打通了模型推理全链路，并深度释放MTT S5000的原生FP8加速能力，在确保模型精度的同时显著降低了显存占用，实现了GLM-5的高性能推理。"
SAMPLE2_TEXT = "2月14日，摩尔线程在其旗舰级AI训推一体全功能GPU MTT S5000上，成功实现了对MiniMax新一代大模型MiniMax M2.5的Day-0极速适配。"
SAMPLE_NOTE = ("离线回放：由 DeepSeek V4.1 Flash 辅助整理，内容可对照所附官方原文逐字复核；"
               "不是人工标注，也不是本次实时 API 调用。")

SAMPLES = [
    {"id": "sample:mtt-glm5-adapt",
     "title": "Day-0 支持｜摩尔线程 MTT S5000 率先完成对 GLM-5 的适配",
     "document_id": "src:mthreads-glm5", "text": SAMPLE1_TEXT,
     "url": "https://www.mthreads.com/news/280", "model": "DeepSeek V4.1 Flash",
     "notes": SAMPLE_NOTE + " 初始图谱刻意未包含 MTT S5000 → GLM-5 的 SUPPORTS_MODEL 边；导入后新增摩尔线程（688795.SH）的适配型解释路径。",
     "extraction": {
         "entities": [
             n("product:mtt-s5000", "MTT S5000", "Product", ["MTT S5000", "S5000"], "", ["src:mthreads-glm5"]),
             n("model:glm5", "GLM-5", "Model", ["GLM5", "GLM-5"], "", ["src:mthreads-glm5"]),
             n("company:mthreads", "摩尔线程", "Company", ["Moore Threads"], "", ["src:mthreads-glm5"]),
             n("company:zhipu", "智谱", "Company", ["Zhipu", "Z.ai"], "", ["src:mthreads-glm5"]),
             n("event:mtt-glm5-adapt", "MTT S5000 完成 GLM-5 Day-0 适配", "Event", [], "", ["src:mthreads-glm5"]),
         ],
         "relations": [
             e("rel:mtt-s5000-supports-glm5", "product:mtt-s5000", "model:glm5", "SUPPORTS_MODEL",
               ["src:mthreads-glm5"], "Day-0完成了全流程适配与验证", "2026-02-12", "adaptation"),
             e("rel:mtt-glm5-adapt-concerns-product", "event:mtt-glm5-adapt", "product:mtt-s5000", "CONCERNS",
               ["src:mthreads-glm5"], "在旗舰级AI训推一体全功能GPU MTT S5000上", "2026-02-12"),
             e("rel:mtt-glm5-adapt-concerns-model", "event:mtt-glm5-adapt", "model:glm5", "CONCERNS",
               ["src:mthreads-glm5"], "智谱正式发布新一代大模型GLM-5", "2026-02-12"),
         ],
         "events": [{"id": "event:mtt-glm5-adapt", "title": "MTT S5000 完成 GLM-5 Day-0 适配",
                     "date": "2026-02-12", "event_at": "2026-02-12", "disclosed_at": "2026-02-12",
                     "type": "PRODUCT_ADAPTATION",
                     "summary": "摩尔线程在 MTT S5000 上完成 GLM-5 的 Day-0 适配，并释放原生 FP8 推理能力。",
                     "entity_id": "model:glm5", "source_ids": ["src:mthreads-glm5"],
                     "properties": {"timezone": "Asia/Shanghai"}}],
     }},
    {"id": "sample:mtt-minimax-adapt",
     "title": "Day-0 支持｜摩尔线程完成 MiniMax M2.5 模型极速适配",
     "document_id": "src:mthreads-minimax", "text": SAMPLE2_TEXT,
     "url": "https://www.mthreads.com/news/281", "model": "DeepSeek V4.1 Flash",
     "notes": SAMPLE_NOTE + " 该样例对应的关系已在初始图谱中，重复抽取应显示 matched / 无新增事实。",
     "extraction": {
         "entities": [
             n("product:mtt-s5000", "MTT S5000", "Product", ["MTT S5000", "S5000"], "", ["src:mthreads-minimax"]),
             n("model:minimax-m25", "MiniMax-M2.5", "Model", ["M2.5", "MiniMax M2.5"], "", ["src:mthreads-minimax"]),
             n("company:mthreads", "摩尔线程", "Company", ["Moore Threads"], "", ["src:mthreads-minimax"]),
             n("company:minimax", "MiniMax", "Company", ["MiniMax Group Inc."], "", ["src:mthreads-minimax"]),
             n("event:mtt-minimax-adapt", "MTT S5000 完成 MiniMax-M2.5 Day-0 适配", "Event", [], "", ["src:mthreads-minimax"]),
         ],
         "relations": [
             e("rel:mtt-s5000-supports-minimax-m25", "product:mtt-s5000", "model:minimax-m25", "SUPPORTS_MODEL",
               ["src:mthreads-minimax"], "成功实现了对MiniMax新一代大模型MiniMax M2.5的Day-0极速适配", "2026-02-14", "adaptation"),
             e("rel:mtt-minimax-adapt-concerns-product", "event:mtt-minimax-adapt", "product:mtt-s5000", "CONCERNS",
               ["src:mthreads-minimax"], "旗舰级AI训推一体全功能GPU MTT S5000", "2026-02-14"),
             e("rel:mtt-minimax-adapt-concerns-model", "event:mtt-minimax-adapt", "model:minimax-m25", "CONCERNS",
               ["src:mthreads-minimax"], "MiniMax新一代大模型MiniMax M2.5", "2026-02-14"),
             e("rel:mthreads-produces-s5000", "company:mthreads", "product:mtt-s5000", "PRODUCES",
               ["src:mthreads-minimax"], "摩尔线程在其旗舰级AI训推一体全功能GPU MTT S5000上", "2026-02-14"),
             e("rel:minimax-m25-developed-by-minimax", "model:minimax-m25", "company:minimax", "DEVELOPED_BY",
               ["src:mthreads-minimax"], "MiniMax新一代大模型MiniMax M2.5", "2026-02-14"),
         ],
         "events": [{"id": "event:mtt-minimax-adapt", "title": "MTT S5000 完成 MiniMax-M2.5 Day-0 适配",
                     "date": "2026-02-14", "event_at": "2026-02-14", "disclosed_at": "2026-02-14",
                     "type": "PRODUCT_ADAPTATION",
                     "summary": "摩尔线程在 MTT S5000 上完成 MiniMax-M2.5 的 Day-0 极速适配。",
                     "entity_id": "model:minimax-m25", "source_ids": ["src:mthreads-minimax"],
                     "properties": {"timezone": "Asia/Shanghai"}}],
     }},
]

# ---------------------------------------------------------------- market series
STOCKS = {
    "02513.HK": ("hk02513", "智谱", "HKD", "HK", "HSI"),
    "688795.SH": ("sh688795", "摩尔线程-U", "CNY", "SH", "000688.SH"),
    "00100.HK": ("hk00100", "MINIMAX-W", "HKD", "HK", "HSI"),
    "09988.HK": ("hk09988", "阿里巴巴-W", "HKD", "HK", "HSI"),
}
BENCHMARKS = {
    "HSI": ("hkHSI", "恒生指数", "HKD", "HK"),
    "000688.SH": ("sh000688", "科创50", "CNY", "SH"),
}

LISTING_DATES = {
    "02513.HK": "2026-01-08", "688795.SH": "2025-12-05", "00100.HK": "2026-01-09",
    "09988.HK": "2019-11-26", "688041.SH": "2022-08-12", "00700.HK": "2004-06-16",
    "09888.HK": "2021-03-23", "00728.HK": "2002-11-15",
}


def fetch(symbol: str, refresh: bool = False) -> tuple[str, bytes]:
    url = ("https://web.ifzq.gtimg.cn/appstock/app/fqkline/get?"
           f"param={symbol},day,2024-12-01,2026-03-31,500,qfq")
    cached = RAW / f"tencent_{symbol}_2024-12_2026Q1.json"
    if cached.exists() and not refresh:
        body = cached.read_bytes()
        assert symbol in json.loads(body)["data"], f"Invalid cached response: {symbol}"
        return url, body
    last = None
    for attempt in range(5):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(request, timeout=40) as response:
                return url, response.read()
        except Exception as exc:  # network only; never synthesise prices
            last = exc
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"行情下载失败：{symbol}: {last}")


def build_market(refresh=False):
    RAW.mkdir(parents=True, exist_ok=True)
    MARKET.mkdir(parents=True, exist_ok=True)
    manifest = []
    previous_path = MARKET / "manifest.json"
    previous = {item["symbol"]: item for item in json.loads(previous_path.read_text(encoding="utf-8-sig"))} if previous_path.exists() else {}
    for symbol, (tencent, name, currency, market, benchmark) in STOCKS.items():
        cached = (RAW / f"tencent_{tencent}_2024-12_2026Q1.json").exists() and not refresh
        url, body = fetch(tencent, refresh)
        (RAW / f"tencent_{tencent}_2024-12_2026Q1.json").write_bytes(body)
        payload = json.loads(body)["data"][tencent]
        rows = payload.get("qfqday") or payload["day"]
        path = MARKET / f"{symbol}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["date", "open", "high", "low", "close", "volume"])
            for row in rows:  # Tencent order: date, open, close, high, low, volume
                writer.writerow([row[0], row[1], row[3], row[4], row[2], row[5]])
        manifest.append({"symbol": symbol, "name": name, "currency": currency, "market": market,
                         "file": f"market/{symbol}.csv",
                         "provider": "Tencent Finance · ifzq.gtimg.cn qfq daily",
                         "url": url, "adjusted": "qfq", "benchmark_symbol": benchmark,
                         "is_benchmark": False, "listing_date": LISTING_DATES.get(symbol, ""),
                         "volume_unit": "provider_native",
                         "retrieved_at": previous.get(symbol, {}).get("retrieved_at", RETRIEVED_AT) if cached else RETRIEVED_AT})
    for symbol, (tencent, name, currency, market) in BENCHMARKS.items():
        cached = (RAW / f"tencent_{tencent}_2024-12_2026Q1.json").exists() and not refresh
        url, body = fetch(tencent, refresh)
        (RAW / f"tencent_{tencent}_2024-12_2026Q1.json").write_bytes(body)
        payload = json.loads(body)["data"][tencent]
        rows = payload.get("qfqday") or payload["day"]
        path = MARKET / f"{symbol}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(["date", "open", "high", "low", "close", "volume"])
            for row in rows:
                writer.writerow([row[0], row[1], row[3], row[4], row[2], row[5]])
        manifest.append({"symbol": symbol, "name": name, "currency": currency, "market": market,
                         "file": f"market/{symbol}.csv",
                         "provider": "Tencent Finance · ifzq.gtimg.cn index daily",
                         "url": url, "adjusted": "index", "benchmark_symbol": None,
                         "is_benchmark": True, "listing_date": None, "volume_unit": "provider_native",
                         "retrieved_at": previous.get(symbol, {}).get("retrieved_at", RETRIEVED_AT) if cached else RETRIEVED_AT})
    (MARKET / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return manifest


def write_json(path: Path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def validate(graph, sources, samples, manifest):
    node_ids = [node["id"] for node in graph["nodes"]]
    edge_ids = [edge["id"] for edge in graph["edges"]]
    assert len(node_ids) == len(set(node_ids)), "重复节点 ID"
    assert len(edge_ids) == len(set(edge_ids)), "重复边 ID"
    assert node_ids and edge_ids, "图谱必须包含实际实体与关系"
    assert len(sources) >= 2, "多源融合至少需要两份来源"
    assert 2 <= sum(e["type"] == "MODEL_RELEASE" for e in graph["events"]) <= 6
    node_map = {node["id"]: node for node in graph["nodes"]}
    source_map = {source["id"]: source for source in sources}
    for node in graph["nodes"]:
        assert node["type"] in NODE_TYPES, node["id"]
        assert node["source_ids"] and set(node["source_ids"]) <= set(source_map), node["id"]
    for edge in graph["edges"]:
        assert edge["source"] in node_map and edge["target"] in node_map, edge["id"]
        assert edge["type"] in RELATION_SCHEMA, edge["type"]
        rule = RELATION_SCHEMA[edge["type"]]
        assert node_map[edge["source"]]["type"] in rule[0], edge["id"]
        assert node_map[edge["target"]]["type"] in rule[1], edge["id"]
        assert edge["evidence"].strip() and edge["disclosed_at"], edge["id"]
        assert set(edge["source_ids"]) <= set(source_map), edge["id"]
        assert edge["relation_group"] in {"direct", "adaptation", "industry", "distribution"}, edge["id"]
    for event in graph["events"]:
        assert event["entity_id"] in node_map, event["id"]
        assert set(event["source_ids"]) <= set(source_map), event["id"]
    for sample in samples:
        assert sample["document_id"] in source_map, sample["id"]
        text = sample["text"]
        for relation in sample["extraction"]["relations"]:
            assert relation["evidence"] in text, f"样例证据不在文本中: {sample['id']} / {relation['id']}"
            assert relation["source"] in node_map or relation["source"].startswith("event:")
    for item in manifest:
        path = DATA / item["file"]
        assert path.exists(), item["file"]
        rows = list(csv.DictReader(path.open(encoding="utf-8")))
        dates = [row["date"] for row in rows]
        assert dates == sorted(set(dates)), f"{item['symbol']} 日期乱序或重复"
        for row in rows:
            low, high = float(row["low"]), float(row["high"])
            assert low <= min(float(row["open"]), float(row["close"])) <= max(float(row["open"]), float(row["close"])) <= high, row
            assert float(row["close"]) > 0 and float(row["volume"]) >= 0
        assert len(rows) >= 40, f"{item['symbol']} 行数不足"
        if not item["is_benchmark"]:
            spec = item
            benchmark = spec["benchmark_symbol"]
            assert benchmark in {x["symbol"] for x in manifest}, benchmark
    return {"nodes": len(node_ids), "edges": len(edge_ids), "events": len(graph["events"]),
            "sources": len(sources), "stocks": sum(1 for x in manifest if not x["is_benchmark"]),
            "series": len(manifest)}


def main():
    parser = argparse.ArgumentParser(description="Rebuild from the delivered factual snapshot and cached real prices")
    parser.add_argument("--refresh", action="store_true", help="Download fresh market responses instead of using data/raw caches")
    args = parser.parse_args()
    existing_sources_path = DATA / "sources.json"
    if existing_sources_path.exists():
        previous_sources = {s["id"]: s for s in json.loads(existing_sources_path.read_text(encoding="utf-8-sig"))}
        for source in SOURCES:
            if source["id"] in previous_sources and previous_sources[source["id"]].get("retrieved_at"):
                source["retrieved_at"] = previous_sources[source["id"]]["retrieved_at"]
    STOCKS.update(EXTRA_STOCKS)
    BENCHMARKS.update(EXTRA_BENCHMARKS)
    sources = SOURCES + EXTRA_SOURCES
    nodes = NODES + EXTRA_NODES
    edges = EDGES + EXTRA_EDGES
    events = EVENTS + EXTRA_EVENTS
    samples = SAMPLES + EXTRA_SAMPLES
    for edge in edges:
        if edge["id"] == "rel:glm5-developed-by-zhipu":
            edge["evidence_records"] = [
                {"source_ids": ["src:bigmodel-glm5"], "evidence": "GLM-5 是智谱的基座模型", "disclosed_at": "2026-11-06"},
                {"source_ids": ["src:zai-glm5"],
                 "evidence": "GLM-4.5 is our first step for reasoning, coding, and agent, enabling the model to complete complex tasks. With GLM-5, we further enhance complex systems engineering and long-horizon agent capabilities.",
                 "disclosed_at": "2026-02-12"},
            ]
        if edge["id"] in {"rel:qwen3-235b-developed-by-alibaba", "rel:qwen3-30b-developed-by-alibaba"}:
            edge["attribution_scope"] = "Qwen3 series-level; official Alibaba Cloud press release 2025-04-29 lists the 30B/235B MoE variants"
    graph = {
        "meta": {"title": "FinGraph", "as_of": "2026-11-07",
                 "description": "以 DeepSeek-R1、Qwen3、GLM-5 与 MiniMax-M2.5 等真实事件为线索，区分模型研发、硬件适配与云服务接入，连接上市公司、证券与证据路径。行情为 2024-12 至 2026-03 的真实日线缓存。"},
        "nodes": nodes, "edges": edges, "events": events,
    }
    write_json(DATA / "knowledge_graph.json", graph)
    write_json(DATA / "sources.json", sources)
    write_json(DATA / "extraction_samples.json", samples)
    write_json(DATA / "extraction_eval.json", EXTRACTION_EVAL)
    print("JSON written:", len(nodes), "nodes,", len(edges), "edges,", len(events), "events,", len(sources), "sources")
    manifest = build_market(refresh=args.refresh)
    print("Market written:", len(manifest), "series")
    print("VALIDATION:", validate(graph, sources, samples, manifest))


if __name__ == "__main__":
    main()
