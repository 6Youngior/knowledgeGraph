import { useMemo, useState } from 'react';
import { useQueries, useQuery } from '@tanstack/react-query';
import { ArrowRight } from 'lucide-react';
import { api } from '../api';
import type { EventDetail, EventItem, Overview } from '../types';
import { Skeleton } from '../components/Ui';
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
  const [filter, setFilter] = useState('all');
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

  const models = [...new Set(cases.map((item) => item.model))];
  return (
    <div className="cases-page">
      <header className="cases-header"><h1>事件目录</h1><p>围绕四个模型主题整理发布、适配和云服务接入资料，选择事件查看关联证券。</p></header>
      <div className="case-filters" aria-label="按模型筛选">
        {['all', ...models].map((model) => <button type="button" key={model} className={filter === model ? 'active' : ''} onClick={() => setFilter(model)}>{model === 'all' ? '全部事件' : model}<span> · {model === 'all' ? cases.length : cases.filter((item) => item.model === model).length}</span></button>)}
      </div>
      {loading ? <Skeleton height={420} /> : <div className="case-table">
        <div className="case-table-row head"><span>日期</span><span>产业事件</span><span>模型主题</span><span>关联证券</span><span>来源</span><span /></div>
        {cases.filter((item) => filter === 'all' || item.model === filter).map((item) => <button type="button" className="case-table-row" key={item.id} onClick={() => onOpenEvent(item.id)}>
          <span className="mono">{formatDate(item.date)}</span><strong>{item.title}</strong><span>{item.model}</span><span>{item.stockCount} 只</span><span>{item.sourceCount} 项</span><ArrowRight size={15} />
        </button>)}
      </div>}
      <p className="case-note">当前图谱：{formatNumber(overview?.stats.entities)} 个实体、{formatNumber(overview?.stats.relations)} 条关系、{formatNumber(overview?.stats.documents)} 项来源。证券数按当前已收集资料计算。</p>
    </div>
  );
}
