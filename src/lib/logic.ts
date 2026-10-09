import content from '../content/content.json';
import type { Content, Equipment, Module, TeamMember } from '../content/types';

export const C = content as unknown as Content;

export const STANDARDS = 'QTS S7117 V1.4 Rev 39; Spec 01 40 00; Spec 01 91 13';
export const PASS_FRACTION = C.passThreshold;

export const coreIndexes = (modules: Module[] = C.modules) =>
  modules.map((m, i) => (m.trade ? -1 : i)).filter(i => i >= 0);

/** First core module not yet done, or -1 when every core module is complete. */
export function firstOpenIndex(done: number[], modules: Module[] = C.modules): number {
  return modules.findIndex((m, i) => !m.trade && !done.includes(i));
}

/** Core modules unlock sequentially; trade modules are always open. */
export function isModuleOpen(i: number, done: number[], unlockAll = false, modules: Module[] = C.modules): boolean {
  const first = firstOpenIndex(done, modules);
  return !!modules[i]?.trade || unlockAll || done.includes(i) || first === -1 || i <= first;
}

export const coreDoneCount = (done: number[], modules: Module[] = C.modules) =>
  done.filter(i => modules[i] && !modules[i].trade).length;

export const passMark = (total: number) => Math.ceil(total * PASS_FRACTION);

export const scoreExam = (answers: (number | null)[], exam = C.finalExam) =>
  answers.reduce<number>((n, a, i) => n + (exam[i] && a === exam[i].a ? 1 : 0), 0);

export const isCertified = (m: TeamMember, total = C.finalExam.length) =>
  m.ack && m.score !== null && m.score >= passMark(total);

export interface Ack { name: string; co: string; track: string; score: number; date: string }

const esc = (v: unknown) => '"' + String(v).replace(/"/g, '""') + '"';

export function buildCompletionCsv(a: Ack, coreDone: number, coreTotal: number, total = C.finalExam.length): string {
  const head = 'name,company,track,best_score,pass_threshold,core_modules_completed,acknowledged_on,standards';
  const row = [a.name, a.co, a.track, `${a.score}/${total}`, `${passMark(total)}/${total}`, `${coreDone}/${coreTotal}`, a.date, STANDARDS];
  return head + '\n' + row.map(esc).join(',');
}

/** Equipment with no site checklists listed in the tracker at all (e.g. BAT, SKID). */
export const siteMissing = (e: Equipment) =>
  e.siteRequired.length === 0 && !e.notRequired.includes('Site Arrival Inspection');

export function filterEquipment(list: Equipment[], category: string, query: string): Equipment[] {
  const q = query.trim().toLowerCase();
  return list.filter(e => (category === 'All' || e.category === category) && (!q || `${e.acr} ${e.name}`.toLowerCase().includes(q)));
}

export function filterGlossary(query: string) {
  const q = query.trim().toLowerCase();
  return q ? C.glossary.filter(t => `${t.abbr} ${t.name} ${t.def}`.toLowerCase().includes(q)) : C.glossary;
}

export function shuffle<T>(a: T[]): T[] {
  const b = a.slice();
  for (let i = b.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [b[i], b[j]] = [b[j], b[i]];
  }
  return b;
}

export const today = () => new Date().toISOString().slice(0, 10);
