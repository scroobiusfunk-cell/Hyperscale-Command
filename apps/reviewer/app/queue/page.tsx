import Link from 'next/link';
import { Topbar } from '../../components/Topbar';
import { Chip } from '../../components/Chip';
import { ConfigHint } from '../../components/ConfigHint';
import { getQueue, PROJECT_ID, ApiError } from '../../lib/api';
import { waitingFor } from '../../lib/format';

export const dynamic = 'force-dynamic';

export default async function QueuePage() {
  if (!PROJECT_ID) return <ConfigHint />;

  let entries;
  try {
    entries = await getQueue(PROJECT_ID);
  } catch (error) {
    return (
      <>
        <Topbar title="Review queue" />
        <div className="content">
          <div className="banner">
            Could not reach the API: {error instanceof ApiError ? error.message : String(error)}
          </div>
        </div>
      </>
    );
  }

  const safety = entries.filter((e) => e.criticality === 'safety').length;
  const first = entries[0];

  return (
    <>
      <Topbar
        title="Review queue"
        subtitle={
          entries.length === 0
            ? 'Nothing waiting'
            : `${entries.length} waiting · safety items first, then longest waiting`
        }
        right={
          first ? (
            <Link href={`/review/${first.checklist_item_id}`} className="btn btn-primary">
              Review next
            </Link>
          ) : null
        }
      />
      <div className="content">
        {safety > 0 ? (
          <div className="banner is-critical">
            <strong>{safety}</strong> safety {safety === 1 ? 'item is' : 'items are'} waiting.
            These always carry a qualified person&apos;s name and never clear on their own.
          </div>
        ) : null}

        <div className="card">
          {entries.length === 0 ? (
            <div className="empty">
              <div className="empty-title">Queue is clear</div>
              Nothing captured in the field is waiting on you.
            </div>
          ) : (
            <div className="queue-list">
              {entries.map((entry) => (
                <Link
                  key={entry.checklist_item_id}
                  href={`/review/${entry.checklist_item_id}`}
                  className={`queue-row${entry.criticality === 'safety' ? ' is-safety' : ''}`}
                >
                  <div className="queue-main">
                    <div className="queue-title">
                      <span className="queue-tag">{entry.asset_tag}</span>
                      {entry.criticality === 'safety' ? (
                        <Chip tone="critical">Safety</Chip>
                      ) : null}
                      {entry.is_recapture ? <Chip tone="warning">Recaptured</Chip> : null}
                    </div>
                    <div className="queue-statement">{entry.statement}</div>
                    <div className="queue-meta">
                      {entry.room ? <span>{entry.room}</span> : <span>No room recorded</span>}
                      <span>
                        {entry.evidence_count}{' '}
                        {entry.evidence_count === 1 ? 'photo' : 'photos'}
                      </span>
                    </div>
                  </div>
                  <div className="queue-side">
                    <span className="queue-meta">waiting {waitingFor(entry.captured_at)}</span>
                    <span aria-hidden="true" className="muted">
                      →
                    </span>
                  </div>
                </Link>
              ))}
            </div>
          )}
        </div>
      </div>
    </>
  );
}
