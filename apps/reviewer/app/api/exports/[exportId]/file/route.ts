import { API_URL } from '../../../../../lib/api';

/**
 * Streams one package.
 *
 * Proxied rather than linked at object storage, for the same reason the
 * evidence route is: downloading every ruling on the job should need the same
 * identity as making one, and a signed URL outlives the session it was made in.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ exportId: string }> },
) {
  const { exportId } = await params;
  const upstream = await fetch(`${API_URL}/exports/${exportId}/file`, {
    headers: process.env.UNDERSTUDY_DEV_USER_ID
      ? { 'X-Dev-User-Id': process.env.UNDERSTUDY_DEV_USER_ID }
      : {},
    cache: 'no-store',
  });

  if (!upstream.ok) {
    return new Response('That package is not available.', { status: upstream.status });
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type': 'application/zip',
      'Content-Disposition':
        upstream.headers.get('Content-Disposition') ??
        `attachment; filename="understudy-export-${exportId}.zip"`,
      'Cache-Control': 'no-store',
    },
  });
}
