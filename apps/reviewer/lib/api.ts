/**
 * Talking to the API.
 *
 * Every call goes through the server side, never the browser. The reviewer's
 * identity is attached here and the API's address is never exposed to the page:
 * a console that put its credentials in the client would be a console where
 * "who ruled on this" is a suggestion.
 */

export const API_URL = process.env.UNDERSTUDY_API_URL ?? 'http://127.0.0.1:8000';
export const PROJECT_ID = process.env.UNDERSTUDY_PROJECT_ID ?? '';
const DEV_USER_ID = process.env.UNDERSTUDY_DEV_USER_ID ?? '';

export type Criticality = 'safety' | 'contractual' | 'quality';
export type Verdict = 'pass' | 'fail' | 'recapture_requested';

export interface QueueEntry {
  checklist_item_id: string;
  asset_tag: string;
  room: string | null;
  statement: string;
  criticality: Criticality;
  evidence_count: number;
  captured_at: string | null;
  is_recapture: boolean;
}

export interface EvidenceRef {
  evidence_id: string;
  step_index: number;
  captured_at: string;
  mime_type: string;
  gate_results: { gate_id: string; outcome: string; measured_value?: unknown }[];
  is_retake: boolean;
}

export interface RulingRecord {
  id: string;
  verdict: Verdict;
  note: string | null;
  reviewer_id: string;
  created_at: string;
  supersedes: string | null;
}

export interface ItemDetail {
  checklist_item_id: string;
  asset_tag: string;
  asset_cxalloy_id: string | null;
  room: string | null;
  equipment_class: string;
  statement: string;
  why_it_matters: string;
  criticality: Criticality;
  pass_criteria: Record<string, unknown>;
  source_clause: string;
  source_page: number;
  ruleset_version: string;
  state: string;
  evidence: EvidenceRef[];
  history: RulingRecord[];
}

export interface ReviewerStats {
  reviewer_id: string;
  display_name: string;
  rulings: number;
  passes: number;
  fails: number;
  recaptures: number;
  notes_on_passes: number;
  labeling_rate: number;
}

export interface Dashboard {
  awaiting_review: number;
  safety_awaiting_review: number;
  undelivered: number;
  undelivered_failures: number;
  unresolved_assets: number;
  reviewers: ReviewerStats[];
}

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    cache: 'no-store',
    headers: {
      'Content-Type': 'application/json',
      ...(DEV_USER_ID ? { 'X-Dev-User-Id': DEV_USER_ID } : {}),
      ...(init?.headers ?? {}),
    },
  });

  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body?.detail === 'string') detail = body.detail;
    } catch {
      /* the body was not JSON; the status line will have to do */
    }
    throw new ApiError(detail, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const getQueue = (projectId: string) =>
  apiFetch<QueueEntry[]>(`/review/projects/${projectId}/queue`);

export const getItem = (itemId: string) =>
  apiFetch<ItemDetail>(`/review/items/${itemId}`);

export const getDashboard = (projectId: string) =>
  apiFetch<Dashboard>(`/review/projects/${projectId}/dashboard`);

export const getDeliveryStatus = (projectId: string) =>
  apiFetch<{
    pending_export: number;
    exported_not_confirmed: number;
    undelivered: number;
    undelivered_failures: number;
  }>(`/projects/${projectId}/delivery-status`);
