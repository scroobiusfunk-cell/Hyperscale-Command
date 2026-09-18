/**
 * The field app's copies of shared enums, against the schemas themselves.
 *
 * `packages/schemas` is the contract between the API, this app and the reviewer
 * console. This app hand-writes the small part of it the walk payload carries,
 * and a hand-written copy is only wrong at the moment somebody sends a value
 * across — which for a deferral reason is the day a tech cannot get into the
 * room, and for `Criticality` was never, because nothing sent it back.
 *
 * Both had drifted. `Criticality` said `performance | documentation` where the
 * schema says `contractual | quality`, and the Capture screen deferred with
 * `access_blocked` where the schema says `no_access`. This is the test that
 * would have caught them, and now does.
 *
 * Run from `apps/field`, which is where `npm test` runs from.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import test from 'node:test';
import assert from 'node:assert/strict';

import { BLOCKED_REASONS, CRITICALITIES, MEDIA_TYPES } from './types.ts';

const SCHEMAS = join(process.cwd(), '../../packages/schemas/schemas');

/** The enum at a path inside a schema file. A moved definition fails loudly. */
function enumAt(document: string, ...path: (string | number)[]): string[] {
  let node: unknown = JSON.parse(readFileSync(join(SCHEMAS, document), 'utf8'));
  for (const step of path) {
    assert.ok(
      node !== null && typeof node === 'object',
      `${document}: nothing at ${path.join('/')}`,
    );
    node = (node as Record<string | number, unknown>)[step];
  }
  assert.ok(
    node !== null && typeof node === 'object' && Array.isArray((node as { enum?: unknown }).enum),
    `${document}: no enum at ${path.join('/')}`,
  );
  return (node as { enum: string[] }).enum;
}

const drift = (what: string) =>
  `${what} has drifted between packages/schemas and apps/field. Change both in the ` +
  `same commit, or the app sends the server a value it refuses.`;

test('the schemas are where this test thinks they are', () => {
  assert.doesNotThrow(() => enumAt('common/definitions.schema.json', '$defs', 'criticality'));
});

test('Criticality matches the schema', () => {
  assert.deepEqual(
    [...CRITICALITIES].sort(),
    enumAt('common/definitions.schema.json', '$defs', 'criticality').sort(),
    drift('Criticality'),
  );
});

test('BlockedReason matches the schema', () => {
  assert.deepEqual(
    [...BLOCKED_REASONS].sort(),
    enumAt('checklist-item.schema.json', 'properties', 'blocked_reason', 'oneOf', 0).sort(),
    drift('BlockedReason'),
  );
});

test('MediaType matches the schema', () => {
  assert.deepEqual(
    [...MEDIA_TYPES].sort(),
    enumAt('evidence.schema.json', 'properties', 'media_type').sort(),
    drift('MediaType'),
  );
});
