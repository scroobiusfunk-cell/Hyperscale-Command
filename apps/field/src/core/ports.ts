/**
 * What the core needs from a device, stated as interfaces.
 *
 * The offline logic is the part of this app that can be wrong in ways nobody
 * notices until evidence is missing, so it is written as plain TypeScript with
 * no React Native imports and runs under `node --test`. SQLite, the filesystem
 * and the camera are supplied through these ports; the tests supply fakes.
 */

/** Small durable key/value. `expo-sqlite` on device, a Map in tests. */
export interface KeyValueStore {
  get(key: string): Promise<string | null>;
  set(key: string, value: string): Promise<void>;
  remove(key: string): Promise<void>;
  keys(prefix: string): Promise<string[]>;
}

/** Photograph bytes. `expo-file-system` on device, a Map in tests. */
export interface BlobStore {
  write(id: string, bytes: Uint8Array): Promise<void>;
  read(id: string): Promise<Uint8Array | null>;
  remove(id: string): Promise<void>;
}

export interface Clock {
  now(): Date;
}

export interface Ids {
  uuid(): string;
}

/** Everything the core needs, in one bag. */
export interface Device {
  kv: KeyValueStore;
  blobs: BlobStore;
  clock: Clock;
  ids: Ids;
}

export class MemoryKeyValueStore implements KeyValueStore {
  private readonly map = new Map<string, string>();

  async get(key: string): Promise<string | null> {
    return this.map.get(key) ?? null;
  }

  async set(key: string, value: string): Promise<void> {
    this.map.set(key, value);
  }

  async remove(key: string): Promise<void> {
    this.map.delete(key);
  }

  async keys(prefix: string): Promise<string[]> {
    return [...this.map.keys()].filter((k) => k.startsWith(prefix)).sort();
  }
}

export class MemoryBlobStore implements BlobStore {
  private readonly map = new Map<string, Uint8Array>();

  async write(id: string, bytes: Uint8Array): Promise<void> {
    this.map.set(id, bytes);
  }

  async read(id: string): Promise<Uint8Array | null> {
    return this.map.get(id) ?? null;
  }

  async remove(id: string): Promise<void> {
    this.map.delete(id);
  }

  get size(): number {
    return this.map.size;
  }
}
