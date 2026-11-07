import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { ArrowUpRight, CornerDownLeft, Loader2, Search, X } from 'lucide-react';
import { api } from '../api';
import { useDebounced } from '../hooks/useDebounced';
import { nodeColor, typeLabel } from '../lib/palette';
import type { GraphNode, Health, Overview, ViewKey } from '../types';
import { formatDate } from '../lib/format';

const VIEW_LABEL: Record<ViewKey, string> = {
  research: '事件研究',
  cases: '案例库',
  update: '知识更新',
  sources: '资料与方法',
};

export function Topbar({
  view,
  health,
  overview,
  onSearchSelect,
  onRefresh,
  refreshing,
}: {
  view: ViewKey;
  health?: Health;
  overview?: Overview;
  onSearchSelect: (node: GraphNode) => void;
  onRefresh: () => void;
  refreshing: boolean;
}) {
  const [query, setQuery] = useState('');
  const [open, setOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const wrapRef = useRef<HTMLDivElement>(null);
  const debounced = useDebounced(query, 300);

  const searchQuery = useQuery({
    queryKey: ['global-search', debounced],
    queryFn: () => api.graph({ q: debounced.trim() }),
    enabled: open && debounced.trim().length >= 2,
    staleTime: 15000,
    retry: 1,
  });

  const results = searchQuery.data?.nodes ?? [];
  const online = health?.status === 'ok';

  useEffect(() => {
    const onPointerDown = (event: MouseEvent) => {
      if (!wrapRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKeyDown = (event: KeyboardEvent) => {
      if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
        event.preventDefault();
        inputRef.current?.focus();
        setOpen(true);
      }
    };
    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, []);

  useEffect(() => setActiveIndex(0), [debounced]);

  const select = (node: GraphNode) => {
    onSearchSelect(node);
    setQuery('');
    setOpen(false);
    inputRef.current?.blur();
  };

  const handleKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    if (event.key === 'Escape') {
      setOpen(false);
      inputRef.current?.blur();
      return;
    }
    if (!open || results.length === 0) return;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      setActiveIndex((index) => (index + 1) % results.length);
    } else if (event.key === 'ArrowUp') {
      event.preventDefault();
      setActiveIndex((index) => (index - 1 + results.length) % results.length);
    } else if (event.key === 'Enter') {
      event.preventDefault();
      const node = results[Math.min(activeIndex, results.length - 1)];
      if (node) select(node);
    }
  };

  return (
    <header className="topbar">
      <div className="topbar-left">
        <div className="breadcrumb"><span>FinGraph</span><i>/</i><strong>{VIEW_LABEL[view]}</strong></div>
        <span className="topbar-date">数据截至 {formatDate(overview?.as_of)}</span>
      </div>

      <div className="topbar-right">
        <div className="global-search" ref={wrapRef}>
          <Search size={16} />
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => { setQuery(event.target.value); setOpen(true); }}
            onFocus={() => setOpen(true)}
            onKeyDown={handleKeyDown}
            placeholder="搜索公司、模型、产品…"
            aria-label="搜索图谱实体"
            spellCheck={false}
          />
          {query ? (
            <button type="button" className="search-clear" onClick={() => { setQuery(''); inputRef.current?.focus(); }} aria-label="清空搜索">
              <X size={13} />
            </button>
          ) : <kbd>Ctrl K</kbd>}

          {open && query.trim() ? (
            <div className="search-popover">
              <div className="search-popover-head">
                <span>实体检索</span>
                {searchQuery.data ? <span>{searchQuery.data.nodes.length} 个匹配</span> : null}
              </div>
              {debounced.trim().length < 2 ? (
                <div className="search-hint">输入至少 2 个字符</div>
              ) : searchQuery.isLoading ? (
                <div className="search-hint"><Loader2 size={14} className="spin" /> 正在检索图谱…</div>
              ) : searchQuery.isError ? (
                <div className="search-hint error">检索暂不可用</div>
              ) : results.length === 0 ? (
                <div className="search-hint">没有匹配“{debounced.trim()}”的实体</div>
              ) : (
                <div className="search-results">
                  {results.slice(0, 8).map((node, index) => (
                    <button
                      type="button"
                      key={node.id}
                      className={index === activeIndex ? 'active' : ''}
                      onMouseEnter={() => setActiveIndex(index)}
                      onClick={() => select(node)}
                    >
                      <i style={{ background: nodeColor(node.type) }} />
                      <span><strong>{node.label}</strong><small>{typeLabel(node.type)}{node.description ? ` · ${node.description}` : ''}</small></span>
                      <ArrowUpRight size={14} />
                    </button>
                  ))}
                </div>
              )}
              <div className="search-popover-foot"><span><CornerDownLeft size={12} /> 打开首个结果</span><span>Esc 关闭</span></div>
            </div>
          ) : null}
        </div>

        <span className={`service-state ${online ? 'online' : 'offline'}`}>
          <i /> {online ? '数据服务正常' : '服务未连接'}
        </span>
        <button type="button" className="refresh-button" onClick={onRefresh} disabled={refreshing} aria-label="刷新全部数据">
          <Loader2 size={15} className={refreshing ? 'spin' : ''} />
        </button>
      </div>
    </header>
  );
}
