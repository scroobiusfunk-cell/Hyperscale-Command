import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { FlowNode } from '../types'

const PANE = 'agent-flow'
const nodes = atom({ plugin: 'agent-flow', key: 'nodes' } as const, [])
const MAIN = 'main'

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'agent-flow', description: 'Show how agents pass work to each other' })
    return next(e)
  })

  on('command.run', { command: 'agent-flow' }, async $ => {
    await $.ui.open({ id: PANE, title: 'Agent flow' })
    return { text: 'Agent flow pane opened.' }
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
      }
      await update($, nodes, list => [...list, node].slice(-100))
    }
    return r
  })

  on('tool.call', async ($, e, next) => {
    if (e.agentId) {
      await update($, nodes, list =>
        list.map(n => (n.id === e.agentId ? { ...n, tools: n.tools + 1, lastTool: e.tool } : n)),
      )
    }
    return next(e)
  })

  on('turn.complete', async ($, e, next) => {
    const id = (e as { agentId?: string }).agentId
    if (id) await update($, nodes, list => list.map(n => (n.id === id ? { ...n, isDone: true } : n)))
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
