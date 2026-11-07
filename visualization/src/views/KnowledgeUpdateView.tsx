import { useEffect, useMemo, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  AlertTriangle,
  ArrowLeft,
  ArrowRight,
  CheckCircle2,
  ChevronDown,
  Clipboard,
  Database,
  ExternalLink,
  FileText,
  GitBranch,
  History,
  Link2,
  Plus,
  Radio,
  RotateCcw,
  Sparkles,
  Wand2,
} from 'lucide-react';
import { api, errorMessage } from '../api';
import type { EventItem, ExtractRequest, GraphNode, Overview } from '../types';
import { ConfirmDialog } from '../components/ConfirmDialog';
import { useToast } from '../components/Toast';
import { ErrorState, ModeBadge, Skeleton, Spinner, TypeBadge } from '../components/Ui';
import { nodeColor, relationLabel } from '../lib/palette';
import { formatDate, formatNumber } from '../lib/format';

const MODES = [
  { value: 'auto' as const, label: '自动', icon: Wand2, hint: '自动选择实时或回放' },
  { value: 'live' as const, label: '实时', icon: Radio, hint: '调用已配置模型' },
  { value: 'replay' as const, label: '回放', icon: History, hint: '使用已有抽取结果' },
];

export function KnowledgeUpdateView({
  overview,
  event,
  demoActive,
  onNavigateResearch,
}: {
  overview?: Overview;
  event?: EventItem;
  demoActive: boolean;
  onNavigateResearch: (focusGroup?: string, focusSymbol?: string) => void;
}) {
  const queryClient = useQueryClient();
  const { notify } = useToast();
  const [sourceMode, setSourceMode] = useState<'sample' | 'text'>('sample');
  const [sampleId, setSampleId] = useState<string | null>(null);
  const [text, setText] = useState('');
  const [title, setTitle] = useState('');
  const [url, setUrl] = useState('');
  const [mode, setMode] = useState<'auto' | 'live' | 'replay'>('auto');
  const [elapsed, setElapsed] = useState(0);
  const [confirmReset, setConfirmReset] = useState(false);
  const demoPrepared = useRef(false);

  const samplesQuery = useQuery({ queryKey: ['samples'], queryFn: api.samples, retry: 1 });
  const samples = samplesQuery.data?.samples ?? [];
  const selectedSample = samples.find((sample) => sample.id === sampleId);

  useEffect(() => {
    if (!sampleId && samples.length > 0) setSampleId(samples[0].id);
  }, [samples, sampleId]);

  useEffect(() => {
    if (!demoActive || demoPrepared.current || samples.length === 0) return;
    demoPrepared.current = true;
    setSourceMode('sample');
    setSampleId(samples[0].id);
    setMode('replay');
  }, [demoActive, samples]);

  const extractMutation = useMutation({ mutationFn: (body: ExtractRequest) => api.extract(body) });
  const ingestMutation = useMutation({
    mutationFn: (extractionId: string) => api.ingest(extractionId),
    onSuccess: (result) => {
      queryClient.invalidateQueries();
      notify(
        result.added_nodes + result.added_edges > 0
          ? '已写入图谱，当前事件的研究结果会同步刷新。'
          : '未新增节点或关系。',
        'success',
      );
    },
    onError: (error) => notify(errorMessage(error), 'error'),
  });
  const resetMutation = useMutation({
    mutationFn: api.reset,
    onSuccess: () => {
      queryClient.invalidateQueries();
      extractMutation.reset();
      ingestMutation.reset();
      setConfirmReset(false);
      notify('图谱已恢复初始数据。', 'success');
    },
    onError: (error) => {
      setConfirmReset(false);
      notify(errorMessage(error), 'error');
    },
  });

  useEffect(() => {
    if (!extractMutation.isPending) return;
    const started = Date.now();
    setElapsed(0);
    const timer = window.setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 250);
    return () => window.clearInterval(timer);
  }, [extractMutation.isPending]);

  const request = useMemo<ExtractRequest | null>(() => {
    if (sourceMode === 'sample') return sampleId ? { sample_id: sampleId, mode } : null;
    return text.trim() ? { text: text.trim(), title: title.trim() || undefined, url: url.trim() || undefined, mode } : null;
  }, [sourceMode, sampleId, mode, text, title, url]);

  const result = extractMutation.data;
  const ingestResult = ingestMutation.data;
  const entityGroups = useMemo(() => {
    const groups = new Map<string, GraphNode[]>();
    (result?.entities ?? []).forEach((entity) => {
      const list = groups.get(entity.type) ?? [];
      list.push(entity);
      groups.set(entity.type, list);
    });
    return [...groups.entries()];
  }, [result]);
  const nodeLabels = useMemo(() => {
    const map = new Map<string, string>();
    result?.entities.forEach((entity) => map.set(entity.id, entity.label));
    result?.preview.matched_entities?.forEach((match) => map.set(match.canonical_id, match.label));
    return map;
  }, [result]);
  const rawText = useMemo(() => {
    if (!result) return '';
    return typeof result.raw_output === 'string' ? result.raw_output : JSON.stringify(result.raw_output, null, 2);
  }, [result]);

  const preferredGroup = useMemo(() => {
    if (!result) return 'direct';
    if (result.relations.some((relation) => relation.type === 'HOSTS_MODEL')) return 'distribution';
    if (result.relations.some((relation) => relation.type === 'SUPPORTS_MODEL')) return 'adaptation';
    return 'direct';
  }, [result]);

  const focusSymbol = useMemo(() => {
    const graph = ingestMutation.data?.graph;
    if (!result || !graph) return undefined;
    // Focus the company that owns the newly connected product, not any
    // company mentioned by the document (e.g. the model developer).
    const support = result.relations.find(
      (relation) => relation.type === 'SUPPORTS_MODEL' || relation.type === 'HOSTS_MODEL',
    );
    let companyId: string | undefined;
    if (support) {
      const producer = graph.edges.find(
        (edge) => edge.type === 'PRODUCES' && edge.target === support.source,
      );
      companyId = producer?.source;
    }
    const stock = graph.nodes.find(
      (node) =>
        node.type === 'Stock' &&
        (companyId
          ? String(node.properties?.company_id ?? '') === companyId
          : false),
    );
    const symbol = stock?.properties?.symbol;
    return symbol ? String(symbol) : undefined;
  }, [result, ingestMutation.data]);

  const resetResults = () => {
    extractMutation.reset();
    ingestMutation.reset();
  };

  return (
    <div className="update-page">
      <header className="page-header">
        <div>
          <span className="section-kicker">知识更新</span>
          <h1>用新资料更新图谱</h1>
          <p>选择或粘贴一篇资料，抽取实体与关系；核对原文后写入图谱。</p>
        </div>
        {event ? (
          <div className="context-pill">
            <span>当前事件</span>
            <strong>{event.title}</strong>
            <small>{formatDate(event.event_at || event.date)}</small>
          </div>
        ) : null}
      </header>

      {demoActive ? (
        <div className="demo-context">
          <Sparkles size={15} />
          <div>
            <strong>操作演示 5/5 · 更新图谱</strong>
            <span>已选好 GLM-5 适配样例和回放模式；运行抽取、确认入图后，回到事件查看新增证券。</span>
          </div>
        </div>
      ) : null}

      <div className="update-grid">
        <section className="panel update-input">
          <div className="panel-head">
            <div>
              <span className="panel-kicker">资料输入</span>
              <h2>选择资料</h2>
            </div>
            <span className="count-note"><FileText size={12} /> 单篇增量</span>
          </div>

          <div className="tab-row">
            <button type="button" className={sourceMode === 'sample' ? 'active' : ''} onClick={() => { setSourceMode('sample'); resetResults(); }}>
              示例资料
            </button>
            <button type="button" className={sourceMode === 'text' ? 'active' : ''} onClick={() => { setSourceMode('text'); resetResults(); }}>
              粘贴文本
            </button>
          </div>

          {sourceMode === 'sample' ? (
            <div className="sample-area">
              {samplesQuery.isLoading ? (
                <div className="sample-list">{[0, 1].map((item) => <Skeleton key={item} height={70} />)}</div>
              ) : samplesQuery.isError ? (
                <ErrorState title="样例加载失败" error={samplesQuery.error} onRetry={() => samplesQuery.refetch()} compact />
              ) : samples.length === 0 ? (
                <p className="muted">后端没有返回已验证样例。</p>
              ) : (
                <div className="sample-list">
                  {samples.map((sample) => (
                    <button
                      type="button"
                      key={sample.id}
                      className={`sample-item ${sample.id === sampleId ? 'selected' : ''}`}
                      onClick={() => { setSampleId(sample.id); resetResults(); }}
                    >
                      <span className="sample-radio" />
                      <span>
                        <strong>{sample.title}</strong>
                        <small>{sample.notes}</small>
                      </span>
                    </button>
                  ))}
                </div>
              )}
              {selectedSample ? (
                <div className="sample-excerpt">
                  <div>
                    <span>原文摘录</span>
                    {selectedSample.url ? (
                      <a href={selectedSample.url} target="_blank" rel="noreferrer noopener">
                        打开来源 <ExternalLink size={11} />
                      </a>
                    ) : null}
                  </div>
                  <p>{selectedSample.text}</p>
                </div>
              ) : null}
            </div>
          ) : (
            <div className="text-form">
              <label><span>标题</span><input value={title} onChange={(event) => { setTitle(event.target.value); resetResults(); }} placeholder="公告或新闻标题" /></label>
              <label><span>来源链接</span><input value={url} onChange={(event) => { setUrl(event.target.value); resetResults(); }} placeholder="https://…" /></label>
              <label><span>正文摘录</span><textarea rows={8} value={text} onChange={(event) => { setText(event.target.value); resetResults(); }} placeholder="粘贴新闻或公告正文…" /></label>
              <small className="field-hint">{formatNumber(text.length)} / 16,000 字符</small>
            </div>
          )}

          <div className="mode-block">
            <div className="mode-title"><span>抽取模式</span><small>结果会标注实时或回放</small></div>
            <div className="mode-cards" role="group" aria-label="选择抽取模式">
              {MODES.map((item) => {
                const Icon = item.icon;
                return (
                  <button
                    type="button"
                    key={item.value}
                    className={`mode-card ${mode === item.value ? 'active' : ''}`}
                    onClick={() => setMode(item.value)}
                    aria-pressed={mode === item.value}
                  >
                    <Icon size={15} />
                    <strong>{item.label}</strong>
                    <small>{item.hint}</small>
                  </button>
                );
              })}
            </div>
          </div>

          <div className="update-actions">
            <button
              type="button"
              className="button primary block btn-primary btn-block"
              onClick={() => { ingestMutation.reset(); if (request) extractMutation.mutate(request); }}
              disabled={!request || extractMutation.isPending}
            >
              {extractMutation.isPending ? <><Spinner size={15} /> 正在抽取 · {elapsed}s</> : <><Sparkles size={15} /> 执行知识抽取</>}
            </button>
            <span>抽取结果需要确认后才会写入图谱。</span>
          </div>

          <div className="reset-row">
            <div><strong>重置图谱</strong><span>清除本次运行期新增内容，恢复初始图谱。</span></div>
            <button type="button" className="icon-text-button" onClick={() => setConfirmReset(true)}>
              <RotateCcw size={13} /> 重置
            </button>
          </div>
        </section>

        <section className="panel update-result">
          <div className="panel-head">
            <div>
              <span className="panel-kicker">抽取结果</span>
              <h2>实体、关系与校验</h2>
            </div>
            {result ? <ModeBadge mode={result.mode} /> : <span className="count-note">等待抽取</span>}
          </div>

          <div className="result-body">
            {extractMutation.isPending ? (
              <div className="extract-progress">
                <Spinner size={24} />
                <h3>正在解析这篇资料</h3>
                <p>文本较长或网络较慢时需要更久。</p>
                <div className="progress-flow">
                  {['解析文档', '识别实体', '校验证据'].map((label, index) => (
                    <span key={label}><i>{index + 1}</i>{label}</span>
                  ))}
                </div>
                <b>已等待 {elapsed}s</b>
              </div>
            ) : extractMutation.isError ? (
              <ErrorState title="知识抽取失败" error={extractMutation.error} onRetry={() => request && extractMutation.mutate(request)} />
            ) : !result ? (
              <div className="result-empty">
                <GitBranch size={24} />
                <h3>抽取结果会在这里展开</h3>
                <p>实体、关系、校验警告与入图预览都会保留，技术 JSON 默认折叠。</p>
                <div><span>实体对齐</span><span>Schema 校验</span><span>增量预览</span></div>
              </div>
            ) : (
              <div className="result-content">
                <div className="result-top">
                  <div><span className="mono">{result.model}</span><small>{formatNumber(result.elapsed_ms)} ms</small></div>
                  <p className={result.mode}>{result.mode === 'live' ? '本次结果由模型实时生成。' : '本次使用已保存的抽取结果，未调用模型。'}</p>
                </div>

                <div className="doc-row">
                  <FileText size={16} />
                  <div><strong>{result.document.title || '未命名文档'}</strong><span>{result.document.publisher} {result.document.published_at ? `· ${formatDate(result.document.published_at)}` : ''}</span></div>
                  {result.document.url ? <a href={result.document.url} target="_blank" rel="noreferrer noopener"><ExternalLink size={14} /></a> : null}
                </div>

                <div className={`validation ${result.validation.valid ? 'ok' : 'bad'}`}>
                  {result.validation.valid ? <CheckCircle2 size={16} /> : <AlertTriangle size={16} />}
                  <div>
                    <strong>{result.validation.valid ? '关系与原文证据校验通过' : '校验未通过，暂不可入图'}</strong>
                    {result.validation.warnings.length === 0 ? <span>没有额外警告。</span> : (
                      <ul>{result.validation.warnings.map((warning) => <li key={warning}>{warning}</li>)}</ul>
                    )}
                  </div>
                </div>

                <div className="result-metrics">
                  <div><span>实体</span><b>{result.entities.length}</b></div>
                  <div><span>关系</span><b>{result.relations.length}</b></div>
                  <div><span>事件</span><b>{result.events.length}</b></div>
                  <div><span>预计新增</span><b>{result.preview.new_nodes ?? 0} 节点 / {result.preview.new_edges ?? 0} 关系</b></div>
                </div>

                <section className="result-section">
                  <h3>实体预览 <span>{result.entities.length}</span></h3>
                  <div className="entity-groups">
                    {entityGroups.map(([type, entities]) => (
                      <div key={type}>
                        <TypeBadge type={type} small />
                        <span className="chips">
                          {entities.map((entity) => <em key={entity.id} style={{ borderColor: `${nodeColor(entity.type)}55` }}>{entity.label}</em>)}
                        </span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="result-section">
                  <h3>关系预览 <span>{result.relations.length}</span></h3>
                  <div className="relation-list">
                    {result.relations.map((relation) => (
                      <div key={relation.id}>
                        <span>{nodeLabels.get(relation.source) ?? relation.source}</span>
                        <em>{relationLabel(relation.type, relation.label)}</em>
                        <ArrowRight size={12} />
                        <span>{nodeLabels.get(relation.target) ?? relation.target}</span>
                      </div>
                    ))}
                  </div>
                </section>

                <section className="result-section">
                  <h3>新增内容 <span>入图前预览</span></h3>
                  <div className="align-grid">
                    <div><span>新增节点</span><b>{result.preview.new_nodes ?? 0}</b></div>
                    <div><span>新增关系</span><b>{result.preview.new_edges ?? 0}</b></div>
                    <div className="align-matches">
                      <span>已对齐</span>
                      <p>{(result.preview.matched_entities ?? []).length === 0 ? '无已有实体匹配' : (result.preview.matched_entities ?? []).map((match) => `${match.input} → ${match.label}`).join(' · ')}</p>
                    </div>
                  </div>
                </section>

                <details className="raw-json">
                  <summary><ChevronDown size={14} /> 原始抽取 JSON <span>{formatNumber(rawText.length)} 字符</span></summary>
                  <div className="raw-actions">
                    <button type="button" className="icon-text-button" onClick={async () => { await navigator.clipboard.writeText(rawText); notify('原始 JSON 已复制。', 'success'); }}>
                      <Clipboard size={13} /> 复制
                    </button>
                  </div>
                  <pre>{rawText}</pre>
                </details>

                <div className="ingest-block">
                  {ingestResult ? (
                    <>
                      <div className="ingest-success ingested-panel">
                        <CheckCircle2 size={18} />
                        <div>
                          <strong>{ingestResult.added_nodes + ingestResult.added_edges > 0 ? '已写入图谱' : '没有新增内容'}</strong>
                          <span>新增 {ingestResult.added_nodes} 节点 / {ingestResult.added_edges} 关系；更新 {ingestResult.updated_nodes} 节点 / {ingestResult.updated_edges} 关系。</span>
                        </div>
                      </div>
                      <div className="ingest-actions">
                        <button type="button" className="button primary" onClick={() => onNavigateResearch(preferredGroup, focusSymbol)}>
                          查看更新后的图谱 <ArrowRight size={14} />
                        </button>
                        <button type="button" className="button ghost" onClick={() => ingestMutation.mutate(result.extraction_id)} disabled={ingestMutation.isPending}>
                          {ingestMutation.isPending ? <Spinner size={13} /> : null} 再次导入
                        </button>
                      </div>
                    </>
                  ) : (
                    <>
                      <div><Database size={16} /><span>确认后将 {result.preview.new_nodes ?? 0} 个节点与 {result.preview.new_edges ?? 0} 条关系写入当前图谱。</span></div>
                      <button type="button" className="button primary" onClick={() => ingestMutation.mutate(result.extraction_id)} disabled={!result.validation.valid || ingestMutation.isPending}>
                        {ingestMutation.isPending ? <Spinner size={14} /> : <Plus size={14} />} 确认入图
                      </button>
                    </>
                  )}
                </div>
                {ingestMutation.isError ? <ErrorState title="入图失败" error={ingestMutation.error} onRetry={() => ingestMutation.mutate(result.extraction_id)} compact /> : null}
              </div>
            )}
          </div>
        </section>
      </div>

      <div className="update-footnote">
        <span><Link2 size={13} /> 当前图谱：{formatNumber(overview?.stats.entities)} 实体 · {formatNumber(overview?.stats.relations)} 关系 · {formatNumber(overview?.stats.documents)} 来源</span>
      </div>

      <ConfirmDialog
        open={confirmReset}
        title="重置图谱？"
        description="将清除本次运行期新增内容并恢复初始图谱；原始数据文件不会被修改。"
        confirmLabel="确认重置"
        danger
        busy={resetMutation.isPending}
        onConfirm={() => resetMutation.mutate()}
        onCancel={() => setConfirmReset(false)}
      />
    </div>
  );
}
