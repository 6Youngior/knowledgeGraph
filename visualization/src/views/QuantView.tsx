import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { EChartsOption } from 'echarts';
import { Activity, AlertCircle, RefreshCw } from 'lucide-react';
import { api, errorMessage } from '../api';
import { EChart } from '../components/EChart';
import { Skeleton } from '../components/Ui';
import { formatDate, formatNumber, formatPercent, formatSignedNumber } from '../lib/format';
import type { QuantBacktest, QuantRanking } from '../types';

function returnText(value: number | undefined) {
  return value === undefined ? '—' : formatPercent(value, 2);
}

function metric(value: number | undefined, digits = 4) {
  return value === undefined ? '—' : formatSignedNumber(value, digits);
}

function rateText(value: number | undefined) {
  return value === undefined ? '—' : `${(value * 100).toFixed(2)}%`;
}

export function QuantView() {
  const rankingQuery = useQuery({
    queryKey: ['quant', 'ranking', 50],
    queryFn: () => api.quant('ranking', 50),
    retry: 1,
  });
  const backtestQuery = useQuery({
    queryKey: ['quant', 'backtest', 30],
    queryFn: () => api.quant('backtest', 30),
    retry: 1,
  });

  const ranking = rankingQuery.data as QuantRanking | undefined;
  const backtest = backtestQuery.data as QuantBacktest | undefined;
  const found = Boolean(ranking?.found || backtest?.found);
  const loading = rankingQuery.isLoading || backtestQuery.isLoading;
  const error = rankingQuery.error || backtestQuery.error;
  const rows = ranking?.ranking ?? [];
  const universeSize = ranking?.universe_size ?? backtest?.universe_size;
  const featureAsOf = ranking?.feature_as_of ?? backtest?.feature_as_of;
  const availableAt = ranking?.available_at ?? backtest?.available_at;
  const horizon = ranking?.horizon_trading_days ?? backtest?.horizon_trading_days;
  const model = ranking?.model ?? backtest?.model;
  const curve = backtest?.curve ?? [];

  const chartOption = useMemo<EChartsOption>(() => ({
    animationDuration: 250,
    color: ['#b07a25', '#3b7f8c', '#9973a6', '#8e99a7'],
    grid: { left: 45, right: 18, top: 58, bottom: 34 },
    legend: {
      top: 0,
      right: 4,
      itemWidth: 16,
      itemHeight: 3,
      textStyle: { color: '#64748b', fontSize: 13 },
      data: ['量价模型', '同池等权', '20日动量', '沪深300'],
    },
    tooltip: {
      trigger: 'axis',
      valueFormatter: (value) => (typeof value === 'number' ? value.toFixed(4) : String(value ?? '—')),
      textStyle: { fontSize: 13 },
    },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: curve.map((point) => point.date),
      axisLine: { lineStyle: { color: '#dbe3eb' } },
      axisTick: { show: false },
      axisLabel: {
        color: '#788594',
        fontSize: 12,
        formatter: (value: string) => value.slice(5),
      },
    },
    yAxis: {
      type: 'value',
      name: '净值',
      scale: true,
      nameTextStyle: { color: '#788594', fontSize: 12 },
      splitLine: { lineStyle: { color: '#eef2f6' } },
      axisLabel: { color: '#788594', fontSize: 12 },
    },
    series: [
      {
        name: '量价模型',
        type: 'line',
        showSymbol: false,
        smooth: false,
        lineStyle: { width: 2 },
        data: curve.map((point) => point.strategy),
      },
      {
        name: '同池等权', type: 'line', showSymbol: false,
        lineStyle: { width: 1.5 }, data: curve.map((point) => point.ai_equal_weight ?? null),
      },
      {
        name: '20日动量', type: 'line', showSymbol: false,
        lineStyle: { width: 1.5 }, data: curve.map((point) => point.momentum_20d ?? null),
      },
      {
        name: '沪深300',
        type: 'line',
        showSymbol: false,
        smooth: false,
        lineStyle: { width: 1.5 },
        data: curve.map((point) => point.benchmark),
      },
    ],
  }), [curve]);

  if (loading) {
    return (
      <div className="quant-page">
        <Skeleton height={32} width="38%" />
        <Skeleton height={86} />
        <Skeleton height={360} />
      </div>
    );
  }

  if (!found) {
    return (
      <div className="quant-page">
        <header className="quant-header">
          <div>
            <span className="quant-kicker">量化研究</span>
            <h1>AI 股票量化研究</h1>
            <p>当前没有可用的量化研究结果。</p>
          </div>
        </header>
        <div className="quant-empty panel">
          <AlertCircle size={24} />
          <div>
            <strong>暂无可发布结果</strong>
            <p>{error ? errorMessage(error) : '所选日期还没有可用的实验结果。'}</p>
          </div>
          <button type="button" className="button ghost small" onClick={() => { rankingQuery.refetch(); backtestQuery.refetch(); }}>
            <RefreshCw size={14} /> 重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="quant-page">
      <header className="quant-header">
        <div>
          <span className="quant-kicker">量化研究</span>
          <h1>AI 股票量化研究</h1>
          <p>芯片、服务器、光互联等 {universeSize ?? '—'} 只 A 股的模型排序与历史回测。</p>
        </div>
        <div className="quant-status">
          <span className="quant-status-dot" />
          <div><strong>量价基线</strong><small>{backtest?.engine ?? 'Qlib'}</small></div>
        </div>
      </header>

      <div className="quant-meta">
        <span>模型 <b>{model ?? '—'}</b></span>
        <span>股票池 <b>{formatNumber(universeSize)} 只 A 股</b></span>
        <span>行情截止 <b>{formatDate(featureAsOf)}</b></span>
        <span>结果可用 <b>{formatDate(availableAt)}</b></span>
        <span>排序窗口 <b>未来 {horizon ?? '—'} 个交易日</b></span>
      </div>

      <div className="quant-scope-note">
        <Activity size={14} />
        <span>量价基线，图谱特征尚未加入。</span>
        <small>特征日收盘后形成排序，下一交易日收盘成交。</small>
      </div>

      <section className="quant-metrics" aria-label="量化指标">
        <div><span>量价组合净收益</span><b className={(backtest?.net_cumulative_return ?? 0) >= 0 ? 'up' : 'down'}>{returnText(backtest?.net_cumulative_return)}</b><small>扣除模拟交易费用</small></div>
        <div><span>沪深300</span><b className={(backtest?.benchmark_cumulative_return ?? 0) >= 0 ? 'up' : 'down'}>{returnText(backtest?.benchmark_cumulative_return)}</b><small>同区间基准</small></div>
        <div><span>平均 Rank IC</span><b>{metric(backtest?.rank_ic_mean)}</b><small>接近零，排序能力尚不明显</small></div>
        <div><span>最大回撤</span><b className="down">{returnText(backtest?.max_drawdown)}</b><small>成本后</small></div>
      </section>

      <div className="quant-main-grid">
        <section className="panel quant-chart-panel">
          <div className="panel-head">
            <div>
              <span className="panel-kicker">历史回放</span>
              <h2>组合净值对比</h2>
            </div>
            <span className="quant-range">{formatDate(backtest?.start)} 至 {formatDate(backtest?.end)}</span>
          </div>
          {curve.length ? (
            <EChart option={chartOption} className="quant-chart" />
          ) : (
            <div className="quant-inline-empty">回测曲线暂不可用。</div>
          )}
          <div className="quant-chart-foot">
            <span>持仓前 {backtest?.topk ?? '—'} 名 · 每 {backtest?.rebalance_sessions ?? '—'} 个交易日调仓</span>
            <span>成本假设：开仓 {rateText(backtest?.cost_assumption?.open_rate)} / 平仓 {rateText(backtest?.cost_assumption?.close_rate)}</span>
          </div>
          <div className="quant-comparisons">
            {([['ai_equal_weight', '同池等权'], ['momentum_20d', '20日动量']] as const).map(([key, label]) => (
              <div key={key}><span>{label}净收益</span><strong>{returnText(backtest?.controls?.[key]?.net_cumulative_return)}</strong></div>
            ))}
          </div>
        </section>

        <section className="panel quant-ranking-panel">
          <div className="panel-head">
            <div>
              <span className="panel-kicker">五日相对收益预测</span>
              <h2>量价排序</h2>
            </div>
            <span className="quant-range">{rows.length} / {formatNumber(universeSize)}</span>
          </div>
          <div className="quant-table-wrap">
            <table className="quant-table">
              <thead>
                <tr><th>排名</th><th>证券</th><th>代码</th><th className="num">得分</th></tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.symbol}>
                    <td className="rank">{row.rank}</td>
                    <td><strong>{row.name}</strong></td>
                    <td className="mono symbol">{row.symbol}</td>
                    <td className="num mono">{row.score.toFixed(6)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            {rows.length === 0 ? <div className="quant-inline-empty">没有可显示的排序记录。</div> : null}
          </div>
          <p className="quant-table-note">
            相对排序得分；同分并列，不代表上涨概率。
          </p>
        </section>
      </div>

      <details className="quant-details">
        <summary>实验设置与数据范围</summary>
        <div className="quant-details-grid">
          <div>
            <h3>时间划分</h3>
            <p>模型：{model ?? '—'} · 引擎：{backtest?.engine ?? '—'}</p>
            <p>测试预测：{formatNumber(backtest?.test_predictions)} 条 · IC：{metric(backtest?.ic_mean)}</p>
            {Object.entries(backtest?.segments ?? {}).map(([key, value]) => <p key={key}>{({ train: '训练', valid: '验证', test: '测试' } as Record<string, string>)[key] ?? key}：{value[0]} 至 {value[1]}</p>)}
          </div>
          <div>
            <h3>数据与成交假设</h3>
            <p>三组组合使用相同日期、初始资金和模拟费用；期末按收盘市值计价，未强制平仓。</p>
            {backtest?.limitations?.slice(0, 3).map((item) => <p key={item}>{item}</p>)}
          </div>
        </div>
      </details>
    </div>
  );
}
