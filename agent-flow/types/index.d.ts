export type FlowNode = {
  id: string
  parent: string
  label: string
  type: string
  model: string
  tools: number
  lastTool: string
  isDone: boolean
  startedAt: number
  endedAt: number
  recent: string[]
}

declare module 'claude-code' {
  interface PluginState {
    'agent-flow': { nodes: FlowNode[] }
  }
}
