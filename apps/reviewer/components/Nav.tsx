'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const LINKS = [
  { href: '/', label: 'Overview' },
  { href: '/queue', label: 'Review queue' },
  { href: '/delivery', label: 'Delivery' },
];

export function Nav() {
  const pathname = usePathname();

  return (
    <nav className="sidebar" aria-label="Sections">
      <div className="brand">
        <span className="brand-mark" aria-hidden="true">
          FI
        </span>
        <span>
          <span className="brand-name">Reviewer console</span>
          <br />
          <span className="brand-sub">Field Inspection Engine</span>
        </span>
      </div>

      <div className="nav">
        {LINKS.map((link) => {
          const active =
            link.href === '/' ? pathname === '/' : pathname.startsWith(link.href);
          return (
            <Link
              key={link.href}
              href={link.href}
              className="nav-link"
              aria-current={active ? 'page' : undefined}
            >
              {link.label}
            </Link>
          );
        })}
      </div>

      <div className="sidebar-foot">
        Phase 1 — every item is ruled on by a person. Nothing clears automatically.
      </div>
    </nav>
  );
}
