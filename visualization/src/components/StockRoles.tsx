import { Building2, ChevronRight, GitBranch, ShieldAlert } from 'lucide-react';
import type { RelatedStock, ResearchExcluded } from '../types';
import { formatNumber, splitSymbol } from '../lib/format';
import { groupColor, groupLabel } from '../lib/palette';

const GROUP_ORDER = ['direct', 'adaptation', 'distribution'] as const;

const GROUP_META: Record<string, { label: string; hint: string }> = {
  direct: {
    label: '研发主体与上市证券',
    hint: '模型由谁研发，对应哪只证券',
  },
  adaptation: {
    label: '硬件适配路径',
    hint: '产品完成适配，映射到上市公司',
  },
  distribution: {
    label: '云服务接入路径',
    hint: '云平台托管模型，映射到平台公司',
  },
};

const REASON_LABEL: Record<string, string> = {
  industry_only: '仅有行业分类',
  not_yet_disclosed: '缺少当时资料',
  no_evidence: '缺少原文来源',
};

export function StockRoles({
  stocks,
  selectedSymbol,
  selectedGroup,
  onSelect,
  excluded,
}: {
  stocks: RelatedStock[];
  selectedSymbol: string | null;
  selectedGroup: string;
  onSelect: (stock: RelatedStock, group: string) => void;
  excluded?: ResearchExcluded[];
}) {
  return (
    <section className="panel stock-roles stocks-panel">
      <div className="panel-head">
        <div>
          <span className="panel-kicker">关联证券</span>
          <h2>关联公司</h2>
        </div>
        <span className="count-note">{formatNumber(stocks.length)} 只证券 · {formatNumber(stocks.reduce((sum, stock) => sum + (stock.path_count ?? 1), 0))} 条路径</span>
      </div>

      {stocks.length === 0 ? (
        <div className="empty-inline">
          <Building2 size={20} />
          <div>
            <strong>当前日期没有关联证券</strong>
            <span>切换日期，或查看其他候选。</span>
          </div>
        </div>
      ) : (
        <div className="stock-groups">
          {GROUP_ORDER.map((group) => {
            const items = stocks.filter(
              (stock) =>
                stock.relation_groups?.includes(group) ||
                (stock.relation_group || 'direct') === group,
            );
            if (items.length === 0) return null;
            const meta = GROUP_META[group];
            return (
              <div className="stock-group" key={group}>
                <div className="stock-group-head">
                  <span className="role-dot" style={{ background: groupColor(group) }} />
                  <strong>{meta.label}</strong>
                  <small>{meta.hint}</small>
                  <b>{items.length}</b>
                </div>
                <div className="stock-rows">
                  {items.map((stock) => {
                    const { code, market } = splitSymbol(stock.symbol);
                    const selected = stock.symbol === selectedSymbol && selectedGroup === group;
                    return (
                      <button
                        type="button"
                        key={`${stock.id || stock.symbol}-${group}`}
                        className={`stock-row ${selected ? 'selected' : ''}`}
                        onClick={() => onSelect(stock, group)}
                      >
                        <span className="stock-code">
                          <b>{code}</b>
                          <small>{market || stock.market}</small>
                        </span>
                        <span className="stock-copy">
                          <strong>
                            {stock.company_name || stock.label}
                            {stock.listed_at_event === false ? (
                              <em className="listing-badge" title={stock.market_note || ''}>事件时未上市</em>
                            ) : null}
                          </strong>
                          <small>
                            <GitBranch size={11} />
                            {stock.path.edges.length} 跳 · {stock.path.nodes.map((item) => item.label).join(' → ')}
                          </small>
                        </span>
                        <span className="stock-path-count">
                          {stock.source_ids.length} 条来源
                        </span>
                        <ChevronRight size={15} />
                      </button>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {excluded && excluded.length > 0 ? (
        <div className="excluded-box">
          <div className="excluded-head">
            <ShieldAlert size={14} />
            <strong>其他候选 · {excluded.length}</strong>
            <span>未形成证券关联</span>
          </div>
          <div className="excluded-list">
            {excluded.slice(0, 6).map((item) => (
              <div className="excluded-item" key={item.id}>
                <span>{item.label}</span>
                {item.symbol ? <em>{item.symbol}</em> : null}
                <small>{REASON_LABEL[item.reason_code] ?? item.reason}</small>
              </div>
            ))}
          </div>
        </div>
      ) : (
        <div className="excluded-note">
          <ShieldAlert size={13} />
          行业分类不会单独形成关联；晚于所选日期的记录不显示。
        </div>
      )}
    </section>
  );
}
