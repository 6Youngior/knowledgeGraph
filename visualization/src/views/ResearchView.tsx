import { useEffect, useMemo, useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  ArrowRight,
  CalendarDays,
  ChevronDown,
  Download,
  ExternalLink,
  GitBranch,
  Layers3,
  Link2,
  Play,
  Search,
  ShieldCheck,
  Sparkles,
  Waypoints,
} from 'lucide-react';
import { api, errorMessage } from '../api';
import type {
  EventDetail,
  EventItem,
  GraphEdge,
  GraphNode,
  Overview,
  RelationGroup,
  RelatedStock,
  ResearchDetail,
  ResearchFinding,
  ResearchRole,
  SourceItem,
} from '../types';
import { ResearchGraph, type GraphSelection } from '../components/ResearchGraph';
import { PathEvidence } from '../components/PathEvidence';
import { StockRoles } from '../components/StockRoles';
import { MarketChart } from '../components/MarketChart';
import { EmptyState, ErrorState, Skeleton } from '../components/Ui';
import { useToast } from '../components/Toast';
import { groupColor, groupLabel, nodeColor, typeLabel } from '../lib/palette';
import { formatDate, formatDateCn, formatNumber } from '../lib/format';

const EVENT_TYPE_LABEL: Record<string, string> = {
  MODEL_RELEASE: '模型发布',
  ADAPTATION: '技术适配',
  PRODUCT_ADAPTATION: '硬件适配',
  CLOUD_ACCESS: '云服务接入',
  PARTNERSHIP: '合作公告',
  PRODUCT_RELEASE: '产品发布',
};

const KIND_LABEL: Record<string, string> = {
  fact: '来源',
  derived: '路径',
  boundary: '说明',
};

function maxHops(stocks: RelatedStock[]): number {
  return stocks.reduce((max, stock) => Math.max(max, stock.path.edges.length), 0);
}

export function ResearchView({
  events,
  eventId,
  overview,
  demoStep,
  pendingFocusGroup,
  pendingFocusSymbol,
  onFocusApplied,
  onEventChange,
  onStartDemo,
  onOpenCases,
  onOpenUpdate,
  focusTarget,
}: {
  events: EventItem[];
  eventId: string | null;
  overview?: Overview;
  demoStep: number | null;
  pendingFocusGroup: string | null;
  pendingFocusSymbol: string | null;
  onFocusApplied: () => void;
  onEventChange: (eventId: string) => void;
  onStartDemo: () => void;
  onOpenCases: () => void;
  onOpenUpdate: () => void;
  focusTarget: { node: GraphNode; token: number } | null;
}) {
  const { notify } = useToast();
  const [asOf, setAsOf] = useState('');
  const [group, setGroup] = useState<'all' | RelationGroup>('all');
  const [selectedSymbol, setSelectedSymbol] = useState<string | null>(null);
  const [selectedGroup, setSelectedGroup] = useState('direct');
  const [highlightPath, setHighlightPath] = useState(false);
  const [selection, setSelection] = useState<GraphSelection | null>(null);
  const [fullscreen, setFullscreen] = useState(false);
  const [lens, setLens] = useState<'current' | 'historical' | 'excluded'>('current');
  const [externalNode, setExternalNode] = useState<GraphNode | null>(null);

  const detailQuery = useQuery({
    queryKey: ['event', eventId, asOf],
    queryFn: () => api.event(eventId as string, asOf || undefined),
    enabled: Boolean(eventId),
    retry: 1,
  });
  const researchQuery = useQuery({
    queryKey: ['research', eventId, asOf],
    queryFn: () => api.researchDetail(eventId as string, asOf || undefined),
    enabled: Boolean(eventId),
    retry: false,
  });
  const sourcesQuery = useQuery({
    queryKey: ['sources'],
    queryFn: api.sources,
    retry: 1,
    staleTime: 60000,
  });

  const detail = detailQuery.data;
  const stocks = detail?.stocks ?? [];
  const research = researchQuery.data;
  const event = detail?.event ?? events.find((item) => item.id === eventId);

  const sourceMap = useMemo(() => {
    const map = new Map<string, SourceItem>();
    sourcesQuery.data?.sources.forEach((source) => map.set(source.id, source));
    detail?.sources.forEach((source) => map.set(source.id, source));
    return map;
  }, [sourcesQuery.data, detail]);

  useEffect(() => {
    setAsOf('');
    setGroup('all');
    setSelection(null);
    setSelectedSymbol(null);
    setSelectedGroup('direct');
    setHighlightPath(false);
    setFullscreen(false);
    setLens('current');
    setExternalNode(null);
  }, [eventId]);

  useEffect(() => {
    if (pendingFocusGroup || pendingFocusSymbol) return;
    if (stocks.length === 0) {
      setSelectedSymbol(null);
      return;
    }
    if (!selectedSymbol || !stocks.some((stock) => stock.symbol === selectedSymbol)) {
      setSelectedSymbol(stocks[0].symbol);
      setSelectedGroup(stocks[0].relation_group || 'direct');
      setHighlightPath(false);
    }
  }, [stocks, selectedSymbol, pendingFocusGroup, pendingFocusSymbol]);

  useEffect(() => {
    if ((!pendingFocusGroup && !pendingFocusSymbol) || stocks.length === 0) return;
    const bySymbol = pendingFocusSymbol
      ? stocks.find((stock) => stock.symbol === pendingFocusSymbol)
      : undefined;
    const target =
      bySymbol ??
      stocks.find(
        (stock) =>
          stock.relation_groups?.includes(pendingFocusGroup ?? '') ||
          (stock.relation_group || 'direct') === pendingFocusGroup,
      );
    // Do not consume the pending focus until the requested symbol (or role
    // path) actually exists. TanStack often serves the old 2-stock cache first;
    // consuming then lets the default-first-stock effect win the race.
    if (!target) return;
    setSelectedSymbol(target.symbol);
    setSelectedGroup(
      target.relation_groups?.includes(pendingFocusGroup ?? '')
        ? (pendingFocusGroup as string)
        : target.relation_group || 'direct',
    );
    setSelection(null);
    setHighlightPath(true);
    onFocusApplied();
  }, [pendingFocusGroup, pendingFocusSymbol, stocks, onFocusApplied]);

  const selectedStock = useMemo(
    () => stocks.find((stock) => stock.symbol === selectedSymbol) ?? null,
    [stocks, selectedSymbol],
  );

  const activePath = useMemo(() => {
    if (!selectedStock) return null;
    const fromPaths = selectedStock.paths?.find(
      (item) => item.relation_group === selectedGroup,
    );
    return fromPaths ?? selectedStock.path;
  }, [selectedStock, selectedGroup]);

  const displayStock = useMemo<RelatedStock | null>(() => {
    if (!selectedStock) return null;
    return {
      ...selectedStock,
      relation_group: selectedGroup,
      path: (activePath ?? selectedStock.path) as RelatedStock['path'],
    };
  }, [selectedStock, selectedGroup, activePath]);

  useEffect(() => {
    if (!focusTarget) return;
    const inGraph = detail?.graph.nodes.find((node) => node.id === focusTarget.node.id);
    if (inGraph) {
      setExternalNode(null);
      setSelection({ kind: 'node', id: inGraph.id });
    } else {
      setExternalNode(focusTarget.node);
      setSelection(null);
    }
    setHighlightPath(false);
  }, [focusTarget, detail]);

  const selectedNode: GraphNode | null =
    selection?.kind === 'node'
      ? detail?.graph.nodes.find((node) => node.id === selection.id) ?? null
      : null;
  const selectedEdge: GraphEdge | null =
    selection?.kind === 'edge'
      ? detail?.graph.edges.find((edge) => edge.id === selection.id) ?? null
      : null;

  const roles: ResearchRole[] = useMemo(() => {
    if (research?.roles?.length) return research.roles;
    const map = new Map<string, ResearchRole>();
    stocks.forEach((stock) => {
      const groupKey = stock.relation_group || 'direct';
      const current = map.get(groupKey) ?? {
        group: groupKey,
        label: groupLabel(groupKey),
        count: 0,
        symbols: [],
      };
      current.count += 1;
      if (!current.symbols.includes(stock.symbol)) current.symbols.push(stock.symbol);
      map.set(groupKey, current);
    });
    return ['direct', 'adaptation', 'distribution']
      .map((key) => map.get(key))
      .filter(Boolean) as ResearchRole[];
  }, [research, stocks]);

  const findings: ResearchFinding[] = useMemo(() => {
    if (research?.findings?.length) return research.findings;
    if (!detail) return [];
    const direct = stocks.filter((stock) => (stock.relation_group || 'direct') === 'direct').length;
    const adaptation = stocks.filter((stock) => stock.relation_group === 'adaptation').length;
    const distribution = stocks.filter((stock) => stock.relation_group === 'distribution').length;
    return [
      {
        id: 'derived-paths',
        kind: 'derived',
        title: `关联 ${stocks.length} 只证券`,
        text: stocks.length
          ? `从事件出发，沿研发、产品适配或云服务接入关系，可连接到 ${stocks.map((stock) => stock.company_name || stock.label).join('、')}。`
          : '该日期下没有已记录的关联证券。',
        source_ids: [],
      },
      {
        id: 'derived-roles',
        kind: 'fact',
        title: '关系类型分布',
        text: `研发/上市 ${direct} 只、硬件适配 ${adaptation} 只、云服务接入 ${distribution} 只。`,
        source_ids: [],
      },
      {
        id: 'boundary-market',
        kind: 'boundary',
        title: '行情区间',
        text: '事件窗口使用本地日线，展示 1/3/5 日累计收益与相对基准差值。',
        source_ids: [],
      },
    ];
  }, [research, detail, stocks]);

  const coverage = research?.coverage ?? {
    path_count: stocks.length,
    source_count: detail?.sources.length ?? 0,
    source_types: [...new Set((detail?.sources ?? []).map((source) => source.source_type))],
    max_hops: maxHops(stocks),
  };

  const quickDates = useMemo(() => {
    const dates: Array<{ label: string; value: string }> = [
      { label: '全部已收集资料', value: '' },
    ];
    if (event) {
      const eventDate = (event.event_at || event.date).slice(0, 10);
      dates.push({ label: `发布日 ${formatDate(eventDate)}`, value: eventDate });
    }
    const milestones = [...(research?.temporal.milestones ?? [])].sort((a, b) =>
      a.date.localeCompare(b.date),
    );
    milestones.forEach((milestone) => {
      if (milestone.date && !dates.some((item) => item.value === milestone.date)) {
        dates.push({ label: `${formatDate(milestone.date)} ${milestone.title}`, value: milestone.date });
      }
    });
    return dates.slice(0, 6);
  }, [event, research]);

  const briefMutation = useMutation({
    mutationFn: () => api.researchBrief(eventId as string, asOf || undefined),
    onSuccess: (brief) => {
      const blob = new Blob([brief.markdown], { type: 'text/markdown;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = brief.filename || 'fingraph-brief.md';
      link.click();
      URL.revokeObjectURL(url);
      notify('研究简报已生成并下载。', 'success');
    },
    onError: (error) => notify(`简报下载失败：${errorMessage(error)}`, 'error'),
  });

  // Demo steps are declarative: they only move the camera / select real data.
  useEffect(() => {
    if (demoStep === null) return;
    if (demoStep === 0) {
      setAsOf('');
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } else if (demoStep === 1) {
      if (stocks[0]) {
        setSelectedSymbol(stocks[0].symbol);
        setSelectedGroup(stocks[0].relation_group || 'direct');
        setSelection(null);
        setHighlightPath(true);
      }
      window.setTimeout(() => {
        document.querySelector('.research-main')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      }, 120);
    } else if (demoStep === 2) {
      window.setTimeout(() => {
        document.querySelector('.evidence-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 120);
    } else if (demoStep === 3) {
      if (event) setAsOf((event.event_at || event.date).slice(0, 10));
      setLens('historical');
      window.setTimeout(() => {
        document.querySelector('.temporal-panel')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }, 120);
    }
  }, [demoStep, event, stocks]);

  if (!eventId && !detailQuery.isLoading) {
    return (
      <div className="research-page">
        <EmptyState
          title="还没有选择研究案例"
          description="从案例库选择事件，或检查数据服务。"
          action={<button type="button" className="button primary" onClick={onOpenCases}>打开案例库</button>}
        />
      </div>
    );
  }

  const isLoading = detailQuery.isLoading;

  return (
    <div className="research-page">
      <header className="research-header">
        <div className="research-heading">
          <span className="section-kicker">股票量化情报</span>
          <h1>AI 产业事件的关联证券研究</h1>
          <p>
            从模型发布、产品适配和云服务接入出发，查找相关上市公司，核对公告日期与原文。
          </p>
        </div>
        <div className="research-actions">
          <label className="event-select">
            <span>事件</span>
            <div>
              <select value={eventId ?? ''} aria-label="选择研究案例"
                onChange={(changeEvent) => onEventChange(changeEvent.target.value)}>
                {events.map((item) => (
                  <option key={item.id} value={item.id}>
                    {formatDate(item.event_at || item.date)} · {item.title}
                  </option>
                ))}
              </select>
              <ChevronDown size={15} />
            </div>
          </label>
          <button
            type="button"
            className="button ghost small brief-button"
            onClick={() => briefMutation.mutate()}
            disabled={briefMutation.isPending}
            title="基于当前图谱生成 Markdown 研究简报"
          >
            <Download size={14} /> 研究简报
          </button>
          <button type="button" className="button primary demo-button" onClick={onStartDemo}>
            <Play size={15} fill="currentColor" />
            操作演示
          </button>
        </div>
      </header>

      <section className="event-banner">
        <div className="event-banner-main">
          <div className="event-tags">
            <span className="tag pink">{event ? (EVENT_TYPE_LABEL[event.type] ?? event.type) : '事件'}</span>
            <span className="tag">{event ? formatDateCn(event.event_at || event.date) : '—'}</span>
            <span className="tag">{formatNumber(detail?.sources.length ?? 0)} 条资料</span>
          </div>
          <h2>{event?.title ?? '正在载入事件…'}</h2>
          <p className="event-result">
            <span>关联摘要：</span>
            {stocks.length > 0
              ? stocks
                  .map(
                    (stock) =>
                      `${stock.company_name || stock.label}（${
                        stock.relation_group === 'distribution'
                          ? '云服务接入'
                          : stock.relation_group === 'adaptation'
                            ? '硬件适配'
                            : '研发主体'
                      }）`,
                  )
                  .join('；')
              : '该日期下没有已记录的关联证券'}
          </p>
          <div className="event-meta">
            <span><Layers3 size={14} /> 模型：{detail?.graph.nodes.find((node) => node.id === detail.graph.focus_id)?.label ?? '—'}</span>
            <span><Waypoints size={14} /> 最大 {coverage.max_hops} 跳</span>
            <span><Link2 size={14} /> {coverage.source_count} 条路径来源</span>
          </div>
        </div>
        <aside className="event-banner-side">
          <div>
            <span>关联公司</span>
            <b>{formatNumber(isLoading ? undefined : stocks.length)}</b>
          </div>
          <div>
            <span>产业角色</span>
            <b>{formatNumber(roles.filter((role) => role.count > 0).length)}</b>
          </div>
          <button type="button" className="text-link" onClick={onOpenCases}>
            切换案例 <ArrowRight size={13} />
          </button>
        </aside>
      </section>

      <section className="panel temporal-panel">
        <div className="temporal-main">
          <span className="panel-kicker">研究日期</span>
          <div className="lens-row">
            <div className="lens-tabs">
              <button
                type="button"
                className={lens === 'current' ? 'active' : ''}
                onClick={() => { setLens('current'); setAsOf(''); setSelection(null); }}
              >
                全部资料
              </button>
              <button
                type="button"
                className={lens === 'historical' ? 'active' : ''}
                onClick={() => {
                  setLens('historical');
                  if (!asOf && event) setAsOf((event.event_at || event.date).slice(0, 10));
                  setSelection(null);
                }}
              >
                历史日期
              </button>
              <button
                type="button"
                className={lens === 'excluded' ? 'active' : ''}
                onClick={() => setLens('excluded')}
              >
                其他候选 <span>{research?.excluded.length ?? 0}</span>
              </button>
            </div>
            {lens === 'historical' ? (
              <div className="date-chips">
                {quickDates.map((item) => (
                  <button
                    key={`${item.label}-${item.value}`}
                    type="button"
                    className={asOf === item.value ? 'active' : ''}
                    onClick={() => {
                      setAsOf(item.value);
                      setLens(item.value ? 'historical' : 'current');
                      setSelection(null);
                    }}
                  >
                    {item.label}
                  </button>
                ))}
                <label className="date-input">
                  <CalendarDays size={13} />
                  <input
                    type="date"
                    aria-label="选择历史日期"
                    value={asOf}
                    onChange={(changeEvent) => {
                      setAsOf(changeEvent.target.value);
                      setLens(changeEvent.target.value ? 'historical' : 'current');
                    }}
                  />
                </label>
              </div>
            ) : (
              <span className="lens-state">
                {lens === 'current' ? '当前图谱中的全部资料' : '查看未计入的候选'}
              </span>
            )}
            <details className="lens-help">
              <summary>日期说明</summary>
              <p>
                {lens === 'historical'
                  ? `仅显示 ${formatDate(asOf)} 及以前已披露的关系；图谱、股票与行情同步过滤。`
                  : '全部资料包含当前图谱中已登记的关系。'}
              </p>
            </details>
          </div>
        </div>
        <div className="temporal-stats">
          <div><span>关联证券</span><b>{formatNumber(research?.temporal.visible_count ?? coverage.path_count)}</b></div>
          <div><span>其他候选</span><b>{formatNumber(asOf ? (research?.temporal.excluded_count ?? research?.excluded.length ?? 0) : (research?.excluded.length ?? research?.temporal.excluded_count ?? 0))}</b></div>
        </div>
        {lens === 'excluded' ? (
          <div className="excluded-lens">
            {(research?.excluded ?? []).length === 0 ? (
              <p className="muted">没有未计入的候选。</p>
            ) : (
              (research?.excluded ?? []).map((item) => (
                <div key={item.id}>
                  <strong>{item.label}</strong>
                  <span>{item.symbol}</span>
                  <em className={`reason ${item.reason_code}`}>
                    {item.reason_code === 'industry_only'
                      ? '仅有行业分类'
                      : item.reason_code === 'not_yet_disclosed'
                        ? '缺少当时资料'
                        : item.reason_code === 'no_evidence'
                          ? '缺少原文证据'
                          : item.reason}
                  </em>
                  <small>{item.reason}</small>
                </div>
              ))
            )}
          </div>
        ) : null}
      </section>

      <div className="research-main research-grid">
        {detail ? (
          <ResearchGraph
            graph={detail.graph}
            group={group}
            onGroupChange={setGroup}
            selection={selection}
            path={highlightPath && activePath ? activePath : null}
            stocks={stocks}
            onSelectNode={(node) => {
              if (node.type === 'Stock') {
                const stock = stocks.find((item) => item.id === node.id);
                if (stock) {
                  setSelectedSymbol(stock.symbol);
                  setSelectedGroup(stock.relation_group || 'direct');
                  setHighlightPath(true);
                  setSelection(null);
                  return;
                }
              }
              setSelection({ kind: 'node', id: node.id });
            }}
            onSelectEdge={(edge) => setSelection({ kind: 'edge', id: edge.id })}
            onClearPath={() => setHighlightPath(false)}
            onToggleFullscreen={() => setFullscreen((value) => !value)}
            fullscreen={fullscreen}
          />
        ) : detailQuery.isError ? (
          <section className="panel">
            <ErrorState title="事件图谱加载失败" error={detailQuery.error} onRetry={() => detailQuery.refetch()} />
          </section>
        ) : (
          <Skeleton height={560} />
        )}

        {detail ? (
          <PathEvidence
            stock={displayStock}
            node={selectedNode ?? externalNode}
            edge={selectedEdge}
            graph={detail.graph}
            event={event}
            eventSources={detail.sources}
            sourceMap={sourceMap}
            asOf={asOf}
            onBack={() => { setSelection(null); setExternalNode(null); }}
            onSelectEdge={(edge) => setSelection({ kind: 'edge', id: edge.id })}
          />
        ) : (
          <Skeleton height={560} />
        )}
      </div>

      <div className="discovery-grid">
        <section className="panel findings-panel">
          <div className="panel-head">
            <div>
              <span className="panel-kicker">关联概览</span>
              <h2>本次事件</h2>
            </div>
            {!research && researchQuery.isError ? (
              <span className="fallback-note">摘要未加载，以下由图谱数据生成</span>
            ) : null}
          </div>
          <div className="finding-list">
            {findings.slice(0, 3).map((finding, index) => (
              <article className="finding" key={finding.id}>
                <span className={`finding-index ${finding.kind}`}>{String(index + 1).padStart(2, '0')}</span>
                <div>
                  <div className="finding-title">
                    <span className={`kind ${finding.kind}`}>{KIND_LABEL[finding.kind] ?? finding.kind}</span>
                    <strong>{finding.title}</strong>
                  </div>
                  <p>{finding.text}</p>
                </div>
              </article>
            ))}
            {findings.length === 0 ? <Skeleton height={160} /> : null}
          </div>
        </section>

        <aside className="panel roles-panel">
          <div className="panel-head">
            <div>
              <span className="panel-kicker">产业角色</span>
              <h2>研发、适配与云接入</h2>
            </div>
          </div>
          <div className="role-list">
            {roles.length === 0 ? (
              <p className="muted">当前日期没有关联证券。</p>
            ) : (
              roles.map((role) => (
                <div className="role-row" key={role.group}>
                  <span className="role-dot" style={{ background: groupColor(role.group) }} />
                  <div>
                    <strong>{role.label || groupLabel(role.group)}</strong>
                    <small>{role.symbols.length ? role.symbols.join(' · ') : '暂无证券'}</small>
                  </div>
                  <b>{role.count}</b>
                </div>
              ))
            )}
          </div>
          <div className="role-note">
            <ShieldCheck size={13} />
            关系类型来自图谱中的明确事实，证据见右侧原文。
          </div>
        </aside>
      </div>

      <div className="research-bottom">
        <StockRoles
          stocks={stocks}
          selectedSymbol={selectedSymbol}
          selectedGroup={selectedGroup}
          onSelect={(stock, nextGroup) => {
            setSelectedSymbol(stock.symbol);
            setSelectedGroup(nextGroup);
            setSelection(null);
            setHighlightPath(true);
          }}
        />
        <MarketChart
          stock={selectedStock}
          eventId={eventId ?? ''}
          asOf={asOf}
          onChangeAsOf={(value) => {
            setAsOf(value);
            setLens(value ? 'historical' : 'current');
          }}
        />
      </div>

      <div className="research-footer">
        <span><Search size={13} /> 图谱统计：{formatNumber(overview?.stats.entities)} 实体 · {formatNumber(overview?.stats.relations)} 关系 · {formatNumber(overview?.stats.documents)} 来源</span>
        <span>数据来自知识图谱与本地行情缓存。</span>
      </div>
    </div>
  );
}
