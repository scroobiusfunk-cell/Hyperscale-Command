import Link from 'next/link';
import { notFound } from 'next/navigation';
import { Topbar } from '../../../components/Topbar';
import { Chip } from '../../../components/Chip';
import { EvidenceViewer } from '../../../components/EvidenceViewer';
import { RulingForm } from '../../../components/RulingForm';
import { getItem, getQueue, PROJECT_ID, ApiError } from '../../../lib/api';
import { describeCriteria, shortTime } from '../../../lib/format';

export const dynamic = 'force-dynamic';

// The words a reviewer reads. `indeterminate` is the wire value, not something
// anybody says out loud about a photograph.
const VERDICT_WORD: Record<string, string> = {
  pass: 'Passed',
  fail: 'Failed',
  indeterminate: 'Asked for a recapture',
  not_visible: 'Could not be seen',
};

export default async function ReviewPage({
  params,
}: {
  params: Promise<{ itemId: string }>;
}) {
  const { itemId } = await params;

  let item;
  try {
    item = await getItem(itemId);
  } catch (error) {
    if (error instanceof ApiError && error.status === 404) notFound();
    throw error;
  }

  // Where to go after the ruling. Knowing this up front is what lets the
  // reviewer keep moving without coming back to the list each time.
  const queue = PROJECT_ID ? await getQueue(PROJECT_ID).catch(() => []) : [];
  const position = queue.findIndex((entry) => entry.checklist_item_id === itemId);
  const next = queue.filter((entry) => entry.checklist_item_id !== itemId)[0] ?? null;
  const isSafety = item.criticality === 'safety';

  return (
    <>
      <Topbar
        title={item.asset_tag}
        subtitle={[item.room, item.equipment_class.replace(/_/g, ' ')]
          .filter(Boolean)
          .join(' · ')}
        right={
          <div className="queue-side">
            {position >= 0 ? (
              <span className="card-note">
                {position + 1} of {queue.length} waiting
              </span>
            ) : null}
            <Link href="/queue" className="btn btn-ghost">
              Back to queue
            </Link>
          </div>
        }
      />
      <div className="content">
        <div className="review">
          <div className="panel-stack">
            <EvidenceViewer evidence={item.evidence} />
          </div>

          <div className="panel-stack">
            <div className="card">
              <div className="card-head">
                <h2>What is being checked</h2>
                {isSafety ? <Chip tone="critical">Safety</Chip> : null}
              </div>
              <div className="card-body">
                <p className="statement" style={{ margin: 0 }}>
                  {item.statement}
                </p>
                <div className="why">
                  <span className="why-label">Why it matters</span>
                  {item.why_it_matters}
                </div>
                <dl className="kv" style={{ marginTop: 14 }}>
                  <dt>Passes if</dt>
                  <dd>{describeCriteria(item.pass_criteria)}</dd>
                  <dt>Source</dt>
                  <dd className="mono">
                    {item.source_clause} · p.{item.source_page}
                  </dd>
                  <dt>Rule set</dt>
                  <dd className="mono">{item.ruleset_version}</dd>
                  <dt>CxAlloy</dt>
                  <dd className="mono">{item.asset_cxalloy_id ?? '(not in CxAlloy)'}</dd>
                </dl>
              </div>
            </div>

            <RulingForm
              itemId={item.checklist_item_id}
              isSafety={isSafety}
              nextItemId={next?.checklist_item_id ?? null}
            />

            {item.history.length > 0 ? (
              <div className="card">
                <div className="card-head">
                  <h2>Earlier rulings</h2>
                  <span className="card-note">Append-only</span>
                </div>
                <div className="card-body history">
                  {item.history.map((ruling) => (
                    <div key={ruling.id} className="history-item">
                      <Chip
                        tone={
                          ruling.verdict === 'pass'
                            ? 'good'
                            : ruling.verdict === 'fail'
                              ? 'critical'
                              : 'warning'
                        }
                      >
                        {VERDICT_WORD[ruling.verdict]}
                      </Chip>
                      <div className="history-body">
                        <div className="history-when">
                          {shortTime(ruling.created_at)}
                          {ruling.supersedes ? ' · corrects an earlier ruling' : ''}
                        </div>
                        {ruling.note ? (
                          <div className="history-note">{ruling.note}</div>
                        ) : (
                          <div className="history-note muted">No note left.</div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </div>
    </>
  );
}
