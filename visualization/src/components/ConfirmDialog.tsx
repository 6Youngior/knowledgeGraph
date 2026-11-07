import { useEffect } from 'react';
import { AlertTriangle, X } from 'lucide-react';
import { Spinner } from './Ui';

export function ConfirmDialog({
  open,
  title,
  description,
  confirmLabel = '确认',
  busy = false,
  danger = false,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  busy?: boolean;
  danger?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  useEffect(() => {
    if (!open) return;
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape' && !busy) onCancel();
    };
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [open, busy, onCancel]);

  if (!open) return null;

  return (
    <div
      className="dialog-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget && !busy) onCancel();
      }}
    >
      <div className="dialog" role="dialog" aria-modal="true" aria-labelledby="dialog-title">
        <div className="dialog-icon">
          <AlertTriangle size={20} />
        </div>
        <button
          type="button"
          className="dialog-close"
          aria-label="关闭"
          onClick={onCancel}
          disabled={busy}
        >
          <X size={16} />
        </button>
        <h3 id="dialog-title">{title}</h3>
        <p>{description}</p>
        <div className="dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`}
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? <Spinner size={14} /> : null}
            {confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
