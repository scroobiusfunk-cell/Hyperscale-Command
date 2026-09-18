/**
 * The real device behind the core's ports.
 *
 * SQLite for the event log because it survives the app being killed, which a
 * phone in a pocket on a cold morning does often. The filesystem for the
 * photographs because they are far too big for a key/value row.
 */

import * as Crypto from 'expo-crypto';
import * as FileSystem from 'expo-file-system';
import * as SQLite from 'expo-sqlite';

import type { BlobStore, Device, KeyValueStore } from './core/ports.ts';

const BLOB_DIR = `${FileSystem.documentDirectory ?? ''}evidence/`;

class SqliteKeyValueStore implements KeyValueStore {
  private readonly db: SQLite.SQLiteDatabase;

  constructor(db: SQLite.SQLiteDatabase) {
    this.db = db;
  }

  static async open(): Promise<SqliteKeyValueStore> {
    const db = await SQLite.openDatabaseAsync('fie-field.db');
    await db.execAsync(
      'CREATE TABLE IF NOT EXISTS kv (key TEXT PRIMARY KEY NOT NULL, value TEXT NOT NULL)',
    );
    return new SqliteKeyValueStore(db);
  }

  async get(key: string): Promise<string | null> {
    const row = await this.db.getFirstAsync<{ value: string }>(
      'SELECT value FROM kv WHERE key = ?',
      key,
    );
    return row?.value ?? null;
  }

  async set(key: string, value: string): Promise<void> {
    await this.db.runAsync(
      'INSERT INTO kv (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value',
      key,
      value,
    );
  }

  async remove(key: string): Promise<void> {
    await this.db.runAsync('DELETE FROM kv WHERE key = ?', key);
  }

  async keys(prefix: string): Promise<string[]> {
    const rows = await this.db.getAllAsync<{ key: string }>(
      'SELECT key FROM kv WHERE key LIKE ? ORDER BY key',
      `${prefix}%`,
    );
    return rows.map((r) => r.key);
  }
}

class FileBlobStore implements BlobStore {
  private async ensureDir(): Promise<void> {
    const info = await FileSystem.getInfoAsync(BLOB_DIR);
    if (!info.exists) await FileSystem.makeDirectoryAsync(BLOB_DIR, { intermediates: true });
  }

  private path(id: string): string {
    return `${BLOB_DIR}${id}`;
  }

  async write(id: string, bytes: Uint8Array): Promise<void> {
    await this.ensureDir();
    await FileSystem.writeAsStringAsync(this.path(id), toBase64(bytes), {
      encoding: FileSystem.EncodingType.Base64,
    });
  }

  async read(id: string): Promise<Uint8Array | null> {
    const info = await FileSystem.getInfoAsync(this.path(id));
    if (!info.exists) return null;
    const base64 = await FileSystem.readAsStringAsync(this.path(id), {
      encoding: FileSystem.EncodingType.Base64,
    });
    return fromBase64(base64);
  }

  async remove(id: string): Promise<void> {
    await FileSystem.deleteAsync(this.path(id), { idempotent: true });
  }
}

export function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return globalThis.btoa(binary);
}

export function fromBase64(base64: string): Uint8Array {
  const binary = globalThis.atob(base64);
  const out = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i += 1) out[i] = binary.charCodeAt(i);
  return out;
}

/**
 * The hash the server checks the upload against.
 *
 * Over the raw bytes, not over a base64 rendering of them — the server hashes
 * what it receives, so anything else here would reject every photograph.
 */
export async function sha256(bytes: Uint8Array): Promise<string> {
  const digest = await Crypto.digest(
    Crypto.CryptoDigestAlgorithm.SHA256,
    bytes as unknown as ArrayBufferView<ArrayBuffer>,
  );
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, '0')).join('');
}

export async function openDevice(): Promise<Device> {
  return {
    kv: await SqliteKeyValueStore.open(),
    blobs: new FileBlobStore(),
    clock: { now: () => new Date() },
    ids: { uuid: () => Crypto.randomUUID() },
  };
}
