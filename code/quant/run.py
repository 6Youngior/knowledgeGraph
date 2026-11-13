"""Train a Qlib Alpha158/LightGBM baseline and run Qlib's own backtest.

This is a reproducible research baseline, not a live trading service. Current
universe selection and price snapshots are explicitly recorded limitations.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from pathlib import Path

from quant.data import prepare_market, purged_segments


def run(source, output, *, horizon=5, train_end="2024-12-31", valid_end="2025-12-31", rounds=120):
    import numpy as np
    import pandas as pd
    import qlib
    from qlib.contrib.data.handler import Alpha158
    from qlib.contrib.evaluate import backtest_daily, risk_analysis
    from qlib.contrib.eva.alpha import calc_ic
    from qlib.contrib.model.gbdt import LGBModel
    from qlib.contrib.strategy import TopkDropoutStrategy
    from qlib.data import D
    from qlib.data.dataset import DatasetH
    from qlib.data.dataset.handler import DataHandlerLP
    from qlib.workflow import R
    from quant.strategies import EqualWeightUniverse

    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    capture, calendar = prepare_market(source, output / "qlib_data")
    if len(capture["stocks"]) < 5:
        raise ValueError("at least five securities are needed for this ranking baseline")
    boundaries = {"train": (str(calendar[min(80, len(calendar) - 1)].date()), train_end),
                  "valid": (str((pd.Timestamp(train_end) + pd.Timedelta(days=1)).date()), valid_end),
                  "test": (str((pd.Timestamp(valid_end) + pd.Timedelta(days=1)).date()), capture["data_end"])}
    segments = purged_segments(calendar, boundaries, horizon)
    os.environ.setdefault("MLFLOW_ALLOW_FILE_STORE", "true")
    qlib.init(provider_uri=str(output / "qlib_data"), region="cn", kernels=1,
              expression_cache=None, dataset_cache=None, logging_level=logging.WARNING,
              exp_manager={"class": "MLflowExpManager", "module_path": "qlib.workflow.expm",
                           "kwargs": {"uri": (output / "mlruns").as_uri(), "default_exp_name": "fingraph"}})
    instruments = [row["qlib_symbol"] for row in capture["stocks"]]
    # Confirm the adapter can actually be read through Qlib before training.
    readback = D.features(instruments, ["$close"], start_time=capture["data_start"], end_time=capture["data_end"])
    if readback.empty:
        raise RuntimeError("Qlib could not read the prepared provider")
    expression = f"Ref($close, -{horizon + 1}) / Ref($close, -1) - 1"
    handler = Alpha158(instruments=instruments, start_time=capture["data_start"], end_time=capture["data_end"],
                       fit_start_time=segments["train"][0], fit_end_time=segments["train"][1],
                       label=([expression], ["LABEL0"]))
    dataset = DatasetH(handler=handler, segments=segments)
    model = LGBModel(num_boost_round=rounds, early_stopping_rounds=15, learning_rate=0.05,
                     num_leaves=15, min_data_in_leaf=100, num_threads=4, verbosity=-1,
                     seed=1729, deterministic=True, force_col_wise=True)
    with R.start(experiment_name="fingraph_baseline", uri=(output / "mlruns").as_uri()):
        model.fit(dataset, verbose_eval=0)
        prediction = model.predict(dataset, "test").rename("score")
    if prediction.empty or not np.isfinite(prediction).all():
        raise RuntimeError("invalid Qlib predictions")
    # Eligibility uses the feature day's known bar, never the future label.
    observed = readback["$close"].swaplevel().reindex(prediction.index).notna()
    prediction = prediction[observed]
    model.model.save_model(str(output / "lightgbm.txt"))
    labels = dataset.prepare("test", col_set="label", data_key=DataHandlerLP.DK_I).iloc[:, 0].rename("forward_return")
    evaluated_labels = labels.reindex(prediction.index)
    ic, rank_ic = calc_ic(prediction, evaluated_labels, dropna=True)
    pd.concat([prediction, evaluated_labels], axis=1).to_csv(output / "test_predictions.csv", lineterminator="\n")
    pd.concat([ic.rename("ic"), rank_ic.rename("rank_ic")], axis=1).to_csv(output / "daily_ic.csv", lineterminator="\n")
    # Sparse weekly decisions; Qlib's strategy uses the prior session signal
    # and executes at the next close, rather than trading on the feature bar.
    decision_days = prediction.index.get_level_values("datetime").unique().sort_values()[::horizon]
    sparse = prediction[prediction.index.get_level_values("datetime").isin(decision_days)]
    topk = min(8, max(2, len(instruments) // 4))
    strategy = TopkDropoutStrategy(signal=sparse, topk=topk, n_drop=topk)
    first_trade = calendar[calendar.get_loc(decision_days[0]) + 1]
    execution = dict(
        start_time=str(first_trade.date()), end_time=str(calendar[-2].date()),
        account=1_000_000, benchmark="SH000300", exchange_kwargs={
            "deal_price": "close", "limit_threshold": None,
            "open_cost": 0.001, "close_cost": 0.001, "min_cost": 5,
        })
    report, _ = backtest_daily(strategy=strategy, **execution)
    report.to_csv(output / "backtest.csv", lineterminator="\n")
    net = report["return"] - report["cost"]
    equity = (1 + net).cumprod()
    np.testing.assert_allclose(equity, report["account"] / 1_000_000, rtol=1e-8)
    # Align benchmark capital deployment with the first executable close.
    benchmark_returns = report["bench"].copy()
    benchmark_returns.iloc[0] = 0
    benchmark_equity = (1 + benchmark_returns).cumprod()
    risks = risk_analysis(net, N=252, freq=None, mode="product")["risk"].to_dict()
    risks = {str(k): float(v) if pd.notna(v) else None for k, v in risks.items()}
    # Controls use identical dates, execution engine, capital and fee settings.
    # The equal-weight policy tests whether an apparent gain just reflects the
    # retrospectively selected AI sector; momentum uses the same top-eight rule.
    close = readback["$close"].unstack("instrument")
    momentum = close.div(close.shift(20)).sub(1).stack().reindex(sparse.index).dropna()
    controls, control_curves = {}, {}
    policies = {"ai_equal_weight": EqualWeightUniverse(signal=sparse),
                "momentum_20d": TopkDropoutStrategy(signal=momentum, topk=topk, n_drop=topk)}
    for name, policy in policies.items():
        comparison, _ = backtest_daily(strategy=policy, **execution)
        comparison.to_csv(output / f"backtest_{name}.csv", lineterminator="\n")
        comparison_net = comparison["return"] - comparison["cost"]
        comparison_equity = (1 + comparison_net).cumprod()
        np.testing.assert_allclose(comparison_equity, comparison["account"] / 1_000_000, rtol=1e-8)
        if not comparison.index.equals(report.index):
            raise RuntimeError("control backtest dates differ")
        control_curves[name] = comparison_equity
        controls[name] = {"net_cumulative_return": float(comparison_equity.iloc[-1] - 1),
                          "max_drawdown": float((comparison_equity / comparison_equity.cummax() - 1).min()),
                          "trading_days_with_cost": int((comparison.cost > 0).sum())}
    latest = handler.fetch(selector=slice(capture["data_end"], capture["data_end"]),
                           col_set="feature", data_key=DataHandlerLP.DK_I)
    current_close = readback.loc[(slice(None), pd.Timestamp(capture["data_end"])), :].dropna()
    active = set(current_close.index.get_level_values("instrument"))
    latest = latest[latest.index.get_level_values("instrument").isin(active)]
    scores = pd.Series(model.model.predict(latest.to_numpy()), index=latest.index)
    ties = scores.rank(method="min", ascending=False).astype(int)
    names = {r["qlib_symbol"]: r for r in capture["stocks"]}
    ranking = [{"rank": int(ties.loc[index]), "symbol": names[index[1]]["symbol"], "name": names[index[1]]["name"],
                "score": float(score)} for index, score in scores.items()]
    ranking.sort(key=lambda row: (-row["score"], row["symbol"]))
    curve = [{"date": str(d.date()), "strategy": float(equity.loc[d]),
              "benchmark": float(benchmark_equity.loc[d]),
              **{name: float(values.loc[d]) for name, values in control_curves.items()}} for d in report.index]
    result = {"schema_version": "quant-baseline-v1", "engine": "Qlib", "qlib_version": qlib.__version__,
              "created_at": datetime.now(timezone.utc).isoformat(),
              "available_at": datetime.now(ZoneInfo("Asia/Shanghai")).date().isoformat(),
              "model": "Alpha158 / LightGBM", "horizon_trading_days": horizon,
              "training": {"seed": 1729, "max_rounds": rounds, "best_iteration": model.model.best_iteration,
                           "early_stopping_rounds": 15, "learning_rate": 0.05, "num_leaves": 15,
                           "min_data_in_leaf": 100, "label_transform": "per-date cross-sectional z-score",
                           "infer_processors": []},
              "feature_as_of": capture["data_end"], "capture": capture, "segments": segments,
              "label_expression": expression, "test_predictions": len(prediction),
              "test_valid_labels": int(labels.reindex(prediction.index).notna().sum()),
              "raw_valid_labels": int(labels.notna().sum()),
              "ic_mean": float(ic.mean()), "rank_ic_mean": float(rank_ic.mean()),
              "risk_after_assumed_cost": risks, "backtest_days": len(report),
              "backtest_start": str(report.index[0].date()), "backtest_end": str(report.index[-1].date()),
              "net_cumulative_return": float(equity.iloc[-1] - 1),
              "final_day_net_return": float(net.iloc[-1]),
              "cumulative_ex_final_day": float(equity.iloc[-2] - 1),
              "benchmark_cumulative_return": float(benchmark_equity.iloc[-1] - 1),
              "curve": curve,
              "controls": controls,
              "execution": {"account_cny": 1_000_000, "target_risk_degree": 0.95,
                            "deal_price": "next_session_close", "trade_unit": 100,
                            "historical_price_limits": False},
              "total_cost_fraction_sum": float(report.cost.sum()), "topk": topk,
              "rebalance_sessions": horizon, "trading_days_with_cost": int((report.cost > 0).sum()),
              "cost_assumption": {"open_rate": 0.001, "close_rate": 0.001, "min_cost_cny": 5},
              "score_type": "relative ranking score; not a return or probability",
              "latest_ranking": ranking,
              "limitations": ["Current AI universe selected retrospectively; not historical membership.",
                              "Current adjusted snapshot, not a vintage reconstruction.",
                              "Price-volume baseline only; no graph or historical financial features yet.",
                              "No historical daily price-limit/ST metadata: execution model is simplified.",
                              "Costs are explicit simulation assumptions, not a broker fee schedule.",
                              "Frozen model and historical snapshot ranking, not live trading."]}
    (output / "result.json").write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
                                         encoding="utf-8", newline="\n")
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--horizon", type=int, choices=[5, 20], default=5)
    parser.add_argument("--rounds", type=int, default=120)
    args = parser.parse_args()
    result = run(args.source, args.output, horizon=args.horizon, rounds=args.rounds)
    print(json.dumps({k: v for k, v in result.items() if k not in {"capture", "latest_ranking", "curve"}}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
