import { Check } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Bar, BackBtn, Blueprint, Cite, CloseBtn, Kicker, Label, Option, Primary, Secondary, Tag } from '../components/ui';
import type { TrackKey } from '../content/types';
import { C, coreDoneCount, firstOpenIndex, isModuleOpen, passMark } from '../lib/logic';

export function TrackPicker({ onPick }: { onPick: (t: TrackKey) => void }) {
  return (
    <div className="page" style={{ paddingTop: 24, gap: 20 }}>
      <div className="stack stack-8">
        <Kicker>QTS CDR Campus · DC4 · DC5 · DC7</Kicker>
        <h1 className="screen lg">Pick your track</h1>
        <p className="lede">Every track covers the same seven modules. Your track sets what each module asks of you. You can change it later.</p>
      </div>
      {(Object.keys(C.tracks) as TrackKey[]).map(k => (
        <Blueprint key={k} as="button" className="card-btn" onClick={() => onPick(k)}>
          <span className="card-kicker">{C.tracks[k].level}</span>
          <span className="heading-24">{C.tracks[k].name}</span>
          <span style={{ fontSize: 13, lineHeight: 1.45, color: 'var(--color-neutral-800)' }}>{C.tracks[k].desc}</span>
        </Blueprint>
      ))}
    </div>
  );
}

interface HomeProps {
  track: TrackKey;
  done: number[];
  best: number | null;
  unlockAll: boolean;
  teamHeadline: string;
  onChange: () => void;
  onOpenModule: (i: number) => void;
  onTeam: () => void;
  onExam: () => void;
}

export function Home({ track, done, best, unlockAll, teamHeadline, onChange, onOpenModule, onTeam, onExam }: HomeProps) {
  const T = C.tracks[track];
  const total = C.finalExam.length;
  const firstOpen = firstOpenIndex(done);
  const allDone = firstOpen === -1;
  const coreN = C.modules.filter(m => !m.trade).length;
  const coreDone = coreDoneCount(done);
  const pct = Math.round((coreDone / coreN) * 100);
  const examLocked = !(allDone || unlockAll);
  const nextIdx = allDone ? 0 : firstOpen;

  const row = (i: number) => {
    const m = C.modules[i];
    const isDone = done.includes(i);
    const open = isModuleOpen(i, done, unlockAll);
    const cur = i === firstOpen;
    const status = isDone ? 'Done' : m.trade ? 'Optional' : cur ? 'Next' : open ? 'Open' : 'Locked';
    const kind = isDone ? 'accent' : cur ? 'outline' : 'neutral';
    return (
      <button key={m.code} className={`row-btn ${open ? '' : 'locked'}`} disabled={!open} onClick={() => onOpenModule(i)}>
        <div className={`code-box ${isDone ? 'done' : ''}`}>{m.code}</div>
        <div className="stack" style={{ gap: 2, minWidth: 0 }}>
          <span className="row-title">{m.title}</span>
          <span className="row-sub">{m.sub}</span>
        </div>
        <Tag kind={kind}>{status}</Tag>
      </button>
    );
  };
  const idx = C.modules.map((_, i) => i);

  return (
    <div className="page">
      <div className="stack stack-8">
        <Kicker>QTS CDR Campus · S7117 V1.4 Rev 39</Kicker>
        <h1 className="screen">QA/QC &amp; Commissioning</h1>
        <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
          <Tag kind="accent">Track: {T.name} · {T.level}</Tag>
          <button className="btn btn-ghost" style={{ minHeight: 32, fontSize: 13 }} onClick={onChange}>Change</button>
        </div>
      </div>
      <div className="stack" style={{ gap: 6 }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: 12, color: 'var(--color-neutral-700)' }}>
          <span>{coreDone} of {coreN} modules complete</span><span>{pct}%</span>
        </div>
        <Bar pct={pct} />
      </div>

      {!allDone && (
        <Blueprint style={{ gap: 10 }}>
          <Kicker>Up next · {C.modules[nextIdx].levelLabel}</Kicker>
          <div className="heading-26">{C.modules[nextIdx].title}</div>
          <p className="card-body" style={{ lineHeight: 1.45 }}>{C.modules[nextIdx].summary}</p>
          <Primary className="sm" style={{ alignSelf: 'flex-start' }} onClick={() => onOpenModule(nextIdx)}>Open module</Primary>
        </Blueprint>
      )}

      <div className="stack">
        <Label>The path · Flowchart R5</Label>
        {idx.filter(i => !C.modules[i].trade).map(row)}
      </div>
      <div className="stack">
        <Label>Trade focus · optional</Label>
        {idx.filter(i => C.modules[i].trade).map(row)}
      </div>

      {track === 'ad' && (
        <Blueprint as="button" className="card-btn" onClick={onTeam}>
          <span className="card-kicker">Admin · Team readiness</span>
          <span className="heading-24">{teamHeadline}</span>
          <span style={{ fontSize: 13, color: 'var(--color-neutral-800)' }}>Completion and certification by track and trade partner</span>
        </Blueprint>
      )}

      <Blueprint style={{ gap: 10, opacity: examLocked ? 0.55 : 1 }}>
        <Kicker>Final knowledge check</Kicker>
        <div className="heading-24">{total} scenarios · 80% to pass</div>
        <p className="card-body" style={{ lineHeight: 1.45 }}>
          {examLocked ? 'Unlocks when all seven core modules are complete.'
            : best === null ? 'Scenario-based, drawn from CDR Campus situations.'
            : `Best score: ${best}/${total}${best >= passMark(total) ? ' · Passed' : ''}`}
        </p>
        <Primary className="sm" style={{ alignSelf: 'flex-start' }} disabled={examLocked} onClick={onExam}>{best === null ? 'Start check' : 'Retake check'}</Primary>
      </Blueprint>
    </div>
  );
}

export function ModuleOverview({ index, track, done, onBack, onStart }: { index: number; track: TrackKey; done: boolean; onBack: () => void; onStart: () => void }) {
  const m = C.modules[index];
  const T = C.tracks[track];
  const gateLabel = m.code === 'CO' ? 'Owner acceptance requires' : m.code === 'QA' ? 'Always true' : 'Gate to next level';
  return (
    <div className="page back">
      <BackBtn label="The path" onClick={onBack} />
      <div className="stack stack-8">
        <Kicker>{m.levelLabel}</Kicker>
        <h1 className="screen lg">{m.title}</h1>
        <p className="lede">{m.summary}</p>
      </div>
      <div className="two-col">
        <div><span className="card-kicker">Leads</span><span>{m.leads}</span></div>
        <div><span className="card-kicker">Witness / accept</span><span>{m.witness}</span></div>
      </div>
      <Blueprint style={{ gap: 6 }}>
        <Kicker>Your role · {T.name}</Kicker>
        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.5 }}>{m.role[track]}</p>
      </Blueprint>
      <div className="stack">
        <Label>Hard rules</Label>
        {m.rules.map(r => (
          <div className="rule" key={r.t}><span>{r.t}</span><Cite>{r.c}</Cite></div>
        ))}
      </div>
      {track !== 'aw' && m.checklists.length > 0 && (
        <div className="stack">
          <Label>CxAlloy checklists · naming</Label>
          {m.checklists.map(k => <div className="mono" key={k}>{k}</div>)}
        </div>
      )}
      <div className="stack">
        <Label>{gateLabel}</Label>
        {m.gate.map(g => (
          <div className="gate" key={g}><Check size={18} strokeWidth={1.5} color="var(--color-accent)" /><span>{g}</span></div>
        ))}
      </div>
      <Primary className="primary-lg" style={{ width: '100%' }} onClick={onStart}>
        {done ? 'Review lesson' : 'Start lesson'} · {m.steps.length} steps + check
      </Primary>
    </div>
  );
}

export function LessonPlayer({ index, showNotes, onExit, onFinish }: { index: number; showNotes: boolean; onExit: () => void; onFinish: () => void }) {
  const m = C.modules[index];
  const n = m.steps.length;
  const [step, setStep] = useState(0);
  const [answer, setAnswer] = useState<number | null>(null);
  const isCheck = step === n;
  const answered = answer !== null;
  const correct = answered && answer === m.quiz.a;
  const s = m.steps[Math.min(step, n - 1)];

  useEffect(() => { document.querySelector('.scroll')?.scrollTo(0, 0); }, [step]);

  const next = () => {
    if (isCheck) return onFinish();
    setStep(step + 1);
  };
  const prev = () => { setStep(Math.max(0, step - 1)); setAnswer(null); };

  return (
    <div className="page lesson" style={{ paddingTop: 8, gap: 20 }}>
      <div className="topbar">
        <CloseBtn label="Close lesson" onClick={onExit} />
        <div className="segs" aria-label={`Step ${step + 1} of ${n + 1}`}>
          {Array.from({ length: n + 1 }, (_, i) => <i key={i} className={i <= step ? 'on' : ''} />)}
        </div>
      </div>
      {!isCheck ? (
        <div className="stack stack-14">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
            <span className="card-kicker">Step {step + 1} of {n} · {m.levelLabel}</span>
            <Cite>{s.c}</Cite>
          </div>
          <h2 className="step-title">{s.title}</h2>
          <p className="step-body">{s.body}</p>
          {showNotes && (
            <Blueprint style={{ marginTop: 8 }}>
              <Kicker>On the CDR Campus</Kicker>
              <p className="card-body" style={{ fontSize: 14, lineHeight: 1.5, opacity: 1, color: 'var(--color-neutral-800)' }}>{s.field}</p>
            </Blueprint>
          )}
        </div>
      ) : (
        <div className="stack stack-14">
          <Kicker>Check · {m.levelLabel}</Kicker>
          <h2 className="q26">{m.quiz.q}</h2>
          <div className="stack stack-10">
            {m.quiz.opts.map((text, i) => (
              <Option key={text} text={text} primary={answered && i === m.quiz.a}
                mark={answered ? (i === m.quiz.a ? 'Correct' : i === answer ? 'Your pick' : '') : ''}
                onClick={() => { if (!answered) setAnswer(i); }} />
            ))}
          </div>
          {answered && (
            <div className="explain">
              <Tag kind={correct ? 'accent' : 'neutral'} className="">{correct ? 'Correct' : 'Not quite'}</Tag>
              <p>{m.quiz.why}</p>
            </div>
          )}
        </div>
      )}
      <div className="lesson-footer">
        <Secondary className="primary-lg" disabled={step === 0} onClick={prev}>Back</Secondary>
        <Primary className="primary-lg" disabled={isCheck && !answered} onClick={next}>
          {isCheck ? 'Finish module' : step === n - 1 ? 'Go to check' : 'Next'}
        </Primary>
      </div>
    </div>
  );
}
