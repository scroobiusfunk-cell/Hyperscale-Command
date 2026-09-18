/**
 * The outbox, which is where a tech's work is lost if anything here is wrong.
 *
 * CLAUDE.md requires tests for event replay. This is its client half: the
 * server can only be idempotent about events the device actually kept.
 */

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { Outbox } from './outbox.ts';
import { MemoryBlobStore, MemoryKeyValueStore } from './ports.ts';
import type { Device } from './ports.ts';
import type { CaptureTaken, ItemOpened } from './types.ts';

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

function opened(itemId: string): Omit<
  ItemOpened,
  'client_event_id' | 'client_walk_id' | 'sequence' | 'occurred_at'
> {
  return { event_type: 'item_opened', checklist_item_id: itemId };
}

function capture(
  itemId: string,
  clientId: string,
): Omit<
  CaptureTaken,
  'client_event_id' | 'client_walk_id' | 'sequence' | 'occurred_at' | 'byte_size'
> {
  return {
    event_type: 'capture_taken',
    checklist_item_id: itemId,
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

describe('appending events', () => {
  test('every event gets an id, a walk, a sequence and a time', async () => {
    const outbox = new Outbox(makeDevice());
    const event = await outbox.append(WALK, opened('item-1'));

    assert.equal(event.client_walk_id, WALK);
    assert.equal(event.sequence, 0);
    assert.ok(event.client_event_id);
    assert.ok(event.occurred_at.endsWith('Z'));
  });

  test('sequence is monotonic within a walk', async () => {
    const outbox = new Outbox(makeDevice());
    for (let i = 0; i < 3; i += 1) await outbox.append(WALK, opened(`item-${i}`));

    const pending = await outbox.pendingEvents(WALK);
    assert.deepEqual(
      pending.map((p) => p.event.sequence),
      [0, 1, 2],
    );
  });

  test('sequence survives a restart', async () => {
    const device = makeDevice();
    await new Outbox(device).append(WALK, opened('item-1'));
    // A new Outbox over the same storage is what a relaunched app looks like.
    const event = await new Outbox(device).append(WALK, opened('item-2'));
    assert.equal(event.sequence, 1);
  });

  test('two walks number themselves independently', async () => {
    const outbox = new Outbox(makeDevice());
    await outbox.append('walk-a', opened('item-1'));
    const second = await outbox.append('walk-b', opened('item-2'));
    assert.equal(second.sequence, 0);
  });

  test('past a hundred events the order is still right', async () => {
    // A lexical key sort has to survive the jump from 9 to 10 to 100.
    const outbox = new Outbox(makeDevice());
    for (let i = 0; i < 120; i += 1) await outbox.append(WALK, opened(`item-${i}`));

    const sequences = (await outbox.pendingEvents(WALK)).map((p) => p.event.sequence);
    assert.deepEqual(sequences, [...Array(120).keys()]);
  });
});

describe('captures', () => {
  test('the bytes are stored and the size is measured, not trusted', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    const bytes = new Uint8Array([1, 2, 3, 4, 5]);

    const event = await outbox.appendCapture(WALK, bytes, capture('item-1', 'cap-1'));

    assert.equal(event.byte_size, 5);
    assert.deepEqual(await device.blobs.read('cap-1'), bytes);
  });

  test('a capture queues both an event and a blob', async () => {
    const outbox = new Outbox(makeDevice());
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('item-1', 'cap-1'));

    assert.deepEqual(await outbox.counts(), { events: 1, blobs: 1 });
  });

  test('a retake names what it replaces', async () => {
    const outbox = new Outbox(makeDevice());
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('item-1', 'cap-1'));
    const retake = await outbox.appendCapture(WALK, new Uint8Array([2]), {
      ...capture('item-1', 'cap-2'),
      retake_of_client_id: 'cap-1',
    });

    assert.equal(retake.retake_of_client_id, 'cap-1');
  });
});

describe('acknowledgement', () => {
  test('nothing leaves the outbox until it is acknowledged', async () => {
    const outbox = new Outbox(makeDevice());
    await outbox.append(WALK, opened('item-1'));

    assert.equal((await outbox.counts()).events, 1);
    const pending = await outbox.pendingEvents(WALK);
    await outbox.acknowledgeEvents(pending.map((p) => p.key));
    assert.equal((await outbox.counts()).events, 0);
  });

  test('acknowledging a blob frees the bytes too', async () => {
    const device = makeDevice();
    const outbox = new Outbox(device);
    await outbox.appendCapture(WALK, new Uint8Array([1]), capture('item-1', 'cap-1'));

    await outbox.acknowledgeBlob('cap-1');

    assert.equal((await outbox.counts()).blobs, 0);
    assert.equal(await device.blobs.read('cap-1'), null);
  });

  test('acknowledging part of a queue leaves the rest', async () => {
    const outbox = new Outbox(makeDevice());
    await outbox.append(WALK, opened('item-1'));
    await outbox.append(WALK, opened('item-2'));

    const pending = await outbox.pendingEvents(WALK);
    await outbox.acknowledgeEvents([pending[0]!.key]);

    const left = await outbox.pendingEvents(WALK);
    assert.equal(left.length, 1);
    assert.equal(left[0]!.event.sequence, 1);
  });
});
