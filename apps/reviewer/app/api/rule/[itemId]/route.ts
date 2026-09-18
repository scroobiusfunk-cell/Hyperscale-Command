import { NextResponse } from 'next/server';
import { apiFetch, ApiError } from '../../../../lib/api';

/** Records a ruling. The reviewer's identity is attached server-side. */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ itemId: string }> },
) {
  const { itemId } = await params;
  const body = await request.json();

  try {
    const ruling = await apiFetch(`/review/items/${itemId}/rule`, {
      method: 'POST',
      body: JSON.stringify(body),
    });
    return NextResponse.json(ruling);
  } catch (error) {
    const status = error instanceof ApiError ? error.status : 500;
    const detail = error instanceof ApiError ? error.message : 'Could not record that ruling.';
    return NextResponse.json({ detail }, { status });
  }
}
