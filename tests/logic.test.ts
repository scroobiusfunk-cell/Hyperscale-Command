import { describe, expect, it } from 'vitest';
import {
  C, buildCompletionCsv, coreDoneCount, filterEquipment, filterGlossary, firstOpenIndex, isCertified,
  isModuleOpen, passMark, scoreExam, siteMissing,
} from '../src/lib/logic';

describe('module unlocking', () => {
  it('opens only the first core module initially, trade modules always', () => {
    expect(isModuleOpen(0, [])).toBe(true);
    expect(isModuleOpen(1, [])).toBe(false);
    expect(isModuleOpen(7, [])).toBe(true);
  });
  it('unlocks the next after completion', () => {
    expect(isModuleOpen(1, [0])).toBe(true);
    expect(isModuleOpen(2, [0])).toBe(false);
  });
  it('unlockAll opens everything; all done gives -1', () => {
    expect(isModuleOpen(6, [], true)).toBe(true);
    expect(firstOpenIndex([0, 1, 2, 3, 4, 5, 6])).toBe(-1);
    expect(coreDoneCount([0, 1, 7])).toBe(2);
  });
});

describe('exam', () => {
  it('pass mark is 12 of 15', () => {
    expect(C.finalExam.length).toBe(15);
    expect(passMark(15)).toBe(12);
  });
  it('scores answers', () => {
    const all = C.finalExam.map(q => q.a);
    expect(scoreExam(all)).toBe(15);
    expect(scoreExam(all.map((a, i) => (i < 4 ? (a + 1) % 3 : a)))).toBe(11);
  });
  it('certified = passed and acknowledged', () => {
    expect(isCertified({ name: 'x', co: 'y', track: 'pr', mods: 7, score: 12, ack: true })).toBe(true);
    expect(isCertified({ name: 'x', co: 'y', track: 'pr', mods: 7, score: 12, ack: false })).toBe(false);
    expect(isCertified({ name: 'x', co: 'y', track: 'pr', mods: 7, score: 11, ack: true })).toBe(false);
    expect(isCertified({ name: 'x', co: 'y', track: 'pr', mods: 7, score: null, ack: true })).toBe(false);
  });
});

describe('csv', () => {
  it('matches the documented columns and escapes quotes', () => {
    const csv = buildCompletionCsv({ name: 'A "Q" B', co: 'CEI', track: 'Field engineer', score: 13, date: '2026-10-09' }, 7, 7);
    const [head, row] = csv.split('\n');
    expect(head).toBe('name,company,track,best_score,pass_threshold,core_modules_completed,acknowledged_on,standards');
    expect(row).toBe('"A ""Q"" B","CEI","Field engineer","13/15","12/15","7/7","2026-10-09","QTS S7117 V1.4 Rev 39; Spec 01 40 00; Spec 01 91 13"');
  });
});

describe('content lookups', () => {
  it('has 7 core and 3 trade modules, 6 spot items with images', () => {
    expect(C.modules.filter(m => !m.trade).length).toBe(7);
    expect(C.modules.filter(m => m.trade).length).toBe(3);
    expect(C.practiceSpot.every(s => s.image)).toBe(true);
  });
  it('flags only BAT and SKID as missing site checklists', () => {
    expect(C.equipmentTracker.equipment.filter(siteMissing).map(e => e.key).sort()).toEqual(['BAT', 'SKID']);
  });
  it('filters equipment and glossary', () => {
    const eq = C.equipmentTracker.equipment;
    expect(filterEquipment(eq, 'Mechanical', '').every(e => e.category === 'Mechanical')).toBe(true);
    expect(filterEquipment(eq, 'All', 'ups').some(e => e.acr === 'UPS')).toBe(true);
    expect(filterGlossary('zzzz')).toHaveLength(0);
    expect(filterGlossary('').length).toBe(C.glossary.length);
  });
});
