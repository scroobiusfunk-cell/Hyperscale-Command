import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { BrainMap, GraphNode, MapNode } from '../types'

const PANE = 'brain-map'
const MAX_DEPTH = 6
const MAX_NOTES = 250
const NOTE = /\.(md|markdown)$/i
const DEFAULT_ROOT = 'C:/Users/DButler/Second Brain'
const COLORS = ['cyan', 'magenta', 'yellow', 'green', 'blue', 'red']
const map = atom({ plugin: 'brain-map', key: 'map' } as const, null)

// Obsidian-style force layout in the unit square: links pull, notes push apart.
function layout(nodes: GraphNode[], edges: [number, number][]) {
  const n = nodes.length
  nodes.forEach((p, i) => {
    const a = (i / Math.max(1, n)) * Math.PI * 2
    p.x = 0.5 + 0.4 * Math.cos(a) * (0.5 + ((i * 7919) % 100) / 200)
    p.y = 0.5 + 0.4 * Math.sin(a) * (0.5 + ((i * 104729) % 100) / 200)
  })
  const k = Math.sqrt(1 / Math.max(1, n)) * 0.9
  for (let it = 0; it < 150; it++) {
    const t = 0.08 * (1 - it / 150) + 0.002
    const dx = new Array(n).fill(0)
    const dy = new Array(n).fill(0)
    for (let i = 0; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        let vx = nodes[i].x - nodes[j].x
        let vy = nodes[i].y - nodes[j].y
        const d = Math.max(0.001, Math.hypot(vx, vy))
        const f = (k * k) / d
        vx = (vx / d) * f; vy = (vy / d) * f
        dx[i] += vx; dy[i] += vy; dx[j] -= vx; dy[j] -= vy
      }
    }
    for (const [a, b] of edges) {
      const vx = nodes[a].x - nodes[b].x
      const vy = nodes[a].y - nodes[b].y
      const d = Math.max(0.001, Math.hypot(vx, vy))
      const f = (d * d) / k
      dx[a] -= (vx / d) * f; dy[a] -= (vy / d) * f; dx[b] += (vx / d) * f; dy[b] += (vy / d) * f
    }
    for (let i = 0; i < n; i++) {
      dx[i] += (0.5 - nodes[i].x) * 0.05; dy[i] += (0.5 - nodes[i].y) * 0.05
      const d = Math.max(0.0001, Math.hypot(dx[i], dy[i]))
      nodes[i].x += (dx[i] / d) * Math.min(d, t)
      nodes[i].y += (dy[i] / d) * Math.min(d, t)
    }
  }
  const xs = nodes.map(p => p.x), ys = nodes.map(p => p.y)
  const x0 = Math.min(...xs), x1 = Math.max(...xs), y0 = Math.min(...ys), y1 = Math.max(...ys)
  for (const p of nodes) {
    p.x = x1 > x0 ? (p.x - x0) / (x1 - x0) : 0.5
    p.y = y1 > y0 ? (p.y - y0) / (y1 - y0) : 0.5
  }
}

type Cell = { ch: string; color?: string; dim?: boolean; bold?: boolean }

function drawGraph(m: BrainMap, w: number, h: number): Cell[][] {
  const grid: Cell[][] = Array.from({ length: h }, () => Array.from({ length: w }, () => ({ ch: ' ' })))
  const px = (p: GraphNode) => 1 + Math.round(p.x * (w - 3))
  const py = (p: GraphNode) => Math.round(p.y * (h - 1))
  for (const [a, b] of m.edges) {
    let x = px(m.nodes[a]), y = py(m.nodes[a])
    const x1 = px(m.nodes[b]), y1 = py(m.nodes[b])
    const sx = x < x1 ? 1 : -1, sy = y < y1 ? 1 : -1
    const ddx = Math.abs(x1 - x), ddy = Math.abs(y1 - y)
    let err = ddx - ddy
    for (let s = 0; s < w + h; s++) {
      if (grid[y][x].ch === ' ') grid[y][x] = { ch: '·', dim: true }
      if (x === x1 && y === y1) break
      const e2 = 2 * err
      if (e2 > -ddy) { err -= ddy; x += sx }
      if (e2 < ddx) { err += ddx; y += sy }
    }
  }
  const order = m.nodes.map((_, i) => i).sort((a, b) => m.nodes[a].degree - m.nodes[b].degree)
  for (const i of order) {
    const p = m.nodes[i]
    const color = COLORS[p.group % COLORS.length]
    grid[py(p)][px(p)] = { ch: p.degree >= 6 ? '◉' : p.degree >= 2 ? '●' : '○', color, bold: p.degree >= 6 }
  }
  const labelled = [...order].reverse().slice(0, Math.max(6, Math.floor(h / 2)))
  for (const i of labelled) {
    const p = m.nodes[i]
    const text = p.name.slice(0, 18)
    let x = px(p) + 2
    const y = py(p)
    if (x + text.length >= w) x = px(p) - 1 - text.length
    if (x < 0 || grid[y].slice(Math.max(0, x - 1), x + text.length + 1).some(c => /[a-z0-9]/i.test(c.ch))) continue
    for (let c = 0; c < text.length; c++) grid[y][x + c] = { ch: text[c], dim: p.degree < 6, bold: p.degree >= 6 }
  }
  return grid
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({
      name: 'brain-map',
      description: 'Obsidian-style map of your second brain: /brain-map [folder path]',
    })
    return next(e)
  })

  on('command.run', { command: 'brain-map' }, async ($, e) => {
    const home = (await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? ''
    const stored = (await $.store.get('root')) as string | undefined
    const root = (e.args.trim() || stored || DEFAULT_ROOT).replace(/^~/, home).replace(/\\/g, '/').replace(/\/+$/, '')
    if (!(await $.fs.exists(root))) {
      return { text: `Folder not found: ${root}. Run /brain-map "<full path>" (this session must run on the machine that has the folder).` }
    }
    await $.store.set('root', root)

    const groups: string[] = []
    const files: { name: string; path: string; group: number }[] = []
    const walk = async (path: string, name: string, depth: number, group: number): Promise<MapNode> => {
      const node: MapNode = { name, kind: 'dir', notes: 0, children: [] }
      const entries = (await $.fs.list(path)).filter(x => !x.name.startsWith('.'))
      entries.sort((a, b) => (a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === 'dir' ? -1 : 1))
      for (const x of entries) {
        if (x.kind === 'dir' && depth < MAX_DEPTH) {
          let g = group
          if (depth === 0) { g = groups.length; groups.push(x.name) }
          const child = await walk(`${path}/${x.name}`, x.name, depth + 1, g)
          node.notes += child.notes
          node.children.push(child)
        } else if (x.kind === 'file' && NOTE.test(x.name)) {
          node.notes += 1
          node.children.push({ name: x.name.replace(NOTE, ''), kind: 'file', notes: 0, children: [] })
          files.push({ name: x.name.replace(NOTE, ''), path: `${path}/${x.name}`, group })
        }
      }
      return node
    }

    let result: BrainMap
    try {
      const tree = await walk(root, root.split('/').pop() || root, 0, 0)
      const used = files.slice(0, MAX_NOTES)
      const nodes: GraphNode[] = used.map(f => ({ name: f.name, group: f.group, degree: 0, x: 0, y: 0 }))
      const byName = new Map(used.map((f, i) => [f.name.toLowerCase(), i]))
      const seen = new Set<string>()
      const edges: [number, number][] = []
      for (let i = 0; i < used.length; i++) {
        let text = ''
        try { text = (await $.fs.read(used[i].path)) as string } catch { continue }
        for (const m of text.matchAll(/\[\[([^\]|#]+)/g)) {
          const j = byName.get(m[1].trim().split('/').pop()!.toLowerCase())
          if (j === undefined || j === i || seen.has(`${Math.min(i, j)}:${Math.max(i, j)}`)) continue
          seen.add(`${Math.min(i, j)}:${Math.max(i, j)}`)
          edges.push([i, j]); nodes[i].degree++; nodes[j].degree++
        }
      }
      layout(nodes, edges)
      result = { root, tree, groups, nodes, edges }
    } catch (err) {
      result = { root, tree: { name: root, kind: 'dir', notes: 0, children: [] }, groups, nodes: [], edges: [], error: String(err) }
    }
    await update($, map, () => result)
    await $.ui.open({ id: PANE, title: 'Second brain' })
    return { text: `Mapped ${root}: ${result.tree.notes} notes, ${result.edges.length} links.` }
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const m = (await read($, map)) as BrainMap | null
    if (!m) return <Text dimColor>Run /brain-map to draw your second brain.</Text>
    const cols = e.viewport?.columns ?? 100
    const rows = Math.max(8, (e.viewport?.rows ?? 30) - 6)
    const side = Math.min(34, Math.floor(cols * 0.32))
    const gw = Math.max(20, cols - side - 6)

    const lines: { text: string; color?: string; dim?: boolean }[] = []
    const draw = (n: MapNode, prefix: string, top: boolean) => {
      n.children.forEach((c, i) => {
        const last = i === n.children.length - 1
        const color = c.kind === 'dir' ? COLORS[(top ? i : 0) % COLORS.length] : undefined
        const label = c.kind === 'dir' ? `▸ ${c.name} ${c.notes}` : c.name
        lines.push({ text: `${prefix}${last ? '└ ' : '├ '}${label}`.slice(0, side - 1), color: top ? color : undefined, dim: c.kind === 'file' })
        if (c.kind === 'dir') draw(c, prefix + (last ? '  ' : '│ '), false)
      })
    }
    draw(m.tree, '', true)

    const grid = drawGraph(m, gw, rows)
    return (
      <Box flexDirection="column">
        <Text bold>{m.tree.name} <Text dimColor>· {m.tree.notes} notes · {m.edges.length} links</Text></Text>
        {m.error && <Text color="red">{m.error}</Text>}
        <Box flexDirection="row">
          <Box flexDirection="column" width={side} borderStyle="round" borderColor="gray">
            <Text bold>Files</Text>
            {lines.slice(0, rows - 1).map(l => (
              <Text color={l.color} dimColor={l.dim}>{l.text}</Text>
            ))}
            {lines.length > rows - 1 && <Text dimColor>… {lines.length - rows + 1} more</Text>}
          </Box>
          <Box flexDirection="column" marginLeft={1}>
            <Text bold>Graph view</Text>
            {grid.map(row => (
              <Text>
                {row.map(c => (
                  <Text color={c.color} dimColor={c.dim} bold={c.bold}>{c.ch}</Text>
                ))}
              </Text>
            ))}
          </Box>
        </Box>
        <Text>
          {m.groups.slice(0, 6).map((g, i) => (
            <Text color={COLORS[i % COLORS.length]}>● {g}  </Text>
          ))}
        </Text>
      </Box>
    )
  })
}
