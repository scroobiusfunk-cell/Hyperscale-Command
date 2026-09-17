/**
 * Compiles every schema and runs the example records against them.
 *
 * Valid examples must pass. Invalid examples must fail, and must fail for the
 * stated reason: each carries `_expect`, a fragment that has to appear in the
 * validation error. Without that check a negative test passes for any reason at
 * all, including a typo, which is worse than having no negative test.
 */
import { readFileSync, readdirSync } from 'node:fs';
import { basename, join } from 'node:path';

import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const SCHEMA_DIR = 'schemas';
const BASE_URI = 'https://schemas.fieldinspectionengine.dev/';

const readJson = (path) => JSON.parse(readFileSync(path, 'utf8'));

const ajv = new Ajv2020({ allErrors: true, strict: true, allowUnionTypes: true });
addFormats(ajv);

const schemaFiles = [
  ...readdirSync(join(SCHEMA_DIR, 'common')).map((f) => join(SCHEMA_DIR, 'common', f)),
  ...readdirSync(SCHEMA_DIR)
    .filter((f) => f.endsWith('.schema.json'))
    .map((f) => join(SCHEMA_DIR, f)),
];

for (const file of schemaFiles) ajv.addSchema(readJson(file));

const validatorFor = (exampleFile) => {
  const name = basename(exampleFile).split('.')[0];
  const uri = `${BASE_URI}${name}.schema.json`;
  const validate = ajv.getSchema(uri);
  if (!validate) throw new Error(`No schema at ${uri} for example ${exampleFile}`);
  return validate;
};

/** Strip the underscore-prefixed annotations so examples fail for the real reason. */
const stripAnnotations = (record) =>
  Object.fromEntries(Object.entries(record).filter(([k]) => !k.startsWith('_')));

/**
 * Error text that names the offending property. ajv's own errorsText drops
 * `params`, so an additionalProperties failure reads "must NOT have additional
 * properties" without saying which one — useless for asserting a negative test
 * failed for the right reason.
 */
const describe = (errors) =>
  (errors ?? [])
    .map((e) => {
      const where = e.instancePath || '/';
      const params = Object.values(e.params ?? {}).filter((v) => typeof v === 'string');
      return `${where} ${e.message}${params.length ? ` (${params.join(', ')})` : ''}`;
    })
    .join('; ');

let failures = 0;
const report = (ok, label, detail) => {
  if (!ok) failures += 1;
  console.log(`${ok ? '  ok  ' : ' FAIL '} ${label}${detail ? ` — ${detail}` : ''}`);
};

console.log(`\nCompiled ${schemaFiles.length} schemas\n\nValid examples (must pass):`);
for (const file of readdirSync('examples/valid').sort()) {
  const path = join('examples/valid', file);
  const validate = validatorFor(path);
  const ok = validate(stripAnnotations(readJson(path)));
  report(ok, file, ok ? '' : describe(validate.errors));
}

console.log('\nInvalid examples (must be rejected, for the stated reason):');
for (const file of readdirSync('examples/invalid').sort()) {
  const path = join('examples/invalid', file);
  const raw = readJson(path);
  const expected = raw._expect;
  if (!expected) {
    report(false, file, 'missing _expect annotation');
    continue;
  }
  const validate = validatorFor(path);
  const passed = validate(stripAnnotations(raw));
  if (passed) {
    report(false, file, 'was accepted but should have been rejected');
    continue;
  }
  const errorText = describe(validate.errors);
  const matched = errorText.includes(expected);
  report(matched, file, matched ? `rejected on ${expected}` : `rejected, but not on "${expected}": ${errorText}`);
}

console.log(failures === 0 ? '\nAll schema checks passed.\n' : `\n${failures} check(s) failed.\n`);
process.exit(failures === 0 ? 0 : 1);
