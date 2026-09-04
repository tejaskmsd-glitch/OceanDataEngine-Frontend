import type { WsStatus } from '../hooks/useAlertStream';
import type { StatusTone } from '../lib/format';

const LABELS: Record<WsStatus, { text: string; tone: StatusTone }> = {
  connecting: { text: 'Connecting…', tone: 'info' },
  open: { text: 'Live', tone: 'ok' },
  reconnecting: { text: 'Reconnecting…', tone: 'warn' },
  closed: { text: 'Disconnected', tone: 'neutral' },
  disabled: { text: 'Polling', tone: 'neutral' },
};

/**
 * Shows the realtime connection state. When the stream is not open, the
 * dashboard falls back to REST polling — communicated here so operators
 * understand data latency.
 */
export function ConnectionIndicator({ status }: { status: WsStatus }) {
  const info = LABELS[status] ?? LABELS.disabled;
  const pollingNote =
    status === 'open' ? 'realtime stream connected' : 'using fallback polling';
  return (
    <span className="conn" title={pollingNote} aria-live="polite">
      <span className={`dot dot--${info.tone}`} aria-hidden="true" />
      {info.text}
    </span>
  );
}
