/**
 * The small pieces every screen is built from.
 */

import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { TAP_TARGET, colour, radius, space, type } from './theme.ts';

export type Tone = 'neutral' | 'good' | 'warning' | 'critical';

const toneStyles: Record<Tone, { bg: string; fg: string }> = {
  neutral: { bg: colour.sunken, fg: colour.inkSecondary },
  good: { bg: colour.goodSoft, fg: '#0a7a0a' },
  warning: { bg: colour.warningSoft, fg: '#8a6000' },
  critical: { bg: colour.criticalSoft, fg: colour.criticalInk },
};

/** Icon plus word, always. Colour never carries the meaning by itself. */
export function Chip({ tone, icon, children }: { tone: Tone; icon: string; children: string }) {
  const t = toneStyles[tone];
  return (
    <View style={[styles.chip, { backgroundColor: t.bg }]}>
      <Text style={[styles.chipText, { color: t.fg }]}>
        {icon} {children}
      </Text>
    </View>
  );
}

export function Button({
  title,
  onPress,
  kind = 'primary',
  disabled = false,
  busy = false,
}: {
  title: string;
  onPress: () => void;
  kind?: 'primary' | 'secondary' | 'danger';
  disabled?: boolean;
  busy?: boolean;
}) {
  const off = disabled || busy;
  const background =
    kind === 'primary' ? colour.accent : kind === 'danger' ? colour.criticalSoft : colour.surface;
  const foreground =
    kind === 'primary' ? colour.accentInk : kind === 'danger' ? colour.criticalInk : colour.ink;
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ disabled: off, busy }}
      disabled={off}
      onPress={onPress}
      style={({ pressed }) => [
        styles.button,
        { backgroundColor: background, opacity: off ? 0.45 : pressed ? 0.82 : 1 },
        kind !== 'primary' && styles.buttonBordered,
      ]}
    >
      {busy ? (
        <ActivityIndicator color={foreground} />
      ) : (
        <Text style={[styles.buttonText, { color: foreground }]}>{title}</Text>
      )}
    </Pressable>
  );
}

export function Card({ children, style }: { children: ReactNode; style?: object }) {
  return <View style={[styles.card, style]}>{children}</View>;
}

export function Banner({ tone, children }: { tone: Tone; children: ReactNode }) {
  const t = toneStyles[tone];
  return (
    <View style={[styles.banner, { backgroundColor: t.bg, borderColor: t.fg }]}>
      <Text style={[styles.bannerText, { color: t.fg }]}>{children}</Text>
    </View>
  );
}

export function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <View style={{ marginBottom: space.lg }}>
      <Text style={styles.fieldLabel}>{label}</Text>
      {children}
    </View>
  );
}

/** How far through the walk the tech is. A bar plus the numbers beside it. */
export function Progress({ done, total }: { done: number; total: number }) {
  const share = total === 0 ? 0 : done / total;
  return (
    <View>
      <View style={styles.progressTrack}>
        <View style={[styles.progressFill, { width: `${Math.round(share * 100)}%` }]} />
      </View>
      <Text style={styles.progressLabel}>
        {done} of {total} done
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  chip: { paddingHorizontal: 10, paddingVertical: 4, borderRadius: 999, alignSelf: 'flex-start' },
  chipText: { fontSize: 13, fontWeight: '700' },
  button: {
    minHeight: TAP_TARGET,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: space.lg,
  },
  buttonBordered: { borderWidth: 1, borderColor: colour.hairline },
  buttonText: { fontSize: 17, fontWeight: '700' },
  card: {
    backgroundColor: colour.surface,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: colour.hairline,
    padding: space.lg,
  },
  banner: {
    borderRadius: radius.md,
    borderWidth: 1,
    padding: space.md,
    marginBottom: space.lg,
  },
  bannerText: { fontSize: 15, lineHeight: 21, fontWeight: '500' },
  fieldLabel: {
    ...type.label,
    color: colour.inkMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: space.sm,
  },
  progressTrack: {
    height: 8,
    borderRadius: 999,
    backgroundColor: colour.sunken,
    overflow: 'hidden',
  },
  progressFill: { height: 8, borderRadius: 999, backgroundColor: colour.accent },
  progressLabel: { ...type.small, color: colour.inkMuted, marginTop: space.xs },
});
