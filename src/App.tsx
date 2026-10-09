import { BookOpen, Clock, ListChecks, Search, Server } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Acknowledgment, FinalCheck, freshExam, TeamReadiness, type ExamState } from './screens/Exam';
import { Home, LessonPlayer, ModuleOverview, TrackPicker } from './screens/Learn';
import { EquipmentTab, Glossary, Practice, Rules } from './screens/Tabs';
import { C, isCertified } from './lib/logic';
import { usePersisted } from './state/store';

type Tab = 'learn' | 'practice' | 'equip' | 'rules' | 'glossary';
type View = 'home' | 'module' | 'lesson' | 'exam' | 'ack' | 'team';

const TABS: { id: Tab; label: string; Icon: typeof BookOpen }[] = [
  { id: 'learn', label: 'Learn', Icon: BookOpen },
  { id: 'practice', label: 'Practice', Icon: ListChecks },
  { id: 'equip', label: 'Equipment', Icon: Server },
  { id: 'rules', label: 'Rules', Icon: Clock },
  { id: 'glossary', label: 'Glossary', Icon: Search },
];

const params = new URLSearchParams(window.location.search);
const UNLOCK_ALL = params.get('unlock') === '1';
const SHOW_NOTES = params.get('notes') !== '0';

export default function App() {
  const [p, patch] = usePersisted();
  const [tab, setTab] = useState<Tab>('learn');
  const [view, setView] = useState<View>('home');
  const [mod, setMod] = useState(0);
  const [exam, setExam] = useState<ExamState>(freshExam);
  const [eqSel, setEqSel] = useState<string | null>(null);
  const [changing, setChanging] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);

  useEffect(() => { scrollRef.current?.scrollTo(0, 0); }, [tab, view, mod, eqSel, exam.idx, changing]);

  const track = changing ? null : p.track;
  const showTabs = !!track && !(tab === 'learn' && ['lesson', 'exam', 'ack'].includes(view));
  const teamHeadline = `${C.sampleTeam.filter(r => isCertified(r)).length} of ${C.sampleTeam.length} certified`;

  const goTab = (t: Tab) => {
    if (t === 'learn') { setView(tab === 'learn' ? 'home' : view); }
    if (t === 'equip' && tab === 'equip') setEqSel(null);
    setTab(t);
  };

  let body;
  if (!track) {
    body = <TrackPicker onPick={k => { patch({ track: k }); setChanging(false); setTab('learn'); setView('home'); }} />;
  } else if (tab === 'learn') {
    if (view === 'module') {
      body = <ModuleOverview index={mod} track={track} done={p.done.includes(mod)} onBack={() => setView('home')} onStart={() => setView('lesson')} />;
    } else if (view === 'lesson') {
      body = <LessonPlayer key={mod} index={mod} showNotes={SHOW_NOTES} onExit={() => setView('module')}
        onFinish={() => { patch(s => ({ done: s.done.includes(mod) ? s.done : [...s.done, mod] })); setView('home'); }} />;
    } else if (view === 'exam') {
      body = <FinalCheck exam={exam} setExam={setExam} best={p.best} ack={p.ack} done={p.done}
        onHome={() => setView('home')} onRetake={() => setExam(freshExam())} onSign={() => setView('ack')}
        onSubmit={score => patch(s => ({ best: Math.max(s.best ?? 0, score) }))} />;
    } else if (view === 'ack') {
      body = <Acknowledgment track={track} score={p.best ?? 0} onBack={() => setView('exam')}
        onSign={a => { patch({ ack: a }); setView('exam'); }} />;
    } else if (view === 'team') {
      body = <TeamReadiness onBack={() => setView('home')} />;
    } else {
      body = <Home track={track} done={p.done} best={p.best} unlockAll={UNLOCK_ALL} teamHeadline={teamHeadline}
        onChange={() => setChanging(true)} onOpenModule={i => { setMod(i); setView('module'); }}
        onTeam={() => setView('team')} onExam={() => { setExam(freshExam()); setView('exam'); }} />;
    }
  } else if (tab === 'practice') body = <Practice />;
  else if (tab === 'equip') body = <EquipmentTab sel={eqSel} setSel={setEqSel} />;
  else if (tab === 'rules') body = <Rules />;
  else body = <Glossary />;

  return (
    <div className="shell">
      <div className="scroll" ref={scrollRef}>{body}</div>
      {showTabs && (
        <nav className="tabbar" aria-label="Primary">
          {TABS.map(({ id, label, Icon }) => (
            <button key={id} className="tab" aria-current={tab === id ? 'page' : undefined} onClick={() => goTab(id)}>
              <Icon size={22} strokeWidth={1.5} />{label}
            </button>
          ))}
        </nav>
      )}
    </div>
  );
}
