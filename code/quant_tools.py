"""Read published Qlib results without importing the optional quant stack."""
from __future__ import annotations

import hashlib
import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

CHINA = ZoneInfo("Asia/Shanghai")


class QuantResearch:
    def __init__(self, path: Path, as_of=None):
        self.path = Path(path)
        self.as_of = as_of or datetime.now(CHINA).date().isoformat()
        if date.fromisoformat(self.as_of).isoformat() != self.as_of:
            raise ValueError("研究日期必须是 YYYY-MM-DD")
        if self.as_of > datetime.now(CHINA).date().isoformat():
            raise ValueError("研究日期不能晚于今天")

    def analyze(self, view="ranking", limit=10, *, include_curve=False):
        if view not in {"overview", "ranking", "backtest"}:
            raise ValueError("view must be overview, ranking or backtest")
        hidden = {"as_of": self.as_of, "found": False, "view": view}
        if not self.path.is_file():
            return hidden
        if self.path.stat().st_size > 2_000_000:
            raise ValueError("quant result exceeds the supported size")
        content = self.path.read_bytes()
        def reject_nonfinite(value):
            raise ValueError("non-finite quant result")
        result = json.loads(content, parse_constant=reject_nonfinite)
        if result.get("schema_version") != "quant-baseline-v1":
            raise ValueError("unsupported quant result")
        available = result.get("available_at", "")
        if not available or date.fromisoformat(available).isoformat() != available or available > self.as_of:
            return hidden
        if result["feature_as_of"] > self.as_of:
            return hidden
        shared = {"as_of": self.as_of, "found": True, "view": view,
                  "experiment_id": hashlib.sha256(content).hexdigest()[:16],
                  "model": result["model"], "engine": result["engine"],
                  "feature_as_of": result["feature_as_of"], "available_at": available,
                  "horizon_trading_days": result["horizon_trading_days"],
                  "universe_size": len(result["capture"]["stocks"]),
                  "segments": result["segments"],
                  "status": "量价研究基线；当前股票池的历史回放，尚未加入图谱预测特征。"}
        if view == "ranking":
            count = max(1, min(int(limit), 50))
            return {**shared, "ranking": result["latest_ranking"][:count],
                    "score_type": "相对排序得分，不是上涨概率或预期收益率；相同得分并列。",
                    "note": "基于所列行情快照和固定模型，不是实时交易信号。"}
        if view == "backtest":
            curve = result["curve"]
            sampled = curve if include_curve else curve[::20]
            if sampled and sampled[-1] != curve[-1]:
                sampled = [*sampled, curve[-1]]
            return {**shared, "start": result["backtest_start"], "end": result["backtest_end"],
                    "test_predictions": result["test_predictions"],
                    "test_valid_labels": result.get("test_valid_labels"),
                    "ic_mean": result["ic_mean"], "rank_ic_mean": result["rank_ic_mean"],
                    "net_cumulative_return": result["net_cumulative_return"],
                    "final_day_net_return": result.get("final_day_net_return"),
                    "cumulative_ex_final_day": result.get("cumulative_ex_final_day"),
                    "benchmark_cumulative_return": result["benchmark_cumulative_return"],
                    "max_drawdown": result["risk_after_assumed_cost"]["max_drawdown"],
                    "topk": result["topk"], "rebalance_sessions": result["rebalance_sessions"],
                    "cost_assumption": result["cost_assumption"], "curve": sampled,
                    "controls": result.get("controls", {}), "execution": result.get("execution", {}),
                    "limitations": ["证券池按当前 AI 公司选择，含事后选池偏差。",
                                    "使用当前复权快照，未重建历史涨跌停与 ST 状态，成交模型简化。",
                                    "费用为统一模拟假设；尚不能据此认定具有可实盘复现的选股收益。"]}
        return shared
