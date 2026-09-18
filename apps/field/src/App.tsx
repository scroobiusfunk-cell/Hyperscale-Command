/**
 * The field app.
 *
 * Three screens and a sync bar. Navigation is a state machine rather than a
 * router because there are three screens and a dependency would be the larger
 * thing.
 *
 * The rule the whole app is arranged around: every action the tech takes is
 * written to the outbox before the screen moves on. Sync is something that
 * happens in the background, not something the tech waits for — a walk works
 * identically with the radio off, which is the normal case in a plant room.
 */

import * as FileSystem from 'expo-file-system';
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Pressable, SafeAreaView, StyleSheet, Text, View } from 'react-native';

import { Banner } from './components.tsx';
import { HttpFieldApi } from './core/api.ts';
import type { FieldApi } from './core/api.ts';
import type { Measurement } from './core/gates.ts';
import { Outbox } from './core/outbox.ts';
import type { Device } from './core/ports.ts';
import { runSync } from './core/sync.ts';
import type { SyncReport } from './core/sync.ts';
import type {
  DeclaredState,
  GateFailed,
  ItemCaptured,
  ItemDeferred,
  ItemOpened,
  WalkCompleted,
  WalkItem,
} from './core/types.ts';
import { WalkStore, nextItem } from './core/walkStore.ts';
import type { ItemProgress, StoredWalk } from './core/walkStore.ts';
import { fromBase64, openDevice, sha256 } from './device.ts';
import { Capture } from './screens/Capture.tsx';
import type { CaptureOutcome } from './screens/Capture.tsx';
import { Setup } from './screens/Setup.tsx';
import type { Config } from './screens/Setup.tsx';
import { MyWork } from './screens/MyWork.tsx';
import { WalkList } from './screens/WalkList.tsx';
import { colour, space, type } from './theme.ts';

const CONFIG_KEY = 'config';
const SYNC_EVERY_MS = 30_000;

type Screen =
  | { name: 'loading' }
  | { name: 'setup' }
  | { name: 'walk' }
  | { name: 'my-work' }
  | { name: 'capture'; item: WalkItem; assetTag: string };

export default function App() {
  const [device, setDevice] = useState<Device | null>(null);
  const [config, setConfig] = useState<Config>({ baseUrl: '', projectId: '', devUserId: '' });
  const [screen, setScreen] = useState<Screen>({ name: 'loading' });
  const [stored, setStored] = useState<StoredWalk | null>(null);
  const [progress, setProgress] = useState<Record<string, ItemProgress>>({});
  const [counts, setCounts] = useState({ events: 0, blobs: 0 });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastSync, setLastSync] = useState<SyncReport | null>(null);
  const syncing = useRef(false);

  const outbox = device === null ? null : new Outbox(device);
  const walkStore = device === null ? null : new WalkStore(device);

  const api: FieldApi | null =
    config.baseUrl.trim() === ''
      ? null
      : new HttpFieldApi({ baseUrl: config.baseUrl.trim(), devUserId: config.devUserId.trim() });

  // Open the device, then decide whether there is a walk to carry on with.
  useEffect(() => {
    void (async () => {
      const opened = await openDevice();
      setDevice(opened);
      const savedConfig = await opened.kv.get(CONFIG_KEY);
      if (savedConfig !== null) setConfig(JSON.parse(savedConfig) as Config);
      const store = new WalkStore(opened);
      const current = await store.current();
      setStored(current);
      setProgress(await store.progress());
      setCounts(await new Outbox(opened).counts());
      setScreen(current === null ? { name: 'setup' } : { name: 'walk' });
    })();
  }, []);

  const refreshCounts = useCallback(async () => {
    if (outbox === null) return;
    setCounts(await outbox.counts());
  }, [outbox]);

  const sync = useCallback(async () => {
    if (api === null || outbox === null || device === null || syncing.current) return;
    syncing.current = true;
    try {
      const report = await runSync(api, outbox, device);
      setLastSync(report);
    } catch (caught) {
      setLastSync(null);
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      syncing.current = false;
      await refreshCounts();
    }
  }, [api, outbox, device, refreshCounts]);

  // Try periodically rather than on a connectivity event. Signal on a site comes
  // and goes in seconds, and an attempt that fails costs nothing.
  useEffect(() => {
    const timer = setInterval(() => void sync(), SYNC_EVERY_MS);
    return () => clearInterval(timer);
  }, [sync]);

  async function saveConfig(next: Config): Promise<void> {
    setConfig(next);
    if (device !== null) await device.kv.set(CONFIG_KEY, JSON.stringify(next));
  }

  async function startWalk(declared: DeclaredState): Promise<void> {
    if (api === null || walkStore === null) return;
    setBusy(true);
    setError(null);
    try {
      const walk = await api.startWalk(config.projectId.trim(), declared);
      if (walk.item_count === 0) {
        setError('Nothing on that list is reachable in the state you described.');
        return;
      }
      setStored(await walkStore.save(config.projectId.trim(), walk));
      setProgress({});
      setScreen({ name: 'walk' });
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  }

  async function openItem(item: WalkItem, assetTag: string): Promise<void> {
    if (outbox === null || stored === null) return;
    await outbox.append<ItemOpened>(stored.walkId, {
      event_type: 'item_opened',
      checklist_item_id: item.checklist_item_id,
    });
    await refreshCounts();
    setScreen({ name: 'capture', item, assetTag });
  }

  async function recordCapture(item: WalkItem, outcome: CaptureOutcome): Promise<void> {
    if (outbox === null || stored === null || device === null) return;
    const clientId = device.ids.uuid();
    await outbox.appendCapture(stored.walkId, outcome.bytes, {
      event_type: 'capture_taken',
      checklist_item_id: item.checklist_item_id,
      client_id: clientId,
      capture_recipe_id: item.capture_recipe_id,
      capture_recipe_version: item.recipe_version,
      step_index: outcome.stepIndex,
      media_type: 'photo',
      storage_key: `evidence/${clientId}`,
      content_hash: await sha256(outcome.bytes),
      mime_type: 'image/jpeg',
      gate_results: outcome.gateResults,
    });
    if (!outcome.gatePassed) {
      await outbox.append<GateFailed>(stored.walkId, {
        event_type: 'gate_failed',
        checklist_item_id: item.checklist_item_id,
        capture_recipe_id: item.capture_recipe_id,
        step_index: outcome.stepIndex,
        gate_results: outcome.gateResults.filter((g) => g.outcome === 'failed'),
      });
    }
    await refreshCounts();
  }

  async function finishItem(item: WalkItem): Promise<void> {
    if (outbox === null || stored === null || walkStore === null) return;
    setBusy(true);
    try {
      await outbox.append<ItemCaptured>(stored.walkId, {
        event_type: 'item_captured',
        checklist_item_id: item.checklist_item_id,
      });
      await walkStore.setProgress(item.checklist_item_id, 'captured');
      setProgress(await walkStore.progress());
      await refreshCounts();
      void sync();
      setScreen({ name: 'walk' });
    } finally {
      setBusy(false);
    }
  }

  async function deferItem(item: WalkItem, reason: string, note: string): Promise<void> {
    if (outbox === null || stored === null || walkStore === null) return;
    setBusy(true);
    try {
      await outbox.append<ItemDeferred>(stored.walkId, {
        event_type: 'item_deferred',
        checklist_item_id: item.checklist_item_id,
        reason,
        note,
      });
      await walkStore.setProgress(item.checklist_item_id, 'deferred');
      setProgress(await walkStore.progress());
      await refreshCounts();
      setScreen({ name: 'walk' });
    } finally {
      setBusy(false);
    }
  }

  async function finishWalk(): Promise<void> {
    if (outbox === null || stored === null || walkStore === null) return;
    setBusy(true);
    try {
      await outbox.append<WalkCompleted>(stored.walkId, {
        event_type: 'walk_completed',
        items_attempted: Object.keys(progress).length,
      });
      await walkStore.clear();
      setStored(null);
      setProgress({});
      await refreshCounts();
      void sync();
      setScreen({ name: 'setup' });
    } finally {
      setBusy(false);
    }
  }

  function goNext(): void {
    if (stored === null) return;
    const next = nextItem(stored.walk, progress);
    if (next === null) return;
    void openItem(next.item, next.stop.tag);
  }

  if (screen.name === 'loading' || device === null) {
    return (
      <SafeAreaView style={styles.centred}>
        <ActivityIndicator size="large" color={colour.accent} />
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.app}>
      <StatusBar style="dark" />
      <SyncBar counts={counts} report={lastSync} onPress={() => void sync()} />
      {lastSync?.changed.length ? (
        <View style={{ paddingHorizontal: space.lg, paddingTop: space.md }}>
          <Banner tone="warning">
            {lastSync.changed.map((c) => c.message).join(' ')}
          </Banner>
        </View>
      ) : null}

      {screen.name === 'setup' && (
        <Setup
          config={config}
          onConfigChange={(next) => void saveConfig(next)}
          onStart={(declared) => void startWalk(declared)}
          onOpenMyWork={() => setScreen({ name: 'my-work' })}
          busy={busy}
          error={error}
        />
      )}

      {screen.name === 'my-work' && (
        <MyWork
          load={async () => {
            if (api === null) throw new Error('Set the connection details first.');
            return api.myWork(config.projectId.trim() === '' ? undefined : config.projectId.trim());
          }}
          imageFor={(evidenceId) => {
            if (api === null) return { uri: '', headers: {} };
            return api.evidenceImage(evidenceId);
          }}
          onBack={() => setScreen(stored === null ? { name: 'setup' } : { name: 'walk' })}
        />
      )}

      {screen.name === 'walk' && stored !== null && (
        <WalkList
          walk={stored.walk}
          progress={progress}
          onOpenItem={(item, tag) => void openItem(item, tag)}
          onNext={goNext}
          onFinish={() => void finishWalk()}
          onOpenMyWork={() => setScreen({ name: 'my-work' })}
          pendingEvents={counts.events}
          pendingBlobs={counts.blobs}
        />
      )}

      {screen.name === 'capture' && (
        <Capture
          item={screen.item}
          assetTag={screen.assetTag}
          busy={busy}
          takePhoto={takePhoto}
          measure={measure}
          onCaptured={(outcome) => recordCapture(screen.item, outcome)}
          onDefer={(reason, note) => deferItem(screen.item, reason, note)}
          onDone={() => finishItem(screen.item)}
          onBack={() => setScreen({ name: 'walk' })}
        />
      )}
    </SafeAreaView>
  );
}

function SyncBar({
  counts,
  report,
  onPress,
}: {
  counts: { events: number; blobs: number };
  report: SyncReport | null;
  onPress: () => void;
}) {
  const waiting = counts.events + counts.blobs;
  const stuck = report?.stoppedBecause ?? null;
  const tone = waiting === 0 ? colour.goodSoft : stuck === null ? colour.sunken : colour.warningSoft;
  const label =
    waiting === 0
      ? '✓ Everything is sent'
      : stuck === null
        ? `● ${waiting} waiting to send`
        : `● ${waiting} waiting — no connection`;

  return (
    <Pressable onPress={onPress} style={[styles.syncBar, { backgroundColor: tone }]}>
      <Text style={styles.syncText}>{label}</Text>
      <Text style={styles.syncHint}>Tap to try now</Text>
    </Pressable>
  );
}

/** Take a shot and hand back its bytes. */
async function takePhoto(camera: { takePictureAsync?: Function } | null): Promise<Uint8Array> {
  if (camera?.takePictureAsync === undefined) throw new Error('The camera is not ready yet.');
  const photo = (await camera.takePictureAsync({ quality: 0.7, skipProcessing: true })) as {
    uri: string;
  } | null;
  if (photo === null) throw new Error('That photo did not save. Try again.');
  const base64 = await FileSystem.readAsStringAsync(photo.uri, {
    encoding: FileSystem.EncodingType.Base64,
  });
  return fromBase64(base64);
}

/**
 * What the device can say about a shot.
 *
 * Phase 1 ships without on-device image analysis, so there is no sharpness or
 * framing number to report and the gates record `skipped` rather than a
 * fabricated pass. Wiring a real blur metric in here is the one change needed
 * to turn those gates on, and nothing downstream has to change.
 */
async function measure(_bytes: Uint8Array): Promise<Measurement> {
  return {};
}

const styles = StyleSheet.create({
  app: { flex: 1, backgroundColor: colour.plane },
  centred: { flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: colour.plane },
  syncBar: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.lg,
    paddingVertical: space.md,
    borderBottomWidth: 1,
    borderBottomColor: colour.hairline,
  },
  syncText: { ...type.body, fontWeight: '600', color: colour.ink },
  syncHint: { ...type.small, color: colour.inkMuted },
});
