import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import type { EChartsOption, EChartsType } from 'echarts';
import {
  Eye,
  EyeOff,
  Maximize2,
  Minimize2,
  Network,
  RotateCcw,
  ZoomIn,
  ZoomOut,
} from 'lucide-react';
import type { GraphEdge, GraphNode, GraphPayload, RelationGroup, RelatedStock } from '../types';
import { buildRoleLayout } from '../lib/roleLayout';
import {
  groupColor,
  groupLabel,
  nodeColor,
  relationLabel,
  typeLabel,
  TYPE_ORDER,
} from '../lib/palette';
import { truncate } from '../lib/format';
import { EChart } from './EChart';
import { EmptyState } from './Ui';

export interface GraphSelection {
  kind: 'node' | 'edge';
  id: string;
}

const GROUPS: Array<{ value: 'all' | RelationGroup; label: string }> = [
  { value: 'all', label: '全部关系' },
  { value: 'direct', label: '研发 / 上市' },
  { value: 'adaptation', label: '硬件适配' },
  { value: 'distribution', label: '云服务接入' },
];

function symbolFor(type: string): string {
  if (type === 'Event') return 'roundRect';
  if (type === 'Model') return 'diamond';
  if (type === 'Product' || type === 'Stock') return 'roundRect';
  return 'circle';
}

function sizeFor(type: string): number | [number, number] {
  if (type === 'Event') return [60, 30];
  if (type === 'Model') return 42;
  if (type === 'Product') return [42, 27];
  if (type === 'Stock') return [54, 27];
  if (type === 'Company') return 38;
  return 28;
}

export function ResearchGraph({
  graph,
  group,
  onGroupChange,
  selection,
  path,
  stocks,
  onSelectNode,
  onSelectEdge,
  onClearPath,
  onToggleFullscreen,
  fullscreen,
}: {
  graph: GraphPayload;
  group: 'all' | RelationGroup;
  onGroupChange: (group: 'all' | RelationGroup) => void;
  selection: GraphSelection | null;
  path: { nodes: GraphNode[]; edges: GraphEdge[] } | null;
  stocks: RelatedStock[];
  onSelectNode: (node: GraphNode) => void;
  onSelectEdge: (edge: GraphEdge) => void;
  onClearPath: () => void;
  onToggleFullscreen: () => void;
  fullscreen: boolean;
}) {
  const chartRef = useRef<EChartsType | null>(null);
  const zoomRef = useRef(1);
  const [showIndustry, setShowIndustry] = useState(false);

  const baseNodes = useMemo(
    () => graph.nodes.filter((node) => showIndustry || node.type !== 'Industry'),
    [graph.nodes, showIndustry],
  );
  const baseNodeIds = useMemo(
    () => new Set(baseNodes.map((node) => node.id)),
    [baseNodes],
  );

  const rolePaths = useMemo(() => {
    if (group === 'all') return null;
    const edgeIds = new Set<string>();
    const nodeIds = new Set<string>();
    stocks.forEach((stock) => {
      const groups = stock.relation_groups ?? [stock.relation_group];
      if (!groups.includes(group)) return;
      const rolePath =
        stock.paths?.find((item) => item.relation_group === group) ?? stock.path;
      rolePath.edges.forEach((edge) => edgeIds.add(edge.id));
      rolePath.nodes.forEach((node) => nodeIds.add(node.id));
    });
    return { edgeIds, nodeIds };
  }, [stocks, group]);

  const visibleEdges = useMemo(() => {
    const sourceEdges = rolePaths
      ? graph.edges.filter((edge) => rolePaths.edgeIds.has(edge.id))
      : graph.edges;
    return sourceEdges.filter(
      (edge) =>
        baseNodeIds.has(edge.source) &&
        baseNodeIds.has(edge.target) &&
        (group === 'all' || rolePaths !== null),
    );
  }, [graph.edges, group, baseNodeIds, rolePaths]);

  const visibleNodes = useMemo(() => {
    if (rolePaths) {
      return baseNodes.filter((node) => rolePaths.nodeIds.has(node.id));
    }
    if (group === 'all') return baseNodes;
    const ids = new Set<string>();
    visibleEdges.forEach((edge) => {
      ids.add(edge.source);
      ids.add(edge.target);
    });
    if (graph.focus_id) ids.add(graph.focus_id);
    return baseNodes.filter((node) => ids.has(node.id));
  }, [graph, group, visibleEdges, baseNodes, rolePaths]);

  const layout = useMemo(() => buildRoleLayout(visibleNodes, visibleEdges), [visibleNodes, visibleEdges]);
  const nodeMap = useMemo(
    () => new Map(visibleNodes.map((node) => [node.id, node])),
    [visibleNodes],
  );
  const pathNodeIds = useMemo(
    () => new Set(path?.nodes.map((node) => node.id) ?? []),
    [path],
  );
  const pathEdgeIds = useMemo(
    () => new Set(path?.edges.map((edge) => edge.id) ?? []),
    [path],
  );
  const hasPath = pathEdgeIds.size > 0;

  const applyZoom = useCallback((next: number) => {
    zoomRef.current = next;
    chartRef.current?.setOption({ series: [{ zoom: next, center: null }] });
  }, []);

  useEffect(() => {
    zoomRef.current = layout.zoom;
    chartRef.current?.setOption({ series: [{ zoom: layout.zoom, center: null }] });
  }, [layout.zoom, graph.focus_id]);

  const option = useMemo<EChartsOption>(() => {
    const data = visibleNodes.map((node) => {
      const position = layout.positions.get(node.id) ?? { x: 0, y: 0 };
      const color = nodeColor(node.type);
      const selected = selection?.kind === 'node' && selection.id === node.id;
      const onPath = hasPath && pathNodeIds.has(node.id);
      const dim = hasPath && !onPath;
      const code =
        node.type === 'Stock'
          ? String(
              node.properties?.symbol ??
                node.aliases?.find((alias) => /^\d{4,5}\./.test(alias)) ??
                node.label.match(/\(([^)]+)\)/)?.[1] ??
                '',
            )
          : '';
      const displayName =
        node.type === 'Stock'
          ? node.label.replace(/\s*\([^)]*\)\s*$/, '')
          : node.label;
      const meta =
        node.type === 'Stock'
          ? `${code || '证券'} · 证券`
          : typeLabel(node.type);
      return {
        id: node.id,
        nodeId: node.id,
        name: node.label,
        x: position.x,
        y: position.y,
        symbol: 'roundRect',
        symbolSize: node.type === 'Industry' ? [116, 44] : [142, 50],
        itemStyle: {
          color: onPath || selected ? `${color}33` : '#101c30',
          borderColor: selected ? '#ffffff' : color,
          borderWidth: selected ? 2.6 : 1.8,
          opacity: dim ? 0.62 : 1,
          shadowBlur: selected ? 12 : 0,
          shadowColor: `${color}55`,
        },
        label: {
          show: true,
          position: 'inside' as const,
          formatter: `{name|${displayName}}\n{meta|${meta}}`,
          rich: {
            name: {
              fontSize: displayName.length > 9 ? 13 : 14.5,
              fontWeight: 650,
              color: dim ? 'rgba(226,232,240,.68)' : '#f8fafc',
              lineHeight: 19,
              width: 126,
              overflow: 'break' as const,
            },
            meta: {
              fontSize: 10.5,
              fontWeight: 400,
              color: dim ? 'rgba(148,163,184,.52)' : color,
              lineHeight: 13,
            },
          },
        },
      };
    });

    const links = visibleEdges.map((edge) => {
      const onPath = pathEdgeIds.has(edge.id);
      const selected = selection?.kind === 'edge' && selection.id === edge.id;
      const dim = (hasPath && !onPath) || (selection?.kind === 'edge' && !selected);
      const color = onPath || selected ? '#67e8f9' : groupColor(edge.relation_group);
      return {
        id: edge.id,
        edgeId: edge.id,
        source: edge.source,
        target: edge.target,
        value: 1,
        lineStyle: {
          color,
          width: onPath || selected ? 2.8 : 1.5,
          opacity: dim ? 0.14 : 0.7,
          curveness: 0.04,
          shadowBlur: onPath ? 12 : 0,
          shadowColor: 'rgba(34,211,238,.5)',
        },
        label: {
          show: false,
          formatter: relationLabel(edge.type, edge.label),
          color: '#a5f3fc',
          fontSize: 9.5,
          rotate: 0,
          backgroundColor: 'rgba(7,15,28,.86)',
          padding: [2, 5],
          borderRadius: 4,
        },
      };
    });

    const sourceLabel = (id: string) => nodeMap.get(id)?.label ?? id;

    return {
      animationDuration: 500,
      animationDurationUpdate: 300,
      tooltip: {
        trigger: 'item',
        confine: true,
        backgroundColor: 'rgba(7,15,28,.97)',
        borderColor: 'rgba(148,163,184,.3)',
        textStyle: { color: '#e2e8f0', fontSize: 12 },
        extraCssText: 'border-radius:10px;box-shadow:0 18px 44px rgba(0,0,0,.5);max-width:340px;',
        formatter: (params: unknown) => {
          const item = params as { dataType?: string; data?: Record<string, unknown> };
          if (item.dataType === 'edge') {
            const edge = visibleEdges.find((entry) => entry.id === item.data?.edgeId);
            if (!edge) return '';
            return `<div style="font-size:10px;letter-spacing:.12em;color:#5eead4;margin-bottom:5px;">关系</div>
              <div style="font-weight:600;margin-bottom:3px;">${sourceLabel(edge.source)} → ${sourceLabel(edge.target)}</div>
              <div style="color:#94a3b8;">${relationLabel(edge.type, edge.label)} · ${edge.type}</div>
              ${edge.evidence ? `<div style="margin-top:7px;color:#cbd5e1;line-height:1.55;">${truncate(edge.evidence, 120)}</div>` : ''}
              ${edge.disclosed_at ? `<div style="margin-top:5px;color:#64748b;">披露 ${edge.disclosed_at}</div>` : ''}`;
          }
          const node = visibleNodes.find((entry) => entry.id === item.data?.nodeId);
          if (!node) return '';
          return `<div style="font-size:10px;letter-spacing:.12em;color:${nodeColor(node.type)};margin-bottom:5px;">${typeLabel(node.type)}</div>
            <div style="font-weight:600;margin-bottom:3px;">${node.label}</div>
            ${node.description ? `<div style="color:#94a3b8;line-height:1.55;">${truncate(node.description, 130)}</div>` : ''}
            ${node.source_ids?.length ? `<div style="margin-top:5px;color:#64748b;">${node.source_ids.length} 条来源</div>` : ''}`;
        },
      },
      series: [
        {
          type: 'graph',
          layout: 'none',
          roam: true,
          draggable: false,
          selectedMode: false,
          data,
          links,
          edgeSymbol: ['none', 'arrow'],
          edgeSymbolSize: 7,
          lineStyle: { curveness: 0.04 },
          emphasis: {
            focus: 'adjacency',
            scale: 1.06,
            lineStyle: { width: 2.6, opacity: 1 },
            label: { show: true, color: '#ffffff' },
          },
          blur: {
            itemStyle: { opacity: 0.35 },
            lineStyle: { opacity: 0.1 },
            label: { opacity: 0.45 },
          },
        },
      ],
    };
  }, [
    visibleNodes,
    visibleEdges,
    layout.positions,
    selection,
    pathEdgeIds,
    pathNodeIds,
    hasPath,
    nodeMap,
  ]);

  const onReady = useCallback((chart: EChartsType) => {
    chartRef.current = chart;
  }, []);

  const handleClick = useCallback(
    (params: unknown) => {
      const clicked = params as { dataType?: string; data?: { nodeId?: string; edgeId?: string } };
      if (clicked.dataType === 'node' && clicked.data?.nodeId) {
        const node = visibleNodes.find((entry) => entry.id === clicked.data?.nodeId);
        if (node) onSelectNode(node);
      } else if (clicked.dataType === 'edge' && clicked.data?.edgeId) {
        const edge = visibleEdges.find((entry) => entry.id === clicked.data?.edgeId);
        if (edge) onSelectEdge(edge);
      }
    },
    [visibleNodes, visibleEdges, onSelectNode, onSelectEdge],
  );

  const types = [...new Set(visibleNodes.map((node) => node.type))].sort(
    (a, b) =>
      (TYPE_ORDER.indexOf(a) === -1 ? 99 : TYPE_ORDER.indexOf(a)) -
      (TYPE_ORDER.indexOf(b) === -1 ? 99 : TYPE_ORDER.indexOf(b)),
  );

  return (
    <section className={`research-graph ${fullscreen ? 'fullscreen' : ''}`}>
      {fullscreen ? <div className="graph-backdrop" onClick={onToggleFullscreen} /> : null}
      <div className="graph-top">
        <div>
          <span className="graph-kicker">关系图</span>
          <h2>事件关联网络</h2>
        </div>
        <div className="graph-top-right">
          <span className="graph-count">
            {visibleNodes.length} 实体 · {visibleEdges.length} 关系
          </span>
          <button type="button" className="icon-button" aria-label="放大" onClick={() => applyZoom(Math.min(2, zoomRef.current * 1.18))}>
            <ZoomIn size={16} />
          </button>
          <button type="button" className="icon-button" aria-label="缩小" onClick={() => applyZoom(Math.max(0.4, zoomRef.current * 0.85))}>
            <ZoomOut size={16} />
          </button>
          <button type="button" className="icon-button" aria-label="重置视图" onClick={() => applyZoom(layout.zoom)}>
            <RotateCcw size={15} />
          </button>
          <button type="button" className="icon-button" aria-label="全屏" onClick={onToggleFullscreen}>
            {fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}
          </button>
        </div>
      </div>

      <div className="graph-filters">
        {GROUPS.map((item) => (
          <button
            key={item.value}
            type="button"
            className={group === item.value ? 'active' : ''}
            onClick={() => onGroupChange(item.value)}
          >
            {item.label}
          </button>
        ))}
        <button
          type="button"
          className={`industry-toggle ${showIndustry ? 'active' : ''}`}
          onClick={() => setShowIndustry((value) => !value)}
          title="行业节点只用于分类，不参与证券路径"
        >
          {showIndustry ? <Eye size={12} /> : <EyeOff size={12} />}
          {showIndustry ? '隐藏行业' : '显示行业'}
        </button>
      </div>

      {hasPath && path ? (
        <div className="graph-path-note">
          <span className="path-dot" />
          已选中：{path.nodes[path.nodes.length - 1]?.label} 的关联路径
          <button type="button" onClick={onClearPath}>取消选中</button>
        </div>
      ) : null}

      <div className="graph-canvas-wrap">
        {visibleNodes.length === 0 ? (
          <EmptyState title="没有符合条件的关系" description="切换关系类型后查看。" compact />
        ) : (
          <EChart option={option} className="research-graph-canvas" onReady={onReady} onClick={handleClick} />
        )}
      </div>

      <div className="graph-bottom">
        <div className="graph-legend">
          {types.map((type) => (
            <span key={type}>
              <i style={{ background: nodeColor(type) }} />
              {typeLabel(type)}
            </span>
          ))}
          <b />
          {(['direct', 'adaptation', 'distribution', 'industry'] as const).map((value) => (
            <span key={value}>
              <i className="line" style={{ background: groupColor(value) }} />
              {groupLabel(value)}
            </span>
          ))}
        </div>
        <span className="graph-tip">
          <Network size={12} /> 滚轮缩放 · 点击节点或关系查看详情
        </span>
      </div>
    </section>
  );
}
