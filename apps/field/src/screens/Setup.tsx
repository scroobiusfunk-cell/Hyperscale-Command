/**
 * Before the walk: who you are, where you are, and what is actually reachable.
 *
 * The declared state is not paperwork. The capture plan compiler uses it to
 * defer items the tech cannot safely or physically reach, so that the walk they
 * are handed is one they can finish. Saying a room is energized here is what
 * keeps a de-energized-only check off the list.
 */

import { useState } from 'react';
import { ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { Banner, Button, Card, Field } from '../components.tsx';
import type { DeclaredState } from '../core/types.ts';
import { colour, radius, space, type } from '../theme.ts';

export interface Config {
  baseUrl: string;
  projectId: string;
  devUserId: string;
}

export function Setup({
  config,
  onConfigChange,
  onStart,
  busy,
  error,
}: {
  config: Config;
  onConfigChange: (next: Config) => void;
  onStart: (declared: DeclaredState) => void;
  busy: boolean;
  error: string | null;
}) {
  const [room, setRoom] = useState('');
  const [energized, setEnergized] = useState(false);
  const [ladder, setLadder] = useState(false);
  const [permit, setPermit] = useState(false);

  const ready =
    config.baseUrl.trim() !== '' && config.projectId.trim() !== '' && config.devUserId.trim() !== '';

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Text style={styles.heading}>Start a walk</Text>
      <Text style={styles.sub}>
        Download it here while you still have signal. Everything after this works offline.
      </Text>

      {error !== null && <Banner tone="critical">{error}</Banner>}

      <Card style={{ marginBottom: space.lg }}>
        <Field label="Room or area">
          <TextInput
            style={styles.input}
            value={room}
            onChangeText={setRoom}
            placeholder="Electrical Room 1-04"
            placeholderTextColor={colour.inkMuted}
            autoCapitalize="words"
          />
        </Field>

        <Toggle
          label="This room is energized"
          hint="De-energized-only checks will be left off your list."
          value={energized}
          onChange={setEnergized}
        />
        <Toggle
          label="I have a ladder"
          hint="Anything above reach is deferred without one."
          value={ladder}
          onChange={setLadder}
        />
        <Toggle
          label="I have a confined space permit"
          value={permit}
          onChange={setPermit}
        />
      </Card>

      <Button
        title="Download this walk"
        busy={busy}
        disabled={!ready}
        onPress={() =>
          onStart({
            room: room.trim() === '' ? null : room.trim(),
            energized_rooms: energized && room.trim() !== '' ? [room.trim()] : [],
            ladder_available: ladder,
            confined_space_permit: permit,
          })
        }
      />

      <Text style={styles.connectionHeading}>Connection</Text>
      <Card>
        <Field label="API address">
          <TextInput
            style={styles.input}
            value={config.baseUrl}
            onChangeText={(baseUrl) => onConfigChange({ ...config, baseUrl })}
            autoCapitalize="none"
            autoCorrect={false}
            inputMode="url"
          />
        </Field>
        <Field label="Project id">
          <TextInput
            style={styles.input}
            value={config.projectId}
            onChangeText={(projectId) => onConfigChange({ ...config, projectId })}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </Field>
        <Field label="Your user id">
          <TextInput
            style={styles.input}
            value={config.devUserId}
            onChangeText={(devUserId) => onConfigChange({ ...config, devUserId })}
            autoCapitalize="none"
            autoCorrect={false}
          />
        </Field>
        <Text style={styles.note}>
          Development sign-in. Company SSO replaces this before anyone uses it on a real job.
        </Text>
      </Card>
    </ScrollView>
  );
}

function Toggle({
  label,
  hint,
  value,
  onChange,
}: {
  label: string;
  hint?: string;
  value: boolean;
  onChange: (next: boolean) => void;
}) {
  return (
    <View style={styles.toggle}>
      <View style={{ flex: 1, paddingRight: space.md }}>
        <Text style={styles.toggleLabel}>{label}</Text>
        {hint !== undefined && <Text style={styles.note}>{hint}</Text>}
      </View>
      <Switch value={value} onValueChange={onChange} />
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: space.lg, paddingBottom: space.xxl, backgroundColor: colour.plane },
  heading: { ...type.hero, color: colour.ink, marginBottom: space.xs },
  sub: { ...type.body, color: colour.inkSecondary, marginBottom: space.lg },
  connectionHeading: {
    ...type.label,
    color: colour.inkMuted,
    textTransform: 'uppercase',
    letterSpacing: 0.6,
    marginTop: space.xl,
    marginBottom: space.sm,
  },
  input: {
    borderWidth: 1,
    borderColor: colour.hairline,
    borderRadius: radius.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.md,
    fontSize: 16,
    color: colour.ink,
    backgroundColor: colour.surface,
    minHeight: 48,
  },
  toggle: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingVertical: space.md,
    borderTopWidth: 1,
    borderTopColor: colour.hairline,
  },
  toggleLabel: { ...type.body, fontWeight: '600', color: colour.ink },
  note: { ...type.small, color: colour.inkMuted, marginTop: 2 },
});
