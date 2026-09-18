'use client';

/**
 * The ruling and its note, as one action.
 *
 * "The flywheel dies if reviewers clear items without labeling." So there is no
 * separate save-a-note step to skip: choosing a verdict and writing the note
 * are the same form and the same submit.
 *
 * A fail or a recapture cannot be submitted without a note — "this is wrong"
 * with nothing else said is not something a tech can act on. A pass can be
 * silent, and the dashboard counts how often it is.
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import type { Verdict } from '../lib/api';

const MIN_NOTE = 8;

const VERDICTS: { value: Verdict; label: string; key: string; className: string }[] = [
  { value: 'pass', label: 'Pass', key: 'p', className: 'pass' },
  { value: 'fail', label: 'Fail', key: 'f', className: 'fail' },
  { value: 'recapture_requested', label: 'Recapture', key: 'r', className: 'recapture' },
];

export function RulingForm({
  itemId,
  isSafety,
  nextItemId,
}: {
  itemId: string;
  isSafety: boolean;
  nextItemId: string | null;
}) {
  const router = useRouter();
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [note, setNote] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const noteRef = useRef<HTMLTextAreaElement>(null);

  const noteRequired = verdict === 'fail' || verdict === 'recapture_requested';
  const noteTooShort = note.trim().length < MIN_NOTE;
  const blocked = !verdict || (noteRequired && noteTooShort);

  const submit = useCallback(async () => {
    if (!verdict || busy) return;
    if (noteRequired && noteTooShort) {
      setError('Say what is wrong — the tech has to know what to do differently.');
      noteRef.current?.focus();
      return;
    }
    setBusy(true);
    setError(null);
    const response = await fetch(`/api/rule/${itemId}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ verdict, note: note.trim() || null }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      setError(body?.detail ?? 'That ruling could not be recorded.');
      setBusy(false);
      return;
    }
    // Straight on to the next one: reviewer minutes per inspection is the
    // number this whole product is judged on.
    router.push(nextItemId ? `/review/${nextItemId}` : '/queue');
    router.refresh();
  }, [verdict, busy, noteRequired, noteTooShort, itemId, note, nextItemId, router]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      const typing =
        event.target instanceof HTMLElement &&
        ['TEXTAREA', 'INPUT'].includes(event.target.tagName);

      if ((event.metaKey || event.ctrlKey) && event.key === 'Enter') {
        event.preventDefault();
        void submit();
        return;
      }
      if (typing) return;

      const match = VERDICTS.find((v) => v.key === event.key.toLowerCase());
      if (match) {
        event.preventDefault();
        setVerdict(match.value);
        setError(null);
        if (match.value !== 'pass') noteRef.current?.focus();
      }
    }
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [submit]);

  return (
    <div className="card">
      <div className="card-head">
        <h2>Your ruling</h2>
        <span className="card-note">
          <kbd className="mono">⌘</kbd>+<kbd className="mono">↵</kbd> to submit
        </span>
      </div>
      <div className="card-body ruling">
        {isSafety ? (
          <div className="safety-banner">
            <span aria-hidden="true">▲</span>
            <span>
              <strong>Safety item.</strong> This carries your name and cannot be edited
              afterwards. A correction is a new ruling, recorded alongside this one.
            </span>
          </div>
        ) : null}

        <div className="verdicts" role="group" aria-label="Verdict">
          {VERDICTS.map((option) => (
            <button
              key={option.value}
              type="button"
              className={`verdict ${option.className}`}
              aria-pressed={verdict === option.value}
              onClick={() => {
                setVerdict(option.value);
                setError(null);
                if (option.value !== 'pass') noteRef.current?.focus();
              }}
            >
              {option.label}
              <kbd>{option.key.toUpperCase()}</kbd>
            </button>
          ))}
        </div>

        <div className="note-field">
          <label htmlFor="note">
            Note
            {noteRequired ? (
              <span className="req">Required for a fail or recapture</span>
            ) : (
              <span className="opt">Optional on a pass — but it is what trains the tool</span>
            )}
          </label>
          <textarea
            id="note"
            ref={noteRef}
            value={note}
            placeholder={
              verdict === 'recapture_requested'
                ? 'What is wrong with the photo, and what should they do differently?'
                : verdict === 'fail'
                  ? 'What is wrong with the installation?'
                  : 'Anything worth recording about this one.'
            }
            onChange={(event) => {
              setNote(event.target.value);
              if (error) setError(null);
            }}
          />
        </div>

        {error ? (
          <p className="form-error" role="alert">
            <span aria-hidden="true">▲</span>
            {error}
          </p>
        ) : null}

        <div className="row-between">
          <span className="card-note">
            {nextItemId ? 'Goes straight to the next item' : 'Last one in the queue'}
          </span>
          <button
            type="button"
            className="btn btn-primary"
            disabled={blocked || busy}
            onClick={() => void submit()}
          >
            {busy ? 'Recording…' : 'Record ruling'}
          </button>
        </div>
      </div>
    </div>
  );
}
