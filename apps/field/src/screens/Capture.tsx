/**
 * One checklist item, step by step.
 *
 * This is the screen a tech spends the walk in, so it says one thing at a time:
 * what is being checked, why it matters, and the single step in front of them.
 * The requirement is stated in full before the camera opens, because a tech who
 * does not know what they are photographing takes a photograph of the wrong
 * thing.
 *
 * Nothing here judges the equipment. The gates check the photograph — sharp
 * enough, close enough, legible — and a failed gate asks for a retake without
 * refusing the shot. Whether the filler plate is fitted is a person's call,
 * every time, in Phase 1.
 */

import { CameraView, useCameraPermissions } from 'expo-camera';
import { useRef, useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { Banner, Button, Card, Chip } from '../components.tsx';
import { runGates } from '../core/gates.ts';
import type { Measurement } from '../core/gates.ts';
import type { BlockedReason, GateResult, WalkItem } from '../core/types.ts';
import { colour, radius, space, type } from '../theme.ts';

export interface CaptureOutcome {
  bytes: Uint8Array;
  stepIndex: number;
  gateResults: GateResult[];
  gatePassed: boolean;
}

export function Capture({
  item,
  assetTag,
  onCaptured,
  onDefer,
  onDone,
  onBack,
  busy,
  takePhoto,
  measure,
}: {
  item: WalkItem;
  assetTag: string;
  onCaptured: (outcome: CaptureOutcome) => Promise<void>;
  onDefer: (reason: BlockedReason, note: string) => Promise<void>;
  onDone: () => Promise<void>;
  onBack: () => void;
  busy: boolean;
  /** Injected so the screen can be driven without a camera in a test. */
  takePhoto: (camera: CameraView | null) => Promise<Uint8Array>;
  measure: (bytes: Uint8Array) => Promise<Measurement>;
}) {
  const [permission, requestPermission] = useCameraPermissions();
  const [stepIndex, setStepIndex] = useState(0);
  const [captured, setCaptured] = useState<Set<number>>(new Set());
  const [advice, setAdvice] = useState<string | null>(null);
  const [deferring, setDeferring] = useState(false);
  const [deferNote, setDeferNote] = useState('');
  const [shooting, setShooting] = useState(false);
  const cameraRef = useRef<CameraView | null>(null);

  const step = item.steps[stepIndex];
  const lastStep = stepIndex >= item.steps.length - 1;
  const everyStepDone = item.steps.every((_, i) => captured.has(i));

  async function shoot(): Promise<void> {
    if (step === undefined) return;
    setShooting(true);
    setAdvice(null);
    try {
      const bytes = await takePhoto(cameraRef.current);
      const measured = await measure(bytes);
      const verdict = runGates([step.gate_check], measured);
      await onCaptured({
        bytes,
        stepIndex,
        gateResults: verdict.results,
        gatePassed: verdict.failed.length === 0,
      });
      setCaptured((prev) => new Set(prev).add(stepIndex));
      setAdvice(verdict.advice);
      // A failed gate keeps the tech on this step so a retake is the obvious
      // next tap. It does not block them: the shot is already recorded.
      if (verdict.failed.length === 0 && !lastStep) setStepIndex(stepIndex + 1);
    } catch (error) {
      setAdvice(error instanceof Error ? error.message : String(error));
    } finally {
      setShooting(false);
    }
  }

  if (deferring) {
    return (
      <ScrollView contentContainerStyle={styles.page}>
        <Text style={styles.heading}>Why can you not do this one?</Text>
        <Text style={styles.sub}>
          This is recorded against the item so a reviewer can see why it is outstanding.
        </Text>
        <TextInput
          style={styles.noteInput}
          value={deferNote}
          onChangeText={setDeferNote}
          multiline
          placeholder="The room was locked and nobody had the key."
          placeholderTextColor={colour.inkMuted}
        />
        <View style={{ gap: space.md, marginTop: space.lg }}>
          <Button
            title="Record and move on"
            busy={busy}
            disabled={deferNote.trim().length < 5}
            onPress={() => void onDefer('no_access', deferNote.trim())}
          />
          <Button kind="secondary" title="Back" onPress={() => setDeferring(false)} />
        </View>
      </ScrollView>
    );
  }

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

      {item.criticality === 'safety' && (
        <Banner tone="critical">
          A reviewer decides this one. Take the photographs and it goes to them — it will not clear
          on its own.
        </Banner>
      )}

      {step === undefined ? (
        <Banner tone="warning">This item has no capture steps. Report it and move on.</Banner>
      ) : (
        <>
          <Text style={styles.stepCount}>
            Step {stepIndex + 1} of {item.steps.length}
          </Text>
          <Text style={styles.instruction}>{step.instruction}</Text>
          <Text style={styles.framing}>{step.framing_rule}</Text>

          {permission?.granted !== true ? (
            <Card style={{ marginBottom: space.lg }}>
              <Text style={styles.whyText}>
                The camera is how evidence gets captured. Allow it to carry on.
              </Text>
              <View style={{ marginTop: space.md }}>
                <Button title="Allow the camera" onPress={() => void requestPermission()} />
              </View>
            </Card>
          ) : (
            <View style={styles.viewfinder}>
              <CameraView ref={cameraRef} style={StyleSheet.absoluteFill} facing="back" />
            </View>
          )}

          {advice !== null && <Banner tone="warning">{advice}</Banner>}

          <View style={{ gap: space.md }}>
            <Button
              title={captured.has(stepIndex) ? 'Take it again' : 'Take the photo'}
              busy={shooting || busy}
              disabled={permission?.granted !== true}
              onPress={() => void shoot()}
            />
            <View style={styles.stepRow}>
              <View style={{ flex: 1 }}>
                <Button
                  kind="secondary"
                  title="Previous step"
                  disabled={stepIndex === 0}
                  onPress={() => setStepIndex(stepIndex - 1)}
                />
              </View>
              <View style={{ flex: 1 }}>
                <Button
                  kind="secondary"
                  title="Next step"
                  disabled={lastStep}
                  onPress={() => setStepIndex(stepIndex + 1)}
                />
              </View>
            </View>
          </View>
        </>
      )}

      <View style={styles.footer}>
        <Button
          title="Send to a reviewer"
          busy={busy}
          disabled={!everyStepDone}
          onPress={() => void onDone()}
        />
        {!everyStepDone && (
          <Text style={styles.footNote}>
            Every step needs a photo first. {captured.size} of {item.steps.length} taken.
          </Text>
        )}
        <Button kind="secondary" title="I cannot do this one" onPress={() => setDeferring(true)} />
        <Button kind="secondary" title="Back to the walk" onPress={onBack} />
      </View>
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.lg, paddingBottom: space.xxl, backgroundColor: colour.plane },
  topRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: space.md,
    marginBottom: space.sm,
  },
  assetTag: { ...type.title, color: colour.ink },
  statement: { ...type.statement, color: colour.ink, marginBottom: space.md },
  heading: { ...type.hero, color: colour.ink, marginBottom: space.xs },
  sub: { ...type.body, color: colour.inkSecondary, marginBottom: space.lg },
  why: { backgroundColor: colour.sunken, marginBottom: space.lg },
  whyLabel: {
    ...type.label,
    color: colour.inkMuted,
    letterSpacing: 0.6,
    marginBottom: space.xs,
  },
  whyText: { ...type.body, color: colour.inkSecondary },
  stepCount: {
    ...type.label,
    color: colour.inkMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginBottom: space.xs,
  },
  instruction: { ...type.statement, color: colour.ink, marginBottom: space.xs },
  framing: { ...type.body, color: colour.inkSecondary, marginBottom: space.lg },
  viewfinder: {
    height: 300,
    borderRadius: radius.lg,
    overflow: 'hidden',
    backgroundColor: colour.sunken,
    marginBottom: space.lg,
  },
  stepRow: { flexDirection: 'row', gap: space.md },
  footer: { marginTop: space.xl, gap: space.md },
  footNote: { ...type.small, color: colour.inkMuted, textAlign: 'center' },
  noteInput: {
    borderWidth: 1,
    borderColor: colour.hairline,
    borderRadius: radius.sm,
    padding: space.md,
    fontSize: 16,
    minHeight: 120,
    textAlignVertical: 'top',
    color: colour.ink,
    backgroundColor: colour.surface,
  },
});
