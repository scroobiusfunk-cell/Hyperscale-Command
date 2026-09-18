/**
 * The device's event log, and the photographs waiting to go with it.
 *
 * This is the client half of event replay. The rule it exists to keep:
 *
 *   Nothing leaves the outbox until the server has said it has it.
 *
 * A tech who walks a plant room with no signal has an hour of work sitting on
 * a phone. Every way that work can be lost runs through this file, so the
 * ordering is deliberate:
 *
 * - An event is written to durable storage *before* the UI moves on, never
 *   after. A crash between the tap and the write loses one tap; a crash
 *   between the write and the send loses nothing.
 * - Each event carries a `client_event_id` generated here and never changed.
 *   Re-sending after a timeout is the normal case on a bad connection, and the
 *   server discards the duplicate by that id.
 * - `sequence` is monotonic per walk, so the server applies a tech's actions in
 *   the order they happened rather than the order the packets arrived.
 * - Acknowledged events are removed only after the server confirms. A sync that
 *   fails halfway leaves the outbox exactly as it was.
 */

import type { Device } from './ports.ts';
import type { CaptureTaken, OutboxEvent, PendingBlob } from './types.ts';

const EVENT_PREFIX = 'outbox:event:';
const BLOB_PREFIX = 'outbox:blob:';
const SEQUENCE_KEY = 'outbox:sequence:';

/** Zero-padded so a lexical key sort is also a numeric sort. */
function eventKey(walkId: string, sequence: number): string {
  return `${EVENT_PREFIX}${walkId}:${String(sequence).padStart(9, '0')}`;
}

export interface QueuedEvent {
  key: string;
  event: OutboxEvent;
}

export class Outbox {
  private readonly device: Device;

  constructor(device: Device) {
    this.device = device;
  }

  /** The next sequence number for this walk, reserved durably before use. */
  private async nextSequence(walkId: string): Promise<number> {
    const key = `${SEQUENCE_KEY}${walkId}`;
    const current = await this.device.kv.get(key);
    const next = current === null ? 0 : Number.parseInt(current, 10) + 1;
    await this.device.kv.set(key, String(next));
    return next;
  }

  /**
   * Append one event.
   *
   * The caller supplies everything except the fields that make the event
   * addressable — id, sequence and timestamp are assigned here so that no
   * screen can forget one.
   */
  async append<E extends OutboxEvent>(
    walkId: string,
    event: Omit<E, 'client_event_id' | 'client_walk_id' | 'sequence' | 'occurred_at'>,
  ): Promise<E> {
    const sequence = await this.nextSequence(walkId);
    const full = {
      ...event,
      client_event_id: this.device.ids.uuid(),
      client_walk_id: walkId,
      sequence,
      occurred_at: this.device.clock.now().toISOString(),
    } as E;
    await this.device.kv.set(eventKey(walkId, sequence), JSON.stringify(full));
    return full;
  }

  /**
   * Record a capture: the bytes, and the event that describes them.
   *
   * The bytes are written first. An event describing a photograph the device
   * cannot produce would sync, create a `pending_upload` row, and never resolve.
   */
  async appendCapture(
    walkId: string,
    bytes: Uint8Array,
    event: Omit<
      CaptureTaken,
      'client_event_id' | 'client_walk_id' | 'sequence' | 'occurred_at' | 'byte_size'
    >,
  ): Promise<CaptureTaken> {
    await this.device.blobs.write(event.client_id, bytes);
    await this.device.kv.set(
      `${BLOB_PREFIX}${event.client_id}`,
      JSON.stringify({
        client_id: event.client_id,
        content_hash: event.content_hash,
        byte_size: bytes.byteLength,
        mime_type: event.mime_type,
      } satisfies PendingBlob),
    );
    return this.append<CaptureTaken>(walkId, { ...event, byte_size: bytes.byteLength });
  }

  /** Everything waiting to go, oldest first. */
  async pendingEvents(walkId?: string): Promise<QueuedEvent[]> {
    const prefix = walkId === undefined ? EVENT_PREFIX : `${EVENT_PREFIX}${walkId}:`;
    const keys = await this.device.kv.keys(prefix);
    const out: QueuedEvent[] = [];
    for (const key of keys) {
      const raw = await this.device.kv.get(key);
      if (raw === null) continue;
      out.push({ key, event: JSON.parse(raw) as OutboxEvent });
    }
    // Keys sort lexically within a walk; across walks, sort by when it happened.
    return out.sort((a, b) => a.event.occurred_at.localeCompare(b.event.occurred_at));
  }

  async pendingBlobs(): Promise<PendingBlob[]> {
    const keys = await this.device.kv.keys(BLOB_PREFIX);
    const out: PendingBlob[] = [];
    for (const key of keys) {
      const raw = await this.device.kv.get(key);
      if (raw === null) continue;
      out.push(JSON.parse(raw) as PendingBlob);
    }
    return out;
  }

  /** Called only once the server has acknowledged these events. */
  async acknowledgeEvents(keys: string[]): Promise<void> {
    for (const key of keys) await this.device.kv.remove(key);
  }

  /**
   * Called once the bytes are up.
   *
   * The local copy goes too. Keeping it would fill a phone over a week of
   * walks, and the server has the only copy that matters from here on.
   */
  async acknowledgeBlob(clientId: string): Promise<void> {
    await this.device.kv.remove(`${BLOB_PREFIX}${clientId}`);
    await this.device.blobs.remove(clientId);
  }

  async counts(): Promise<{ events: number; blobs: number }> {
    return {
      events: (await this.device.kv.keys(EVENT_PREFIX)).length,
      blobs: (await this.device.kv.keys(BLOB_PREFIX)).length,
    };
  }
}
