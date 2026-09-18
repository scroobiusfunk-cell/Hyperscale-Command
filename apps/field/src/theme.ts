/**
 * How the app looks.
 *
 * Built for a phone held in one gloved hand in a badly lit plant room, which
 * sets most of the decisions here: large type, tall touch targets, and status
 * that never depends on colour alone — every state carries a word as well.
 *
 * The palette is the same validated one the reviewer console uses, so a failure
 * a tech sees and the same failure on a reviewer's screen are the same colour.
 */

export const colour = {
  plane: '#f9f9f7',
  surface: '#ffffff',
  sunken: '#f2f2ee',
  ink: '#0b0b0b',
  inkSecondary: '#3d3d3a',
  inkMuted: '#6b6b66',
  hairline: '#e3e3dd',
  accent: '#1668d9',
  accentInk: '#ffffff',
  good: '#0ca30c',
  goodSoft: '#e8f6e8',
  warning: '#fab219',
  warningSoft: '#fdf3dd',
  critical: '#d03b3b',
  criticalSoft: '#fbe9e9',
  criticalInk: '#a52121',
} as const;

export const space = {
  xs: 4,
  sm: 8,
  md: 12,
  lg: 16,
  xl: 24,
  xxl: 32,
} as const;

export const radius = { sm: 8, md: 12, lg: 16 } as const;

/** Minimum height for anything tappable. A gloved thumb is not precise. */
export const TAP_TARGET = 56;

export const type = {
  hero: { fontSize: 30, fontWeight: '700' },
  title: { fontSize: 22, fontWeight: '700' },
  statement: { fontSize: 20, fontWeight: '600', lineHeight: 27 },
  body: { fontSize: 16, lineHeight: 23 },
  label: { fontSize: 13, fontWeight: '600' },
  small: { fontSize: 13 },
} as const;
