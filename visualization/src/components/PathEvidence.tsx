import { useEffect, useMemo, useRef } from 'react';
import {
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  Clock3,
  ExternalLink,
  FileText,
  GitBranch,
  Link2,
  ShieldCheck,
} from 'lucide-react';
import type {
  EventItem,
  GraphEdge,
  GraphNode,
  GraphPayload,
  RelatedStock,
  SourceItem,
} from '../types';
import { groupLabel, nodeColor, relationLabel, sourceTypeLabel, typeLabel } from '../lib/palette';
import { formatDate, formatDateCn, truncate } from '../lib/format';

function idsOf(value: string[] | string | undefined): string[] {
  if (Array.isArray(value)) return value;
  if (!value) return [];
  return [value];
}

function disclosureText(edge: GraphEdge, asOf: string): string {
  if (!edge.disclosed_at) return '日期未登记';
  if (asOf && edge.disclosed_at.slice(0, 10) > asOf) {
    return `晚于所选日期（${formatDate(edge.disclosed_at)}）`;
  }
  return `最早记录日期 ${formatDate(edge.disclosed_at)}`;
}

function sourceDateLabel(source?: SourceItem | null): string {
  if (source?.published_at) return formatDate(source.published_at);
  if (source?.retrieved_at) return `采集 ${formatDate(source.retrieved_at)}`;
  return '日期未核实';
}

export function PathEvidence({
  stock,
  node,
  edge,
  graph,
  event,
  eventSources,
  sourceMap,
  asOf,
  onBack,
  onSelectEdge,
}: {
  stock: RelatedStock | null;
  node: GraphNode | null;
  edge: GraphEdge | null;
  graph: GraphPayload;
  event?: EventItem;
  eventSources: SourceItem[];
  sourceMap: Map<string, SourceItem>;
  asOf: string;
  onBack: () => void;
  onSelectEdge: (edge: GraphEdge) => void;
}) {
  const panelRef = useRef<HTMLElement>(null);
  useEffect(() => { panelRef.current?.scrollTo({ top: 0 }); }, [stock?.symbol, stock?.relation_group, node?.id, edge?.id]);
  const nodes = useMemo(
    () => new Map(graph.nodes.map((item) => [item.id, item])),
    [graph.nodes],
  );

  const sourceFor = (ids?: string[] | string) =>
    idsOf(ids).map((id) => sourceMap.get(id)).find(Boolean) ?? null;

  if (edge) {
    const source = nodes.get(edge.source);
    const target = nodes.get(edge.target);
    const sourceItem = sourceFor(edge.source_ids);
    return (
      <section ref={panelRef} className="evidence-card evidence-panel">
        <button type="button" className="back-action" onClick={onBack}>
          <ArrowLeft size={14} /> 返回关联路径
        </button>
        <span className="evidence-kicker">关系 · {groupLabel(edge.relation_group)}</span>
        <h2>{relationLabel(edge.type, edge.label)}</h2>
        <div className="edge-statement">
          <span>{source?.label ?? edge.source}</span>
          <ArrowRight size={14} />
          <span>{target?.label ?? edge.target}</span>
        </div>
        <div className="disclosure-row">
          <Clock3 size={13} />
          {disclosureText(edge, asOf)}
          {asOf && edge.disclosed_at && edge.disclosed_at.slice(0, 10) <= asOf ? (
            <span className="public-badge"><CheckCircle2 size={11} /> 日期前已披露</span>
          ) : null}
        </div>
        {edge.evidence ? (
          <blockquote className="quote">“{edge.evidence}”</blockquote>
        ) : (
          <p className="muted">没有原文摘录。</p>
        )}
        <h3 className="evidence-subtitle"><FileText size={14} /> 来源</h3>
        <SourceList ids={edge.source_ids} sourceMap={sourceMap} />
        <details className="tech-details">
          <summary>技术详情</summary>
          <code>{edge.id}</code>
          <span>{edge.source} → {edge.type} → {edge.target}</span>
          {sourceItem ? <span>来源标识 {sourceItem.id}</span> : null}
        </details>
      </section>
    );
  }

  if (node) {
    const related = graph.edges.filter(
      (item) => item.source === node.id || item.target === node.id,
    );
    return (
      <section ref={panelRef} className="evidence-card evidence-panel">
        <button type="button" className="back-action" onClick={onBack}>
          <ArrowLeft size={14} /> 返回关联路径
        </button>
        <span className="evidence-kicker">{typeLabel(node.type)}</span>
        <h2>{node.label}</h2>
        <p className="evidence-lead">
          {node.description || '该实体暂无描述。'}
        </p>
        {node.aliases?.length ? (
          <p className="alias-line">别名：{node.aliases.join('、')}</p>
        ) : null}
        <h3 className="evidence-subtitle"><GitBranch size={14} /> 关联关系 · {related.length}</h3>
        <div className="mini-relations">
          {related.map((item) => {
            const outgoing = item.source === node.id;
            const other = nodes.get(outgoing ? item.target : item.source);
            return (
              <button type="button" key={item.id} onClick={() => onSelectEdge(item)}>
                <span>{outgoing ? '→' : '←'} {other?.label ?? '—'}</span>
                <em>{relationLabel(item.type, item.label)}</em>
              </button>
            );
          })}
        </div>
        <h3 className="evidence-subtitle"><FileText size={14} /> 来源</h3>
        <SourceList ids={node.source_ids} sourceMap={sourceMap} />
        <details className="tech-details">
          <summary>技术详情</summary>
          <code>{node.id}</code>
          {Object.entries(node.properties ?? {})
            .filter(([, value]) => ['string', 'number', 'boolean'].includes(typeof value))
            .map(([key, value]) => (
              <span key={key}>{key}: {String(value)}</span>
            ))}
        </details>
      </section>
    );
  }

  if (!stock) {
    return (
      <section ref={panelRef} className="evidence-card evidence-empty-card evidence-panel">
        <span className="evidence-kicker">证据</span>
        <h2>该日期没有关联证券</h2>
        <p className="evidence-lead">
          当前日期下，图谱中没有记录到证券关系。可以切换日期，或查看事件来源。
        </p>
        {event ? (
          <>
            <div className="event-mini">
              <span>{formatDateCn(event.event_at || event.date)}</span>
              <strong>{event.title}</strong>
              <small>{event.summary}</small>
            </div>
            <h3 className="evidence-subtitle"><FileText size={14} /> 事件来源</h3>
            <SourceList ids={event.source_ids} sourceMap={sourceMap} />
          </>
        ) : null}
      </section>
    );
  }

  const allSourceIds = [...new Set(stock.path.edges.flatMap((item) => idsOf(item.source_ids)))];
  const asOfPublic = stock.path.edges.every(
    (item) => !item.disclosed_at || !asOf || item.disclosed_at.slice(0, 10) <= asOf,
  );

  return (
    <section ref={panelRef} className="evidence-card evidence-panel">
      <span className="evidence-kicker">关联依据 · {groupLabel(stock.relation_group)}</span>
      <div className="path-heading">
        <h2>{stock.company_name || stock.label}</h2>
        <span className="symbol-pill">{stock.symbol}</span>
      </div>
      <div className="path-facts">
        <span><GitBranch size={13} /> {stock.path.edges.length} 条关系</span>
        <span><Link2 size={13} /> {allSourceIds.length} 条来源</span>
        {asOf ? <span className={asOfPublic ? '' : 'warn'}><Clock3 size={13} /> 截至 {formatDate(asOf)}</span> : null}
      </div>

      <h3 className="evidence-subtitle"><ShieldCheck size={14} /> 关系与原文</h3>
      <div className="evidence-steps">
        {stock.path.edges.map((item, index) => {
          const from = nodes.get(item.source)?.label ?? item.source;
          const to = nodes.get(item.target)?.label ?? item.target;
          const sourceItem = sourceFor(item.source_ids);
          return (
            <article className="evidence-step" key={item.id || index}>
              <span className="step-index">{index + 1}</span>
              <div className="step-copy">
                <div className="step-title">
                  <strong>{from}</strong>
                  <em style={{ color: nodeColor(nodes.get(item.target)?.type ?? '') }}>
                    {relationLabel(item.type, item.label)}
                  </em>
                  <strong>{to}</strong>
                </div>
                {item.evidence ? (
                  <blockquote>“{truncate(item.evidence, 180)}”</blockquote>
                ) : (
                  <p className="muted">该关系暂无原文摘录。</p>
                )}
                <div className="step-meta">
                  <span>{sourceItem?.publisher ?? '来源未登记'}</span>
                  <span>{sourceDateLabel(sourceItem)}</span>
                  {sourceItem?.url ? (
                    <a href={sourceItem.url} target="_blank" rel="noreferrer noopener">
                      原文 <ExternalLink size={11} />
                    </a>
                  ) : null}
                  <button type="button" onClick={() => onSelectEdge(item)}>
                    关系详情
                  </button>
                </div>
              </div>
            </article>
          );
        })}
      </div>

      {eventSources.length > 0 ? (
        <details className="event-sources">
          <summary><FileText size={13} /> 事件来源 · {eventSources.length}</summary>
          <SourceList ids={eventSources.map((item) => item.id)} sourceMap={sourceMap} />
        </details>
      ) : null}

      <details className="tech-details">
        <summary>技术详情</summary>
        <code>{stock.id}</code>
        <span>路径节点 {stock.path.nodes.map((item) => item.id).join(' → ')}</span>
        <span>路径关系 {stock.path.edges.map((item) => item.type).join(' → ')}</span>
      </details>
    </section>
  );
}

function SourceList({
  ids,
  sourceMap,
}: {
  ids?: string[] | string;
  sourceMap: Map<string, SourceItem>;
}) {
  const unique = [...new Set(idsOf(ids))];
  const items = unique.map((id) => sourceMap.get(id)).filter(Boolean) as SourceItem[];
  if (items.length === 0) return <p className="muted">暂无已登记来源。</p>;
  return (
    <div className="evidence-source-list">
      {items.map((source) => (
        <a key={source.id} href={source.url} target="_blank" rel="noreferrer noopener">
          <span className="source-type">{sourceTypeLabel(source.source_type)}</span>
          <span className="source-copy">
            <strong>{source.title}</strong>
            <small>{source.publisher} · {sourceDateLabel(source)}</small>
          </span>
          <ExternalLink size={12} />
        </a>
      ))}
    </div>
  );
}
