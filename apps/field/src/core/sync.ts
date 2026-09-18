/**
 * Getting a walk off the phone.
 *
 * Order matters and is not the obvious one. The event log goes first, then the
 * photographs:
 *
 * - The log is a few kilobytes and the photographs are megabytes. Sending the
 *   log first means that thirty seconds of signal in a stairwell records what
 *   the tech did, even if no photograph gets through.
 * - The server creates each evidence row as `pending_upload` and promotes it
 *   when the bytes land, in either order, so nothing is waiting on the photos.
 *
 * Every step is safe to repeat. Events carry a `client_event_id` the server
 * deduplicates on; a blob upload is keyed by its capture's client id and the
 * second one is a no-op. So the recovery for almost any failure is to run this
 * again, and that is what the app does.
 */

import type { FieldApi } from './api.ts';
import { ApiError } from './api.ts';
import type { Outbox } from './outbox.ts';
import type { Device } from './ports.ts';
import type { SyncResult } from './types.ts';

/** How many events go in one request. Small enough to get through a bad link. */
export const EVENT_BATCH = 50;

export interface SyncReport {
  eventsSent: number;
  eventsAcknowledged: number;
  blobsUploaded: number;
  blobsRemaining: number;
  eventsRemaining: number;
  /** Reviewer decisions that landed while the tech was offline. */
  changed: { checklist_item_id: string; message: string }[];
  /** Populated when the run stopped early. The outbox is intact. */
  stoppedBecause: string | null;
  /** True when a capture's bytes were dropped as unsendable. */
  droppedBlobs: string[];
}

export async function runSync(
  api: FieldApi,
  outbox: Outbox,
  device: Device,
): Promise<SyncReport> {
  const report: SyncReport = {
    eventsSent: 0,
    eventsAcknowledged: 0,
    blobsUploaded: 0,
    blobsRemaining: 0,
    eventsRemaining: 0,
    changed: [],
    stoppedBecause: null,
    droppedBlobs: [],
  };

  const queued = await outbox.pendingEvents();
  for (let i = 0; i < queued.length; i += EVENT_BATCH) {
    const batch = queued.slice(i, i + EVENT_BATCH);
    let result: SyncResult;
    try {
      result = await api.sync(batch.map((q) => q.event));
    } catch (error) {
      report.stoppedBecause = describe(error);
      break;
    }
    report.eventsSent += batch.length;
    // Only now. A crash before this line means the batch is sent again, and
    // the server throws the duplicate away.
    await outbox.acknowledgeEvents(batch.map((q) => q.key));
    report.eventsAcknowledged += batch.length;
    report.changed.push(...result.changed_while_you_were_away);
  }

  // Photographs, one at a time, smallest first so a thin connection clears the
  // backlog rather than stalling on one large shot.
  if (report.stoppedBecause === null) {
    const blobs = (await outbox.pendingBlobs()).sort((a, b) => a.byte_size - b.byte_size);
    for (const blob of blobs) {
      const bytes = await device.blobs.read(blob.client_id);
      if (bytes === null) {
        // The event describing this capture is already with the server, which
        // will hold the row at `pending_upload`. Nothing here can fix that, so
        // stop carrying a queue entry that can never succeed.
        await outbox.acknowledgeBlob(blob.client_id);
        report.droppedBlobs.push(blob.client_id);
        continue;
      }
      try {
        await api.uploadBlob(blob.client_id, bytes, blob.content_hash, blob.mime_type);
      } catch (error) {
        if (error instanceof ApiError && !error.worthRetrying) {
          // The server will never take these bytes. Keeping them would block
          // every photograph behind them on every future sync.
          await outbox.acknowledgeBlob(blob.client_id);
          report.droppedBlobs.push(blob.client_id);
          continue;
        }
        report.stoppedBecause = describe(error);
        break;
      }
      await outbox.acknowledgeBlob(blob.client_id);
      report.blobsUploaded += 1;
    }
  }

  const counts = await outbox.counts();
  report.eventsRemaining = counts.events;
  report.blobsRemaining = counts.blobs;
  return report;
}

function describe(error: unknown): string {
  if (error instanceof ApiError) return error.message;
  if (error instanceof Error) return error.message;
  return String(error);
}
