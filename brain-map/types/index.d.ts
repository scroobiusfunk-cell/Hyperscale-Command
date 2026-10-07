export type MapNode = { name: string; kind: 'dir' | 'file'; notes: number; children: MapNode[] }
export type GraphNode = { name: string; group: number; degree: number; x: number; y: number }
export type BrainMap = {
  root: string
  tree: MapNode
  groups: string[]
  nodes: GraphNode[]
  edges: [number, number][]
  error?: string
}

declare module 'claude-code' {
  interface PluginState {
    'brain-map': { map: BrainMap | null }
  }
}
