import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import type { EChartsOption } from 'echarts';
import { CalendarClock, ExternalLink, LineChart, TrendingDown, TrendingUp } from 'lucide-react';
import { api } from '../api';
import type { MarketData, PricePoint, RelatedStock } from '../types';
import { EmptyState, ErrorState, Skeleton, Spinner } from './Ui';
import { EChart } from './EChart';
import { formatDate, formatNumber, formatPercent, trendClass } from '../lib/format';

function formatPp(value: number | null | undefined): string {
  if (value === null || value === undefined) return '—';
  const pp = value * 100;
  return `${pp > 0 ? '+' : ''}${pp.toFixed(2)} pp`;
}

function normalizedPercent(prices: PricePoint[], key: 'normalized' | 'benchmark_normalized') {
  return prices.map((point) => {
    const value = point[key];
    return value === null || value === undefined ? null : value - 100;
  });
}

function returnAt(prices: PricePoint[], key: 'normalized' | 'benchmark_normalized', day: number) {
  const point = prices.find((item) => item.relative_day === day);
  const value = point?.[key];
  return value === null || value === undefined ? null : value / 100 - 1;
}

export function MarketChart({
  stock,
  eventId,
  asOf,
  onChangeAsOf,
}: {
  stock: RelatedStock | null;
  eventId: string;
  asOf: string;
  onChangeAsOf: (value: string) => void;
}) {
  const [windowDays, setWindowDays] = useState(5);
  const market = useQuery({
    queryKey: ['market', stock?.symbol, eventId, windowDays, asOf],
    queryFn: () => api.market(stock?.symbol ?? '', eventId, windowDays, asOf || undefined),
    enabled: Boolean(stock?.symbol && eventId && stock.listed_at_event !== false),
    retry: 1,
  });
  const data = market.data;

  const rows = useMemo(() => {
    if (!data) return [];
    return (['1', '3', '5'] as const).map((horizon) => {
      const day = Number(horizon) - 1;
      const stockReturn = data.returns?.[horizon] ?? returnAt(data.prices, 'normalized', day);
      const benchmarkReturn =
        data.benchmark_returns?.[horizon] ??
        (data.benchmark ? returnAt(data.prices, 'benchmark_normalized', day) : null);
      const excess =
        data.excess_returns?.[horizon] ??
        (stockReturn !== null && benchmarkReturn !== null ? stockReturn - benchmarkReturn : null);
      return { horizon, stockReturn, benchmarkReturn, excess };
    });
  }, [data]);

  const option = useMemo<EChartsOption | null>(() => {
    if (!data || data.prices.length === 0) return null;
    const dates = data.prices.map((item) => item.date);
    const stockSeries = normalizedPercent(data.prices, 'normalized');
    const benchmarkSeries = normalizedPercent(data.prices, 'benchmark_normalized');

    return {
      animationDuration: 450,
      grid: { left: 44, right: 16, top: 28, bottom: 26 },
      tooltip: {
        trigger: 'axis', renderMode: 'richText', confine: true,
        backgroundColor: '#ffffff', borderColor: '#d7e0e8',
        textStyle: { color: '#33475b', fontSize: 13 },
        formatter: (params: unknown) => {
          const list = (Array.isArray(params) ? params : [params]) as Array<{ dataIndex: number; value: number | null }>;
          const point = data.prices[list[0]?.dataIndex ?? 0];
          if (!point) return '';
          const fmt = (value: number | null | undefined) => value === null || value === undefined ? '—' : (value > 0 ? '+' : '') + value.toFixed(2) + '%';
          return [
            point.date + '  T' + (point.relative_day >= 0 ? '+' : '') + point.relative_day,
            data.name + '  ' + fmt(list[0]?.value),
            data.benchmark ? data.benchmark.name + '  ' + fmt(list[1]?.value) : '',
            '收盘 ' + (point.close ?? '—') + ' ' + data.currency,
          ].filter(Boolean).join('\n');
        },
      },
      xAxis: {
        type: 'category',
        data: dates,
        boundaryGap: false,
        axisLine: { lineStyle: { color: '#e2e8f0' } },
        axisTick: { show: false },
        axisLabel: { color: '#94a3b8', fontSize: 12, formatter: (value: string) => value.slice(5) },
      },
      yAxis: {
        type: 'value',
        scale: true,
        axisLabel: { color: '#94a3b8', fontSize: 12, formatter: (value: number) => `${value.toFixed(0)}%` },
        splitLine: { lineStyle: { color: '#eef2f7' } },
      },
      series: [
        {
          name: data.name || stock?.label || data.symbol,
          type: 'line',
          data: stockSeries,
          showSymbol: false,
          connectNulls: false,
          lineStyle: { width: 2.4, color: '#234f78' },
          itemStyle: { color: '#234f78' },
          markLine: {
            symbol: 'none',
            silent: true,
            label: { formatter: 'T0', color: '#607b94', fontSize: 12, rotate: 0 },
            lineStyle: { color: '#8ca1b4', type: 'dashed', width: 1 },
            data: [{ xAxis: data.anchor_date }],
          },
        },
        ...(data.benchmark
          ? [{
              name: data.benchmark.name,
              type: 'line' as const,
              data: benchmarkSeries,
              showSymbol: false,
              connectNulls: false,
              lineStyle: { width: 1.5, type: 'dashed' as const, color: '#94a3b8' },
              itemStyle: { color: '#94a3b8' },
            }]
          : []),
      ],
    };
  }, [data, stock?.label]);

  return (
    <section className="panel market-panel">
      <div className="panel-head market-head">
        <div>
          <span className="panel-kicker">行情</span>
          <h2>事件窗口收益</h2>
        </div>
        <div className="window-tabs">
          {[5, 10, 20].map((days) => (
            <button
              key={days}
              type="button"
              className={windowDays === days ? 'active' : ''}
              onClick={() => setWindowDays(days)}
            >
              T±{days}
            </button>
          ))}
        </div>
      </div>

      {!stock ? (
        <EmptyState icon={<LineChart size={22} />} title="选择关联证券" description="点击上方证券，查看事件前后走势。" compact />
      ) : stock.listed_at_event === false ? (
        <div className="market-listed">
          <CalendarClock size={18} />
          <div>
            <strong>该证券在事件日尚未上市</strong>
            <span>
              {stock.market_note || `上市日期 ${formatDate(stock.listing_date)}。`}
              事件日之前没有行情，不生成事件窗口。
            </span>
          </div>
        </div>
      ) : market.isLoading ? (
        <div className="market-loading">
          <div className="inline-loading"><Spinner size={16} /> 正在读取日线…</div>
          <Skeleton height={200} />
        </div>
      ) : market.isError ? (
        String(market.error).includes('422') || String(market.error).includes('时点') ? (
          <div className="market-cutoff">
            <CalendarClock size={18} />
            <div>
              <strong>该日期没有完整事件行情</strong>
              <span>所选日期早于 T0 或超出可用行情，无法生成事件窗口。切换回全部资料可查看当前窗口。</span>
            </div>
            <button type="button" className="button ghost small" onClick={() => onChangeAsOf('')}>
              查看全部资料
            </button>
          </div>
        ) : (
          <ErrorState title="行情读取失败" error={market.error} onRetry={() => market.refetch()} compact />
        )
      ) : !data || data.prices.length === 0 ? (
        <EmptyState
          icon={<CalendarClock size={22} />}
          title="该证券在事件窗口内暂无行情"
          description={data?.notes?.join(' ') || '本地日线缓存未覆盖该窗口。'}
          compact
        />
      ) : option ? (
        <>
          <div className="market-meta">
            <div>
              <strong>{data.name || stock.label}</strong>
              <span>{data.symbol} · {data.currency} · {data.adjusted === 'qfq' ? '前复权' : data.adjusted === 'hfq' ? '后复权' : '未复权'}</span>
            </div>
            <div className="market-dates">
              <span>事件日 {formatDate(data.event_date)}</span>
              <span>T0 {formatDate(data.anchor_date)}</span>
            </div>
          </div>

          <div className="return-table">
            <div className="return-row head">
              <span>区间</span>
              <span>证券</span>
              <span>基准</span>
              <span>相对基准 pp</span>
            </div>
            {rows.map((row) => (
              <div className="return-row" key={row.horizon}>
                <span>{row.horizon}日</span>
                <b className={trendClass(row.stockReturn)}>{formatPercent(row.stockReturn)}</b>
                <b className={trendClass(row.benchmarkReturn)}>
                  {data.benchmark ? formatPercent(row.benchmarkReturn) : '—'}
                </b>
                <b className={trendClass(row.excess)}>{formatPp(row.excess)}</b>
              </div>
            ))}
          </div>

          <div className="chart-legend">
            <span><i className="solid" /> {data.name || stock.label}</span>
            {data.benchmark ? <span><i className="dashed" /> {data.benchmark.name}</span> : null}
            <em>归一化：T−1 = 0%</em>
          </div>

          <div className="market-chart">
            <EChart option={option} className="market-chart-canvas" />
          </div>

          <div className="market-foot">
            <span>
              1 / 3 / 5 个交易日分别截至 T0、T+2、T+4；相对基准为同窗口差值（pp）。
            </span>
            {data.source_url ? (
              <a href={data.source_url} target="_blank" rel="noreferrer noopener">
                数据来源 <ExternalLink size={11} />
              </a>
            ) : null}
          </div>
        </>
      ) : null}
    </section>
  );
}
