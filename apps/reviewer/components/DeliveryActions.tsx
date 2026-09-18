'use client';

/**
 * The three things the Delivery page describes, as three things you can do.
 *
 * The page already explained the workflow — build a package, work through it in
 * CxAlloy, confirm it here — and offered no way to perform any of it. Reading
 * instructions for a process with no controls is worse than no page at all: it
 * tells somebody the platform does something it does not.
 *
 * Confirming is deliberately the heaviest action on the screen. It is the only
 * thing that clears the undelivered count, it clears it for everybody, and the
 * platform cannot check whether it is true: our access to CxAlloy is read only.
 * So it says what it is asserting, and it asks once more before it does it.
 */

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import type { ExportRecord } from '../lib/api';
import { shortTime, waitingFor } from '../lib/format';

/** `waitingFor` already reads as a phrase for the recent case. */
function builtWhen(iso: string): string {
  const elapsed = waitingFor(iso);
  return elapsed === 'just now' ? elapsed : `${elapsed} ago`;
}

function StatusChip({ record }: { record: ExportRecord }) {
  if (record.status === 'failed') {
    return (
      <span className="chip is-critical">
        <span className="chip-dot" />
        Did not build
      </span>
    );
  }
  if (record.confirmed_at) {
    return (
      <span className="chip is-good">
        <span className="chip-dot" />
        Entered in CxAlloy
      </span>
    );
  }
  if (!record.has_file) {
    return (
      <span className="chip">
        <span className="chip-dot" />
        Nothing was waiting
      </span>
    );
  }
  return (
    <span className="chip is-warning">
      <span className="chip-dot" />
      Waiting to be entered
    </span>
  );
}

export function DeliveryActions({
  exports,
  pendingExport,
}: {
  exports: ExportRecord[];
  pendingExport: number;
}) {
  const router = useRouter();
  const [busy, setBusy] = useState<string | null>(null);
  const [confirming, setConfirming] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  async function post(path: string, key: string) {
    setBusy(key);
    setError(null);
    const response = await fetch(path, { method: 'POST' });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body?.detail ?? 'That did not work.');
      setBusy(null);
      return false;
    }
    setBusy(null);
    router.refresh();
    return true;
  }

  return (
    <>
      <div className="card">
        <div className="card-head">
          <h2>Build a package</h2>
          <span className="card-note">
            {pendingExport > 0
              ? `${pendingExport} ruling${pendingExport === 1 ? '' : 's'} waiting`
              : 'Nothing waiting'}
          </span>
        </div>
        <div className="card-body">
          <p className="muted" style={{ fontSize: '0.86rem', margin: '0 0 14px' }}>
            One zip holding every ruling not yet entered: a worklist to type from, the
            failures on their own sheet, and the photographs. A ruling already in a package
            is not included again, so building twice does not duplicate anything.
          </p>
          <button
            type="button"
            className="btn btn-primary"
            disabled={busy !== null || pendingExport === 0}
            onClick={() => void post('/api/exports', 'build')}
          >
            {busy === 'build'
              ? 'Building…'
              : pendingExport > 0
                ? `Build a package — ${pendingExport} ruling${pendingExport === 1 ? '' : 's'}`
                : 'Nothing to package'}
          </button>
        </div>
      </div>

      {error ? (
        <div className="banner is-critical" role="alert">
          <strong>Could not do that.</strong> {error}
        </div>
      ) : null}

      <div className="card">
        <div className="card-head">
          <h2>Packages</h2>
          <span className="card-note">Newest first</span>
        </div>

        {exports.length === 0 ? (
          <div className="empty">
            <div className="empty-title">No packages yet</div>
            Nothing has been handed to anybody to enter.
          </div>
        ) : (
          <div className="table-scroll" style={{ padding: '14px 4px 6px' }}>
            <table className="data">
              <thead>
                <tr>
                  <th>Built</th>
                  <th className="num">Rulings</th>
                  <th className="num">Failures</th>
                  <th>State</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {exports.map((record) => (
                  <tr key={record.id}>
                    <td>
                      {shortTime(record.created_at)}
                      <div className="history-when">{builtWhen(record.created_at)}</div>
                    </td>
                    <td className="num">{record.item_count}</td>
                    <td className="num">{record.failure_count || '—'}</td>
                    <td>
                      <StatusChip record={record} />
                      {record.confirmed_at ? (
                        <div className="history-when">{shortTime(record.confirmed_at)}</div>
                      ) : null}
                    </td>
                    <td style={{ textAlign: 'right', whiteSpace: 'nowrap' }}>
                      {record.has_file ? (
                        <a
                          className="btn btn-ghost"
                          href={`/api/exports/${record.id}/file`}
                          download
                        >
                          Download
                        </a>
                      ) : null}{' '}
                      {record.has_file && !record.confirmed_at ? (
                        confirming === record.id ? (
                          <button
                            type="button"
                            className="btn btn-primary"
                            disabled={busy !== null}
                            onClick={() =>
                              void post(`/api/exports/${record.id}/confirm`, record.id)
                            }
                          >
                            {busy === record.id ? 'Recording…' : 'Yes — all of them are in'}
                          </button>
                        ) : (
                          <button
                            type="button"
                            className="btn btn-ghost"
                            disabled={busy !== null}
                            onClick={() => {
                              setConfirming(record.id);
                              setError(null);
                            }}
                          >
                            I have entered these
                          </button>
                        )
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {confirming ? (
          <div className="card-head" style={{ borderTop: '1px solid var(--hairline)' }}>
            <span className="card-note">
              Confirming says every ruling in that package is now in CxAlloy. It clears the
              undelivered count for everyone, and nothing here can check it — our access to
              CxAlloy is read only.
            </span>
          </div>
        ) : null}
      </div>
    </>
  );
}
