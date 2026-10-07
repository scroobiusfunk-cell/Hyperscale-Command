import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { FlowNode } from '../types'

const PANE = 'agent-flow'
const nodes = atom({ plugin: 'agent-flow', key: 'nodes' } as const, [])
const MAIN = 'main'

let writing = false
let dirty = false
async function publish($: any) {
  if (writing) { dirty = true; return }
  writing = true
  try {
    do {
      dirty = false
      await publishNow($)
    } while (dirty)
  } finally { writing = false }
}

async function publishNow($: any) {
  try {
    const list = (await read($, nodes)) as FlowNode[]
    const home = ((await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? '').replace(/\\/g, '/')
    if (!home) return
    await $.fs.write(`${home}/agent-flow-data.js`, `window.FLOW=${JSON.stringify({ updated: Date.now(), nodes: list }).replace(/</g, '\\u003c')};`)
  } catch {}
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await update($, nodes, () => [])
    await publish($)
    await $.command.register({ name: 'agent-flow', description: 'Live agent flow view in your web browser' })
    await $.command.register({ name: 'agent-pane', description: 'Agent flow in a terminal pane' })
    return next(e)
  })

  on('command.run', { command: 'agent-pane' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Agent flow' })
    return { text: 'Agent flow pane opened.' }
  })

  on('command.run', { command: 'agent-flow' }, async $ => {
    const home = ((await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? '').replace(/\\/g, '/')
    await publish($)
    await $.fs.write(`${home}/agent-flow.html`, (await $.fs.read(`${$.plugin.root}/hooks/viewer.html`)) as string)
    const win = `${home}/agent-flow.html`.replace(/\//g, '\\')
    let opened = false
    try { opened = (await $.process.run(['cmd', '/c', 'start', '', 'chrome', win])).exitCode === 0 } catch {}
    if (!opened) { try { await $.process.run(['cmd', '/c', 'start', '', win]) } catch {} }
    return { text: `Opened ${win} in Chrome. It updates live as agents run; ask Claude to use subagents to see the flow.` }
  })

  on('agent.spawn', async ($, e, next) => {
    const r = await next(e)
    if ('agentId' in r && r.agentId) {
      const node: FlowNode = {
        id: r.agentId,
        parent: e.parentAgentId ?? MAIN,
        label: e.description,
        type: e.subagentType,
        model: r.model,
        tools: 0,
        lastTool: '',
        isDone: false,
        startedAt: Date.now(),
        endedAt: 0,
        recent: [],
      }
      await update($, nodes, list => (list.length >= 100 ? list.filter((n, i) => !n.isDone || i >= list.length - 50) : list).concat(node))
      await publish($)
    }
    return r
  })

  on('tool.call', async ($, e, next) => {
    if (e.agentId) {
      await update($, nodes, list =>
        list.map(n => (n.id === e.agentId ? { ...n, tools: n.tools + 1, lastTool: e.tool, recent: [...n.recent, e.tool].slice(-6) } : n)),
      )
      await publish($)
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const id = (e as { agentId?: string }).agentId
    if (id) {
      await update($, nodes, list => list.map(n => (n.id === id ? { ...n, isDone: true, endedAt: Date.now() } : n)))
      await publish($)
    }
    return next(e)
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = (await read($, nodes)) as FlowNode[]
    const rows: { depth: number; n: FlowNode }[] = []
    const walk = (parent: string, depth: number) => {
      for (const n of list.filter(x => x.parent === parent)) {
        rows.push({ depth, n })
        walk(n.id, depth + 1)
      }
    }
    walk(MAIN, 1)
    const known = new Set(list.map(n => n.id))
    for (const n of list) if (n.parent !== MAIN && !known.has(n.parent)) rows.push({ depth: 1, n })
    const room = Math.max(3, (e.viewport?.rows ?? 24) - 5)
    return (
      <Box flexDirection="column">
        <Text bold color="cyan">◉ You / main agent</Text>
        {rows.length === 0 && <Text dimColor>  No subagents yet. Ask Claude to delegate work.</Text>}
        {rows.slice(-room).map(({ depth, n }) => (
          <Box flexDirection="column">
            <Text>
              <Text dimColor>{'   '.repeat(depth - 1)}  ↳ </Text>
              <Text color={n.isDone ? 'green' : 'yellow'}>{n.isDone ? '✔' : '●'} {n.type}</Text>
              <Text> {n.label}</Text>
            </Text>
            <Text dimColor>{'   '.repeat(depth - 1)}      {n.model} · {n.tools} tools{n.lastTool ? ` · ${n.lastTool}` : ''}</Text>
          </Box>
        ))}
      </Box>
    )
  })
}
