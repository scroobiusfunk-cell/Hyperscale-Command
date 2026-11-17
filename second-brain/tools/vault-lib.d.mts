export interface Note {
  id: string; path: string; name: string; title: string; area: string; type: string; summary: string;
  source: string; modified: string; fm: Record<string, unknown>; tags: string[]; body: string;
  links: { target: string; heading?: string; alias?: string }[];
}
export interface VaultIndex {
  notes: Note[]; edges: { source: string; target: string }[]; backlinks: Record<string, string[]>;
  broken: { from: string; target: string }[]; generated: string;
}
export function parseFrontmatter(text: string): { data: Record<string, unknown>; body: string };
export function parseNote(path: string, text: string): Note;
export function makeResolver(notes: Note[]): (target: string) => Note | null;
export function buildGraph(notes: Note[]): { edges: VaultIndex['edges']; backlinks: VaultIndex['backlinks']; broken: VaultIndex['broken'] };
export function buildIndex(files: { path: string; text: string }[]): VaultIndex;
