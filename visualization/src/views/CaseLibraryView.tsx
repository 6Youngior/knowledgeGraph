import { useMemo } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { ArrowRight, CalendarDays, Database, GitBranch, Layers3, Link2, Waypoints } from 'lucide-react';
import { api } from '../api';
import type { EventDetail, EventItem, Overview } from '../types';
import { Skeleton } from '../components/Ui';
import { groupColor, groupLabel } from '../lib/palette';
import { formatDate, formatNumber } from '../lib/format';

interface CaseModel {
  id: string;
  title: string;
  date: string;
  model: string;
  stockCount: number;
  roleCounts: Record<string, number>;
  sourceCount: number;
  maxHops: number;
  summary?: string;
  historicalStockCount?: number;
  temporalSummary?: string;
}

export function CaseLibraryView({
  events,
  overview,
  onOpenEvent,
}: {
  events: EventItem[];
  overview?: Overview;
  onOpenEvent: (eventId: string) => void;
}) {
  const research = useQuery({
    queryKey: ['research-overview'],
    queryFn: api.research,
    retry: false,
  });

  const detailQueries = useQueries({
    queries: events.map((event) => ({
      queryKey: ['event', event.id, ''],
      queryFn: () => api.event(event.id),
      enabled: !research.data,
      retry: 1,
    })),
  });

  const cases = useMemo<CaseModel[]>(() => {
    if (research.data?.events?.length) {
      return research.data.events.map((item) => ({
        id: item.id,
        title: item.title,
        date: item.date,
        model: item.model,
        stockCount: item.stock_count,
        roleCounts: item.role_counts ?? {},
        sourceCount: item.source_count,
        maxHops: item.max_hops,
        summary: item.summary,
        historicalStockCount: item.historical_stock_count,
        temporalSummary: item.temporal_summary,
      }));
    }
    return events.map((event, index) => {
      const detail: EventDetail | undefined = detailQueries[index]?.data;
      const stocks = detail?.stocks ?? [];
      const roleCounts: Record<string, number> = {};
      stocks.forEach((stock) => {
        const key = stock.relation_group || 'direct';
        roleCounts[key] = (roleCounts[key] ?? 0) + 1;
      });
      const focus = detail?.graph.nodes.find((node) => node.id === detail.graph.focus_id);
      return {
        id: event.id,
        title: event.title,
        date: event.event_at || event.date,
        model: focus?.label ?? '—',
        stockCount: stocks.length,
        roleCounts,
        sourceCount: detail?.sources.length ?? 0,
        maxHops: stocks.reduce((max, stock) => Math.max(max, stock.path.edges.length), 0),
        historicalStockCount: stocks.length,
        temporalSummary: `当前资料包含 ${stocks.length} 只证券`,
      };
    });
  }, [research.data, events, detailQueries]);

  const loading = !research.data && detailQueries.some((query) => query.isLoading);

  return (
    <div className="cases-page">
      <header className="cases-header">
        <span className="section-kicker">案例库</span>
        <h1>AI 产业事件案例</h1>
        <p>选择事件，查看关联证券、产业角色、日期和行情。</p>
        <div className="case-stats">
          <span><Database size={14} /> {formatNumber(overview?.stats.entities)} 个实体</span>
          <span><GitBranch size={14} /> {formatNumber(overview?.stats.relations)} 条关系</span>
          <span><Link2 size={14} /> {formatNumber(overview?.stats.documents)} 条来源</span>
          <span><Waypoints size={14} /> {formatNumber(events.length)} 个事件</span>
        </div>
      </header>

      {research.isError ? (
        <p className="case-fallback">案例数据暂未加载，以下由事件列表汇总。</p>
      ) : null}

      <div className="case-grid">
        {loading
          ? events.map((event) => <Skeleton key={event.id} height={280} />)
          : cases.map((item, index) => (
              <button
                type="button"
                className="case-card"
                key={item.id}
                onClick={() => onOpenEvent(item.id)}
              >
                <div className="case-card-top">
                  <span className="case-number">{String(index + 1).padStart(2, '0')}</span>
                  <span className="case-date"><CalendarDays size={13} /> {formatDate(item.date)}</span>
                </div>
                <h2>{item.title}</h2>
                <div className="case-model"><Layers3 size={13} /> {item.model}</div>
                {item.summary ? <p className="case-summary">{item.summary}</p> : null}
                {item.temporalSummary ? <p className="case-temporal">{item.temporalSummary}</p> : null}
                <div className="case-metrics">
                  <div><span>关联证券</span><b>{formatNumber(item.stockCount)}</b></div>
                  <div><span>来源</span><b>{formatNumber(item.sourceCount)}</b></div>
                  <div><span>最大路径</span><b>{formatNumber(item.maxHops)} 跳</b></div>
                </div>
                <div className="case-roles">
                  {(['direct', 'adaptation', 'distribution'] as const).map((group) =>
                    item.roleCounts[group] ? (
                      <span key={group}>
                        <i style={{ background: groupColor(group) }} />
                        {groupLabel(group)} {item.roleCounts[group]}
                      </span>
                    ) : null,
                  )}
                </div>
                <span className="case-open">查看案例 <ArrowRight size={14} /></span>
              </button>
            ))}
      </div>

      <div className="case-note">
        <strong>数据范围</strong>
        <span>
          当前覆盖有公开原文和日线的 AI 产业事件；行业分类与晚于所选日期的记录不进入关联。
        </span>
      </div>
    </div>
  );
}
