/**
 * The walk as the tech sees it: what is left, and what to do next.
 */

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { MemoryBlobStore, MemoryKeyValueStore } from './ports.ts';
import type { Device } from './ports.ts';
import type { Criticality, Walk, WalkItem, WalkStop } from './types.ts';
import { WalkStore, countWalk, nextItem } from './walkStore.ts';

function makeDevice(): Device {
  let counter = 0;
  return {
    kv: new MemoryKeyValueStore(),
    blobs: new MemoryBlobStore(),
    clock: { now: () => new Date(Date.UTC(2026, 8, 18, 9, 0, 0)) },
    ids: { uuid: () => `id-${++counter}` },
  };
}

function item(id: string, criticality: Criticality = 'performance'): WalkItem {
  return {
    checklist_item_id: id,
    statement: `Check ${id}`,
    why_it_matters: 'Because.',
    criticality,
    item_type: 'checkx',
    capture_recipe_id: '00000000-0000-4000-8000-000000000001',
    recipe_slug: 'visual_presence',
    recipe_version: '1.0.0',
    reference_media_slot: null,
    disqualifiers: [],
    scaffold_level: 'full',
    steps: [],
  };
}

function stop(assetId: string, items: WalkItem[]): WalkStop {
  return { asset_id: assetId, tag: assetId.toUpperCase(), room: 'ER-1', grid_ref: null, items };
}

function walkOf(stops: WalkStop[]): Walk {
  return {
    stops,
    deferred: [],
    unroutable: [],
    item_count: stops.reduce((n, s) => n + s.items.length, 0),
    references: {},
  };
}

describe('keeping the walk', () => {
  test('a saved walk comes back after a restart', async () => {
    const device = makeDevice();
    const walk = walkOf([stop('a', [item('i1')])]);

    const saved = await new WalkStore(device).save('project-1', walk);
    const loaded = await new WalkStore(device).current();

    assert.equal(loaded?.walkId, saved.walkId);
    assert.equal(loaded?.walk.stops[0]?.items[0]?.checklist_item_id, 'i1');
  });

  test('no walk yet reads as null rather than throwing', async () => {
    assert.equal(await new WalkStore(makeDevice()).current(), null);
  });

  test('progress survives a restart too', async () => {
    const device = makeDevice();
    await new WalkStore(device).setProgress('i1', 'captured');
    assert.deepEqual(await new WalkStore(device).progress(), { i1: 'captured' });
  });

  test('clearing the walk leaves no progress behind', async () => {
    const device = makeDevice();
    const store = new WalkStore(device);
    await store.save('project-1', walkOf([stop('a', [item('i1')])]));
    await store.setProgress('i1', 'captured');

    await store.clear();

    assert.equal(await store.current(), null);
    assert.deepEqual(await store.progress(), {});
  });
});

describe('counting what is left', () => {
  test('an untouched walk is all to do', () => {
    const walk = walkOf([stop('a', [item('i1'), item('i2', 'safety')])]);
    assert.deepEqual(countWalk(walk, {}), { total: 2, done: 0, safetyRemaining: 1 });
  });

  test('deferring counts as dealt with, not as outstanding', () => {
    const walk = walkOf([stop('a', [item('i1'), item('i2')])]);
    assert.equal(countWalk(walk, { i1: 'deferred' }).done, 1);
  });

  test('a deferred safety item is no longer counted as remaining', () => {
    // It is somebody's problem now, and the deferral says whose.
    const walk = walkOf([stop('a', [item('i1', 'safety')])]);
    assert.equal(countWalk(walk, { i1: 'deferred' }).safetyRemaining, 0);
  });
});

describe('what to do next', () => {
  test('a finished walk has no next item', () => {
    const walk = walkOf([stop('a', [item('i1')])]);
    assert.equal(nextItem(walk, { i1: 'captured' }), null);
  });

  test('safety comes first', () => {
    const walk = walkOf([stop('a', [item('i1'), item('i2', 'safety')])]);
    assert.equal(nextItem(walk, {})?.item.checklist_item_id, 'i2');
  });

  test('the stop the tech is standing at wins over walking back', () => {
    const walk = walkOf([
      stop('a', [item('i1', 'safety')]),
      stop('b', [item('i2')]),
    ]);
    assert.equal(nextItem(walk, {}, 'b')?.item.checklist_item_id, 'i2');
  });

  test('at the same stop, safety still comes first', () => {
    const walk = walkOf([stop('a', [item('i1'), item('i2', 'safety')])]);
    assert.equal(nextItem(walk, {}, 'a')?.item.checklist_item_id, 'i2');
  });

  test('items already dealt with are skipped', () => {
    const walk = walkOf([stop('a', [item('i1'), item('i2')])]);
    assert.equal(nextItem(walk, { i1: 'captured' })?.item.checklist_item_id, 'i2');
  });
});
