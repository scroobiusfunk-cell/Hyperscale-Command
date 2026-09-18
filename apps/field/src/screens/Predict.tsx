/**
 * Make the call first.
 *
 * This screen stands between opening an item and photographing it, and it is
 * the difference between a checklist and a training tool. A learner who
 * photographs first and finds out later has practised photography. A learner
 * who commits to pass or fail *before* seeing anything has practised the
 * judgement they are actually being trained to make, and the senior's ruling
 * afterwards is feedback rather than trivia.
 *
 * Three things here are deliberate.
 *
 * **The worked examples come first.** What good looks like, and what a
 * near-miss looks like, are shown above the question, because a learner who has
 * never seen a correct install cannot be expected to recognise one. The wrong
 * examples matter more: anybody spots a missing part, and what gets walked past
 * is the plate that is fitted but not seated.
 *
 * **"Not sure" is a real answer.** It sits alongside pass and fail, not hidden.
 * Forcing a binary guess teaches guessing, and a senior would far rather know a
 * learner was unsure than have them flip a coin. It is excluded from the
 * agreement rate and counted on its own.
 *
 * **The call cannot be walked back.** Once recorded it is append-only on the
 * server and a second call is refused. The screen says so before they commit,
 * because a number built on revisable answers would be worthless and the
 * learner should know their answer counts.
 */

import { useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { Banner, Button, Card, Chip } from '../components.tsx';
import type { PredictedVerdict, ReferenceImage, WalkItem } from '../core/types.ts';
import { TAP_TARGET, colour, radius, space, type } from '../theme.ts';

const CHOICES: { verdict: PredictedVerdict; label: string; hint: string }[] = [
  { verdict: 'pass', label: 'Looks right', hint: 'It meets the requirement' },
  { verdict: 'fail', label: 'Looks wrong', hint: 'Something is off' },
  { verdict: 'unsure', label: 'Not sure', hint: 'Say so — it is a real answer' },
];

export function Predict({
  item,
  assetTag,
  references,
  imageFor,
  onCommit,
  onBack,
  busy,
}: {
  item: WalkItem;
  assetTag: string;
  references: ReferenceImage[];
  imageFor: (referenceImageId: string) => { uri: string; headers: Record<string, string> };
  onCommit: (verdict: PredictedVerdict, reason: string | null) => Promise<void>;
  onBack: () => void;
  busy: boolean;
}) {
  const [verdict, setVerdict] = useState<PredictedVerdict | null>(null);
  const [reason, setReason] = useState<string | null>(null);

  const good = references.filter((r) => r.kind === 'good');
  const wrong = references.filter((r) => r.kind === 'wrong');
  const needsReason = verdict === 'fail' && item.disqualifiers.length > 0;
  const ready = verdict !== null && (!needsReason || reason !== null);

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <View style={styles.topRow}>
        <Text style={styles.assetTag}>{assetTag}</Text>
        {item.criticality === 'safety' && (
          <Chip tone="critical" icon="▲">
            Safety
          </Chip>
        )}
      </View>

      <Text style={styles.statement}>{item.statement}</Text>

      <Card style={styles.why}>
        <Text style={styles.whyLabel}>WHY IT MATTERS</Text>
        <Text style={styles.whyText}>{item.why_it_matters}</Text>
      </Card>

      {references.length === 0 ? (
        <Banner tone="neutral">
          Nobody has added examples for this check yet. Go on what the requirement says.
        </Banner>
      ) : (
        <>
          {good.length > 0 && <Examples title="What good looks like" tone="good" shots={good} imageFor={imageFor} />}
          {wrong.length > 0 && (
            <Examples title="What wrong looks like" tone="critical" shots={wrong} imageFor={imageFor} />
          )}
        </>
      )}

      <Text style={styles.question}>Before you photograph it — what do you think?</Text>

      <View style={styles.choices}>
        {CHOICES.map((choice) => {
          const picked = verdict === choice.verdict;
          return (
            <Pressable
              key={choice.verdict}
              accessibilityRole="radio"
              accessibilityState={{ selected: picked }}
              onPress={() => {
                setVerdict(choice.verdict);
                if (choice.verdict !== 'fail') setReason(null);
              }}
              style={[styles.choice, picked && styles.choicePicked]}
            >
              <Text style={[styles.choiceLabel, picked && styles.choiceLabelPicked]}>
                {choice.label}
              </Text>
              <Text style={styles.choiceHint}>{choice.hint}</Text>
            </Pressable>
          );
        })}
      </View>

      {needsReason && (
        <View style={{ marginBottom: space.lg }}>
          <Text style={styles.reasonLabel}>What is wrong with it?</Text>
          {item.disqualifiers.map((d) => (
            <Pressable
              key={d}
              accessibilityRole="radio"
              accessibilityState={{ selected: reason === d }}
              onPress={() => setReason(d)}
              style={[styles.reason, reason === d && styles.reasonPicked]}
            >
              <Text style={styles.reasonText}>{d}</Text>
            </Pressable>
          ))}
          <Pressable
            accessibilityRole="radio"
            accessibilityState={{ selected: reason === 'other' }}
            onPress={() => setReason('other')}
            style={[styles.reason, reason === 'other' && styles.reasonPicked]}
          >
            <Text style={styles.reasonText}>Something else</Text>
          </Pressable>
        </View>
      )}

      <Banner tone="neutral">
        Your answer is recorded before you take the photo and cannot be changed. That is what
        makes it worth comparing against the reviewer.
      </Banner>

      <View style={{ gap: space.md }}>
        <Button
          title="Record my call and photograph it"
          busy={busy}
          disabled={!ready}
          onPress={() => verdict !== null && void onCommit(verdict, reason)}
        />
        <Button kind="secondary" title="Back to the walk" onPress={onBack} />
      </View>
    </ScrollView>
  );
}

function Examples({
  title,
  tone,
  shots,
  imageFor,
}: {
  title: string;
  tone: 'good' | 'critical';
  shots: ReferenceImage[];
  imageFor: (referenceImageId: string) => { uri: string; headers: Record<string, string> };
}) {
  return (
    <View style={{ marginBottom: space.lg }}>
      <View style={styles.examplesHead}>
        <Chip tone={tone} icon={tone === 'good' ? '✓' : '▲'}>
          {title}
        </Chip>
      </View>
      {shots.map((shot) => (
        <View key={shot.reference_image_id} style={styles.example}>
          <Image
            source={imageFor(shot.reference_image_id)}
            style={styles.exampleShot}
            resizeMode="cover"
            accessibilityLabel={shot.caption}
          />
          <Text style={styles.exampleCaption}>{shot.caption}</Text>
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.lg, paddingBottom: space.xxl, backgroundColor: colour.plane },
  topRow: { flexDirection: 'row', alignItems: 'center', gap: space.md, marginBottom: space.sm },
  assetTag: { ...type.title, color: colour.ink },
  statement: { ...type.statement, color: colour.ink, marginBottom: space.md },
  why: { backgroundColor: colour.sunken, marginBottom: space.lg },
  whyLabel: { ...type.label, color: colour.inkMuted, letterSpacing: 0.6, marginBottom: space.xs },
  whyText: { ...type.body, color: colour.inkSecondary },
  examplesHead: { marginBottom: space.sm },
  example: { marginBottom: space.md },
  exampleShot: {
    width: '100%',
    height: 200,
    borderRadius: radius.md,
    backgroundColor: colour.sunken,
  },
  exampleCaption: { ...type.body, color: colour.inkSecondary, marginTop: space.xs },
  question: { ...type.statement, color: colour.ink, marginBottom: space.md },
  choices: { gap: space.sm, marginBottom: space.lg },
  choice: {
    minHeight: TAP_TARGET,
    borderRadius: radius.md,
    borderWidth: 2,
    borderColor: colour.hairline,
    backgroundColor: colour.surface,
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    justifyContent: 'center',
  },
  choicePicked: { borderColor: colour.accent, backgroundColor: '#eef4fd' },
  choiceLabel: { ...type.body, fontWeight: '700', color: colour.ink },
  choiceLabelPicked: { color: colour.accent },
  choiceHint: { ...type.small, color: colour.inkMuted },
  reasonLabel: { ...type.body, fontWeight: '600', color: colour.ink, marginBottom: space.sm },
  reason: {
    minHeight: 48,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colour.hairline,
    backgroundColor: colour.surface,
    paddingHorizontal: space.md,
    justifyContent: 'center',
    marginBottom: space.sm,
  },
  reasonPicked: { borderColor: colour.accent, borderWidth: 2 },
  reasonText: { ...type.body, color: colour.ink },
});
