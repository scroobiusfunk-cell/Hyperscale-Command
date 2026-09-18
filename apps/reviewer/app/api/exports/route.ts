import { NextResponse } from 'next/server';
import { apiFetch, ApiError, PROJECT_ID } from '../../../lib/api';

/**
 * Builds one package out of every ruling not yet entered into CxAlloy.
 *
 * The project comes from the server's own configuration, not from the request.
 * A console that let the page name the project would let anybody with the page
 * open build a package for a job that is not theirs.
 */
export async function POST() {
  if (!PROJECT_ID) {
    return NextResponse.json({ detail: 'No project is configured.' }, { status: 500 });
  }

  try {
    const built = await apiFetch(`/projects/${PROJECT_ID}/exports`, { method: 'POST' });
    return NextResponse.json(built, { status: 201 });
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 500;
    const detail = error instanceof ApiError ? error.message : 'Could not build a package.';
    return NextResponse.json({ detail }, { status });
  }
}
