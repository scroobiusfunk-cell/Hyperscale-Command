/**
 * The shapes the API hands the device, and the ones the device hands back.
 *
 * These mirror `apps/api/app/api/routes/field.py`. They are hand-written rather
 * than generated because the field app consumes three endpoints; the shared JSON
 * Schema contracts in `packages/schemas` cover the records that cross all three
 * apps, and these are the wire shapes of one of them.
 */

/** Closed by design, and identical to `packages/schemas` and the API's `Criticality`. */
export type Criticality = 'safety' | 'contractual' | 'quality';

/** The reasons a deferral may carry, verbatim from the API's `BlockedReason`. */
export type BlockedReason =
  | 'no_access'
  | 'energized'
  | 'not_installed_yet'
  | 'equipment_missing'
  | 'tool_unavailable'
  | 'other';

/** Verbatim from the API's `MediaType`. */
export type MediaType = 'photo' | 'video' | 'document' | 'measurement';

export type GateId = 'sharpness_floor' | 'frame_fill' | 'tech_attestation';

export interface WalkStep {
  instruction: string;
  framing_rule: string;
  gate_check: string;
}

export interface WalkItem {
  checklist_item_id: string;
  statement: string;
  why_it_matters: string;
  criticality: Criticality;
  /** The grouping worked examples and agreement are keyed on. */
  item_type: string;
  /** Named on every capture event, so the walk has to carry it. */
  capture_recipe_id: string;
  recipe_slug: string;
  recipe_version: string;
  reference_media_slot: string | null;
  disqualifiers: string[];
  scaffold_level: string;
  steps: WalkStep[];
}

export interface WalkStop {
  asset_id: string;
  tag: string;
  room: string | null;
  grid_ref: string | null;
  items: WalkItem[];
}

export interface Deferred {
  checklist_item_id: string;
  asset_tag: string;
  reason: BlockedReason;
  note: string;
}

export type ReferenceKind = 'good' | 'wrong';

/** A worked example: what a correct install looks like, or a near-miss. */
export interface ReferenceImage {
  reference_image_id: string;
  kind: ReferenceKind;
  caption: string;
  mime_type: string;
}

export interface Walk {
  stops: WalkStop[];
  deferred: Deferred[];
  unroutable: Deferred[];
  item_count: number;
  /** Keyed by item_type. Downloaded with the walk so they work offline. */
  references: Record<string, ReferenceImage[]>;
}

export type PredictedVerdict = 'pass' | 'fail' | 'unsure';

export interface DeclaredState {
  open_rooms?: string[] | null;
  energized_rooms?: string[];
  ladder_available?: boolean;
  confined_space_permit?: boolean;
  room?: string | null;
  asset_ids?: string[];
}

/** What the device recorded about one gate, as it rides along on a capture. */
export interface GateResult {
  gate_id: string;
  outcome: 'passed' | 'failed' | 'skipped';
  measured_value?: number | string | boolean | null;
  threshold?: number | string | boolean | null;
}

export type EventType =
  | 'item_opened'
  | 'prediction_made'
  | 'capture_taken'
  | 'gate_failed'
  | 'item_captured'
  | 'item_deferred'
  | 'walk_completed';

interface EventBase {
  client_event_id: string;
  client_walk_id: string;
  sequence: number;
  occurred_at: string;
  checklist_item_id?: string | null;
}

export interface ItemOpened extends EventBase {
  event_type: 'item_opened';
  checklist_item_id: string;
}

export interface PredictionMade extends EventBase {
  event_type: 'prediction_made';
  checklist_item_id: string;
  verdict: PredictedVerdict;
  /** Which disqualifier they believe they saw, from the item's own list. */
  reason?: string | null;
  note?: string | null;
}

export interface CaptureTaken extends EventBase {
  event_type: 'capture_taken';
  checklist_item_id: string;
  /** The capture's own id, separate from the event's. It names the bytes. */
  client_id: string;
  capture_recipe_id: string;
  capture_recipe_version: string;
  step_index: number;
  media_type: MediaType;
  /**
   * What the device believes the key is. The server derives its own from
   * `client_id` and ignores this; it is sent only so a device log and a server
   * log can be read side by side.
   */
  storage_key: string;
  content_hash: string;
  byte_size: number;
  mime_type: string;
  device_metadata?: { model?: string; os_version?: string; app_version?: string };
  gate_results?: GateResult[];
  retake_of_client_id?: string | null;
}

export interface GateFailed extends EventBase {
  event_type: 'gate_failed';
  checklist_item_id: string;
  capture_recipe_id: string;
  step_index: number;
  gate_results: GateResult[];
}

export interface ItemCaptured extends EventBase {
  event_type: 'item_captured';
  checklist_item_id: string;
}

export interface ItemDeferred extends EventBase {
  event_type: 'item_deferred';
  checklist_item_id: string;
  reason: BlockedReason;
  note?: string | null;
}

export interface WalkCompleted extends EventBase {
  event_type: 'walk_completed';
  items_attempted: number;
}

export type OutboxEvent =
  | ItemOpened
  | PredictionMade
  | CaptureTaken
  | GateFailed
  | ItemCaptured
  | ItemDeferred
  | WalkCompleted;

/** A photograph waiting to go up. The bytes live in the device's blob store. */
export interface PendingBlob {
  client_id: string;
  content_hash: string;
  byte_size: number;
  mime_type: string;
}

export interface SyncResult {
  accepted: number;
  duplicates: number;
  applied: number;
  superseded: number;
  rejected: number;
  evidence_created: number;
  changed_while_you_were_away: { checklist_item_id: string; message: string }[];
}

/** One ruling on something this tech captured. The teaching loop's return leg. */
export interface Feedback {
  checklist_item_id: string;
  asset_tag: string;
  room: string | null;
  statement: string;
  why_it_matters: string;
  criticality: Criticality;
  verdict: 'pass' | 'fail' | 'recapture_requested';
  note: string | null;
  reviewer_name: string;
  ruled_at: string;
  needs_another_visit: boolean;
  is_correction: boolean;
  evidence_ids: string[];
}

/** A count of outcomes. Not a score — nothing is gated on it. */
export interface Agreement {
  item_type: string;
  compared: number;
  agreed: number;
  unsure: number;
  /** Called a real defect correctly. */
  caught: number;
  /** Called a defect fine. The dangerous direction. */
  missed: number;
  over_called: number;
  /** Null when nothing is comparable yet — not the same fact as zero. */
  rate: number | null;
}

export interface Tally {
  ruled: number;
  passed: number;
  failed: number;
  recapture_requested: number;
  awaiting_review: number;
}

export interface MyWork {
  tally: Tally;
  agreement: Agreement;
  by_item_type: Agreement[];
  feedback: Feedback[];
}
