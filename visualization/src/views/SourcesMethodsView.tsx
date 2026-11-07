import { useEffect, useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowUpRight,
  BookOpen,
  CalendarClock,
  ExternalLink,
  FileSearch,
  FileText,
  Filter,
  Link2,
  Search,
  ShieldCheck,
  X,
} from 'lucide-react';
import { api } from '../api';
import type { Health, Overview, SourceItem } from '../types';
import { EmptyState, ErrorState, Skeleton } from '../components/Ui';
import { groupColor, nodeColor, sourceTypeLabel, typeLabel } from '../lib/palette';
import { formatDate, formatDateTime, formatNumber, truncate } from '../lib/format';

const ENTITY_DESCRIPTIONS: Record<string, string> = {
  Company: '公司、集团和模型研发方。',
  Stock: '交易所证券，通过 LISTED_AS 与公司相连。',
  Model: 'AI 模型及版本。',
  Product: '芯片、服务器、云服务与软件产品。',
  Industry: '用于分类，不参与证券路径查询。',
  Event: '模型发布、硬件适配与云服务接入事件。',
};

const RELATION_DESCRIPTIONS: Record<string, string> = {
  DEVELOPED_BY: '模型 → 研发公司',
  RELEASED_MODEL: '事件 → 模型',
  LISTED_AS: '公司 → 上市证券',
  PRODUCES: '公司 → 产品',
  SUPPORTS_MODEL: '产品 → 模型（硬件适配）',
  HOSTS_MODEL: '产品 → 模型（云服务接入）',
  BELONGS_TO: '主体 → 行业分类',
  UPSTREAM_OF: '产品 → 下游产品',
  CONCERNS: '事件 → 涉及实体',
};

const RELATION_GROUP: Record<string, string> = {
  DEVELOPED_BY: 'direct',
  RELEASED_MODEL: 'direct',
  LISTED_AS: 'direct',
  PRODUCES: 'direct',
  CONCERNS: 'direct',
  SUPPORTS_MODEL: 'adaptation',
  HOSTS_MODEL: 'distribution',
  BELONGS_TO: 'industry',
  UPSTREAM_OF: 'industry',
};

export function SourcesMethodsView({
  overview,
  health,
  overviewError,
  onRetryOverview,
}: {
  overview?: Overview;
  health?: Health;
  overviewError: unknown;
  onRetryOverview: () => void;
}) {
  const [tab, setTab] = useState<'sources' | 'methods'>('sources');
  const [search, setSearch] = useState('');
  const [typeFilter, setTypeFilter] = useState('all');
  const [selectedId, setSelectedId] = useState<string | null>(null);

  const sourcesQuery = useQuery({ queryKey: ['sources'], queryFn: api.sources, retry: 1 });
  const sources = sourcesQuery.data?.sources ?? [];
  const types = useMemo(() => [...new Set(sources.map((source) => source.source_type))].sort(), [sources]);
  const filtered = useMemo(() => {
    const needle = search.trim().toLowerCase();
    return sources.filter((source) => {
      if (typeFilter !== 'all' && source.source_type !== typeFilter) return false;
      if (!needle) return true;
      return [source.title, source.publisher, source.text, source.id].join(' ').toLowerCase().includes(needle);
    });
  }, [sources, search, typeFilter]);

  useEffect(() => {
    if (filtered.length === 0) {
      setSelectedId(null);
      return;
    }
    if (!selectedId || !filtered.some((source) => source.id === selectedId)) setSelectedId(filtered[0].id);
  }, [filtered, selectedId]);

  const selected = filtered.find((source) => source.id === selectedId) ?? null;
  const relationTypes = useMemo(
    () => [...(overview?.relation_types ?? [])].sort((a, b) => b.count - a.count),
    [overview],
  );

  return (
    <div className="sources-page">
      <header className="page-header">
        <div>
          <span className="section-kicker">资料与方法</span>
          <h1>资料与方法</h1>
          <p>当前数据范围、关系规则、日期处理与行情计算方法。</p>
        </div>
        <div className="page-tabs">
          <button type="button" className={tab === 'sources' ? 'active' : ''} onClick={() => setTab('sources')}>
            <FileSearch size={14} /> 资料来源
          </button>
          <button type="button" className={tab === 'methods' ? 'active' : ''} onClick={() => setTab('methods')}>
            <BookOpen size={14} /> 方法说明
          </button>
        </div>
      </header>

      {tab === 'sources' ? (
        <section className="panel sources-panel">
          <div className="source-toolbar">
            <div className="search-box">
              <Search size={15} />
              <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="搜索标题、发布方或原文摘录…" />
              {search ? <button type="button" onClick={() => setSearch('')} aria-label="清空"><X size={13} /></button> : null}
            </div>
            <select className="source-type-select" aria-label="筛选来源类型" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)}>
              <option value="all">全部来源类型 · {sources.length}</option>
              {types.map((type) => <option key={type} value={type}>{sourceTypeLabel(type)} · {sources.filter((source) => source.source_type === type).length}</option>)}
            </select>
            <span className="toolbar-count"><Filter size={12} /> {filtered.length} 条</span>
          </div>

          {sourcesQuery.isLoading ? (
            <div className="sources-loading"><Skeleton height={60} /><Skeleton height={60} /><Skeleton height={60} /></div>
          ) : sourcesQuery.isError ? (
            <ErrorState title="来源加载失败" error={sourcesQuery.error} onRetry={() => sourcesQuery.refetch()} />
          ) : sources.length === 0 ? (
            <EmptyState icon={<FileText size={22} />} title="暂无来源记录" description="后端尚未返回来源清单。" />
          ) : (
            <div className="sources-layout">
              <div className="sources-list">
                {filtered.length === 0 ? (
                  <EmptyState icon={<Search size={20} />} title="没有匹配来源" description="清空搜索或切换类型。" compact />
                ) : filtered.map((source) => (
                  <button
                    type="button"
                    key={source.id}
                    className={`source-row ${source.id === selectedId ? 'selected' : ''}`}
                    onClick={() => setSelectedId(source.id)}
                  >
                    <span className="source-type">{sourceTypeLabel(source.source_type)}</span>
                    <span><strong>{source.title}</strong><small>{source.publisher} · {formatDate(source.published_at)}</small></span>
                    <ArrowUpRight size={14} />
                  </button>
                ))}
              </div>
              <div className="source-detail">
                {selected ? <SourceDetail source={selected} /> : <EmptyState icon={<FileSearch size={22} />} title="选择一条来源" description="查看原文摘录和原始链接。" compact />}
              </div>
            </div>
          )}
        </section>
      ) : (
        <div className="methods-page">
          {overviewError ? <ErrorState title="方法数据加载失败" error={overviewError} onRetry={onRetryOverview} /> : null}
          <section className="method-stats">
            {[
              ['图谱实体', overview?.stats.entities],
              ['关系', overview?.stats.relations],
              ['来源', overview?.stats.documents],
              ['事件', overview?.stats.events],
              ['证券', overview?.stats.stocks],
            ].map(([label, value]) => (
              <div key={label as string}><span>{label}</span><b>{formatNumber(value as number | undefined)}</b></div>
            ))}
            <div><span>资料登记至</span><b className="small">{formatDate(overview?.as_of)}</b></div>
          </section>

          <div className="method-grid">
            <section className="panel method-card">
              <div className="panel-head"><div><span className="panel-kicker">图谱结构</span><h2>实体类型</h2></div></div>
              <div className="schema-rows">
                {(overview?.entity_types ?? []).slice().sort((a, b) => b.count - a.count).map((item) => (
                  <div key={item.type}>
                    <i style={{ background: nodeColor(item.type) }} />
                    <span><strong>{typeLabel(item.type)} <em>{item.type}</em></strong><small>{ENTITY_DESCRIPTIONS[item.type] ?? '扩展实体类型'}</small></span>
                    <b>{item.count}</b>
                  </div>
                ))}
              </div>
            </section>

            <section className="panel method-card">
              <div className="panel-head"><div><span className="panel-kicker">关系类型</span><h2>关系定义</h2></div></div>
              <div className="schema-rows">
                {relationTypes.map((item) => {
                  const group = RELATION_GROUP[item.type] ?? 'direct';
                  return (
                    <div key={item.type}>
                      <i style={{ background: groupColor(group) }} />
                      <span><strong>{item.label} <em>{item.type}</em></strong><small>{RELATION_DESCRIPTIONS[item.type] ?? '扩展关系类型'}</small></span>
                      <b>{item.count}</b>
                    </div>
                  );
                })}
              </div>
            </section>

            <section className="panel method-card">
              <div className="panel-head"><div><span className="panel-kicker">来源与规则</span><h2>关系如何成立</h2></div></div>
              <ul className="rule-list">
                <li><ShieldCheck size={14} /> 每条关系保留原文摘录、来源链接与日期。</li>
                <li><ShieldCheck size={14} /> 证券关系由研发、产品、适配、云接入和上市关系组合。</li>
                <li><ShieldCheck size={14} /> 历史日期只显示该日期前已登记的关系。</li>
                <li><ShieldCheck size={14} /> 抽取结果通过实体对齐和原文校验后写入图谱。</li>
              </ul>
            </section>

            <section className="panel method-card">
              <div className="panel-head"><div><span className="panel-kicker">行情计算</span><h2>事件窗口</h2></div></div>
              <div className="formula">R(t₀,t₁) = P(t₁) / P(t₀) − 1</div>
              <ul className="rule-list">
                <li><CalendarClock size={14} /> 披露时间只有日期时，采用其后首个交易日为 T0；基期为 T−1 收盘。</li>
                <li><CalendarClock size={14} /> 展示 1 / 3 / 5 个交易日累计收益与相对基准差值（pp）。</li>
                <li><CalendarClock size={14} /> 窗口收益为区间计算，不解释涨跌原因。</li>
              </ul>
            </section>
          </div>

          <div className="method-bottom">
            <section className="panel method-card">
              <div className="panel-head"><div><span className="panel-kicker">当前范围</span><h2>数据范围</h2></div></div>
              <div className="boundary-cols">
                <div><strong>当前数据</strong><p>覆盖 {formatNumber(overview?.stats.events)} 个事件、{formatNumber(overview?.stats.documents)} 条来源、{formatNumber(overview?.stats.stocks)} 只证券。</p></div>
                <div><strong>后续工作</strong><p>扩充事件与证券覆盖，补充更多官方资料和交易日窗口。</p></div>
              </div>
            </section>
            <section className="panel method-card system-card">
              <div className="panel-head"><div><span className="panel-kicker">系统</span><h2>运行信息</h2></div></div>
              <div className="system-rows">
                <div><span>图引擎</span><b>{health?.engine ?? '—'}</b></div>
                <div><span>抽取方式</span><b>{overview?.llm.available ? '实时 / 回放' : '回放'}</b></div>
                <div><span>资料登记至</span><b>{formatDate(overview?.as_of)}</b></div>
                <div><span>最近更新</span><b>{formatDateTime(overview?.updated_at)}</b></div>
              </div>
            </section>
          </div>

          <p className="method-footnote"><Link2 size={13} /> 统计来自当前图谱与来源清单。</p>
        </div>
      )}
    </div>
  );
}

function SourceDetail({ source }: { source: SourceItem }) {
  return (
    <article>
      <div className="source-detail-top">
        <span className="source-type">{sourceTypeLabel(source.source_type)}</span>
        <span className="mono">{source.id}</span>
      </div>
      <h2>{source.title}</h2>
      <div className="source-meta-grid">
        <div><span>发布方</span><b>{source.publisher || '—'}</b></div>
        <div><span>发布日期</span><b>{formatDate(source.published_at)}</b></div>
        <div><span>采集日期</span><b>{formatDate(source.retrieved_at)}</b></div>
        <div><span>来源类型</span><b>{sourceTypeLabel(source.source_type)}</b></div>
      </div>
      <h3>原文摘录</h3>
      <p className="source-text">{source.text}</p>
      <div className="source-foot">
        {source.url ? <a className="button primary small" href={source.url} target="_blank" rel="noreferrer noopener">打开原始来源 <ExternalLink size={13} /></a> : <span className="muted">未提供外链</span>}
        <span className="mono source-url">{truncate(source.url || '—', 84)}</span>
      </div>
    </article>
  );
}
