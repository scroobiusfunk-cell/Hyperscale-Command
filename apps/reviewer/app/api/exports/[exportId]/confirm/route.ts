import { NextResponse } from 'next/server';
import { apiFetch, ApiError } from '../../../../../lib/api';

/**
 * A person says the import into CxAlloy is done.
 *
 * This is the only thing that clears the undelivered count, and the platform
 * cannot do it on anyone's behalf — its access to CxAlloy is read only.
 */
export async function POST(
  _request: Request,
  { params }: { params: Promise<{ exportId: string }> },
) {
  const { exportId } = await params;

  try {
    const confirmed = await apiFetch(`/exports/${exportId}/confirm-delivery`, { method: 'POST' });
    return NextResponse.json(confirmed);
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 500;
    const detail =
      error instanceof ApiError ? error.message : 'Could not confirm that package.';
    return NextResponse.json({ detail }, { status });
  }
}
