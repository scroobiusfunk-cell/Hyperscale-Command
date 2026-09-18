/**
 * Capture gates: the checks the device runs on a photograph before accepting it.
 *
 * A gate is about the photograph, never about the equipment. "Is this sharp
 * enough to read" is a gate; "is the filler plate fitted" is a requirement, and
 * in Phase 1 only a person answers that. Nothing here produces or influences a
 * verdict — a gate result rides along on the capture so the reviewer can see
 * that the tech was warned the shot was soft.
 *
 * A failed gate asks for a retake. It does not refuse the capture: a tech
 * standing in front of a live board at the top of a ladder may have got the
 * best shot that exists, and a tool that will not let them move on is a tool
 * they stop using. The failure is recorded either way.
 *
 * Thresholds live here as named constants rather than being read from
 * calibration data, and that is allowed: the auto-clear rule in CLAUDE.md is
 * about thresholds that decide whether a requirement passes. These decide
 * whether to suggest taking the photograph again.
 */

import type { GateResult } from './types.ts';

/**
 * Variance of the Laplacian, the usual cheap blur metric. Below this a label is
 * typically not legible in a 12MP phone photograph held at arm's length.
 */
export const SHARPNESS_FLOOR = 100;

/** The subject should occupy at least this share of the frame. */
export const FRAME_FILL_FLOOR = 0.25;

/** What the camera layer measured about one shot. */
export interface Measurement {
  /** Variance of the Laplacian, if the device could compute it. */
  sharpness?: number;
  /** Subject area as a fraction of frame area, 0 to 1. */
  frameFill?: number;
  /** Whether the tech confirmed they can read the label back. */
  attested?: boolean;
}

export interface GateOutcome {
  result: GateResult;
  /** Shown to the tech when the gate fails. Plain language, no jargon. */
  advice: string | null;
}

/**
 * Run one gate.
 *
 * An unknown gate id, or a measurement the device could not take, is `skipped`
 * rather than `passed`. Recording a gate as passed when it never ran would tell
 * a reviewer the shot was checked when it was not.
 */
export function runGate(gateId: string, measured: Measurement): GateOutcome {
  switch (gateId) {
    case 'sharpness_floor': {
      if (measured.sharpness === undefined) return skipped(gateId, 'No sharpness reading.');
      const passed = measured.sharpness >= SHARPNESS_FLOOR;
      return {
        result: {
          gate_id: gateId,
          outcome: passed ? 'passed' : 'failed',
          measured_value: measured.sharpness,
          threshold: SHARPNESS_FLOOR,
        },
        advice: passed ? null : 'That one came out blurry. Hold still and take it again.',
      };
    }
    case 'frame_fill': {
      if (measured.frameFill === undefined) return skipped(gateId, 'No framing reading.');
      const passed = measured.frameFill >= FRAME_FILL_FLOOR;
      return {
        result: {
          gate_id: gateId,
          outcome: passed ? 'passed' : 'failed',
          measured_value: measured.frameFill,
          threshold: FRAME_FILL_FLOOR,
        },
        advice: passed ? null : 'Get closer, or fill more of the frame with it.',
      };
    }
    case 'tech_attestation': {
      if (measured.attested === undefined) return skipped(gateId, 'Not answered yet.');
      return {
        result: {
          gate_id: gateId,
          outcome: measured.attested ? 'passed' : 'failed',
          measured_value: measured.attested,
          threshold: true,
        },
        advice: measured.attested ? null : 'Take it again so every line can be read.',
      };
    }
    default:
      return skipped(gateId, `This device does not know the ${gateId} check.`);
  }
}

function skipped(gateId: string, why: string): GateOutcome {
  return {
    result: { gate_id: gateId, outcome: 'skipped', measured_value: null, threshold: null },
    advice: why,
  };
}

export interface GateVerdict {
  results: GateResult[];
  failed: GateResult[];
  /** The first piece of advice worth showing, or null when all is well. */
  advice: string | null;
}

/** Run every gate a step asks for. */
export function runGates(gateIds: string[], measured: Measurement): GateVerdict {
  const outcomes = gateIds.map((id) => runGate(id, measured));
  const failedOutcomes = outcomes.filter((o) => o.result.outcome === 'failed');
  return {
    results: outcomes.map((o) => o.result),
    failed: failedOutcomes.map((o) => o.result),
    advice: failedOutcomes[0]?.advice ?? null,
  };
}
