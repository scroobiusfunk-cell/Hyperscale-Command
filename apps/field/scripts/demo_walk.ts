/**
 * The learner's half of the loop, narrated, for a demonstration.
 *
 * The field app is React Native and wants a phone. Everything underneath the
 * screens is plain TypeScript with no React in it — the walk, the outbox, the
 * gates, the sync — so this drives that same code against a running API and
 * prints what a learner would be doing at each step. Nothing here is a mock: it
 * is the client the app ships, talking to the server the reviewer console talks
 * to.
 *
 *   npm run demo -- walk <project> <learner> [asset]
 *   npm run demo -- feedback <project> <learner>
 *
 * Run `walk`, rule on the item in the console, then run `feedback`.
 */

import { createHash, randomUUID } from 'node:crypto';
import { readFile } from 'node:fs/promises';
import { join } from 'node:path';

import { HttpFieldApi } from '../src/core/api.ts';
import { Outbox } from '../src/core/outbox.ts';
import { MemoryBlobStore, MemoryKeyValueStore } from '../src/core/ports.ts';
import { runSync } from '../src/core/sync.ts';
import type { Device } from '../src/core/ports.ts';
import type { ItemCaptured, PredictionMade } from '../src/core/types.ts';

const BASE = process.env.UNDERSTUDY_API_URL ?? 'http://127.0.0.1:8000';
// Run from apps/field. The photograph the learner "takes" is one of the
// demo illustrations, so the reviewer sees a picture rather than a placeholder.
const ART = join(process.cwd(), '../api/scripts/reference_art');

const [command, project, learner, asset] = process.argv.slice(2);
if (!command || !project || !learner) {
  console.error('usage: demo_walk.ts <walk|feedback> <project-id> <learner-id> [asset-id]');
  process.exit(2);
}

const api = new HttpFieldApi({ baseUrl: BASE, devUserId: learner });

const rule = (s: string) => console.log(`\n\x1b[1m${s}\x1b[0m\n${'─'.repeat(s.length)}`);
const say = (s = '') => console.log(s);

async function walk(): Promise<void> {
  const device: Device = {
    kv: new MemoryKeyValueStore(),
    blobs: new MemoryBlobStore(),
    clock: { now: () => new Date() },
    ids: { uuid: () => randomUUID() },
  };
  const outbox = new Outbox(device);

  rule('1 · The learner downloads the walk before leaving signal');
  const plan = await api.startWalk(project!, {
    ladder_available: true,
    ...(asset ? { asset_ids: [asset] } : {}),
  });
  if (plan.stops.length === 0) {
    say('Nothing open on this project. Re-seed, or pick another asset.');
    process.exit(1);
  }
  for (const stop of plan.stops) {
    say(`${stop.tag} — ${stop.room ?? 'room not recorded'}`);
    for (const item of stop.items) {
      const examples = plan.references[item.item_type] ?? [];
      const right = examples.filter((e) => e.kind === 'good').length;
      const wrong = examples.length - right;
      say(`  · ${item.statement}`);
      say(`      ${item.criticality}  ·  worked examples: ${right} right, ${wrong} wrong`);
    }
  }
  if (plan.deferred.length > 0) {
    say(`\nDeferred, with a reason recorded: ${plan.deferred.length}`);
    for (const d of plan.deferred) say(`  · ${d.asset_tag}: ${d.note}`);
  }

  const stop = plan.stops[0]!;
  const item = stop.items[0]!;
  const examples = plan.references[item.item_type] ?? [];

  rule('2 · At the equipment: what good looks like, what wrong looks like');
  say(`${stop.tag} · ${item.statement}`);
  say(`Why it matters: ${item.why_it_matters}`);
  for (const example of examples) {
    const shot = api.referenceImage(example.reference_image_id);
    const response = await fetch(shot.uri, { headers: shot.headers });
    say(`  [${example.kind.padEnd(5)}] ${example.caption}`);
    say(`          image ${response.status === 200 ? 'downloaded' : `UNAVAILABLE (${response.status})`}`);
  }

  rule('3 · The call, before the camera');
  say('The learner commits to a verdict first. This is the record the whole');
  say('teaching measurement rests on — a checklist you photograph measures');
  say('photography, not judgement.');
  const walkId = randomUUID();
  await outbox.append<PredictionMade>(walkId, {
    event_type: 'prediction_made',
    checklist_item_id: item.checklist_item_id,
    verdict: 'pass',
    reason: null,
  });
  say('\n  Jordan calls it:  PASS');

  rule('4 · The photograph, offline');
  const bytes = new Uint8Array(await readFile(join(ART, 'ground_untorqued.png')));
  const clientId = randomUUID();
  await outbox.appendCapture(walkId, bytes, {
    event_type: 'capture_taken',
    checklist_item_id: item.checklist_item_id,
    client_id: clientId,
    capture_recipe_id: item.capture_recipe_id,
    capture_recipe_version: item.recipe_version,
    step_index: 0,
    media_type: 'photo',
    storage_key: `evidence/${clientId}`,
    content_hash: createHash('sha256').update(bytes).digest('hex'),
    mime_type: 'image/png',
  });
  await outbox.append<ItemCaptured>(walkId, {
    event_type: 'item_captured',
    checklist_item_id: item.checklist_item_id,
  });
  const queued = await outbox.counts();
  say(`In the outbox, on the phone: ${queued.events} events, ${queued.blobs} photo.`);
  say('Nothing is deleted from the phone until the server has acknowledged it.');

  rule('5 · Back in signal');
  const report = await runSync(api, outbox, device);
  const left = await outbox.counts();
  say(`Sent: ${report.eventsAcknowledged} events, ${report.blobsUploaded} photo.`);
  say(`Still on the phone: ${left.events} events, ${left.blobs} photos.`);
  say('\nThe item is now in the reviewer queue. Rule on it in the console, then run:');
  say(`  npm run demo -- feedback ${project} ${learner}`);
}

async function feedback(): Promise<void> {
  const mine = await api.myWork(project!);

  rule('6 · The ruling comes back to the person who took the photograph');
  const { tally } = mine;
  say(
    `Ruled: ${tally.ruled}  ·  passed ${tally.passed}  ·  failed ${tally.failed}` +
      `  ·  sent back ${tally.recapture_requested}  ·  still waiting ${tally.awaiting_review}`,
  );
  for (const row of mine.feedback.slice(0, 4)) {
    say('');
    say(`  ${row.asset_tag} · ${row.verdict.toUpperCase()}${row.needs_another_visit ? ' · go back' : ''}`);
    say(`  ${row.statement}`);
    if (row.note) say(`  ${row.reviewer_name}: "${row.note}"`);
    const shot = api.evidenceImage(row.evidence_ids[0]!);
    const response = await fetch(shot.uri, { headers: shot.headers });
    say(`  their own photograph: ${response.status === 200 ? 'opens' : `unavailable (${response.status})`}`);
  }

  rule('7 · Agreement, per kind of check');
  const overall = mine.agreement;
  say(
    `Overall: ${overall.agreed}/${overall.compared} agreed` +
      (overall.rate === null ? '' : ` (${Math.round(overall.rate * 100)}%)`) +
      `  ·  missed ${overall.missed}  ·  over-called ${overall.over_called}` +
      `  ·  unsure ${overall.unsure}`,
  );
  for (const bucket of mine.by_item_type) {
    const rate = bucket.rate === null ? '  —' : `${Math.round(bucket.rate * 100)}%`.padStart(4);
    say(`  ${rate}  ${bucket.item_type.padEnd(18)} ${bucket.agreed}/${bucket.compared} agreed, ${bucket.missed} missed`);
  }
  say('');
  say('This is the number the tool is for. Not how many photographs somebody');
  say('took — whether their judgement is converging on a qualified person\'s.');
}

await (command === 'feedback' ? feedback() : walk());
