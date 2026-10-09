import { useCallback, useEffect, useState } from 'react';
import type { TrackKey } from '../content/types';
import type { Ack } from '../lib/logic';

export const STORAGE_KEY = 'cxpath-v2';

export interface Persisted {
  track: TrackKey | null;
  done: number[];
  best: number | null;
  ack: Ack | null;
}

const EMPTY: Persisted = { track: null, done: [], best: null, ack: null };

export function loadPersisted(): Persisted {
  try {
    const raw = JSON.parse(localStorage.getItem(STORAGE_KEY) || '{}') || {};
    return {
      track: ['aw', 'pr', 'ad'].includes(raw.track) ? raw.track : null,
      done: Array.isArray(raw.done) ? raw.done.filter((n: unknown) => Number.isInteger(n)) : [],
      best: typeof raw.best === 'number' ? raw.best : null,
      ack: raw.ack && typeof raw.ack.name === 'string' ? raw.ack : null,
    };
  } catch {
    return EMPTY;
  }
}

export function usePersisted() {
  const [state, setState] = useState<Persisted>(loadPersisted);
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch {
      /* storage unavailable: session-only */
    }
  }, [state]);
  const patch = useCallback((p: Partial<Persisted> | ((s: Persisted) => Partial<Persisted>)) =>
    setState(s => ({ ...s, ...(typeof p === 'function' ? p(s) : p) })), []);
  return [state, patch] as const;
}
