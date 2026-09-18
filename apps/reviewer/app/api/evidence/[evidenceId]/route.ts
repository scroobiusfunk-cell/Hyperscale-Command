import { API_URL } from '../../../../lib/api';

/**
 * Streams one photo.
 *
 * Proxied rather than linked straight at object storage so that looking at
 * evidence needs the same identity as ruling on it.
 */
export async function GET(
  _request: Request,
  { params }: { params: Promise<{ evidenceId: string }> },
) {
  const { evidenceId } = await params;
  const upstream = await fetch(`${API_URL}/evidence/${evidenceId}/image`, {
    headers: process.env.FIE_DEV_USER_ID
      ? { 'X-Dev-User-Id': process.env.FIE_DEV_USER_ID }
      : {},
    cache: 'no-store',
  });

  if (!upstream.ok) {
    return new Response('Evidence not available', { status: upstream.status });
  }

  return new Response(upstream.body, {
    headers: {
      'Content-Type': upstream.headers.get('Content-Type') ?? 'application/octet-stream',
      'Cache-Control': 'private, max-age=300',
    },
  });
}
