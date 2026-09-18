/**
 * Capture gates.
 *
 * The property that matters most: a gate that did not run is never recorded as
 * passed. A reviewer reading `passed` should be able to believe the device
 * actually checked.
 */

import assert from 'node:assert/strict';
import { describe, test } from 'node:test';

import { FRAME_FILL_FLOOR, SHARPNESS_FLOOR, runGate, runGates } from './gates.ts';

describe('sharpness', () => {
  test('a sharp shot passes', () => {
    const { result } = runGate('sharpness_floor', { sharpness: SHARPNESS_FLOOR + 1 });
    assert.equal(result.outcome, 'passed');
  });

  test('a soft shot fails and says what to do', () => {
    const { result, advice } = runGate('sharpness_floor', { sharpness: SHARPNESS_FLOOR - 1 });
    assert.equal(result.outcome, 'failed');
    assert.match(advice ?? '', /again/);
  });

  test('exactly at the floor passes', () => {
    const { result } = runGate('sharpness_floor', { sharpness: SHARPNESS_FLOOR });
    assert.equal(result.outcome, 'passed');
  });

  test('the measurement and the threshold are both recorded', () => {
    const { result } = runGate('sharpness_floor', { sharpness: 42 });
    assert.equal(result.measured_value, 42);
    assert.equal(result.threshold, SHARPNESS_FLOOR);
  });
});

describe('framing', () => {
  test('a full frame passes', () => {
    const { result } = runGate('frame_fill', { frameFill: FRAME_FILL_FLOOR + 0.1 });
    assert.equal(result.outcome, 'passed');
  });

  test('a distant shot fails', () => {
    const { result, advice } = runGate('frame_fill', { frameFill: 0.05 });
    assert.equal(result.outcome, 'failed');
    assert.match(advice ?? '', /closer/);
  });
});

describe('the tech reading it back', () => {
  test('confirming passes', () => {
    assert.equal(runGate('tech_attestation', { attested: true }).result.outcome, 'passed');
  });

  test('saying no fails', () => {
    assert.equal(runGate('tech_attestation', { attested: false }).result.outcome, 'failed');
  });

  test('not having answered is not a pass', () => {
    assert.equal(runGate('tech_attestation', {}).result.outcome, 'skipped');
  });
});

describe('a gate that could not run', () => {
  test('a missing measurement is skipped, never passed', () => {
    assert.equal(runGate('sharpness_floor', {}).result.outcome, 'skipped');
    assert.equal(runGate('frame_fill', {}).result.outcome, 'skipped');
  });

  test('a gate this build does not know is skipped, never passed', () => {
    const { result } = runGate('lidar_plumbness', { sharpness: 900 });
    assert.equal(result.outcome, 'skipped');
  });
});

describe('running a step worth of gates', () => {
  test('all passing gives no advice', () => {
    const verdict = runGates(['sharpness_floor', 'frame_fill'], {
      sharpness: 500,
      frameFill: 0.8,
    });
    assert.equal(verdict.failed.length, 0);
    assert.equal(verdict.advice, null);
  });

  test('every gate is recorded even when one fails', () => {
    const verdict = runGates(['sharpness_floor', 'frame_fill'], { sharpness: 10, frameFill: 0.9 });
    assert.equal(verdict.results.length, 2);
    assert.equal(verdict.failed.length, 1);
    assert.equal(verdict.failed[0]!.gate_id, 'sharpness_floor');
  });

  test('the advice shown is for the first thing that went wrong', () => {
    const verdict = runGates(['sharpness_floor', 'frame_fill'], { sharpness: 10, frameFill: 0.01 });
    assert.match(verdict.advice ?? '', /blurry/);
  });
});
