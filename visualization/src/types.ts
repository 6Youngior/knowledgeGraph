export type ViewKey = 'quant' | 'research' | 'cases' | 'update' | 'sources';

export type RelationGroup = 'direct' | 'adaptation' | 'industry' | 'distribution';

export type EntityType =
  | 'Company'
  | 'Stock'
  | 'Model'
  | 'Product'
  | 'Industry'
  | 'Event'
  | string;

export interface GraphNode {
  id: string;
  label: string;
  type: EntityType;
  aliases?: string[];
  description?: string;
  source_ids?: string[];
  properties?: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  label?: string;
  source_ids?: string[];
  evidence?: string;
  disclosed_at?: string;
  relation_group?: RelationGroup | string;
}

export interface EventItem {
  id: string;
  title: string;
  date: string;
  event_at: string;
  disclosed_at: string;
  type: string;
  summary: string;
  entity_id: string;
  source_ids: string[];
}

export interface SourceItem {
  id: string;
  title: string;
  url: string;
  publisher: string;
  published_at: string;
  retrieved_at?: string;
  event_at: string;
  text: string;
  source_type: string;
}

export interface GraphPayload {
  nodes: GraphNode[];
  edges: GraphEdge[];
  focus_id?: string | null;
  stats: { nodes: number; edges: number };
}

export interface OverviewStats {
  entities: number;
  relations: number;
  documents: number;
  events: number;
  stocks: number;
}

export interface Overview {
  title: string;
  description: string;
  as_of: string;
  stats: OverviewStats;
  entity_types: Array<{ type: string; count: number }>;
  relation_types: Array<{ type: string; label: string; count: number }>;
  llm: { available: boolean; provider: string };
  updated_at: string;
}

export interface Health {
  status: string;
  engine: string;
  llm_available: boolean;
  llm_provider: string;
}

export interface StockPathOption {
  nodes: GraphNode[];
  edges: GraphEdge[];
  relation_group: RelationGroup | string;
  available_from?: string;
  source_ids?: string[] | string;
}

export interface RelatedStock {
  id: string;
  symbol: string;
  label: string;
  company_id: string;
  company_name: string;
  market: string;
  currency: string;
  relation_group: RelationGroup | string;
  relation_groups?: string[];
  path_count?: number;
  listing_date?: string;
  listed_at_event?: boolean;
  market_note?: string;
  paths?: StockPathOption[];
  path: { nodes: GraphNode[]; edges: GraphEdge[] };
  source_ids: string[];
  evidence_dates?: string[];
}

export interface TimelineItem {
  date: string;
  title: string;
  type: string;
  source_ids: string[];
}

export interface EventDetail {
  event: EventItem;
  graph: GraphPayload;
  stocks: RelatedStock[];
  sources: SourceItem[];
  timeline: TimelineItem[];
  summary: string;
}

export interface PricePoint {
  date: string;
  close: number | null;
  volume: number | null;
  relative_day: number;
  normalized: number | null;
  benchmark_normalized: number | null;
}

export interface MarketData {
  symbol: string;
  name: string;
  currency: string;
  event_date: string;
  anchor_date: string;
  anchor_policy: string;
  prices: PricePoint[];
  returns: { '1': number | null; '3': number | null; '5': number | null };
  benchmark_returns?: { '1': number | null; '3': number | null; '5': number | null };
  excess_returns?: { '1': number | null; '3': number | null; '5': number | null };
  window_dates?: string[];
  benchmark: { symbol: string; name: string } | null;
  provider: string;
  source_url: string;
  adjusted: string;
  notes: string[];
}

export interface ResearchFinding {
  id: string;
  title: string;
  text: string;
  kind: 'fact' | 'derived' | 'boundary' | string;
  source_ids: string[];
}

export interface ResearchRole {
  group: string;
  label: string;
  count: number;
  symbols: string[];
}

export interface ResearchExcluded {
  id: string;
  label: string;
  symbol: string;
  reason: string;
  reason_code: string;
}

export interface ResearchMilestone {
  date: string;
  title: string;
  symbols: string[];
}

export interface ResearchTemporal {
  cutoff: string | null;
  current_count: number;
  visible_count: number;
  excluded_count: number;
  milestones: ResearchMilestone[];
}

export interface ResearchCoverage {
  path_count: number;
  source_count: number;
  source_types: string[];
  max_hops: number;
}

export interface ResearchUpdate {
  id: string;
  title: string;
  document_id: string;
}

export interface ResearchDetail {
  question: string;
  event_id: string;
  as_of: string | null;
  headline: string;
  findings: ResearchFinding[];
  roles: ResearchRole[];
  excluded: ResearchExcluded[];
  temporal: ResearchTemporal;
  coverage: ResearchCoverage;
  updates: ResearchUpdate[];
}

export interface ResearchEventSummary {
  id: string;
  title: string;
  date: string;
  model: string;
  stock_count: number;
  role_counts: Record<string, number>;
  source_count: number;
  max_hops: number;
  summary?: string;
  historical_stock_count?: number;
  temporal_summary?: string;
}

export interface ResearchOverview {
  events: ResearchEventSummary[];
  stats: OverviewStats & Record<string, number>;
  coverage: ResearchCoverage;
}

export interface ResearchBrief {
  title: string;
  markdown: string;
  filename: string;
  stats: Record<string, unknown>;
}

export interface ExtractionSample {
  id: string;
  title: string;
  document_id: string;
  text: string;
  url: string;
  notes: string;
}

export interface ExtractionDocument {
  id?: string;
  document_id?: string;
  title?: string;
  url?: string;
  publisher?: string;
  published_at?: string;
  text?: string;
}

export interface ExtractionPreview {
  new_nodes?: number;
  new_edges?: number;
  matched_entities?: Array<{
    input: string;
    canonical_id: string;
    label: string;
  }>;
}

export interface ExtractionResult {
  extraction_id: string;
  mode: 'live' | 'replay';
  model: string;
  elapsed_ms: number;
  document: ExtractionDocument;
  entities: GraphNode[];
  relations: GraphEdge[];
  events: EventItem[];
  validation: { valid: boolean; warnings: string[] };
  preview: ExtractionPreview;
  raw_output: unknown;
}

export interface IngestResult {
  added_nodes: number;
  added_edges: number;
  updated_nodes: number;
  updated_edges: number;
  stats: OverviewStats;
  graph?: GraphPayload;
}

export interface ExtractRequest {
  sample_id?: string;
  text?: string;
  title?: string;
  url?: string;
  mode: 'auto' | 'live' | 'replay';
}

export interface GraphQuery {
  event_id?: string;
  q?: string;
  relation_group?: string;
  as_of?: string;
}


export interface QuantCommon {
  found: boolean;
  view?: string;
  as_of?: string;
  model?: string;
  engine?: string;
  feature_as_of?: string;
  available_at?: string;
  universe_size?: number;
  horizon_trading_days?: number;
  status?: string;
  experiment_id?: string;
  segments?: Record<string, [string, string]>;
}

export interface QuantRankingItem {
  rank: number;
  symbol: string;
  name: string;
  score: number;
}

export interface QuantCostAssumption {
  open_rate?: number;
  close_rate?: number;
  min_cost_cny?: number;
}

export interface QuantCurvePoint {
  date: string;
  strategy: number;
  benchmark: number;
  ai_equal_weight?: number;
  momentum_20d?: number;
}

export interface QuantRanking extends QuantCommon {
  ranking?: QuantRankingItem[];
  score_type?: string;
  note?: string;
}

export interface QuantBacktest extends QuantCommon {
  start?: string;
  end?: string;
  test_predictions?: number;
  controls?: Record<string, { net_cumulative_return: number; max_drawdown: number }>;
  ic_mean?: number;
  rank_ic_mean?: number;
  net_cumulative_return?: number;
  benchmark_cumulative_return?: number;
  max_drawdown?: number;
  topk?: number;
  rebalance_sessions?: number;
  cost_assumption?: QuantCostAssumption;
  curve?: QuantCurvePoint[];
  limitations?: string[];
}

export type QuantResponse = QuantRanking & QuantBacktest;
