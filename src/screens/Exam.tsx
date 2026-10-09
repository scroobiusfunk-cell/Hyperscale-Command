import { useState } from 'react';
import { Bar, BackBtn, Blueprint, Chips, Cite, CloseBtn, Kicker, Label, Option, Primary, Secondary, Tag } from '../components/ui';
import type { TrackKey } from '../content/types';
import { buildCompletionCsv, C, type Ack, coreDoneCount, isCertified, passMark, scoreExam, today } from '../lib/logic';

export interface ExamState { idx: number; answers: number[]; pick: number | null }
export const freshExam = (): ExamState => ({ idx: 0, answers: [], pick: null });

const TOTAL = C.finalExam.length;

export function FinalCheck({ exam, setExam, best, ack, done, onHome, onRetake, onSign, onSubmit }: {
  exam: ExamState; setExam: (e: ExamState) => void; best: number | null; ack: Ack | null; done: number[];
  onHome: () => void; onRetake: () => void; onSign: () => void; onSubmit: (score: number) => void;
}) {
  const finished = exam.idx >= TOTAL;
  const q = C.finalExam[Math.min(exam.idx, TOTAL - 1)];
  const score = scoreExam(exam.answers);
  const mark = passMark(TOTAL);
  const passed = score >= mark;
  const missed = C.finalExam.map((x, i) => ({ x, ok: exam.answers[i] === x.a })).filter((r, i) => i < exam.answers.length && !r.ok);

  const next = () => {
    if (exam.pick === null) return;
    const answers = [...exam.answers, exam.pick];
    setExam({ idx: exam.idx + 1, answers, pick: null });
    if (answers.length >= TOTAL) onSubmit(scoreExam(answers));
  };

  const download = () => {
    if (!ack) return;
    const coreN = C.modules.filter(m => !m.trade).length;
    const csv = buildCompletionCsv(ack, coreDoneCount(done), coreN);
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url;
    a.download = `CDR-QAQC-Cx-completion-${ack.name.replace(/\s+/g, '_')}.csv`;
    document.body.appendChild(a); a.click(); a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };

  return (
    <div className="page lesson" style={{ paddingTop: 8, gap: 20 }}>
      <div className="topbar">
        <CloseBtn label="Exit check" onClick={onHome} />
        <div style={{ flex: 1 }}><Bar pct={Math.round((Math.min(exam.idx, TOTAL) / TOTAL) * 100)} className="thin" /></div>
        <span style={{ fontSize: 12, whiteSpace: 'nowrap', color: 'var(--color-neutral-700)' }}>{Math.min(exam.idx + 1, TOTAL)} / {TOTAL}</span>
      </div>
      {!finished ? (
        <>
          <div className="stack stack-14">
            <Kicker>Scenario</Kicker>
            <h2 className="q24">{q.q}</h2>
            <div className="stack stack-10">
              {q.opts.map((t, i) => <Option key={t} start text={t} primary={exam.pick === i} onClick={() => setExam({ ...exam, pick: i })} />)}
            </div>
          </div>
          <Primary className="primary-lg" style={{ marginTop: 'auto' }} disabled={exam.pick === null} onClick={next}>
            {exam.idx === TOTAL - 1 ? 'Submit' : 'Next'}
          </Primary>
        </>
      ) : (
        <div className="stack" style={{ gap: 16 }}>
          <Blueprint style={{ gap: 10 }}>
            <Kicker>Final knowledge check</Kicker>
            <div className="big-num">{score}/{TOTAL}</div>
            <Tag kind={passed ? 'accent' : 'neutral'} className="">{passed ? 'Passed' : 'Not yet'}</Tag>
            <p className="card-body" style={{ fontSize: 14, lineHeight: 1.45 }}>
              {passed ? `You met the 80% threshold (${mark} of ${TOTAL}).` : `You need ${mark} of ${TOTAL} (80%). Review the items below and retake.`}
            </p>
            {best !== null && <p className="card-body" style={{ fontSize: 12 }}>Best score: {best}/{TOTAL}</p>}
          </Blueprint>
          {missed.length > 0 && (
            <div className="stack">
              <Label>Review what you missed</Label>
              {missed.map(({ x }) => (
                <div key={x.q} className="stack" style={{ padding: '12px 0', borderTop: '1px solid var(--color-divider)', gap: 6 }}>
                  <span style={{ fontSize: 14, fontWeight: 600, lineHeight: 1.35 }}>{x.q}</span>
                  <span style={{ fontSize: 13, lineHeight: 1.45, color: 'var(--color-accent-800)' }}>Answer: {x.opts[x.a]}</span>
                  <Cite>{x.c}</Cite>
                </div>
              ))}
            </div>
          )}
          {passed && !ack && <Primary className="primary-lg" onClick={onSign}>Sign acknowledgment</Primary>}
          {ack && (
            <Blueprint style={{ gap: 8 }}>
              <Kicker>Acknowledgment on file</Kicker>
              <span style={{ fontSize: 14 }}>{ack.name}{ack.co ? `, ${ack.co}` : ''} · signed {ack.date} · {ack.score}/{TOTAL}</span>
              <Secondary style={{ minHeight: 44 }} onClick={download}>Download completion record (CSV)</Secondary>
            </Blueprint>
          )}
          <div className="mode-grid" style={{ gap: 10 }}>
            <Secondary className="primary-lg" onClick={onHome}>Back to path</Secondary>
            <Primary className="primary-lg" onClick={onRetake}>Retake</Primary>
          </div>
        </div>
      )}
    </div>
  );
}

export function Acknowledgment({ track, score, onBack, onSign }: { track: TrackKey; score: number; onBack: () => void; onSign: (a: Ack) => void }) {
  const [name, setName] = useState('');
  const [co, setCo] = useState('');
  const [ok, setOk] = useState(false);
  const date = today();
  return (
    <div className="page back">
      <BackBtn label="Results" onClick={onBack} />
      <div className="stack stack-8">
        <Kicker>Electronic acknowledgment</Kicker>
        <h1 className="screen">Sign and certify</h1>
      </div>
      <Blueprint style={{ gap: 12 }}>
        <p className="card-body" style={{ fontSize: 14, lineHeight: 1.5, opacity: 1 }}>
          I have completed the CDR Campus QA/QC &amp; Commissioning training and will comply with QTS CX Standard V1.4 (S7117) Rev 39, Spec 01 40 00 and Spec 01 91 13.
        </p>
      </Blueprint>
      <div className="ack-grid">
        <div><span className="card-kicker">Track</span><span>{C.tracks[track].name}</span></div>
        <div><span className="card-kicker">Score</span><span>{score}/{TOTAL}</span></div>
        <div><span className="card-kicker">Date</span><span>{date}</span></div>
      </div>
      <div className="field">
        <label htmlFor="ack-name">Full name (required)</label>
        <input id="ack-name" className="input search" value={name} onChange={e => setName(e.target.value)} autoComplete="name" />
      </div>
      <div className="field">
        <label htmlFor="ack-co">Company</label>
        <input id="ack-co" className="input search" value={co} onChange={e => setCo(e.target.value)} autoComplete="organization" />
      </div>
      <label className="check-row">
        <input type="checkbox" checked={ok} onChange={e => setOk(e.target.checked)} />
        <span>I agree, and understand this record is sent to Red Blue University.</span>
      </label>
      <Primary className="primary-lg" disabled={!(name.trim() && ok)}
        onClick={() => onSign({ name: name.trim(), co: co.trim(), track: C.tracks[track].name, score, date })}>Sign</Primary>
    </div>
  );
}

export function TeamReadiness({ onBack }: { onBack: () => void }) {
  const [co, setCo] = useState('All');
  const team = C.sampleTeam;
  const mark = passMark(TOTAL);
  const taken = team.filter(r => r.score !== null);
  const certified = team.filter(r => isCertified(r)).length;
  const avg = taken.length ? Math.round((taken.reduce((n, r) => n + (r.score as number), 0) / taken.length / TOTAL) * 100) + '%' : '—';
  const rows = team.filter(r => co === 'All' || r.co === co);
  return (
    <div className="page back">
      <BackBtn label="The path" onClick={onBack} />
      <div className="stack stack-8">
        <Kicker>Admin · Sample data</Kicker>
        <h1 className="screen md">Team readiness</h1>
      </div>
      <div className="stats">
        <div><span className="card-kicker">Enrolled</span><span className="stat-val">{team.length}</span></div>
        <div><span className="card-kicker">Certified</span><span className="stat-val">{certified}</span></div>
        <div><span className="card-kicker">Avg score</span><span className="stat-val">{avg}</span></div>
      </div>
      <Chips items={['All', 'Suffolk', 'CEI', 'Loenbro', 'Baker']} value={co} onPick={setCo} />
      <div className="stack">
        {rows.map(r => {
          const pass = r.score !== null && r.score >= mark;
          return (
            <div className="team-row" key={r.name}>
              <div className="head">
                <span style={{ fontWeight: 600, fontSize: 15 }}>{r.name}</span>
                <Tag kind={pass ? 'accent' : 'neutral'}>{r.score === null ? 'Not taken' : pass ? `Passed ${r.score}/${TOTAL}` : `Below 80% · ${r.score}/${TOTAL}`}</Tag>
              </div>
              <span style={{ fontSize: 12, color: 'var(--color-neutral-700)' }}>{r.co} · {C.tracks[r.track].name}{r.ack ? ' · Acknowledged' : ''}</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: 10 }}>
                <div style={{ flex: 1, height: 4, border: '1px solid var(--color-divider)' }}><div style={{ height: '100%', background: 'var(--color-accent)', width: `${Math.round((r.mods / 7) * 100)}%` }} /></div>
                <span style={{ fontSize: 11, color: 'var(--color-neutral-700)', whiteSpace: 'nowrap' }}>{r.mods}/7 modules</span>
              </div>
            </div>
          );
        })}
      </div>
      <p className="source">Sample roster for layout. Connect Red Blue University to show live records.</p>
    </div>
  );
}
