import dagre from '@dagrejs/dagre';
import type { GraphEdge, GraphNode } from '../types';

export interface RoleLayout {
  positions: Map<string, { x: number; y: number }>;
  zoom: number;
}

const ROW_TYPES = ['Event', 'Model', 'Product', 'Company', 'Stock', 'Industry'];

/**
 * Dagre layered layout, adapted from the official React Flow "layout/dagre"
 * example (https://reactflow.dev/examples/layout/dagre).
 *
 * Real evidence edges drive crossing minimisation. Their direction is oriented
 * to the reading order only inside the layout input; the rendered facts keep
 * their original direction. In particular each company stays aligned with its
 * own securities instead of connecting every type row to every next row.
 */
export function buildRoleLayout(nodes: GraphNode[], edges: GraphEdge[]): RoleLayout {
  const byType = new Map<string, GraphNode[]>();
  nodes.forEach((node) => {
    const list = byType.get(node.type) ?? [];
    list.push(node);
    byType.set(node.type, list);
  });

  const ranks = new Map(ROW_TYPES.filter((type) => byType.has(type)).map((type, index) => [type, index]));
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: 'TB',
    ranksep: 34,
    nodesep: 42,
    edgesep: 10,
    marginx: 0,
    marginy: 0,
    acyclicer: 'greedy',
    ranker: 'network-simplex',
  });
  graph.setDefaultEdgeLabel(() => ({}));

  nodes.forEach((node) => {
    graph.setNode(node.id, { width: 150, height: 46 });
  });

  for (const edge of edges) {
    const source = nodeMap.get(edge.source);
    const target = nodeMap.get(edge.target);
    if (!source || !target) continue;
    const sourceRank = ranks.get(source.type) ?? 0;
    const targetRank = ranks.get(target.type) ?? 0;
    const forward = sourceRank <= targetRank;
    graph.setEdge(forward ? source.id : target.id, forward ? target.id : source.id, {
      minlen: Math.max(1, Math.abs(sourceRank - targetRank)),
      weight: edge.type === 'LISTED_AS' || edge.type === 'PRODUCES' ? 8 : 2,
    });
  }

  dagre.layout(graph);

  const positions = new Map<string, { x: number; y: number }>();
  let minX = Infinity;
  let maxX = -Infinity;
  let minY = Infinity;
  let maxY = -Infinity;

  nodes.forEach((node) => {
    const point = graph.node(node.id) ?? { x: 0, y: 0 };
    positions.set(node.id, { x: point.x, y: point.y });
    minX = Math.min(minX, point.x);
    maxX = Math.max(maxX, point.x);
    minY = Math.min(minY, point.y);
    maxY = Math.max(maxY, point.y);
  });

  const centerX = Number.isFinite(minX) ? (minX + maxX) / 2 : 0;
  const centerY = Number.isFinite(minY) ? (minY + maxY) / 2 : 0;
  positions.forEach((point, id) => {
    positions.set(id, { x: point.x - centerX, y: point.y - centerY });
  });

  const width = Number.isFinite(minX) ? maxX - minX : 0;
  const height = Number.isFinite(minY) ? maxY - minY : 0;
  const zoom = Math.min(1, Math.max(0.92, Math.min(960 / (width + 200), 380 / (height + 90))));

  return { positions, zoom };
}
