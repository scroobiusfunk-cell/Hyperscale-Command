import { ChevronRight } from 'lucide-react';
import { useMemo, useState } from 'react';
import { BackBtn, Blueprint, Chips, Cite, Kicker, Label, Option, Primary, Tag } from '../components/ui';
import type { Equipment } from '../content/types';
import { C, filterEquipment, filterGlossary, shuffle, siteMissing } from '../lib/logic';

const imgs = import.meta.glob('../assets/*.png', { eager: true, query: '?url', import: 'default' }) as Record<string, string>;
const imageUrl = (name: string) => imgs[`../assets/${name}`];
/** Photos where colour carries the answer (seal, tester, copper, indicator) stay un-tinted. */
const TINTED = new Set(['rtu-open-intake.png', 'panel-handwritten-directory.png']);
const CONTAIN = new Set(['busbar-bolted-joint-notorque.png', 'tiltwatch-tripped.png']);

function SortGame() {
  const items = C.practiceSort.items;
  const [order, setOrder] = useState(() => items.map((_, i) => i));
  const [idx, setIdx] = useState(0);
  const [pick, setPick] = useState<string | null>(null);
  const [score, setScore] = useState(0);
  const finished = idx >= items.length;
  const item = items[order[Math.min(idx, items.length - 1)]];
  const answered = pick !== null;

  if (finished) {
    return (
      <Blueprint style={{ gap: 12 }}>
        <Kicker>Round complete</Kicker>
        <div className="big-num" style={{ fontSize: 56 }}>{score}/{items.length}</div>
        <p className="card-body" style={{ fontSize: 14 }}>{score === items.length ? 'Every activity placed at the right level.' : 'Review the modules for the ones you missed, then try a new order.'}</p>
        <Primary className="primary-lg" onClick={() => { setOrder(shuffle(items.map((_, i) => i))); setIdx(0); setPick(null); setScore(0); }}>Shuffle and retry</Primary>
      </Blueprint>
    );
  }
  return (
    <>
      <Blueprint style={{ minHeight: 150, justifyContent: 'center' }}>
        <Kicker>Activity {idx + 1} of {items.length}</Kicker>
        <p style={{ margin: 0, fontFamily: 'var(--font-heading)', fontSize: 24, lineHeight: 1.15 }}>{item.text}</p>
      </Blueprint>
      <div className="sort-grid">
        {C.practiceSort.options.map(([code, short]) => {
          const right = answered && code === item.a;
          return (
            <button key={code} className={`btn ${right ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={right}
              onClick={() => { if (!answered) { setPick(code); if (code === item.a) setScore(score + 1); } }}>
              <span className="code">{code}</span>
              <span className="short">{answered && code === pick && code !== item.a ? 'Your pick' : short}</span>
            </button>
          );
        })}
      </div>
      {answered && (
        <div className="stack stack-10">
          <Tag kind={pick === item.a ? 'accent' : 'neutral'} className="">{pick === item.a ? 'Correct' : `Answer: ${item.a}`}</Tag>
          <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5, color: 'var(--color-neutral-800)' }}>{item.why}</p>
          <Primary className="primary-lg" onClick={() => { setIdx(idx + 1); setPick(null); }}>{idx === items.length - 1 ? 'See results' : 'Next activity'}</Primary>
        </div>
      )}
    </>
  );
}

function SpotGame() {
  const items = C.practiceSpot;
  const [idx, setIdx] = useState(0);
  const [pick, setPick] = useState<number | null>(null);
  const [score, setScore] = useState(0);
  const finished = idx >= items.length;
  const sp = items[Math.min(idx, items.length - 1)];
  const answered = pick !== null;

  if (finished) {
    return (
      <Blueprint style={{ gap: 12 }}>
        <Kicker>Round complete</Kicker>
        <div className="big-num" style={{ fontSize: 56 }}>{score}/{items.length}</div>
        <p className="card-body" style={{ fontSize: 14 }}>Review the Hard rules in each module for the ones you missed.</p>
        <Primary className="primary-lg" onClick={() => { setIdx(0); setPick(null); setScore(0); }}>Start over</Primary>
      </Blueprint>
    );
  }
  return (
    <>
      <div className={`blueprint photo ${CONTAIN.has(sp.image) ? 'contain' : ''}`}>
        <i className="corner tl" /><i className="corner tr" /><i className="corner bl" /><i className="corner br" />
        <div className={`frame ${TINTED.has(sp.image) ? 'duotone' : ''}`}>
          <img src={imageUrl(sp.image)} alt={`Photo ${idx + 1} of ${items.length}`} />
        </div>
      </div>
      <div className="stack stack-12">
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
          <span className="card-kicker">Photo {idx + 1} of {items.length}</span><Cite>{sp.c}</Cite>
        </div>
        <h2 className="q22">{sp.q}</h2>
        {sp.opts.map((t, i) => (
          <Option key={t} text={t} primary={answered && i === sp.a} mark={answered ? (i === sp.a ? 'Correct' : i === pick ? 'Your pick' : '') : ''}
            onClick={() => { if (!answered) { setPick(i); if (i === sp.a) setScore(score + 1); } }} />
        ))}
        {answered && (
          <div className="explain">
            <Tag kind={pick === sp.a ? 'accent' : 'neutral'} className="">{pick === sp.a ? 'Correct' : 'Not quite'}</Tag>
            <p>{sp.why}</p>
            <Primary className="primary-lg" onClick={() => { setIdx(idx + 1); setPick(null); }}>{idx === items.length - 1 ? 'See results' : 'Next photo'}</Primary>
          </div>
        )}
      </div>
    </>
  );
}

export function Practice() {
  const [mode, setMode] = useState<'sort' | 'spot'>('sort');
  return (
    <div className="page" style={{ gap: 20 }}>
      <div className="stack stack-8">
        <Kicker>Practice</Kicker>
        <h1 className="screen md">{mode === 'sort' ? 'Which level?' : 'Spot the deficiency'}</h1>
      </div>
      <div className="mode-grid">
        <button className={`btn ${mode === 'sort' ? 'btn-primary' : 'btn-secondary'}`} style={{ minHeight: 44 }} aria-pressed={mode === 'sort'} onClick={() => setMode('sort')}>Sort by level</button>
        <button className={`btn ${mode === 'spot' ? 'btn-primary' : 'btn-secondary'}`} style={{ minHeight: 44 }} aria-pressed={mode === 'spot'} onClick={() => setMode('spot')}>Spot the deficiency</button>
      </div>
      {mode === 'sort' ? <SortGame key="sort" /> : <SpotGame key="spot" />}
    </div>
  );
}

function ChecklistSection({ title, rows }: { title: string; rows: Equipment['siteRequired'] }) {
  return (
    <div className="stack">
      <Label>{title}</Label>
      {rows.map(r => (
        <div className="chk-row" key={r.naming}>
          <span className="chk-lvl">{r.lvl}</span>
          <div className="stack" style={{ gap: 2 }}>
            <span style={{ fontSize: 14, fontWeight: 600 }}>{r.title}</span>
            <span className="chk-name">{r.naming}</span>
            <span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{r.meta}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

export function EquipmentTab({ sel, setSel }: { sel: string | null; setSel: (k: string | null) => void }) {
  const [query, setQuery] = useState('');
  const [cat, setCat] = useState('All');
  const all = C.equipmentTracker.equipment;
  const list = useMemo(() => filterEquipment(all, cat, query), [all, cat, query]);
  const eq = sel ? all.find(e => e.key === sel) : undefined;

  if (eq) {
    const req = eq.offsiteRequired.length + eq.siteRequired.length;
    return (
      <div className="page back">
        <BackBtn label="Equipment" onClick={() => setSel(null)} />
        <div className="stack stack-8">
          <Kicker>{eq.category} · {eq.acr}</Kicker>
          <h1 className="screen md">{eq.name}</h1>
          <Tag kind="accent" className="">{eq.category} · {req} checklists required</Tag>
        </div>
        {eq.offsiteRequired.length > 0 && <ChecklistSection title="Offsite / integrator · L1" rows={eq.offsiteRequired} />}
        {eq.siteRequired.length > 0 && <ChecklistSection title="On site · L2–L3" rows={eq.siteRequired} />}
        {siteMissing(eq) && <p style={{ margin: 0, fontSize: 13, color: 'var(--color-neutral-700)' }}>Site checklists for this item are not listed in the tracker.</p>}
        <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--color-neutral-700)', borderTop: '1px solid var(--color-divider)', paddingTop: 12 }}>
          {eq.notRequired} Applicability is reviewed by the Project Team.
        </p>
      </div>
    );
  }
  return (
    <div className="page">
      <div className="stack stack-8">
        <Kicker>Equipment Inspection Tracker · 4.14.26</Kicker>
        <h1 className="screen">Equipment</h1>
        <p className="lede">Pick an asset type to see which checklists apply, who completes them and the upload window.</p>
      </div>
      <input className="input search" type="search" aria-label="Search equipment" placeholder="Search UPS, CRAH, MVG…" value={query} onChange={e => setQuery(e.target.value)} />
      <Chips items={['All', 'Electrical', 'Mechanical']} value={cat} onPick={setCat} />
      <div className="stack">
        {list.map(e => (
          <button key={e.key} className="eq-row" onClick={() => setSel(e.key)}>
            <div className="acr-box">{e.acr}</div>
            <div className="stack" style={{ gap: 2, minWidth: 0 }}>
              <span className="row-title">{e.name}</span>
              <span className="row-sub">{e.category} · {e.offsiteRequired.length + e.siteRequired.length} checklists required</span>
            </div>
            <ChevronRight size={18} strokeWidth={1.5} color="var(--color-neutral-600)" />
          </button>
        ))}
        {list.length === 0 && <p className="empty">No equipment matches.</p>}
      </div>
    </div>
  );
}

export function Rules() {
  return (
    <div className="page">
      <div className="stack stack-8">
        <Kicker>Hard-rule cheat card</Kicker>
        <h1 className="screen">The numbers</h1>
      </div>
      <div className="stack">
        {C.hardRules.map(r => (
          <div className="rule-row" key={r.rule}>
            <span className="rule-val">{r.v}</span>
            <div className="stack" style={{ gap: 2 }}>
              <span style={{ fontSize: 14, fontWeight: 600 }}>{r.rule}</span>
              <span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{r.applies}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="stack">
        <Label>Systems of record</Label>
        {C.systemsOfRecord.map(y => (
          <div className="stack" key={y.name} style={{ padding: '12px 0', borderTop: '1px solid var(--color-divider)', gap: 4 }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', gap: 8 }}>
              <span className="row-title">{y.name}</span><span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{y.owner}</span>
            </div>
            <p style={{ margin: 0, fontSize: 13, lineHeight: 1.45, color: 'var(--color-neutral-800)' }}>{y.holds}</p>
          </div>
        ))}
      </div>
      <p className="source">Source: CDR Campus QA/QC &amp; Cx Training v2, Rev 1.0</p>
    </div>
  );
}

export function Glossary() {
  const [q, setQ] = useState('');
  const terms = filterGlossary(q);
  return (
    <div className="page">
      <div className="stack stack-8">
        <Kicker>Reference</Kicker>
        <h1 className="screen">Glossary</h1>
      </div>
      <input className="input search" type="search" aria-label="Search glossary" placeholder="Search terms or abbreviations" value={q} onChange={e => setQ(e.target.value)} />
      <div className="stack">
        {terms.map(t => (
          <div className="term-row" key={t.abbr}>
            <span className="term-abbr">{t.abbr}</span>
            <div className="stack" style={{ gap: 3 }}>
              <span style={{ fontSize: 13, fontWeight: 600 }}>{t.name}</span>
              <p style={{ margin: 0, fontSize: 13, lineHeight: 1.5, color: 'var(--color-neutral-800)' }}>{t.def}</p>
            </div>
          </div>
        ))}
        {terms.length === 0 && <p className="empty">No terms match “{q}”.</p>}
      </div>
    </div>
  );
}
