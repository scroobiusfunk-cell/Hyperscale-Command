/**
 * The walk, as the tech works through it.
 *
 * Downloaded once while there is still signal and then kept on the device. The
 * progress record here is local: it is what the app shows, not what the
 * platform believes. The platform's view is rebuilt from the event log, and if
 * the two ever disagree the event log wins, because that is the thing the
 * server has actually seen.
 */

import type { Device } from './ports.ts';
import type { Walk, WalkItem, WalkStop } from './types.ts';

const WALK_KEY = 'walk:current';
const PROGRESS_PREFIX = 'walk:progress:';

export type ItemProgress = 'open' | 'captured' | 'deferred';

export interface StoredWalk {
  walkId: string;
  projectId: string;
  downloadedAt: string;
  walk: Walk;
}

export class WalkStore {
  private readonly device: Device;

  constructor(device: Device) {
    this.device = device;
  }

  async save(projectId: string, walk: Walk): Promise<StoredWalk> {
    const stored: StoredWalk = {
      walkId: this.device.ids.uuid(),
      projectId,
      downloadedAt: this.device.clock.now().toISOString(),
      walk,
    };
    await this.device.kv.set(WALK_KEY, JSON.stringify(stored));
    return stored;
  }

  async current(): Promise<StoredWalk | null> {
    const raw = await this.device.kv.get(WALK_KEY);
    return raw === null ? null : (JSON.parse(raw) as StoredWalk);
  }

  async setProgress(itemId: string, progress: ItemProgress): Promise<void> {
    await this.device.kv.set(`${PROGRESS_PREFIX}${itemId}`, progress);
  }

  async progress(): Promise<Record<string, ItemProgress>> {
    const keys = await this.device.kv.keys(PROGRESS_PREFIX);
    const out: Record<string, ItemProgress> = {};
    for (const key of keys) {
      const value = await this.device.kv.get(key);
      if (value !== null) out[key.slice(PROGRESS_PREFIX.length)] = value as ItemProgress;
    }
    return out;
  }

  /** Clearing a finished walk leaves the outbox alone — that syncs on its own. */
  async clear(): Promise<void> {
    await this.device.kv.remove(WALK_KEY);
    for (const key of await this.device.kv.keys(PROGRESS_PREFIX)) {
      await this.device.kv.remove(key);
    }
  }
}

export interface WalkCounts {
  total: number;
  done: number;
  safetyRemaining: number;
}

export function countWalk(walk: Walk, progress: Record<string, ItemProgress>): WalkCounts {
  let total = 0;
  let done = 0;
  let safetyRemaining = 0;
  for (const stop of walk.stops) {
    for (const item of stop.items) {
      total += 1;
      const state = progress[item.checklist_item_id] ?? 'open';
      if (state === 'open') {
        if (item.criticality === 'safety') safetyRemaining += 1;
      } else {
        done += 1;
      }
    }
  }
  return { total, done, safetyRemaining };
}

/**
 * The next thing to do.
 *
 * Safety items first, then whatever comes next at the stop the tech is already
 * standing at. Walking back across a plant room because the list was in upload
 * order is how a guided walk stops feeling guided.
 */
export function nextItem(
  walk: Walk,
  progress: Record<string, ItemProgress>,
  currentAssetId?: string,
): { stop: WalkStop; item: WalkItem } | null {
  const open: { stop: WalkStop; item: WalkItem }[] = [];
  for (const stop of walk.stops) {
    for (const item of stop.items) {
      if ((progress[item.checklist_item_id] ?? 'open') === 'open') open.push({ stop, item });
    }
  }
  if (open.length === 0) return null;

  open.sort((a, b) => {
    const here =
      Number(b.stop.asset_id === currentAssetId) - Number(a.stop.asset_id === currentAssetId);
    if (here !== 0) return here;
    const safety =
      Number(b.item.criticality === 'safety') - Number(a.item.criticality === 'safety');
    return safety;
  });
  return open[0] ?? null;
}
