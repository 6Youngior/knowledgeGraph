import { BookOpen, FolderSearch, GitBranch, Radar } from 'lucide-react';
import type { EventItem, Health, Overview, ViewKey } from '../types';
import { formatDate } from '../lib/format';
import { LogoMark } from './Logo';
import { StatusDot } from './Ui';

const NAV = [
  { key: 'research' as const, label: '事件研究', icon: Radar },
  { key: 'cases' as const, label: '案例库', icon: FolderSearch },
  { key: 'update' as const, label: '知识更新', icon: GitBranch },
  { key: 'sources' as const, label: '资料与方法', icon: BookOpen },
];

export function Sidebar({
  view,
  onNavigate,
  events,
  eventId,
  overview,
  health,
}: {
  view: ViewKey;
  onNavigate: (view: ViewKey) => void;
  events: EventItem[];
  eventId: string | null;
  overview?: Overview;
  health?: Health;
}) {
  const current = events.find((event) => event.id === eventId) ?? events[0];
  return (
    <aside className="sidebar">
      <div className="brand">
        <LogoMark size={38} />
        <div>
          <strong>FinGraph</strong>
          <span>AI 产业事件研究</span>
        </div>
      </div>

      <nav className="side-nav" aria-label="主导航">
        {NAV.map((item) => {
          const Icon = item.icon;
          return (
            <button
              key={item.key}
              type="button"
              className={view === item.key ? 'active' : ''}
              onClick={() => onNavigate(item.key)}
            >
              <Icon size={18} />
              <span>{item.label}</span>
            </button>
          );
        })}
      </nav>

      {current ? (
        <div className="side-current">
          <span>当前事件</span>
          <strong>{current.title}</strong>
          <small>{formatDate(current.event_at || current.date)} · {events.length} 个事件</small>
        </div>
      ) : null}

      <div className="side-spacer" />
      <div className="side-system">
        <div><StatusDot online={health?.status === 'ok'} pulse /> {health?.status === 'ok' ? '数据服务正常' : '服务未连接'}</div>
        <span>数据截至 {formatDate(overview?.as_of)}</span>
        <span>FinGraph · 课程项目</span>
      </div>
      <div className="side-note">图谱与本地行情</div>
    </aside>
  );
}
