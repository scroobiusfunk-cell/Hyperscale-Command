import { Topbar } from './Topbar';

/** What to do when the console has not been pointed at anything yet. */
export function ConfigHint() {
  return (
    <>
      <Topbar title="Reviewer console" subtitle="Not configured yet" />
      <div className="content">
        <div className="card">
          <div className="card-head">
            <h2>Point this at a project</h2>
          </div>
          <div className="card-body">
            <p style={{ marginTop: 0 }}>
              Set these in <code className="mono">apps/reviewer/.env.local</code>:
            </p>
            <pre
              className="mono"
              style={{
                background: 'var(--surface-sunken)',
                padding: '12px 14px',
                borderRadius: 'var(--radius)',
                fontSize: '0.82rem',
                overflowX: 'auto',
              }}
            >{`FIE_API_URL=http://127.0.0.1:8000
FIE_PROJECT_ID=<a project uuid>
FIE_DEV_USER_ID=<a reviewer's user uuid>`}</pre>
            <p className="muted" style={{ fontSize: '0.85rem' }}>
              The dev user id stands in for company SSO, and the API refuses to start
              with it enabled outside development.
            </p>
          </div>
        </div>
      </div>
    </>
  );
}
