import { useEffect, useMemo, useRef, useState } from 'react';
import { forceCollide, forceLink, forceManyBody, forceSimulation, forceX, forceY } from 'd3-force';
import type { VaultIndex } from '../../tools/vault-lib.mjs';

const W = 1000, H = 720;
// Side-view brain: cerebrum, cerebellum, brain stem (world coords).
const inCerebrum = (x: number, y: number) => ((x - 500) / 372) ** 2 + ((y - 300) / 246) ** 2 <= 1;
const inCerebellum = (x: number, y: number) => ((x - 735) / 138) ** 2 + ((y - 585) / 68) ** 2 <= 1;
const inStem = (x: number, y: number) => ((x - 610) / 34) ** 2 + ((y - 640) / 72) ** 2 <= 1;
const inside = (x: number, y: number) => inCerebrum(x, y) || inCerebellum(x, y) || inStem(x, y);

const LOBES: Record<string, [number, number]> = {
  Work: [330, 190], Training: [560, 120], Projects: [215, 340], 'White Papers': [450, 310],
  Meetings: [700, 210], Personal: [760, 360], People: [380, 440], Orgs: [600, 430],
  Topics: [300, 260], Index: [500, 290], Library: [735, 585],
};

/** Wobbly closed outline: an ellipse whose radius ripples like gyri. */
const wobble = (c: CanvasRenderingContext2D, cx: number, cy: number, rx: number, ry: number, amp: number, f1: number, f2: number, ph = 0) => {
  c.beginPath();
  for (let i = 0; i <= 240; i++) {
    const t = (i / 240) * Math.PI * 2, f = 1 + amp * (Math.sin(f1 * t + ph) + 0.6 * Math.sin(f2 * t + ph * 2));
    const x = cx + rx * f * Math.cos(t), y = cy + ry * f * Math.sin(t);
    i ? c.lineTo(x, y) : c.moveTo(x, y);
  }
  c.closePath();
};

interface N { id: string; area: string; title: string; deg: number; r: number; x: number; y: number; vx?: number; vy?: number; flash: number; hue: number }
interface Pulse { a: number; b: number; t: number; speed: number }

export default function Brain({ index, current, highlight, onOpen }: { index: VaultIndex; current: string; highlight: Set<string> | null; onOpen: (id: string) => void }) {
  const canvas = useRef<HTMLCanvasElement>(null);
  const wrap = useRef<HTMLDivElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number; text: string } | null>(null);
  const state = useRef({ hover: -1, tx: 0, ty: 0, k: 1, drag: null as null | { x: number; y: number; tx: number; ty: number; moved: boolean } });
  const live = useRef({ highlight, current });
  live.current = { highlight, current };
  const openRef = useRef(onOpen); openRef.current = onOpen;

  const model = useMemo(() => {
    const areas = [...new Set(index.notes.map(n => n.area))];
    const deg = new Map<string, number>();
    for (const e of index.edges) { deg.set(e.source, (deg.get(e.source) || 0) + 1); deg.set(e.target, (deg.get(e.target) || 0) + 1); }
    const nodes: N[] = index.notes.map((n, i) => {
      const d = deg.get(n.id) || 0;
      const lobe = LOBES[n.area] || [500 + 200 * Math.cos(i), 300 + 150 * Math.sin(i)];
      return { id: n.id, area: n.area, title: n.title, deg: d, r: Math.min(13, 2.6 + Math.sqrt(d) * 1.7), x: lobe[0] + (Math.random() - 0.5) * 140, y: lobe[1] + (Math.random() - 0.5) * 120, flash: 0, hue: (areas.indexOf(n.area) * 47 + 190) % 360 };
    });
    const idx = new Map(nodes.map((n, i) => [n.id, i]));
    const edges = index.edges.filter(e => idx.has(e.source) && idx.has(e.target)).map(e => [idx.get(e.source)!, idx.get(e.target)!] as [number, number]);
    return { nodes, edges, nbrs: nodes.map(() => new Set<number>()) };
  }, [index]);

  useEffect(() => {
    const cv = canvas.current!, box = wrap.current!;
    const ctx = cv.getContext('2d')!;
    const { nodes, nbrs, edges } = model;
    nbrs.forEach(x => x.clear());
    edges.forEach(([a, b]) => { nbrs[a].add(b); nbrs[b].add(a); });
    const links = edges.map(([a, b]) => ({ source: a as number | N, target: b as number | N }));
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    const S = state.current;

    const sim = forceSimulation(nodes as never[])
      .force('link', forceLink(links as never[]).distance(58).strength(0.12))
      .force('charge', forceManyBody().strength(-70).distanceMax(300))
      .force('collide', forceCollide<N>().radius(d => d.r + 6))
      .force('x', forceX<N>(d => (LOBES[d.area] || [500, 300])[0]).strength(0.045))
      .force('y', forceY<N>(d => (LOBES[d.area] || [500, 300])[1]).strength(0.045))
      .force('brain', () => { for (const n of nodes) if (!inside(n.x, n.y)) { n.x += (500 - n.x) * 0.18; n.y += (320 - n.y) * 0.18; } })
      .alphaDecay(0.012);
    if (reduce) { sim.stop(); for (let i = 0; i < 400; i++) sim.tick(); }

    let w = 0, h = 0, dpr = 1;
    const fit = () => {
      dpr = Math.min(2, window.devicePixelRatio || 1);
      w = box.clientWidth; h = box.clientHeight;
      cv.width = w * dpr; cv.height = h * dpr;
      const k = Math.min(w / W, h / H) * 0.96;
      if (!S.drag) { S.k = S.k === 1 && S.tx === 0 ? k : S.k; }
      if (S.tx === 0 && S.ty === 0) { S.k = k; S.tx = (w - W * k) / 2; S.ty = (h - H * k) / 2; }
    };
    fit();
    const ro = new ResizeObserver(() => { S.tx = 0; S.ty = 0; fit(); });
    ro.observe(box);

    const hubs = new Set([...nodes.keys()].sort((a, b) => nodes[b].deg - nodes[a].deg).slice(0, 7));
    const pulses: Pulse[] = [];
    let last = 0, spawn = 0, raf = 0;
    const toWorld = (px: number, py: number) => [(px - S.tx) / S.k, (py - S.ty) / S.k];
    const hit = (px: number, py: number) => {
      const [wx, wy] = toWorld(px, py); let best = -1, bd = 1e9;
      nodes.forEach((n, i) => { const d = Math.hypot(n.x - wx, n.y - wy); if (d < Math.max(10, n.r + 5) && d < bd) { bd = d; best = i; } });
      return best;
    };

    const folds: [number, number, number, number, number, number, number][] = [
      [0.84, 0.82, 0.011, 7, 13, 0.4, 0], [0.68, 0.66, 0.016, 5, 11, 1.3, 1], [0.52, 0.5, 0.02, 4, 9, 2.1, 2], [0.36, 0.34, 0.03, 3, 7, 0.7, 3],
    ];
    const outline = (c: CanvasRenderingContext2D) => { wobble(c, 500, 300, 400, 265, 0.028, 9, 15, 1); };

    const draw = (ts: number) => {
      const dt = Math.min(50, ts - last || 16); last = ts;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      const bg = ctx.createRadialGradient(w / 2, h / 2, 10, w / 2, h / 2, Math.max(w, h) * 0.7);
      bg.addColorStop(0, '#0b1224'); bg.addColorStop(1, '#03050b');
      ctx.fillStyle = bg; ctx.fillRect(0, 0, w, h);
      ctx.setTransform(dpr * S.k, 0, 0, dpr * S.k, dpr * S.tx, dpr * S.ty);

      // brain silhouette with soft glow
      const t = ts / 1000, breathe = 0.5 + 0.5 * Math.sin(t * 1.3);
      ctx.save();
      ctx.shadowColor = `rgba(90,150,255,${0.35 + 0.25 * breathe})`; ctx.shadowBlur = 26;
      ctx.strokeStyle = 'rgba(120,170,255,0.38)'; ctx.lineWidth = 1.6;
      outline(ctx); ctx.fillStyle = 'rgba(70,110,200,0.05)'; ctx.fill(); ctx.stroke();
      wobble(ctx, 735, 585, 150, 78, 0.05, 14, 23, 0.5); ctx.fill(); ctx.stroke();
      wobble(ctx, 610, 640, 42, 80, 0.015, 5, 8, 0); ctx.fill(); ctx.stroke();
      ctx.restore();
      // gyri / sulci
      ctx.lineWidth = 1;
      for (const [fx, fy, a, f1, f2, ph, i] of folds) {
        ctx.strokeStyle = `rgba(120,170,255,${0.06 + 0.04 * Math.sin(t * 0.8 + i)})`;
        wobble(ctx, 500, 300, 400 * fx, 265 * fy, a, f1, f2, ph); ctx.stroke();
      }
      ctx.strokeStyle = 'rgba(120,170,255,0.08)';
      ctx.beginPath(); ctx.moveTo(470, 40); ctx.bezierCurveTo(430, 150, 540, 220, 480, 330); ctx.stroke();
      wobble(ctx, 735, 585, 105, 50, 0.06, 14, 23, 0.5); ctx.stroke();

      const { highlight: hl, current: cur } = live.current;
      const hv = S.hover, hn = hv >= 0 ? nbrs[hv] : null;
      const dimmed = (i: number) => (hv >= 0 && i !== hv && !hn!.has(i)) || (hl && hl.size > 0 && !hl.has(nodes[i].id));

      // synapses
      ctx.lineCap = 'round';
      for (const [ia, ib] of edges) {
        const a = nodes[ia], b = nodes[ib];
        const active = hv >= 0 && (ia === hv || ib === hv);
        const dm = dimmed(ia) && dimmed(ib);
        ctx.strokeStyle = active ? 'rgba(160,210,255,0.75)' : dm ? 'rgba(110,150,230,0.03)' : 'rgba(110,150,230,0.13)';
        ctx.lineWidth = active ? 1.4 : 0.7;
        const mx = (a.x + b.x) / 2 + (b.y - a.y) * 0.08, my = (a.y + b.y) / 2 - (b.x - a.x) * 0.08;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(mx, my, b.x, b.y); ctx.stroke();
      }

      // signals travelling along synapses
      if (!reduce) {
        spawn += dt;
        if (spawn > 90 && pulses.length < 60 && edges.length) {
          spawn = 0;
          const [ea, eb] = edges[Math.floor(Math.random() * edges.length)];
          const fwd = Math.random() < 0.5;
          pulses.push({ a: fwd ? ea : eb, b: fwd ? eb : ea, t: 0, speed: 0.0007 + Math.random() * 0.0009 });
        }
        ctx.globalCompositeOperation = 'lighter';
        for (let i = pulses.length - 1; i >= 0; i--) {
          const p = pulses[i]; p.t += p.speed * dt;
          const A = nodes[p.a], B = nodes[p.b];
          if (p.t >= 1) { B.flash = 1; pulses.splice(i, 1); continue; }
          const mx = (A.x + B.x) / 2 + (B.y - A.y) * 0.08, my = (A.y + B.y) / 2 - (B.x - A.x) * 0.08;
          const u = p.t, x = (1 - u) * (1 - u) * A.x + 2 * (1 - u) * u * mx + u * u * B.x, y = (1 - u) * (1 - u) * A.y + 2 * (1 - u) * u * my + u * u * B.y;
          const g = ctx.createRadialGradient(x, y, 0, x, y, 7);
          g.addColorStop(0, `hsla(${A.hue},100%,80%,0.95)`); g.addColorStop(1, `hsla(${A.hue},100%,60%,0)`);
          ctx.fillStyle = g; ctx.beginPath(); ctx.arc(x, y, 7, 0, 7); ctx.fill();
        }
        ctx.globalCompositeOperation = 'source-over';
      }

      // neurons
      ctx.globalCompositeOperation = 'lighter';
      nodes.forEach((n, i) => {
        n.flash = Math.max(0, n.flash - dt / 700);
        const dm = dimmed(i), isCur = n.id === cur, isHv = i === hv, lit = hl?.has(n.id);
        const pulse = 0.85 + 0.15 * Math.sin(t * 2 + i);
        const gr = n.r * (isHv ? 5 : 3.6) * (1 + n.flash * 0.9) * pulse;
        const al = dm ? 0.1 : 0.55 + n.flash * 0.45 + (isCur || lit ? 0.3 : 0);
        const g = ctx.createRadialGradient(n.x, n.y, 0, n.x, n.y, gr);
        g.addColorStop(0, `hsla(${n.hue},95%,70%,${al})`); g.addColorStop(0.35, `hsla(${n.hue},90%,55%,${al * 0.35})`); g.addColorStop(1, `hsla(${n.hue},90%,50%,0)`);
        ctx.fillStyle = g; ctx.beginPath(); ctx.arc(n.x, n.y, gr, 0, 7); ctx.fill();
      });
      ctx.globalCompositeOperation = 'source-over';
      nodes.forEach((n, i) => {
        const dm = dimmed(i), isCur = n.id === cur;
        ctx.fillStyle = dm ? 'rgba(200,215,255,0.25)' : `hsl(${n.hue},90%,${78 + n.flash * 15}%)`;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r * 0.55 + (isCur ? 1.5 : 0), 0, 7); ctx.fill();
        if (isCur) { ctx.strokeStyle = '#fff'; ctx.lineWidth = 1.2; ctx.beginPath(); ctx.arc(n.x, n.y, n.r + 3, 0, 7); ctx.stroke(); }
      });
      // labels for hubs / hover / current
      ctx.font = '11px Barlow, system-ui, sans-serif'; ctx.textBaseline = 'middle';
      nodes.forEach((n, i) => {
        const show = i === hv || n.id === cur || (hn && hn.has(i)) || (!hn && hubs.has(i) && !(hl && hl.size));
        if (!show || dimmed(i)) return;
        ctx.fillStyle = 'rgba(225,235,255,0.92)'; ctx.fillText(n.title.length > 30 ? n.title.slice(0, 29) + '…' : n.title, n.x + n.r + 5, n.y);
      });

      raf = requestAnimationFrame(draw);
    };
    raf = requestAnimationFrame(draw);

    const pos = (e: PointerEvent | WheelEvent) => { const r = cv.getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; };
    const onMove = (e: PointerEvent) => {
      const [x, y] = pos(e);
      if (S.drag) {
        if (Math.hypot(x - S.drag.x, y - S.drag.y) > 3) S.drag.moved = true;
        S.tx = S.drag.tx + (x - S.drag.x); S.ty = S.drag.ty + (y - S.drag.y); return;
      }
      S.hover = hit(x, y); cv.style.cursor = S.hover >= 0 ? 'pointer' : 'grab';
      setTip(S.hover >= 0 ? { x, y, text: `${nodes[S.hover].title} · ${nodes[S.hover].area}` } : null);
    };
    const onDown = (e: PointerEvent) => { const [x, y] = pos(e); S.drag = { x, y, tx: S.tx, ty: S.ty, moved: false }; cv.setPointerCapture(e.pointerId); };
    const onUp = (e: PointerEvent) => {
      const d = S.drag; S.drag = null; if (!d) return;
      if (!d.moved) { const [x, y] = pos(e); const i = hit(x, y); if (i >= 0) openRef.current(nodes[i].id); }
    };
    const onLeave = () => { S.hover = -1; setTip(null); };
    const onWheel = (e: WheelEvent) => {
      e.preventDefault(); const [x, y] = pos(e); const f = Math.exp(-e.deltaY * 0.0012), k = Math.max(0.4, Math.min(5, S.k * f));
      S.tx = x - (x - S.tx) * (k / S.k); S.ty = y - (y - S.ty) * (k / S.k); S.k = k;
    };
    cv.addEventListener('pointermove', onMove); cv.addEventListener('pointerdown', onDown); cv.addEventListener('pointerup', onUp);
    cv.addEventListener('pointerleave', onLeave); cv.addEventListener('wheel', onWheel, { passive: false });
    return () => { cancelAnimationFrame(raf); sim.stop(); ro.disconnect(); cv.removeEventListener('pointermove', onMove); cv.removeEventListener('pointerdown', onDown); cv.removeEventListener('pointerup', onUp); cv.removeEventListener('pointerleave', onLeave); cv.removeEventListener('wheel', onWheel); };
  }, [model]);

  const areas = [...new Set(index.notes.map(n => n.area))];
  return (
    <div ref={wrap} className="brain" role="img" aria-label="Brain-shaped network of notes. Click a neuron to open the note.">
      <canvas ref={canvas} style={{ width: '100%', height: '100%', touchAction: 'none', cursor: 'grab' }} />
      {tip && <div className="brain-tip" style={{ left: tip.x + 14, top: tip.y + 14 }}>{tip.text}</div>}
      <div className="brain-legend">
        {areas.map(a => <span key={a}><i style={{ background: `hsl(${(areas.indexOf(a) * 47 + 190) % 360} 90% 62%)` }} />{a}</span>)}
      </div>
      <div className="brain-hint">drag to pan · scroll to zoom · click a neuron</div>
    </div>
  );
}
