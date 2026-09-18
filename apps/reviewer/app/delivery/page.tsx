import { Topbar } from '../../components/Topbar';
import { Stat } from '../../components/Stat';
import { ConfigHint } from '../../components/ConfigHint';
import { DeliveryActions } from '../../components/DeliveryActions';
import { getDeliveryStatus, listExports, PROJECT_ID, ApiError } from '../../lib/api';

export const dynamic = 'force-dynamic';

export default async function DeliveryPage() {
  if (!PROJECT_ID) return <ConfigHint />;

  let status;
  let packages;
  try {
    [status, packages] = await Promise.all([
      getDeliveryStatus(PROJECT_ID),
      listExports(PROJECT_ID),
    ]);
  } catch (error) {
    return (
      <>
        <Topbar title="Delivery" />
        <div className="content">
          <div className="banner">
            Could not reach the API: {error instanceof ApiError ? error.message : String(error)}
          </div>
        </div>
      </>
    );
  }

  return (
    <>
      <Topbar
        title="Delivery to CxAlloy"
        subtitle="CxAlloy cannot be written to. These results are entered by hand."
      />
      <div className="content">
        <div className="banner">
          This platform&apos;s access to CxAlloy is read only and cannot be automated.
          Build a package, work through it in CxAlloy, then confirm delivery here — until
          somebody does, these rulings count as not yet in the system of record.
        </div>

        <div className="kpi-row">
          <Stat
            label="Waiting for a package"
            value={status.pending_export}
            hint="Ruled on, not yet in an export"
          />
          <Stat
            label="Exported, not confirmed"
            value={status.exported_not_confirmed}
            hint="Somebody has the file; nobody has said it is done"
            tone={status.exported_not_confirmed > 0 ? 'warning' : 'good'}
            toneLabel={status.exported_not_confirmed > 0 ? 'In progress' : 'Clear'}
          />
          <Stat
            label="Undelivered failures"
            value={status.undelivered_failures}
            hint="A defect nobody has been told to fix yet"
            tone={status.undelivered_failures > 0 ? 'critical' : 'good'}
            toneLabel={status.undelivered_failures > 0 ? 'Chase these' : 'None'}
          />
        </div>

        <DeliveryActions exports={packages} pendingExport={status.pending_export} />
      </div>
    </>
  );
}
