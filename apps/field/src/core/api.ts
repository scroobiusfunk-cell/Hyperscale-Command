/**
 * The three calls the field app makes, plus the one that carries photographs.
 *
 * Kept as an interface with an HTTP implementation so the sync logic can be
 * tested against a fake that fails on demand. Losing a tech's work to a bad
 * connection is the failure this app exists to avoid, so the failures have to
 * be as easy to test as the successes.
 */

import type { DeclaredState, OutboxEvent, SyncResult, Walk } from './types.ts';

export interface BlobUploadResult {
  storage_key: string;
  byte_size: number;
  content_hash: string;
  first_time: boolean;
  evidence_confirmed: boolean;
}

export interface FieldApi {
  previewWalk(projectId: string, declared: DeclaredState): Promise<Walk>;
  startWalk(projectId: string, declared: DeclaredState): Promise<Walk>;
  uploadBlob(
    clientId: string,
    bytes: Uint8Array,
    contentHash: string,
    mimeType: string,
  ): Promise<BlobUploadResult>;
  sync(events: OutboxEvent[]): Promise<SyncResult>;
}

export class ApiError extends Error {
  readonly status: number;
  readonly body: string;

  constructor(status: number, body: string) {
    super(`The server said ${status}: ${body.slice(0, 300)}`);
    this.name = 'ApiError';
    this.status = status;
    this.body = body;
  }

  /**
   * Whether sending the same thing again could plausibly work.
   *
   * A 422 means the device sent something the server will never accept, and
   * retrying it forever would block every event behind it. Anything else —
   * a timeout, a 500, a gateway error — is worth another go.
   */
  get worthRetrying(): boolean {
    return this.status !== 400 && this.status !== 401 && this.status !== 403 && this.status !== 422;
  }
}

export interface HttpConfig {
  baseUrl: string;
  /** Development identity. Replaced by the SSO token when that lands. */
  devUserId?: string;
  fetchImpl?: typeof fetch;
}

export class HttpFieldApi implements FieldApi {
  private readonly fetch: typeof fetch;
  private readonly config: HttpConfig;

  constructor(config: HttpConfig) {
    this.config = config;
    this.fetch = config.fetchImpl ?? globalThis.fetch;
  }

  private headers(extra: Record<string, string> = {}): Record<string, string> {
    const headers: Record<string, string> = { ...extra };
    if (this.config.devUserId !== undefined) headers['X-Dev-User-Id'] = this.config.devUserId;
    return headers;
  }

  private async json<T>(path: string, body: unknown): Promise<T> {
    const response = await this.fetch(`${this.config.baseUrl}${path}`, {
      method: 'POST',
      headers: this.headers({ 'Content-Type': 'application/json' }),
      body: JSON.stringify(body),
    });
    if (!response.ok) throw new ApiError(response.status, await response.text());
    return (await response.json()) as T;
  }

  previewWalk(projectId: string, declared: DeclaredState): Promise<Walk> {
    return this.json<Walk>(`/field/projects/${projectId}/walk`, declared);
  }

  startWalk(projectId: string, declared: DeclaredState): Promise<Walk> {
    return this.json<Walk>(`/field/projects/${projectId}/walk/start`, declared);
  }

  async uploadBlob(
    clientId: string,
    bytes: Uint8Array,
    contentHash: string,
    mimeType: string,
  ): Promise<BlobUploadResult> {
    const form = new FormData();
    form.append('content_hash', contentHash);
    form.append('file', new Blob([bytes as BlobPart], { type: mimeType }), `${clientId}.jpg`);
    const response = await this.fetch(
      `${this.config.baseUrl}/field/evidence/${clientId}/blob`,
      { method: 'POST', headers: this.headers(), body: form },
    );
    if (!response.ok) throw new ApiError(response.status, await response.text());
    return (await response.json()) as BlobUploadResult;
  }

  sync(events: OutboxEvent[]): Promise<SyncResult> {
    return this.json<SyncResult>('/field/sync', { events });
  }
}
