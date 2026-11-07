import type { ReactNode } from 'react';
import {
  AlertTriangle,
  Inbox,
  Loader2,
  Radio,
  RotateCcw,
  History,
} from 'lucide-react';
import { errorMessage } from '../api';
import type { RelationGroup } from '../types';
import {
  groupColor,
  groupLabel,
  nodeColor,
  typeLabel,
} from '../lib/palette';

export function alpha(hex: string, opacity: number): string {
  const normalized = hex.replace('#', '');
  if (normalized.length !== 6) return hex;
  const r = parseInt(normalized.slice(0, 2), 16);
  const g = parseInt(normalized.slice(2, 4), 16);
  const b = parseInt(normalized.slice(4, 6), 16);
  return `rgba(${r}, ${g}, ${b}, ${opacity})`;
}

export function Spinner({ size = 16, className = '' }: { size?: number; className?: string }) {
  return <Loader2 size={size} className={`spin ${className}`} aria-hidden="true" />;
}

export function Skeleton({
  height = 16,
  width = '100%',
  className = '',
}: {
  height?: number | string;
  width?: number | string;
  className?: string;
}) {
  return (
    <span
      className={`skeleton ${className}`}
      style={{ height, width }}
      aria-hidden="true"
    />
  );
}

export function TypeBadge({ type, small = false }: { type: string; small?: boolean }) {
  const color = nodeColor(type);
  return (
    <span
      className={`type-badge ${small ? 'small' : ''}`}
      style={{ color, background: alpha(color, 0.12), borderColor: alpha(color, 0.28) }}
    >
      <span className="type-dot" style={{ background: color }} />
      {typeLabel(type)}
    </span>
  );
}

export function GroupBadge({ group }: { group?: string }) {
  const color = groupColor(group);
  return (
    <span
      className="group-badge"
      style={{ color, background: alpha(color, 0.1), borderColor: alpha(color, 0.24) }}
    >
      {groupLabel(group)}
    </span>
  );
}

export function ModeBadge({ mode }: { mode: 'live' | 'replay' }) {
  if (mode === 'live') {
    return (
      <span className="mode-badge live">
        <Radio size={13} />
        实时抽取
      </span>
    );
  }
  return (
    <span className="mode-badge replay">
      <History size={13} />
      样例回放
    </span>
  );
}

export function IconButton({
  label,
  children,
  onClick,
  active = false,
  disabled = false,
}: {
  label: string;
  children: ReactNode;
  onClick: () => void;
  active?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className={`icon-btn ${active ? 'active' : ''}`}
      aria-label={label}
      title={label}
      onClick={onClick}
      disabled={disabled}
    >
      {children}
    </button>
  );
}

export function EmptyState({
  title,
  description,
  action,
  icon,
  compact = false,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
  icon?: ReactNode;
  compact?: boolean;
}) {
  return (
    <div className={`empty-state ${compact ? 'compact' : ''}`}>
      <div className="empty-icon">{icon ?? <Inbox size={22} />}</div>
      <strong>{title}</strong>
      {description ? <p>{description}</p> : null}
      {action ? <div className="empty-action">{action}</div> : null}
    </div>
  );
}

export function ErrorState({
  title = '数据加载失败',
  error,
  onRetry,
  compact = false,
}: {
  title?: string;
  error: unknown;
  onRetry?: () => void;
  compact?: boolean;
}) {
  return (
    <div className={`error-state ${compact ? 'compact' : ''}`} role="alert">
      <div className="error-icon">
        <AlertTriangle size={20} />
      </div>
      <div className="error-body">
        <strong>{title}</strong>
        <p>{errorMessage(error)}</p>
      </div>
      {onRetry ? (
        <button type="button" className="btn btn-ghost btn-sm" onClick={onRetry}>
          <RotateCcw size={14} />
          重试
        </button>
      ) : null}
    </div>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  aside,
}: {
  eyebrow?: string;
  title: string;
  aside?: ReactNode;
}) {
  return (
    <div className="section-heading">
      <div>
        {eyebrow ? <span className="eyebrow">{eyebrow}</span> : null}
        <h2>{title}</h2>
      </div>
      {aside ? <div className="section-aside">{aside}</div> : null}
    </div>
  );
}

export function StatusDot({ online, pulse = false }: { online: boolean; pulse?: boolean }) {
  return (
    <span
      className={`status-dot ${online ? 'online' : 'offline'} ${pulse ? 'pulse' : ''}`}
      aria-hidden="true"
    />
  );
}

export function RelationChip({
  label,
  group,
}: {
  label: string;
  group?: RelationGroup | string;
}) {
  const color = groupColor(group);
  return (
    <span
      className="relation-chip"
      style={{ color, borderColor: alpha(color, 0.3), background: alpha(color, 0.08) }}
    >
      {label}
    </span>
  );
}
