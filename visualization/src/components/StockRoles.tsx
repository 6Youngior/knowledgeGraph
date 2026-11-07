import { ChevronRight } from 'lucide-react';
import type { RelatedStock, ResearchExcluded } from '../types';
const ROLE_LABEL: Record<string, string> = { direct: '模型研发', adaptation: '硬件适配', distribution: '云服务接入' };
export function StockRoles({ stocks, selectedSymbol, selectedGroup, onSelect }: {
  stocks: RelatedStock[]; selectedSymbol: string | null; selectedGroup: string;
  onSelect: (stock: RelatedStock, group: string) => void; excluded?: ResearchExcluded[];
}) {
  return (
    <section className="stock-roles stocks-panel" aria-label="关联证券">
      <div className="stock-list-heading"><h2>关联证券</h2><span>{stocks.length}</span></div>
      {!stocks.length ? <p className="stock-empty">当前日期下还没有完整的证券路径。</p> : (
        <div className="stock-rows">
          {stocks.flatMap((stock) => (stock.relation_groups?.length ? stock.relation_groups : [stock.relation_group || 'direct']).map((group) => (
            <button type="button" key={stock.symbol + group}
              className={'stock-row ' + (stock.symbol === selectedSymbol && group === selectedGroup ? 'selected' : '')}
              data-symbol={stock.symbol} data-group={group} onClick={() => onSelect(stock, group)}>
              <span className="stock-copy"><strong>{stock.company_name || stock.label}</strong><small>{stock.symbol}</small></span>
              <span className={'stock-role ' + group}>{ROLE_LABEL[group] ?? group}</span>
              <ChevronRight size={15} />
            </button>
          )))}
        </div>
      )}
    </section>
  );
}
