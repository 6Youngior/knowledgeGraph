import dagre from '@dagrejs/dagre';
import type { GraphEdge, GraphNode } from '../types';

const TYPES = ['Event', 'Model', 'Product', 'Company', 'Stock', 'Industry'];
export interface RoleLayout { positions: Map<string, { x: number; y: number }>; }

/** Dagre ranks follow reading order; the displayed edges retain their factual direction. */
export function buildRoleLayout(nodes: GraphNode[], edges: GraphEdge[], horizontal = false): RoleLayout {
  const present = new Set(nodes.map((node) => node.type));
  const ranks = new Map(TYPES.filter((type) => present.has(type)).map((type, i) => [type, i]));
  const nodeMap = new Map(nodes.map((node) => [node.id, node]));
  const graph = new dagre.graphlib.Graph();
  graph.setGraph({
    rankdir: horizontal ? 'LR' : 'TB', ranksep: horizontal ? 88 : 40,
    nodesep: horizontal ? 65 : 50, edgesep: 24, marginx: 16, marginy: 16,
    acyclicer: 'greedy', ranker: 'network-simplex',
  });
  graph.setDefaultEdgeLabel(() => ({}));
  nodes.forEach((node) => graph.setNode(node.id, { width: 174, height: 60 }));
  edges.forEach((edge) => {
    const source = nodeMap.get(edge.source); const target = nodeMap.get(edge.target);
    if (!source || !target) return;
    const a = ranks.get(source.type) ?? 0; const b = ranks.get(target.type) ?? 0;
    graph.setEdge(a <= b ? source.id : target.id, a <= b ? target.id : source.id, {
      minlen: Math.max(1, Math.abs(a - b)), weight: ['LISTED_AS', 'PRODUCES'].includes(edge.type) ? 8 : 2,
    });
  });
  dagre.layout(graph);
  return { positions: new Map(nodes.map((node) => {
    const point = graph.node(node.id);
    return [node.id, { x: point.x - 87, y: point.y - 30 }];
  })) };
}
