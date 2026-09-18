import { Chip, type ChipTone } from './Chip';

/**
 * A stat tile: label, value, and a line saying what the number means.
 *
 * A number with no interpretation invites everyone to invent their own, so
 * every tile says what it is for underneath.
 */
export function Stat({
  label,
  value,
  hint,
  tone,
  toneLabel,
  hero = false,
}: {
  label: string;
  value: number | string;
  hint?: string;
  tone?: ChipTone;
  toneLabel?: string;
  hero?: boolean;
}) {
  return (
    <div className={`stat${hero ? ' is-hero' : ''}`}>
      <div className="row-between">
        <span className="stat-label">{label}</span>
        {tone && toneLabel ? <Chip tone={tone}>{toneLabel}</Chip> : null}
      </div>
      <span className="stat-value">{value}</span>
      {hint ? <span className="stat-hint">{hint}</span> : null}
    </div>
  );
}

/**
 * A single ratio against a limit. Same-ramp track, so state reads across the bar.
 *
 * `n` is how many observations are behind the ratio. Zero of them means there is
 * no rate to show, and printing 100% would be inventing one.
 */
export function Meter({ value, n, warnBelow = 0.8, failBelow = 0.5 }: {
  value: number;
  n?: number;
  warnBelow?: number;
  failBelow?: number;
}) {
  if (n === 0) {
    return <span className="muted" style={{ fontSize: '0.83rem' }}>no passes yet</span>;
  }
  const pct = Math.max(0, Math.min(1, value));
  const tone = pct < failBelow ? 'is-critical' : pct < warnBelow ? 'is-warning' : '';
  return (
    <div className="meter">
      <div
        className="meter-track"
        role="meter"
        aria-valuenow={Math.round(pct * 100)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <div className={`meter-fill ${tone}`} style={{ width: `${pct * 100}%` }} />
      </div>
      <span className="meter-value">{Math.round(pct * 100)}%</span>
    </div>
  );
}
