const J = async (r: Response) => {
  if (!r.ok) throw new Error(`HTTP ${r.status}`)
  return r.json()
}
const POST = (url: string, body?: unknown) =>
  fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: body ? JSON.stringify(body) : undefined,
  }).then(J)

export const api = {
  library: () => fetch('/api/library').then(J),
  projects: () => fetch('/api/projects').then(J),
  createProject: (name: string) => POST('/api/projects', { name }),
  renameProject: (pid: number, name: string) => POST(`/api/projects/${pid}/name`, { name }),
  deleteProject: (pid: number) => fetch(`/api/projects/${pid}`, { method: 'DELETE' }).then(J),
  versions: (pid: number) => fetch(`/api/projects/${pid}/versions`).then(J),
  log: (pid: number) => fetch(`/api/projects/${pid}/log`).then(J),
  prompt: (pid: number, prompt: string, material?: string) =>
    POST(`/api/projects/${pid}/prompt`, { prompt, material }),
  generate: (pid: number, archetype: string, params: Record<string, number>, material: string) =>
    POST(`/api/projects/${pid}/generate`, { archetype, params, material }),
  preview: (pid: number, archetype: string, params: Record<string, number>, material: string) =>
    POST(`/api/projects/${pid}/preview`, { archetype, params, material }),
  invent: (pid: number, prompt: string) => POST(`/api/projects/${pid}/invent`, { prompt }),
  edit: (pid: number, instruction: string, baseVersionId: number) =>
    POST(`/api/projects/${pid}/edit`, { instruction, base_version_id: baseVersionId }),
  annotations: (vid: number) => fetch(`/api/versions/${vid}/annotations`).then(J),
  addAnnotation: (vid: number, x: number, y: number, z: number, text: string) =>
    POST(`/api/versions/${vid}/annotations`, { x, y, z, text }),
  deleteAnnotation: (aid: number) =>
    fetch(`/api/annotations/${aid}`, { method: 'DELETE' }).then(J),
  setLabel: (vid: number, label: string) => POST(`/api/versions/${vid}/label`, { label }),
  components: () => fetch('/api/components').then(J),
  fitCheck: (vid: number, component: string) => POST(`/api/versions/${vid}/fit-check`, { component }),
  regulatoryQuestions: () => fetch('/api/regulatory/questions').then(J),
  regulatoryAssess: (answers: Record<string, string>) => POST('/api/regulatory/assess', { answers }),
  analysis: (vid: number, material: string) =>
    fetch(`/api/versions/${vid}/analysis?material=${encodeURIComponent(material)}`).then(J),
  importStep: (pid: number, file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return fetch(`/api/projects/${pid}/import-step`, { method: 'POST', body: fd }).then(J)
  },
  selftest: (kind: 'isolation' | 'segfault' | 'allowlist') =>
    kind === 'isolation' ? fetch('/api/selftest/isolation').then(J) : POST(`/api/selftest/${kind}`),
  aiStatus: () => fetch('/api/ai-status').then(J),
  setKey: (key: string) => POST('/api/settings/anthropic-key', { key }),
  makePatent: (vid: number, patientContact: boolean) =>
    POST(`/api/versions/${vid}/patent`, { patient_contact: patientContact }),
  priorArt: (vid: number) => POST(`/api/versions/${vid}/prior-art`),
}
