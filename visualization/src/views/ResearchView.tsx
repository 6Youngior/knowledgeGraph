import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import { CalendarDays, ChevronDown, Download, FilePlus2, LineChart, Network, Play } from 'lucide-react';
import { api, errorMessage } from '../api';
import type { EventItem, GraphEdge, GraphNode, Overview, RelatedStock, RelationGroup, SourceItem } from '../types';
import { ResearchGraph, type GraphSelection } from '../components/ResearchGraph';
import { PathEvidence } from '../components/PathEvidence';
import { StockRoles } from '../components/StockRoles';
import { MarketChart } from '../components/MarketChart';
import { EmptyState, ErrorState, Skeleton } from '../components/Ui';
import { useToast } from '../components/Toast';
import { formatDate } from '../lib/format';

const EVENT_TYPE: Record<string, string> = {
  MODEL_RELEASE: '模型发布', ADAPTATION: '技术适配', PRODUCT_ADAPTATION: '硬件适配',
  CLOUD_ACCESS: '云服务接入', PARTNERSHIP: '合作公告', PRODUCT_RELEASE: '产品发布',
};
interface Props {
  events: EventItem[]; eventId: string | null; overview?: Overview; demoStep: number | null;
  pendingFocusGroup: string | null; pendingFocusSymbol: string | null;
  onFocusApplied: () => void; onEventChange: (id: string) => void;
  onStartDemo: () => void; onOpenCases: () => void; onOpenUpdate: () => void;
  focusTarget: { node: GraphNode; token: number } | null;
}
export function ResearchView({
  events, eventId, overview, demoStep, pendingFocusGroup, pendingFocusSymbol,
  onFocusApplied, onEventChange, onStartDemo, onOpenCases, onOpenUpdate, focusTarget,
}: Props) {
  const { notify } = useToast();
  const [asOf, setAsOf] = useState('');
  const [group, setGroup] = useState<'all' | RelationGroup>('all');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState('direct');
  const [highlightPath, setHighlightPath] = useState(false);
  const [selection, setSelection] = useState<GraphSelection | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [lens, setLens] = useState<'current' | 'historical' | 'excluded'>('current');
  const [tab, setTab] = useState<'graph' | 'market'>('graph');
  const [externalNode, setExternalNode] = useState<GraphNode | null>(null);
  const detailQuery = useQuery({
    queryKey: ['event', eventId, asOf], queryFn: () => api.event(eventId as string, asOf || undefined),
    enabled: Boolean(eventId), retry: 1, placeholderData: (previous) => previous,
  });
  const researchQuery = useQuery({
    queryKey: ['research', eventId, asOf], queryFn: () => api.researchDetail(eventId as string, asOf || undefined),
    enabled: Boolean(eventId), retry: false, placeholderData: (previous) => previous,
  });
  const sourcesQuery = useQuery({ queryKey: ['sources'], queryFn: api.sources, retry: 1, staleTime: 60000 });
  const detail = detailQuery.data;
  const stocks = useMemo(() => detail?.stocks ?? [], [detail]);
  const research = researchQuery.data;
  const event = events.find((item) => item.id === eventId) ?? detail?.event;
  const sourceMap = useMemo(() => {
    const map = new Map<string, SourceItem>();
    sourcesQuery.data?.sources.forEach((source) => map.set(source.id, source));
    detail?.sources.forEach((source) => map.set(source.id, source));
    return map;
  }, [sourcesQuery.data, detail]);

  useEffect(() => {
    if (pendingFocusGroup || pendingFocusSymbol) return;
    if (!stocks.length) { setSelectedSymbol(null); return; }
    if (!selectedSymbol || !stocks.some((stock) => stock.symbol === selectedSymbol)) {
      setSelectedSymbol(stocks[0].symbol); setSelectedGroup(stocks[0].relation_group || 'direct'); setHighlightPath(false);
    }
  }, [stocks, selectedSymbol, pendingFocusGroup, pendingFocusSymbol]);
  useEffect(() => {
    if ((!pendingFocusGroup && !pendingFocusSymbol) || !stocks.length) return;
    const target = (pendingFocusSymbol ? stocks.find((stock) => stock.symbol === pendingFocusSymbol) : undefined)
      ?? stocks.find((stock) => stock.relation_groups?.includes(pendingFocusGroup ?? '') || stock.relation_group === pendingFocusGroup);
    // Do not consume pending focus from a stale two-stock query response.
    if (!target) return;
    setSelectedSymbol(target.symbol);
    setSelectedGroup(target.relation_groups?.includes(pendingFocusGroup ?? '') ? pendingFocusGroup as string : target.relation_group || 'direct');
    setSelection(null); setHighlightPath(true); setTab('graph'); onFocusApplied();
  }, [pendingFocusGroup, pendingFocusSymbol, stocks, onFocusApplied]);
  const selectedStock = stocks.find((stock) => stock.symbol === selectedSymbol) ?? null;
  const activePath = selectedStock?.paths?.find((path) => path.relation_group === selectedGroup) ?? selectedStock?.path ?? null;
  const displayStock: RelatedStock | null = selectedStock && activePath
    ? { ...selectedStock, relation_group: selectedGroup, path: activePath as RelatedStock['path'] } : null;
  const selectedNode = selection?.kind === 'node' ? detail?.graph.nodes.find((node) => node.id === selection.id) ?? null : null;
  const selectedEdge = selection?.kind === 'edge' ? detail?.graph.edges.find((edge) => edge.id === selection.id) ?? null : null;
  useEffect(() => {
    if (!focusTarget) return;
    const inGraph = detail?.graph.nodes.find((node) => node.id === focusTarget.node.id);
    setExternalNode(inGraph ? null : focusTarget.node);
    setSelection(inGraph ? { kind: 'node', id: inGraph.id } : null);
    setHighlightPath(false); setTab('graph');
  }, [focusTarget, detail]);
  const selectStock = (stock: RelatedStock, nextGroup: string) => {
    setSelectedSymbol(stock.symbol); setSelectedGroup(nextGroup);
    setSelection(null); setExternalNode(null); setHighlightPath(true);
  };
  const changeDate = (value: string) => {
    setAsOf(value); setLens(value ? 'historical' : 'current');
    setSelection(null); setExternalNode(null); setHighlightPath(false);
  };
  const quickDates = useMemo(() => {
    const dates: Array<{ label: string; value: string }> = [];
    if (event) dates.push({ label: '发布日', value: (event.event_at || event.date).slice(0, 10) });
    [...(research?.temporal.milestones ?? [])].sort((a, b) => a.date.localeCompare(b.date)).forEach((item) => {
      if (item.date && !dates.some((date) => date.value === item.date)) dates.push({ label: item.title, value: item.date });
    });
    return dates.slice(0, 5);
  }, [event, research]);
  const briefMutation = useMutation({
    mutationFn: () => api.researchBrief(eventId as string, asOf || undefined),
    onSuccess: (brief) => {
      const url = URL.createObjectURL(new Blob([brief.markdown], { type: 'text/markdown;charset=utf-8' }));
      const link = document.createElement('a');
      link.href = url; link.download = brief.filename || 'fingraph-brief.md'; link.click();
      URL.revokeObjectURL(url); notify('研究简报已下载。', 'success');
    },
    onError: (error) => notify('下载失败：' + errorMessage(error), 'error'),
  });
  useEffect(() => {
    if (demoStep === null) return;
    setTab('graph');
    if (demoStep === 0) { setAsOf(''); setLens('current'); }
    if (demoStep === 1 && stocks[0]) selectStock(stocks[0], stocks[0].relation_group || 'direct');
    if (demoStep === 3 && event) changeDate((event.event_at || event.date).slice(0, 10));
  }, [demoStep]);
  if (!eventId && !detailQuery.isLoading) return (
    <div className="research-page"><EmptyState title="选择一个产业事件" description="从案例库开始研究。"
      action={<button className="button primary" onClick={onOpenCases}>打开案例库</button>} /></div>
  );
  return (
    <div className="research-page">
      <header className="research-header">
        <div className="research-heading">
          <div className="event-eyebrow"><span>{event ? EVENT_TYPE[event.type] ?? '产业事件' : '产业事件'}</span><span>{event ? formatDate(event.event_at || event.date) : '—'}</span></div>
          <h1>{event?.title ?? '正在读取事件…'}</h1>
        </div>
        <div className="research-actions">
          <label className="event-select"><span className="sr-only">研究事件</span>
            <div><select value={eventId ?? ''} aria-label="选择研究案例" onChange={(e) => onEventChange(e.target.value)}>
              {events.map((item) => <option key={item.id} value={item.id}>{item.title}</option>)}
            </select><ChevronDown size={15} /></div>
          </label>
          <button type="button" className="button ghost brief-button" onClick={() => briefMutation.mutate()} disabled={briefMutation.isPending}><Download size={15} /> 导出简报</button>
          <button type="button" className="button primary" onClick={onOpenUpdate}><FilePlus2 size={15} /> 导入资料</button>
        </div>
      </header>
      <section className="temporal-panel" aria-label="资料日期筛选">
        <div className="temporal-main">
          <span className="filter-label"><CalendarDays size={15} /> 资料日期</span>
          <div className="lens-tabs">
            <button type="button" className={lens === 'current' ? 'active' : ''} onClick={() => changeDate('')}>全部资料</button>
            <button type="button" className={lens === 'historical' ? 'active' : ''} onClick={() => { setLens('historical'); if (!asOf && event) changeDate((event.event_at || event.date).slice(0, 10)); }}>历史日期</button>
            <button type="button" className={lens === 'excluded' ? 'active' : ''} onClick={() => setLens('excluded')}>其他候选 <span>{research?.excluded.length ?? 0}</span></button>
          </div>
          <span className="temporal-summary" aria-live="polite">{detailQuery.isFetching ? '正在更新资料…' : <>{stocks.length} 只关联证券<span>·</span>{detail?.sources.length ?? 0} 项资料</>}</span>
        </div>
        {lens === 'historical' ? <div className="date-chips">
          <span>截至</span>
          {quickDates.map((item) => <button key={item.value} type="button" title={item.label} className={asOf === item.value ? 'active' : ''} onClick={() => changeDate(item.value)}>{item.value}</button>)}
          <label className="date-input"><input type="date" aria-label="选择历史日期" value={asOf} onChange={(e) => changeDate(e.target.value)} /></label>
          <span className="date-explanation">路径中的每条关系均需在此日期前已有资料支持。</span>
        </div> : null}
        {lens === 'excluded' ? <div className="excluded-lens">
          {(research?.excluded ?? []).length ? research?.excluded.map((item) => <div key={item.id}><strong>{item.label}</strong><span>{item.symbol}</span><p>{item.reason}</p></div>) : <p className="muted">没有其他候选。</p>}
        </div> : null}
      </section>
      <div className="workspace-tabs" role="tablist" aria-label="研究视图">
        <button type="button" role="tab" aria-selected={tab === 'graph'} className={tab === 'graph' ? 'active' : ''} onClick={() => setTab('graph')}><Network size={16} /> 关系图谱</button>
        <button type="button" role="tab" aria-selected={tab === 'market'} className={tab === 'market' ? 'active' : ''} onClick={() => setTab('market')}><LineChart size={16} /> 行情对照</button>
        <span>事实箭头保留原始方向；查询可沿关系双向遍历。</span>
      </div>
      <div className="research-main research-grid">
        <div className="analysis-canvas">
          {detail ? (tab === 'graph' ? <ResearchGraph
            graph={detail.graph} group={group} onGroupChange={setGroup} selection={selection}
            path={highlightPath ? activePath : null} stocks={stocks}
            onSelectNode={(node) => {
              if (node.type === 'Stock') {
                const stock = stocks.find((item) => item.id === node.id);
                if (stock) { selectStock(stock, stock.relation_group || 'direct'); return; }
              }
              setSelection({ kind: 'node', id: node.id }); setExternalNode(null);
            }}
            onSelectEdge={(edge: GraphEdge) => { setSelection({ kind: 'edge', id: edge.id }); setExternalNode(null); }}
            onClearPath={() => setHighlightPath(false)}
            onToggleFullscreen={() => setFullscreen((value) => !value)} fullscreen={fullscreen}
          /> : <MarketChart stock={selectedStock} eventId={eventId ?? ''} asOf={asOf} onChangeAsOf={changeDate} />)
            : detailQuery.isError ? <ErrorState title="事件资料加载失败" error={detailQuery.error} onRetry={() => detailQuery.refetch()} />
              : <Skeleton height={580} />}
        </div>
        <aside className="research-inspector">
          <StockRoles stocks={stocks} selectedSymbol={selectedSymbol} selectedGroup={selectedGroup} onSelect={selectStock} />
          {detail ? <PathEvidence stock={displayStock} node={selectedNode ?? externalNode} edge={selectedEdge}
            graph={detail.graph} event={event} eventSources={detail.sources} sourceMap={sourceMap} asOf={asOf}
            onBack={() => { setSelection(null); setExternalNode(null); }}
            onSelectEdge={(edge) => setSelection({ kind: 'edge', id: edge.id })} /> : <Skeleton height={420} />}
        </aside>
      </div>
      <div className="research-footer">
        <span>{overview?.stats.entities ?? '—'} 个实体 · {overview?.stats.relations ?? '—'} 条关系 · {overview?.stats.documents ?? '—'} 项来源</span>
        <button type="button" className="icon-text-button" onClick={onStartDemo}><Play size={13} /> 操作演示</button>
      </div>
    </div>
  );
}
