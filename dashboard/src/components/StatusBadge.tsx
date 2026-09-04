import type { StatusTone } from '../lib/format';

export function StatusBadge({
  tone,
  label,
}: {
  tone: StatusTone;
  label: string;
}) {
  return (
    <span className={`badge badge--${tone}`}>
      <span className={`dot dot--${tone}`} aria-hidden="true" />
      {label}
    </span>
  );
}
