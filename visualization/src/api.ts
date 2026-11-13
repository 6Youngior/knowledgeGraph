import type {
  EventDetail,
  EventItem,
  ExtractRequest,
  ExtractionResult,
  ExtractionSample,
  GraphPayload,
  GraphQuery,
  Health,
  IngestResult,
  MarketData,
  Overview,
  QuantResponse,
  ResearchBrief,
  ResearchDetail,
  ResearchOverview,
  SourceItem,
} from './types';

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? '/api';

export class ApiError extends Error {
  status: number;

  constructor(message: string, status = 0) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

type QueryValue = string | number | boolean | null | undefined;

function withQuery(path: string, params?: Record<string, QueryValue>): string {
  if (!params) return path;
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== '') {
      search.set(key, String(value));
    }
  });
  const suffix = search.toString();
  return suffix ? `${path}?${suffix}` : path;
}

async function request<T>(
  path: string,
  init?: RequestInit,
  timeoutMs = 20000,
): Promise<T> {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...init,
      headers: {
        Accept: 'application/json',
        ...(init?.body ? { 'Content-Type': 'application/json' } : {}),
        ...init?.headers,
      },
      signal: controller.signal,
    });

    const text = await response.text();
    let payload: unknown = null;
    if (text) {
      try {
        payload = JSON.parse(text);
      } catch {
        payload = text;
      }
    }

    if (!response.ok) {
      const record =
        payload && typeof payload === 'object'
          ? (payload as Record<string, unknown>)
          : null;
      const detail = record?.detail ?? record?.error ?? record?.message;
      const message =
        typeof detail === 'string'
          ? detail
          : detail
            ? JSON.stringify(detail)
            : `研究服务返回 ${response.status}`;
      throw new ApiError(message, response.status);
    }

    return payload as T;
  } catch (error) {
    if (error instanceof ApiError) throw error;
    if (error instanceof DOMException && error.name === 'AbortError') {
      throw new ApiError('请求超时，请检查研究服务或稍后重试。');
    }
    throw new ApiError('无法连接研究服务（/api），请确认后端已启动。');
  } finally {
    window.clearTimeout(timer);
  }
}

export const api = {
  health: () => request<Health>('/health', undefined, 8000),
  overview: () => request<Overview>('/overview'),
  events: () => request<{ events: EventItem[] }>('/events'),
  graph: (params: GraphQuery) =>
    request<GraphPayload>(
      withQuery('/graph', {
        event_id: params.event_id,
        q: params.q,
        relation_group: params.relation_group,
        as_of: params.as_of,
      }),
    ),
  event: (id: string, asOf?: string) =>
    request<EventDetail>(
      withQuery(`/events/${encodeURIComponent(id)}`, { as_of: asOf }),
    ),
  relatedStocks: (eventId: string) =>
    request<{ stocks: EventDetail['stocks'] }>(
      withQuery('/stocks/related', { event_id: eventId }),
    ),
  market: (symbol: string, eventId: string, windowDays: number, asOf?: string) =>
    request<MarketData>(
      withQuery(`/market/${encodeURIComponent(symbol)}`, {
        event_id: eventId,
        window: windowDays,
        as_of: asOf,
      }),
    ),
  sources: () => request<{ sources: SourceItem[] }>('/sources'),
  source: (id: string) =>
    request<SourceItem>(`/sources/${encodeURIComponent(id)}`),
  samples: () =>
    request<{ samples: ExtractionSample[] }>('/extraction/samples'),
  extract: (body: ExtractRequest) =>
    request<ExtractionResult>(
      '/extract',
      { method: 'POST', body: JSON.stringify(body) },
      180000,
    ),
  ingest: (extractionId: string) =>
    request<IngestResult>('/ingest', {
      method: 'POST',
      body: JSON.stringify({ extraction_id: extractionId }),
    }),
  reset: () =>
    request<{ status: string; stats: Overview['stats'] }>('/reset', {
      method: 'POST',
    }),
  quant: (view: 'ranking' | 'backtest' | 'overview', limit = 30) =>
    request<QuantResponse>(withQuery('/quant', { view, limit }), undefined, 15000),
  research: () => request<ResearchOverview>('/research', undefined, 12000),
  researchDetail: (eventId: string, asOf?: string) =>
    request<ResearchDetail>(
      withQuery(`/research/${encodeURIComponent(eventId)}`, { as_of: asOf }),
      undefined,
      12000,
    ),
  researchBrief: (eventId: string, asOf?: string) =>
    request<ResearchBrief>(
      `/research/${encodeURIComponent(eventId)}/brief`,
      {
        method: 'POST',
        body: JSON.stringify(asOf ? { as_of: asOf } : {}),
      },
      30000,
    ),
};

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return '发生未知错误，请稍后重试。';
}
