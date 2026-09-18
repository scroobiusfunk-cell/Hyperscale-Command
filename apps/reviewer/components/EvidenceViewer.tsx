'use client';

/**
 * The evidence, big.
 *
 * A reviewer ruling on a photograph they cannot see properly is the failure
 * this screen exists to prevent, so the image gets the space and everything
 * else fits around it.
 */

import { useEffect, useState } from 'react';
import type { EvidenceRef } from '../lib/api';
import { Chip } from './Chip';
import { shortTime } from '../lib/format';

export function EvidenceViewer({ evidence }: { evidence: EvidenceRef[] }) {
  const [index, setIndex] = useState(0);
  const current = evidence[index];

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.target instanceof HTMLElement && ['TEXTAREA', 'INPUT'].includes(event.target.tagName)) {
        return;
      }
      if (event.key === 'ArrowRight') setIndex((i) => Math.min(i + 1, evidence.length - 1));
      if (event.key === 'ArrowLeft') setIndex((i) => Math.max(i - 1, 0));
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [evidence.length]);

  if (evidence.length === 0) {
    return (
      <div className="evidence-stage">
        <div className="evidence-frame">
          <p className="evidence-missing">
            No evidence has reached the server for this item yet. If the tech has
            synced, the photos may still be uploading.
          </p>
        </div>
      </div>
    );
  }

  const failedGates = (current?.gate_results ?? []).filter((g) => g.outcome === 'failed');

  return (
    <div className="evidence-stage">
      <div className="evidence-frame">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={`/api/evidence/${current.evidence_id}`}
          alt={`Evidence ${index + 1} of ${evidence.length}, capture step ${current.step_index + 1}`}
        />
      </div>
      <div className="evidence-bar">
        <div className="thumbs">
          {evidence.map((item, position) => (
            <button
              key={item.evidence_id}
              type="button"
              className="thumb"
              aria-current={position === index}
              aria-label={`Show evidence ${position + 1}`}
              onClick={() => setIndex(position)}
            >
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={`/api/evidence/${item.evidence_id}`} alt="" />
            </button>
          ))}
        </div>
        <div className="queue-meta">
          {current.is_retake ? <Chip tone="warning">Retake</Chip> : null}
          {failedGates.length > 0 ? (
            <Chip tone="serious">{failedGates.length} gate failed</Chip>
          ) : null}
          <span>Taken {shortTime(current.captured_at)}</span>
          {evidence.length > 1 ? (
            <span>
              <kbd className="mono">←</kbd> <kbd className="mono">→</kbd> to switch
            </span>
          ) : null}
          <span className="mono">
            {index + 1}/{evidence.length}
          </span>
        </div>
      </div>
    </div>
  );
}
