import { BookOpen, FolderSearch, GitBranch, Radar } from 'lucide-react';
import type { EventItem, Health, Overview, ViewKey } from '../types';
import { LogoMark } from './Logo';
import { StatusDot } from './Ui';
const NAV = [
  { key: 'research' as const, label: '事件研究', icon: Radar },
  { key: 'cases' as const, label: '事件目录', icon: FolderSearch },
  { key: 'update' as const, label: '资料导入', icon: GitBranch },
  { key: 'sources' as const, label: '资料与方法', icon: BookOpen },
];
export function Sidebar({ view, onNavigate, events, overview, health }: {
  view: ViewKey; onNavigate: (view: ViewKey) => void; events: EventItem[];
  eventId: string | null; overview?: Overview; health?: Health;
}) {
  return (
    <aside className="sidebar">
      <div className="brand"><LogoMark size={32} /><div><strong>FinGraphAgent</strong><span>股票事件研究</span></div></div>
      <nav className="side-nav" aria-label="主导航">
        {NAV.map((item) => { const Icon = item.icon; return <button key={item.key} type="button"
          className={view === item.key ? 'active' : ''} onClick={() => onNavigate(item.key)}>
          <Icon size={18} /><span>{item.label}</span></button>; })}
      </nav>
      <div className="side-dataset"><span>当前数据</span><p>4 个模型主题<br />{events.length} 个产业事件<br />{overview?.stats.stocks ?? '—'} 只 A 股、港股</p></div>
      <div className="side-spacer" />
      <div className="side-system"><div><StatusDot online={health?.status === 'ok'} /> {health?.status === 'ok' ? '本地数据已连接' : '服务未连接'}</div><span>知识图谱课程项目</span></div>
    </aside>
  );
}
