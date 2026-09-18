/**
 * Syncing, mostly by breaking it.
 *
 * The success path is one test. The rest are the ways a site connection fails,
 * because those are the ones that lose a tech's morning.
 */

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { ApiError } from './api.ts';
import type { BlobUploadResult, FieldApi } from './api.ts';
import { Outbox } from './outbox.ts';
import { MemoryBlobStore, MemoryKeyValueStore } from './ports.ts';
import type { Device } from './ports.ts';
import { runSync } from './sync.ts';
import type {
  CaptureTaken,
  DeclaredState,
  MyWork,
  OutboxEvent,
  SyncResult,
  Walk,
} from './types.ts';

const WALK = 'walk-1';

function makeDevice(): Device & { blobs: MemoryBlobStore } {
  let counter = 0;
  let tick = 0;
  const blobs = new MemoryBlobStore();
  return {
    kv: new MemoryKeyValueStore(),
    blobs,
    clock: { now: () => new Date(Date.UTC(2026, 8, 18, 9, 0, tick++)) },
    ids: { uuid: () => `id-${++counter}` },
  };
}

interface FakeOptions {
  failSyncWith?: unknown;
  failUploadWith?: unknown;
  changed?: { checklist_item_id: string; message: string }[];
}

class FakeApi implements FieldApi {
  readonly syncCalls: OutboxEvent[][] = [];
  readonly uploads: string[] = [];

  private readonly options: FakeOptions;

  constructor(options: FakeOptions = {}) {
    this.options = options;
  }

  async previewWalk(_p: string, _d: DeclaredState): Promise<Walk> {
    throw new Error('not used');
  }

  async startWalk(_p: string, _d: DeclaredState): Promise<Walk> {
    throw new Error('not used');
  }

  async sync(events: OutboxEvent[]): Promise<SyncResult> {
    if (this.options.failSyncWith !== undefined) throw this.options.failSyncWith;
    this.syncCalls.push(events);
    return {
      accepted: events.length,
      duplicates: 0,
      applied: events.length,
      superseded: 0,
      rejected: 0,
      evidence_created: 0,
      changed_while_you_were_away: this.options.changed ?? [],
    };
  }

  evidenceImage(evidenceId: string): { uri: string; headers: Record<string, string> } {
    return { uri: `fake://${evidenceId}`, headers: {} };
  }

  async myWork(): Promise<MyWork> {
    return {
      tally: { ruled: 0, passed: 0, failed: 0, recapture_requested: 0, awaiting_review: 0 },
      feedback: [],
    };
  }

  async uploadBlob(clientId: string): Promise<BlobUploadResult> {
    if (this.options.failUploadWith !== undefined) throw this.options.failUploadWith;
    this.uploads.push(clientId);
    return {
      storage_key: `evidence/${clientId}`,
      byte_size: 1,
      content_hash: 'a'.repeat(64),
      first_time: true,
      evidence_confirmed: true,
    };
  }
}

function capture(
  clientId: string,
): Omit<
  CaptureTaken,
  'client_event_id' | 'client_walk_id' | 'sequence' | 'occurred_at' | 'byte_size'
> {
  return {
    event_type: 'capture_taken',
    checklist_item_id: 'item-1',
    client_id: clientId,
    capture_recipe_id: 'recipe-1',
    capture_recipe_version: '1.0.0',
    step_index: 0,
    media_type: 'photo',
    storage_key: `evidence/${clientId}`,
    content_hash: 'a'.repeat(64),
    mime_type: 'image/jpeg',
  };
}

describe('a sync that works', () => {
  test('the log goes first, then the photographs', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi();
    await outbox.appendCapture(WALK, new Uint8Array([1, 2]), capture('cap-1'));

    const report = await runSync(api, outbox, device);

    assert.equal(report.eventsAcknowledged, 1);
    assert.equal(report.blobsUploaded, 1);
    assert.deepEqual(await outbox.counts(), { events: 0, blobs: 0 });
  });

  test('a reviewer decision made while offline is reported back', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi({
      changed: [{ checklist_item_id: 'item-1', message: 'A reviewer already failed this.' }],
    });
    await outbox.append(WALK, { event_type: 'item_opened', checklist_item_id: 'item-1' });

    const report = await runSync(api, outbox, device);

    assert.equal(report.changed.length, 1);
    assert.match(report.changed[0]!.message, /reviewer/);
  });

  test('a large backlog goes up in batches', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi();
    for (let i = 0; i < 120; i += 1) {
      await outbox.append(WALK, { event_type: 'item_opened', checklist_item_id: `item-${i}` });
    }

    await runSync(api, outbox, device);

    assert.equal(api.syncCalls.length, 3); // 50 + 50 + 20
    assert.equal((await outbox.counts()).events, 0);
  });

  test('photographs go smallest first', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi();
    await outbox.appendCapture(WALK, new Uint8Array(500), capture('big'));
    await outbox.appendCapture(WALK, new Uint8Array(10), capture('small'));

    await runSync(api, outbox, device);

    assert.deepEqual(api.uploads, ['small', 'big']);
  });
});

describe('a sync that fails', () => {
  test('a dead connection leaves the whole outbox intact', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi({ failSyncWith: new Error('Network request failed') });
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('cap-1'));

    const report = await runSync(api, outbox, device);

    assert.match(report.stoppedBecause ?? '', /Network/);
    assert.deepEqual(await outbox.counts(), { events: 1, blobs: 1 });
  });

  test('retrying after a failure sends the very same event ids', async () => {
    // This is what makes the server's deduplication work at all.
    const device = makeDevice();
    const outbox = new Outbox(device);
    await outbox.append(WALK, { event_type: 'item_opened', checklist_item_id: 'item-1' });

    const idsBefore = (await outbox.pendingEvents()).map((p) => p.event.client_event_id);
    await runSync(new FakeApi({ failSyncWith: new Error('down') }), outbox, device);
    const idsAfter = (await outbox.pendingEvents()).map((p) => p.event.client_event_id);

    assert.deepEqual(idsAfter, idsBefore);
  });

  test('a failure partway through keeps what was not sent', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    for (let i = 0; i < 80; i += 1) {
      await outbox.append(WALK, { event_type: 'item_opened', checklist_item_id: `item-${i}` });
    }
    let calls = 0;
    const api = new FakeApi();
    const flaky: FieldApi = {
      previewWalk: api.previewWalk.bind(api),
      startWalk: api.startWalk.bind(api),
      myWork: api.myWork.bind(api),
      evidenceImage: api.evidenceImage.bind(api),
      sync: async (events) => {
        calls += 1;
        if (calls > 1) throw new Error('signal gone');
        return api.sync(events);
      },
      uploadBlob: api.uploadBlob.bind(api),
    };

    const report = await runSync(flaky, outbox, device);

    assert.equal(report.eventsAcknowledged, 50);
    assert.equal(report.eventsRemaining, 30);
  });

  test('photographs still waiting are not lost when the upload fails', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi({ failUploadWith: new Error('connection reset') });
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('cap-1'));

    const report = await runSync(api, outbox, device);

    assert.equal(report.eventsAcknowledged, 1); // the log did get through
    assert.equal(report.blobsRemaining, 1);
    assert.deepEqual(await device.blobs.read('cap-1'), new Uint8Array([1]));
  });

  test('bytes the server will never accept are dropped, not retried forever', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi({ failUploadWith: new ApiError(422, 'hash mismatch') });
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('cap-1'));
    await outbox.appendCapture(WALK, new Uint8Array([2]), capture('cap-2'));

    const report = await runSync(api, outbox, device);

    assert.deepEqual(report.droppedBlobs, ['cap-1', 'cap-2']);
    assert.equal(report.blobsRemaining, 0);
  });

  test('a server error blocks the queue rather than dropping it', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi({ failUploadWith: new ApiError(503, 'unavailable') });
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('cap-1'));

    const report = await runSync(api, outbox, device);

    assert.deepEqual(report.droppedBlobs, []);
    assert.equal(report.blobsRemaining, 1);
  });

  test('a queued photograph whose bytes are gone stops being queued', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('cap-1'));
    await device.blobs.remove('cap-1'); // the OS cleared the cache

    const report = await runSync(new FakeApi(), outbox, device);

    assert.deepEqual(report.droppedBlobs, ['cap-1']);
    assert.equal(report.blobsRemaining, 0);
  });

  test('syncing twice over sends nothing the second time', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const api = new FakeApi();
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('cap-1'));

    await runSync(api, outbox, device);
    const second = await runSync(api, outbox, device);

    assert.equal(second.eventsSent, 0);
    assert.equal(second.blobsUploaded, 0);
    assert.equal(api.syncCalls.length, 1);
  });
});
