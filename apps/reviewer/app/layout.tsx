import type { Metadata } from 'next';
import type { ReactNode } from 'react';
import './globals.css';
import { Nav } from '../components/Nav';

export const metadata: Metadata = {
  title: 'Reviewer console — Inspection Understudy AI',
  description: 'Evidence by item, one-action rulings, and what is waiting.',
};

export default function RootLayout({ children }: { children: ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="shell">
          <Nav />
          <div className="main">{children}</div>
        </div>
      </body>
    </html>
  );
}
