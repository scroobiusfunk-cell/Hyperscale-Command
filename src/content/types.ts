export type TrackKey = 'aw' | 'pr' | 'ad';

export interface Track { name: string; level: string; desc: string }
export interface Rule { t: string; c: string }
export interface Step { title: string; body: string; c: string; field: string }
export interface Quiz { q: string; opts: string[]; a: number; why: string }
export interface Module {
  trade?: boolean;
  code: string;
  levelLabel: string;
  title: string;
  sub: string;
  summary: string;
  leads: string;
  witness: string;
  role: Record<TrackKey, string>;
  rules: Rule[];
  checklists: string[];
  gate: string[];
  steps: Step[];
  quiz: Quiz;
}
export interface ExamQ { q: string; opts: string[]; a: number; c: string }
export interface SpotItem extends ExamQ { why: string; image: string }
export interface SortItem { text: string; a: string; why: string }
export interface HardRule { v: string; rule: string; applies: string }
export interface SystemOfRecord { name: string; owner: string; holds: string }
export interface GlossaryTerm { abbr: string; name: string; def: string }
export interface ChecklistRow { lvl: string; title: string; naming: string; meta: string; on: boolean }
export interface Equipment {
  key: string;
  acr: string;
  name: string;
  category: 'Electrical' | 'Mechanical';
  offsiteRequired: ChecklistRow[];
  siteRequired: ChecklistRow[];
  notRequired: string;
  siteMissing?: boolean;
}
export interface TeamMember { name: string; co: string; track: TrackKey; mods: number; score: number | null; ack: boolean }

export interface Content {
  passThreshold: number;
  tracks: Record<TrackKey, Track>;
  modules: Module[];
  practiceSort: { options: [string, string][]; items: SortItem[] };
  practiceSpot: SpotItem[];
  finalExam: ExamQ[];
  hardRules: HardRule[];
  systemsOfRecord: SystemOfRecord[];
  glossary: GlossaryTerm[];
  equipmentTracker: { equipment: Equipment[] };
  sampleTeam: TeamMember[];
}
