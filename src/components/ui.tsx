import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { ChevronLeft, X } from 'lucide-react';

const Corners = () => (
  <>
    <i className="corner tl" /><i className="corner tr" /><i className="corner bl" /><i className="corner br" />
  </>
);

export function Blueprint({ children, className = '', as: Tag = 'div', ...rest }: { children: ReactNode; className?: string; as?: 'div' | 'button' } & ButtonHTMLAttributes<HTMLElement>) {
  const T = Tag as 'div';
  return <T className={`card blueprint ${className}`} {...(rest as object)}><Corners />{children}</T>;
}

export function Primary({ children, className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button className={`btn btn-primary blueprint ${className}`} {...rest}><Corners />{children}</button>;
}

export const Secondary = ({ className = '', ...rest }: ButtonHTMLAttributes<HTMLButtonElement>) =>
  <button className={`btn btn-secondary ${className}`} {...rest} />;

export const Kicker = ({ children, className = '' }: { children: ReactNode; className?: string }) =>
  <div className={`card-kicker ${className}`}>{children}</div>;

export const Label = ({ children }: { children: ReactNode }) => <Kicker className="label">{children}</Kicker>;

export const Cite = ({ children }: { children: ReactNode }) => <span className="tag tag-outline tag-cite">{children}</span>;

export const Tag = ({ kind, children, className = '' }: { kind: 'accent' | 'neutral' | 'outline'; children: ReactNode; className?: string }) =>
  <span className={`tag tag-${kind} ${className}`}>{children}</span>;

export const Bar = ({ pct, className = '' }: { pct: number; className?: string }) =>
  <div className={`progress ${className}`} role="progressbar" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><i style={{ width: `${pct}%` }} /></div>;

export const BackBtn = ({ label, onClick }: { label: string; onClick: () => void }) =>
  <button className="btn btn-ghost" style={{ alignSelf: 'flex-start', marginLeft: -8 }} onClick={onClick}><ChevronLeft size={18} strokeWidth={1.5} />{label}</button>;

export const CloseBtn = ({ label, onClick }: { label: string; onClick: () => void }) =>
  <button className="btn btn-ghost btn-icon hit" onClick={onClick} aria-label={label}><X size={20} strokeWidth={1.5} /></button>;

export function Chips({ items, value, onPick }: { items: string[]; value: string; onPick: (v: string) => void }) {
  return (
    <div className="chips">
      {items.map(c => (
        <button key={c} className={`btn ${value === c ? 'btn-primary' : 'btn-secondary'}`} aria-pressed={value === c} onClick={() => onPick(c)}>{c}</button>
      ))}
    </div>
  );
}

/** Answer option used by lesson checks and the spot-the-deficiency game. */
export function Option({ text, primary, mark, onClick, disabled, start }: { text: string; primary: boolean; mark?: string; onClick: () => void; disabled?: boolean; start?: boolean }) {
  return (
    <button className={`btn ${primary ? 'btn-primary' : 'btn-secondary'} opt ${start ? 'start' : ''}`} onClick={onClick} disabled={disabled} aria-pressed={primary}>
      <span>{text}</span>{mark ? <span className="mark">{mark}</span> : null}
    </button>
  );
}
