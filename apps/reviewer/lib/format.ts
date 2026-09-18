/** Formatting a reviewer reads at a glance. */

export function waitingFor(iso: string | null): string {
  if (!iso) return 'no evidence yet';
  const minutes = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 60000));
  if (minutes < 1) return 'just now';
  if (minutes < 60) return `${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 48) return `${hours} h`;
  return `${Math.round(hours / 24)} d`;
}

export function shortTime(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  });
}

export function percent(value: number): string {
  return `${Math.round(value * 100)}%`;
}

/** Describe pass criteria in words, never as raw JSON. */
export function describeCriteria(criteria: Record<string, unknown>): string {
  const kind = criteria.kind;
  if (kind === 'presence') {
    const subject = String(criteria.subject ?? 'the item');
    const expected = criteria.expected === 'absent' ? 'must not be fitted' : 'must be fitted';
    return `${subject.charAt(0).toUpperCase()}${subject.slice(1)} ${expected}.`;
  }
  if (kind === 'pattern') {
    return String(criteria.description ?? 'Text must match the expected format.');
  }
  if (kind === 'expected_value') {
    const unit = criteria.unit ? ` ${String(criteria.unit)}` : '';
    return `Expected ${String(criteria.value)}${unit}, per the ${String(
      criteria.source_of_truth ?? 'specification',
    ).replace(/_/g, ' ')}.`;
  }
  if (kind === 'tolerance') {
    return `Expected ${String(criteria.nominal)} ${String(criteria.unit)}, +${String(
      criteria.plus,
    )} / -${String(criteria.minus)}.`;
  }
  return 'See the source clause.';
}
