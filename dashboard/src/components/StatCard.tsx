import type { ReactNode } from 'react';

export function StatCard({
  label,
  value,
  hint,
  tone,
}: {
  label: string;
  value: ReactNode;
  hint?: ReactNode;
  tone?: 'ok' | 'warn' | 'error' | 'info' | 'neutral';
}) {
  return (
    <div className="card stat-card">
      <div className="stat-card__label">{label}</div>
      <div
        className="stat-card__value"
        style={tone ? { color: `var(--tone-${tone}-fg)` } : undefined}
      >
        {value}
      </div>
      {hint !== undefined && <div className="stat-card__hint">{hint}</div>}
    </div>
  );
}
