/**
 * The walk: every stop, and what is left to do at each one.
 *
 * Grouped by asset rather than by requirement, because the tech walks the
 * building, not the specification. Deferred items are shown rather than hidden
 * — somebody has to know why a check did not happen, and "it quietly was not on
 * the list" is the answer that gets a project into trouble.
 */

import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { Banner, Button, Card, Chip, Progress } from '../components.tsx';
import type { ItemProgress } from '../core/walkStore.ts';
import { countWalk } from '../core/walkStore.ts';
import type { Walk, WalkItem } from '../core/types.ts';
import { colour, radius, space, type } from '../theme.ts';

export function WalkList({
  walk,
  progress,
  onOpenItem,
  onNext,
  onFinish,
  pendingEvents,
  pendingBlobs,
}: {
  walk: Walk;
  progress: Record<string, ItemProgress>;
  onOpenItem: (item: WalkItem, assetTag: string) => void;
  onNext: () => void;
  onFinish: () => void;
  pendingEvents: number;
  pendingBlobs: number;
}) {
  const counts = countWalk(walk, progress);
  const allDone = counts.done === counts.total && counts.total > 0;

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <Text style={styles.heading}>Your walk</Text>
      <View style={{ marginBottom: space.lg }}>
        <Progress done={counts.done} total={counts.total} />
      </View>

      {counts.safetyRemaining > 0 && (
        <Banner tone="critical">
          {counts.safetyRemaining} safety {counts.safetyRemaining === 1 ? 'item' : 'items'} still to
          do. These always go to a reviewer — nothing clears on its own.
        </Banner>
      )}

      {(pendingEvents > 0 || pendingBlobs > 0) && (
        <Banner tone="warning">
          Waiting to send: {pendingEvents} {pendingEvents === 1 ? 'action' : 'actions'} and{' '}
          {pendingBlobs} {pendingBlobs === 1 ? 'photo' : 'photos'}. They are saved on this phone and
          go up on their own when you have signal.
        </Banner>
      )}

      {!allDone && (
        <View style={{ marginBottom: space.lg }}>
          <Button title="Next item" onPress={onNext} />
        </View>
      )}

      {walk.stops.map((stop) => {
        const remaining = stop.items.filter(
          (i) => (progress[i.checklist_item_id] ?? 'open') === 'open',
        ).length;
        return (
          <View key={stop.asset_id} style={{ marginBottom: space.lg }}>
            <View style={styles.stopHead}>
              <Text style={styles.stopTag}>{stop.tag}</Text>
              <Text style={styles.stopMeta}>
                {stop.room ?? 'Location not recorded'}
                {remaining === 0 ? ' · done' : ` · ${remaining} left`}
              </Text>
            </View>
            <Card style={{ padding: 0 }}>
              {stop.items.map((item, index) => {
                const state = progress[item.checklist_item_id] ?? 'open';
                return (
                  <View
                    key={item.checklist_item_id}
                    style={[styles.row, index > 0 && styles.rowDivided]}
                  >
                    <View style={{ flex: 1, paddingRight: space.md }}>
                      <Text style={styles.statement}>{item.statement}</Text>
                      <View style={styles.rowChips}>
                        {item.criticality === 'safety' && (
                          <Chip tone="critical" icon="▲">
                            Safety
                          </Chip>
                        )}
                        {state === 'captured' && (
                          <Chip tone="good" icon="✓">
                            Captured
                          </Chip>
                        )}
                        {state === 'deferred' && (
                          <Chip tone="warning" icon="●">
                            Deferred
                          </Chip>
                        )}
                      </View>
                    </View>
                    <Button
                      kind="secondary"
                      title={state === 'open' ? 'Open' : 'Again'}
                      onPress={() => onOpenItem(item, stop.tag)}
                    />
                  </View>
                );
              })}
            </Card>
          </View>
        );
      })}

      {walk.deferred.length > 0 && (
        <View style={{ marginBottom: space.lg }}>
          <Text style={styles.sectionHeading}>Left off this walk</Text>
          <Card>
            {walk.deferred.map((d) => (
              <View key={d.checklist_item_id} style={{ marginBottom: space.sm }}>
                <Text style={styles.deferredTag}>{d.asset_tag}</Text>
                <Text style={styles.deferredNote}>{d.note}</Text>
              </View>
            ))}
          </Card>
        </View>
      )}

      <Button
        kind={allDone ? 'primary' : 'secondary'}
        title={allDone ? 'Finish the walk' : 'Finish early'}
        onPress={onFinish}
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.lg, paddingBottom: space.xxl, backgroundColor: colour.plane },
  heading: { ...type.hero, color: colour.ink, marginBottom: space.md },
  sectionHeading: {
    ...type.label,
    color: colour.inkMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: space.sm,
  },
  stopHead: { marginBottom: space.sm },
  stopTag: { ...type.title, color: colour.ink, fontVariant: ['tabular-nums'] },
  stopMeta: { ...type.small, color: colour.inkMuted },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: space.md,
  },
  rowDivided: { borderTopWidth: 1, borderTopColor: colour.hairline },
  rowChips: { flexDirection: 'row', gap: space.sm, marginTop: space.sm, flexWrap: 'wrap' },
  statement: { ...type.body, color: colour.ink, fontWeight: '500' },
  deferredTag: { ...type.body, fontWeight: '700', color: colour.ink },
  deferredNote: { ...type.small, color: colour.inkSecondary },
  radiusHint: { borderRadius: radius.sm },
});
