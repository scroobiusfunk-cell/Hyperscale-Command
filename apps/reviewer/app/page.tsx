import Link from 'next/link';
import { Topbar } from '../components/Topbar';
import { Stat, Meter } from '../components/Stat';

import { getDashboard, PROJECT_ID, ApiError } from '../lib/api';
import { percent } from '../lib/format';
import { ConfigHint } from '../components/ConfigHint';

export const dynamic = 'force-dynamic';

export default async function OverviewPage() {
  if (!PROJECT_ID) return <ConfigHint />;

  let board;
  try {
    board = await getDashboard(PROJECT_ID);
  } catch (error) {
    return (
      <>
        <Topbar title="Overview" />
        <div className="content">
          <div className="banner">
            Could not reach the API: {error instanceof ApiError ? error.message : String(error)}
          </div>
        </div>
      </>
    );
  }

  // Only reviewers who have actually passed something have a labeling rate;
  // including the others would report a rate nobody earned.
  const rated = board.reviewers.filter((r) => r.passes > 0);
  const worstLabeling = rated.length ? Math.min(...rated.map((r) => r.labeling_rate)) : null;

  return (
    <>
      <Topbar
        title="Overview"
        subtitle="The four numbers the architecture doc says to watch from day one."
      />
      <div className="content">
        <div className="kpi-row">
          <Stat
            label="Waiting for review"
            value={board.awaiting_review}
            hint={
              board.safety_awaiting_review > 0
                ? `${board.safety_awaiting_review} of them are safety items`
                : 'No safety items waiting'
            }
            tone={board.safety_awaiting_review > 0 ? 'critical' : undefined}
            toneLabel={board.safety_awaiting_review > 0 ? 'Safety first' : undefined}
          />
          <Stat
            label="Not yet in CxAlloy"
            value={board.undelivered}
            hint="Rulings somebody still has to enter by hand"
            tone={board.undelivered_failures > 0 ? 'serious' : undefined}
            toneLabel={
              board.undelivered_failures > 0
                ? `${board.undelivered_failures} failures`
                : undefined
            }
          />
          <Stat
            label="Unreconciled assets"
            value={board.unresolved_assets}
            hint="Growing faster than it clears means walking to wrong assets"
            tone={board.unresolved_assets > 0 ? 'warning' : 'good'}
            toneLabel={board.unresolved_assets > 0 ? 'Needs a person' : 'Clear'}
          />
          <Stat
            label="Lowest labeling rate"
            value={worstLabeling === null ? '—' : percent(worstLabeling)}
            hint="Share of passes carrying a note worth reading"
            tone={
              worstLabeling === null
                ? undefined
                : worstLabeling < 0.5
                  ? 'critical'
                  : worstLabeling < 0.8
                    ? 'warning'
                    : 'good'
            }
            toneLabel={
              worstLabeling === null
                ? undefined
                : worstLabeling < 0.5
                  ? 'Flywheel starving'
                  : worstLabeling < 0.8
                    ? 'Slipping'
                    : 'Healthy'
            }
          />
        </div>

        <div className="card">
          <div className="card-head">
            <h2>Reviewers</h2>
            <span className="card-note">Last 30 days</span>
          </div>
          {board.reviewers.length === 0 ? (
            <div className="empty">
              <div className="empty-title">No rulings yet</div>
              Throughput and labeling rate appear here once reviewing starts.
            </div>
          ) : (
            <div className="table-scroll" style={{ padding: '14px 4px 6px' }}>
              <table className="data">
                <thead>
                  <tr>
                    <th>Reviewer</th>
                    <th className="num">Rulings</th>
                    <th className="num">Passed</th>
                    <th className="num">Failed</th>
                    <th className="num">Recaptures</th>
                    <th style={{ minWidth: 170 }}>Labeling rate</th>
                  </tr>
                </thead>
                <tbody>
                  {board.reviewers.map((reviewer) => (
                    <tr key={reviewer.reviewer_id}>
                      <td>{reviewer.display_name}</td>
                      <td className="num">{reviewer.rulings}</td>
                      <td className="num">{reviewer.passes}</td>
                      <td className="num">{reviewer.fails}</td>
                      <td className="num">{reviewer.recaptures}</td>
                      <td>
                        <Meter value={reviewer.labeling_rate} n={reviewer.passes} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          <div className="card-head" style={{ borderBottom: 'none', borderTop: '1px solid var(--hairline)' }}>
            <span className="card-note">
              Labeling rate counts passes with a note of real substance. A fail or a
              recapture always carries one — the form will not submit without it.
            </span>
          </div>
        </div>

        <div className="section-gap">
          <Link href="/queue" className="btn btn-primary">
            Start reviewing
            {board.awaiting_review > 0 ? ` — ${board.awaiting_review} waiting` : ''}
          </Link>
        </div>
      </div>
    </>
  );
}
