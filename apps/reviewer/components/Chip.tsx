/**
 * A status chip.
 *
 * Always an icon and a word. The palette's status colours are sub-3:1 on the
 * light surface by design, and the mitigation is that colour never carries the
 * meaning on its own.
 */
export type ChipTone = 'critical' | 'serious' | 'warning' | 'good' | 'accent' | 'neutral';

const ICON: Record<ChipTone, string> = {
  critical: '▲',
  serious: '▲',
  warning: '●',
  good: '✓',
  accent: '●',
  neutral: '●',
};

export function Chip({
  tone = 'neutral',
  children,
}: {
  tone?: ChipTone;
  children: React.ReactNode;
}) {
  return (
    <span className={`chip is-${tone}`}>
      <span aria-hidden="true" style={{ fontSize: '0.6rem', lineHeight: 1 }}>
        {ICON[tone]}
      </span>
      {children}
    </span>
  );
}
