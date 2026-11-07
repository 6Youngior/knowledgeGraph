import { memo, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import {
  Background, getViewportForBounds, Handle, MarkerType, Position, ReactFlow, useUpdateNodeInternals,
  type Edge, type Node, type NodeProps, type ReactFlowInstance,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Eye, EyeOff, Maximize2, Minimize2, RotateCcw, ZoomIn, ZoomOut } from 'lucide-react';
import type { GraphEdge, GraphNode, GraphPayload, RelationGroup, RelatedStock } from '../types';
import { buildRoleLayout } from '../lib/roleLayout';
import { nodeColor, relationLabel, typeLabel } from '../lib/palette';
import { EmptyState } from './Ui';

export interface GraphSelection { kind: 'node' | 'edge'; id: string; }
type EvidenceNode = Node<{ entity: GraphNode; horizontal: boolean; active: boolean }, 'evidence'>;
const EntityNode = memo(function EntityNode({ id, data }: NodeProps<EvidenceNode>) {
  const updateInternals = useUpdateNodeInternals();
  useLayoutEffect(() => { updateInternals(id); }, [id, updateInternals]);
  const node = data.entity;
  const name = node.type === 'Stock' ? node.label.replace(/\s*\([^)]*\)\s*$/, '') : node.label;
  const code = node.type === 'Stock' ? String(node.properties?.symbol ?? '') : typeLabel(node.type);
  return (
    <div className={'entity-node ' + (data.active ? 'on-path' : '')} style={{ borderLeftColor: nodeColor(node.type) }} title={node.label}>
      {([Position.Left, Position.Right, Position.Top, Position.Bottom] as const).flatMap((position) => [
        <Handle key={'s-' + position} id={'s-' + position} type="source" position={position} isConnectable={false} />,
        <Handle key={'t-' + position} id={'t-' + position} type="target" position={position} isConnectable={false} />,
      ])}
      <span className="entity-type">{node.type === 'Stock' ? code : typeLabel(node.type)}</span>
      <strong>{name}</strong>
    </div>
  );
});
const nodeTypes = { evidence: EntityNode };
const GROUPS: Array<{ value: 'all' | RelationGroup; label: string }> = [
  { value: 'all', label: '全部关系' }, { value: 'direct', label: '研发 / 上市' },
  { value: 'adaptation', label: '硬件适配' }, { value: 'distribution', label: '云服务接入' },
];
export function ResearchGraph({
  graph, group, onGroupChange, selection, path, stocks, onSelectNode, onSelectEdge, onClearPath,
  onToggleFullscreen, fullscreen,
}: {
  graph: GraphPayload; group: 'all' | RelationGroup; onGroupChange: (group: 'all' | RelationGroup) => void;
  selection: GraphSelection | null; path: { nodes: GraphNode[]; edges: GraphEdge[] } | null;
  stocks: RelatedStock[]; onSelectNode: (node: GraphNode) => void; onSelectEdge: (edge: GraphEdge) => void;
  onClearPath: () => void; onToggleFullscreen: () => void; fullscreen: boolean;
}) {
  const container = useRef<HTMLDivElement>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<EvidenceNode, Edge> | null>(null);
  const [horizontal, setHorizontal] = useState(false);
  const [canvasSize, setCanvasSize] = useState({ width: 0, height: 0 });
  const [showIndustry, setShowIndustry] = useState(false);
  useEffect(() => {
    if (!fullscreen) return;
    const handle = (event: KeyboardEvent) => { if (event.key === 'Escape') onToggleFullscreen(); };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, [fullscreen, onToggleFullscreen]);
  useEffect(() => {
    if (!container.current) return;
    const observer = new ResizeObserver(([entry]) => {
      setHorizontal(entry.contentRect.width >= 1120);
      const width = Math.round(entry.contentRect.width);
      const height = Math.round(entry.contentRect.height);
      setCanvasSize((old) => old.width === width && old.height === height ? old : { width, height });
    });
    observer.observe(container.current);
    return () => observer.disconnect();
  }, []);
  const filtered = useMemo(() => {
    let nodes = graph.nodes.filter((node) => showIndustry || node.type !== 'Industry');
    let edges = graph.edges;
    if (group !== 'all') {
      const nodeIds = new Set<string>(); const edgeIds = new Set<string>();
      stocks.forEach((stock) => {
        if (!(stock.relation_groups ?? [stock.relation_group]).includes(group)) return;
        const rolePath = stock.paths?.find((item) => item.relation_group === group) ?? stock.path;
        rolePath.nodes.forEach((node) => nodeIds.add(node.id));
        rolePath.edges.forEach((edge) => edgeIds.add(edge.id));
      });
      nodes = nodes.filter((node) => nodeIds.has(node.id));
      edges = edges.filter((edge) => edgeIds.has(edge.id));
    }
    const ids = new Set(nodes.map((node) => node.id));
    return { nodes, edges: edges.filter((edge) => ids.has(edge.source) && ids.has(edge.target)) };
  }, [graph, showIndustry, group, stocks]);
  const layout = useMemo(() => buildRoleLayout(filtered.nodes, filtered.edges, horizontal), [filtered, horizontal]);
  const structureKey = (horizontal ? 'horizontal:' : 'vertical:')
    + filtered.nodes.map((node) => node.id).join('|') + '>'
    + filtered.edges.map((edge) => edge.id).join('|');
  const viewport = useMemo(() => {
    const points = [...layout.positions.values()];
    if (!points.length || !canvasSize.width || !canvasSize.height) return { x: 0, y: 0, zoom: 1 };
    const x = Math.min(...points.map((point) => point.x));
    const y = Math.min(...points.map((point) => point.y));
    const width = Math.max(...points.map((point) => point.x + 174)) - x;
    const height = Math.max(...points.map((point) => point.y + 60)) - y;
    return getViewportForBounds({ x, y, width, height }, canvasSize.width, canvasSize.height, 0.3, 1.1, 0.05);
  }, [layout, canvasSize]);
  const pathNodes = new Set(path?.nodes.map((node) => node.id));
  const pathEdges = new Set(path?.edges.map((edge) => edge.id));
  const nodes: EvidenceNode[] = filtered.nodes.map((entity) => ({
    id: entity.id, type: 'evidence', data: { entity, horizontal, active: pathNodes.has(entity.id) },
    position: layout.positions.get(entity.id) ?? { x: 0, y: 0 },
    className: path && !pathNodes.has(entity.id) ? 'off-path' : '',
    selected: selection?.kind === 'node' && selection.id === entity.id,
    ariaLabel: typeLabel(entity.type) + '：' + entity.label,
    style: { width: 174, height: 60 }, draggable: false, connectable: false, deletable: false,
  }));
  const edges: Edge[] = filtered.edges.map((edge) => {
    const a = layout.positions.get(edge.source); const b = layout.positions.get(edge.target);
    const forward = horizontal ? (a?.x ?? 0) < (b?.x ?? 0) : (a?.y ?? 0) < (b?.y ?? 0);
    const from = horizontal ? (forward ? 'right' : 'left') : (forward ? 'bottom' : 'top');
    const to = horizontal ? (forward ? 'left' : 'right') : (forward ? 'top' : 'bottom');
    const active = pathEdges.has(edge.id) || (selection?.kind === 'edge' && selection.id === edge.id);
    const color = active ? '#157d72' : '#8998a9';
    const span = horizontal ? Math.abs((b?.x ?? 0) - (a?.x ?? 0)) : Math.abs((b?.y ?? 0) - (a?.y ?? 0));
    return {
      id: edge.id, source: edge.source, target: edge.target, type: 'smoothstep',
      // Turn in the first gap when an edge skips a layer, so it does not
      // pass through an unrelated product in the intermediate column.
      pathOptions: { borderRadius: 5, offset: 18, stepPosition: span > (horizontal ? 350 : 150) ? 0.12 : 0.5 },
      sourceHandle: 's-' + from, targetHandle: 't-' + to, label: relationLabel(edge.type, edge.label),
      markerEnd: { type: MarkerType.ArrowClosed, color, width: 18, height: 18 },
      style: { stroke: color, strokeWidth: active ? 2.3 : 1.5, opacity: path && !active ? 0.4 : 1 },
      labelStyle: { fill: active ? '#126e64' : '#526273', fontSize: 13, fontWeight: active ? 600 : 400 },
      labelBgStyle: { fill: '#fff', fillOpacity: 0.97 }, labelBgPadding: [5, 3], labelBgBorderRadius: 3,
      interactionWidth: 22, focusable: true, ariaLabel: relationLabel(edge.type, edge.label),
    };
  });
  useLayoutEffect(() => {
    if (flow && canvasSize.width && canvasSize.height && filtered.nodes.length) {
      void flow.setViewport(viewport);
    }
  }, [flow, viewport, canvasSize.width, canvasSize.height, filtered.nodes.length]);
  return (
    <>
      {fullscreen ? <div className="graph-backdrop" onClick={onToggleFullscreen} /> : null}
    <section className={'research-graph ' + (fullscreen ? 'fullscreen' : '')}>
      <div className="graph-top">
        <h2>事件与证券的关系</h2>
        <div className="graph-top-right">
          <span className="graph-count">{filtered.nodes.length} 个实体 · {filtered.edges.length} 条关系</span>
          <button type="button" className="icon-button" aria-label="放大" onClick={() => flow?.zoomIn({ duration: 200 })}><ZoomIn size={16} /></button>
          <button type="button" className="icon-button" aria-label="缩小" onClick={() => flow?.zoomOut({ duration: 200 })}><ZoomOut size={16} /></button>
          <button type="button" className="icon-button" aria-label="重置视图" onClick={() => flow?.setViewport(viewport, { duration: 200 })}><RotateCcw size={15} /></button>
          <button type="button" className="icon-button" aria-label={fullscreen ? '退出全屏' : '全屏'} onClick={onToggleFullscreen}>{fullscreen ? <Minimize2 size={16} /> : <Maximize2 size={16} />}</button>
        </div>
      </div>
      <div className="graph-filters">
        {GROUPS.map((item) => <button type="button" key={item.value} className={group === item.value ? 'active' : ''} onClick={() => onGroupChange(item.value)}>{item.label}</button>)}
        <button type="button" className={'industry-toggle ' + (showIndustry ? 'active' : '')} onClick={() => setShowIndustry(!showIndustry)} title="行业分类不用于查询证券路径">{showIndustry ? <Eye size={13} /> : <EyeOff size={13} />} 行业分类</button>
      </div>
      <div className="graph-selection-slot">
        {path ? <div className="graph-path-note"><span>已选中 {path.nodes[path.nodes.length - 1]?.label} 的路径</span><button type="button" onClick={onClearPath}>取消选中</button></div> : <p>选择右侧证券可突出显示其路径；点击连线可查看原文。</p>}
      </div>
      <div className="graph-canvas-wrap research-graph-canvas" ref={container}>
        {!filtered.nodes.length ? <EmptyState title="该日期没有可显示的关系" description="切换日期或关系类型。" compact /> :
          <ReactFlow<EvidenceNode, Edge> key={structureKey} nodes={nodes} edges={edges}
            nodeTypes={nodeTypes} onInit={setFlow} defaultViewport={viewport}
            nodesDraggable={false} nodesConnectable={false} edgesReconnectable={false}
            minZoom={0.3} maxZoom={2} zoomOnDoubleClick={false} deleteKeyCode={null}
            onNodeClick={(_, node) => onSelectNode(node.data.entity)}
            onEdgeClick={(_, item) => { const edge = filtered.edges.find((entry) => entry.id === item.id); if (edge) onSelectEdge(edge); }}
            ariaLabelConfig={{ 'node.a11yDescription.default': '按 Enter 查看实体资料。', 'edge.a11yDescription.default': '按 Enter 查看关系原文。' }}>
            <Background gap={24} size={1} color="#e7ebef" />
          </ReactFlow>}
      </div>
      <div className="graph-bottom"><div className="graph-legend">
        {[...new Set(filtered.nodes.map((node) => node.type))].map((type) => <span key={type}><i style={{ background: nodeColor(type) }} />{typeLabel(type)}</span>)}
      </div><span className="graph-tip">拖动平移 · 滚轮缩放</span></div>
    </section>
    </>
  );
}
