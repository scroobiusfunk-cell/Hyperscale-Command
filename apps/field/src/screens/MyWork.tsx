/**
 * What the reviewer said.
 *
 * The teaching half of the app. Everything else here helps a tech capture
 * evidence; this is the only screen where they find out whether they got it
 * right, and why.
 *
 * It is ordered the way it is for a reason. Work to redo comes first because a
 * recapture request is a job — a tech who does not know an item was sent back
 * will not go back for it. Then the failures, because the note on a failure is
 * the lesson. Then the passes, because the note on a pass says what made it
 * right, and that is the part that carries to the next board.
 *
 * Every entry shows the requirement and the why-it-matters line beside the
 * ruling. A note reading "two positions still open" teaches nothing on its own;
 * next to the rule it came from, it does.
 *
 * The photographs are here for the same reason. "Too blurry to read the label"
 * is an instruction; the same words beside the blurry photograph are a lesson
 * the tech can act on next time without having to remember which shot it was.
 * The device deleted its local copy once the bytes were safely up, so these come
 * back from the server, which now checks that the evidence is this tech's own.
 */

import { useCallback, useEffect, useState } from 'react';
import { Image, RefreshControl, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Banner, Button, Card, Chip } from '../components.tsx';
import type { Tone } from '../components.tsx';
import type { Feedback, MyWork as MyWorkData } from '../core/types.ts';
import { colour, space, type } from '../theme.ts';

const VERDICT: Record<Feedback['verdict'], { tone: Tone; icon: string; word: string }> = {
  pass: { tone: 'good', icon: '✓', word: 'Passed' },
  fail: { tone: 'critical', icon: '▲', word: 'Failed' },
  recapture_requested: { tone: 'warning', icon: '●', word: 'Take it again' },
};

export function MyWork({
  load,
  imageFor,
  onBack,
}: {
  load: () => Promise<MyWorkData>;
  imageFor: (evidenceId: string) => { uri: string; headers: Record<string, string> };
  onBack: () => void;
}) {
  const [data, setData] = useState<MyWorkData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const refresh = useCallback(async () => {
    setBusy(true);
    setError(null);
    try {
      setData(await load());
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }, [load]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  const redo = data?.feedback.filter((f) => f.needs_another_visit) ?? [];

  return (
    <ScrollView
      contentContainerStyle={styles.page}
      refreshControl={<RefreshControl refreshing={busy} onRefresh={() => void refresh()} />}
    >
      <Text style={styles.heading}>What the reviewer said</Text>
      <Text style={styles.sub}>Rulings on work you captured. Pull down to check for new ones.</Text>

      {error !== null && <Banner tone="critical">{error}</Banner>}

      {data !== null && (
        <>
          <Card style={{ marginBottom: space.lg }}>
            <View style={styles.tallyRow}>
              <Count n={data.tally.passed} label="passed" />
              <Count n={data.tally.failed} label="failed" />
              <Count n={data.tally.recapture_requested} label="to redo" />
              <Count n={data.tally.awaiting_review} label="waiting" />
            </View>
            <Text style={styles.tallyNote}>
              A count of what happened, not a score. Nothing here changes what you are allowed
              to sign off.
            </Text>
          </Card>

          {redo.length > 0 && (
            <Banner tone="warning">
              {redo.length} {redo.length === 1 ? 'item needs' : 'items need'} another visit. They
              are back on your list.
            </Banner>
          )}

          {data.feedback.length === 0 && (
            <Card>
              <Text style={styles.emptyTitle}>Nothing ruled on yet</Text>
              <Text style={styles.emptyBody}>
                {data.tally.awaiting_review > 0
                  ? `${data.tally.awaiting_review} of your items are with a reviewer. Their notes turn up here.`
                  : 'Once a reviewer rules on something you captured, their note turns up here.'}
              </Text>
            </Card>
          )}

          {data.feedback.map((entry) => (
            <Entry key={entry.checklist_item_id} entry={entry} imageFor={imageFor} />
          ))}
        </>
      )}

      <View style={{ marginTop: space.xl }}>
        <Button kind="secondary" title="Back" onPress={onBack} />
      </View>
    </ScrollView>
  );
}

function Entry({
  entry,
  imageFor,
}: {
  entry: Feedback;
  imageFor: (evidenceId: string) => { uri: string; headers: Record<string, string> };
}) {
  const verdict = VERDICT[entry.verdict];
  return (
    <Card style={{ marginBottom: space.md }}>
      <View style={styles.entryHead}>
        <Text style={styles.entryTag}>{entry.asset_tag}</Text>
        <Chip tone={verdict.tone} icon={verdict.icon}>
          {verdict.word}
        </Chip>
      </View>

      <Text style={styles.entryStatement}>{entry.statement}</Text>

      {entry.evidence_ids.length > 0 && (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} style={styles.shots}>
          {entry.evidence_ids.map((id) => (
            <Image
              key={id}
              source={imageFor(id)}
              style={styles.shot}
              resizeMode="cover"
              accessibilityLabel="The photo you took"
            />
          ))}
        </ScrollView>
      )}

      {entry.note !== null && entry.note !== '' && (
        <View style={styles.note}>
          <Text style={styles.noteLabel}>{entry.reviewer_name.toUpperCase()} SAID</Text>
          <Text style={styles.noteText}>{entry.note}</Text>
        </View>
      )}

      <Text style={styles.why}>{entry.why_it_matters}</Text>

      <View style={styles.entryFoot}>
        {entry.criticality === 'safety' && (
          <Chip tone="critical" icon="▲">
            Safety
          </Chip>
        )}
        {entry.is_correction && (
          <Chip tone="neutral" icon="↺">
            Changed from an earlier ruling
          </Chip>
        )}
        {entry.needs_another_visit && (
          <Chip tone="warning" icon="●">
            Back on your list
          </Chip>
        )}
      </View>
    </Card>
  );
}

function Count({ n, label }: { n: number; label: string }) {
  return (
    <View style={styles.count}>
      <Text style={styles.countValue}>{n}</Text>
      <Text style={styles.countLabel}>{label}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.lg, paddingBottom: space.xxl, backgroundColor: colour.plane },
  heading: { ...type.hero, color: colour.ink, marginBottom: space.xs },
  sub: { ...type.body, color: colour.inkSecondary, marginBottom: space.lg },
  tallyRow: { flexDirection: 'row', justifyContent: 'space-between' },
  count: { alignItems: 'center', flex: 1 },
  countValue: { fontSize: 26, fontWeight: '700', color: colour.ink },
  countLabel: { ...type.small, color: colour.inkMuted },
  tallyNote: {
    ...type.small,
    color: colour.inkMuted,
    marginTop: space.md,
    paddingTop: space.md,
    borderTopWidth: 1,
    borderTopColor: colour.hairline,
  },
  entryHead: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: space.md,
    marginBottom: space.sm,
  },
  entryTag: { ...type.title, color: colour.ink },
  entryStatement: { ...type.body, fontWeight: '600', color: colour.ink, marginBottom: space.md },
  shots: { marginBottom: space.md },
  shot: {
    width: 104,
    height: 78,
    borderRadius: 8,
    marginRight: space.sm,
    backgroundColor: colour.sunken,
  },
  note: {
    backgroundColor: colour.sunken,
    borderRadius: 10,
    padding: space.md,
    marginBottom: space.md,
  },
  noteLabel: {
    ...type.label,
    fontSize: 11,
    letterSpacing: 0.6,
    color: colour.inkMuted,
    marginBottom: space.xs,
  },
  noteText: { ...type.body, color: colour.ink },
  why: { ...type.small, color: colour.inkSecondary },
  entryFoot: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm, marginTop: space.md },
  emptyTitle: { ...type.body, fontWeight: '700', color: colour.ink, marginBottom: space.xs },
  emptyBody: { ...type.body, color: colour.inkSecondary },
});
