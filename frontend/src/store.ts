import { create } from 'zustand'
import { api } from './api'

export type ParamSpec = {
  value: number; min: number; max: number; step: number; unit: string; label: string; integer?: boolean
}
export type Archetype = {
  key: string; label: string; examples: string[]
  params: Record<string, ParamSpec>; defaults: Record<string, number>; default_material: string
}
export type Material = { key: string; name: string; density: number; price_kg: number }
export type Version = {
  id: number; parent_id: number | null; label: string | null; status: 'ok' | 'failed'
  params: Record<string, number>; metrics: any | null; crash: any | null
  files: Record<string, string> | null
}

type State = {
  archetypes: Archetype[]
  materials: Material[]
  projectId: number | null
  archetype: string
  params: Record<string, number>
  material: string
  prompt: string
  versions: Version[]
  currentVersionId: number | null
  log: any[]
  busy: boolean
  building: boolean
  error: string | null
  matched: any | null
  analysisOverride: { versionId: number; analysis: any } | null
  selftest: Record<string, any>
  aiEnabled: boolean
  patientContact: boolean
  busyPatent: boolean
  patent: { versionId: number; payload: any } | null
  busyPriorArt: boolean
  priorArt: { versionId: number; payload: any } | null
  previewing: boolean
  previewUrl: string | null
  previewAnalysis: { geometry: any; analysis: any } | null
  annotations: any[]
  componentsList: any[]
  fitComponent: string
  fitResult: { versionId: number; result: any } | null
  projectsList: any[]
  regQuestions: any[]
  regAnswers: Record<string, string>
  regResult: any | null

  init: () => Promise<void>
  setRegAnswer: (id: string, v: string) => void
  assessRegulatory: () => Promise<void>
  switchProject: (pid: number) => Promise<void>
  newProject: (name: string) => Promise<void>
  renameProject: (pid: number, name: string) => Promise<void>
  deleteProject: (pid: number) => Promise<void>
  setFitComponent: (key: string) => void
  checkFit: () => Promise<void>
  loadAnnotations: (vid: number) => Promise<void>
  addAnnotation: (pt: [number, number, number], text: string) => Promise<void>
  removeAnnotation: (aid: number) => Promise<void>
  renameVersion: (vid: number, label: string) => Promise<void>
  invent: () => Promise<void>
  editByChat: (instruction: string) => Promise<void>
  preview: () => Promise<void>
  saveKey: (key: string) => Promise<void>
  setPatientContact: (v: boolean) => void
  generatePatent: () => Promise<void>
  checkPriorArt: () => Promise<void>
  setPrompt: (p: string) => void
  runPrompt: () => Promise<void>
  selectArchetype: (key: string) => void
  setParam: (k: string, v: number) => void
  setMaterial: (key: string) => Promise<void>
  generate: () => Promise<void>
  importStep: (file: File) => Promise<void>
  selectVersion: (id: number) => void
  runSelftest: (kind: 'isolation' | 'segfault' | 'allowlist') => Promise<void>
}

const archDefaults = (a: Archetype) => ({ ...a.defaults })

export const useStore = create<State>((set, get) => ({
  archetypes: [], materials: [], projectId: null,
  archetype: 'enclosure', params: {}, material: 'PLA', prompt: '',
  versions: [], currentVersionId: null, log: [], busy: false, building: false,
  error: null, matched: null, analysisOverride: null, selftest: {},
  aiEnabled: false, patientContact: false, busyPatent: false, patent: null,
  busyPriorArt: false, priorArt: null,
  previewing: false, previewUrl: null, previewAnalysis: null, annotations: [],
  componentsList: [], fitComponent: '', fitResult: null, projectsList: [],
  regQuestions: [], regAnswers: {}, regResult: null,

  setRegAnswer: (id, v) => set((s) => ({ regAnswers: { ...s.regAnswers, [id]: v }, regResult: null })),
  assessRegulatory: async () => {
    try { set({ regResult: await api.regulatoryAssess(get().regAnswers) }) }
    catch (e: any) { set({ error: 'Regulatory check failed: ' + String(e) }) }
  },

  switchProject: async (pid) => {
    const versions: Version[] = await api.versions(pid)
    const log = await api.log(pid)
    const cur = versions.find((v) => v.status === 'ok')?.id ?? null
    const oldUrl = get().previewUrl
    if (oldUrl) URL.revokeObjectURL(oldUrl)
    set({
      projectId: pid, versions, log, currentVersionId: cur,
      previewUrl: null, previewAnalysis: null, analysisOverride: null,
      matched: null, patent: null, priorArt: null, fitResult: null, annotations: [], error: null,
    })
    if (cur != null) get().loadAnnotations(cur)
  },

  newProject: async (name) => {
    const p = await api.createProject(name || 'Untitled device')
    set({ projectsList: await api.projects() })
    await get().switchProject(p.id)
  },

  renameProject: async (pid, name) => {
    await api.renameProject(pid, name)
    set({ projectsList: await api.projects() })
  },

  deleteProject: async (pid) => {
    await api.deleteProject(pid)
    const projects = await api.projects()
    set({ projectsList: projects })
    if (get().projectId === pid) {
      if (projects.length) await get().switchProject(projects[0].id)
      else await get().newProject('Untitled device')
    }
  },

  setFitComponent: (key) => set({ fitComponent: key }),
  checkFit: async () => {
    const { currentVersionId, fitComponent } = get()
    if (currentVersionId == null || !fitComponent) return
    try {
      const result = await api.fitCheck(currentVersionId, fitComponent)
      set({ fitResult: { versionId: currentVersionId, result } })
    } catch (e: any) { set({ error: 'Fit check failed: ' + String(e) }) }
  },

  loadAnnotations: async (vid) => {
    try { set({ annotations: await api.annotations(vid) }) } catch { set({ annotations: [] }) }
  },
  addAnnotation: async (pt, text) => {
    const { currentVersionId } = get()
    if (currentVersionId == null || !text.trim()) return
    await api.addAnnotation(currentVersionId, pt[0], pt[1], pt[2], text.trim())
    await get().loadAnnotations(currentVersionId)
  },
  removeAnnotation: async (aid) => {
    await api.deleteAnnotation(aid)
    const { currentVersionId } = get()
    if (currentVersionId != null) await get().loadAnnotations(currentVersionId)
  },
  renameVersion: async (vid, label) => {
    await api.setLabel(vid, label)
    const { projectId } = get()
    if (projectId != null) set({ versions: await api.versions(projectId) })
  },

  init: async () => {
    const lib = await api.library()
    const projects = await api.projects()
    const pid = projects.length ? projects[0].id : (await api.createProject('My devices')).id
    const versions: Version[] = await api.versions(pid)
    const log = await api.log(pid)
    const first = lib.archetypes[0]
    let aiEnabled = false
    try { aiEnabled = (await api.aiStatus()).enabled } catch { /* ignore */ }
    let comps: any[] = []
    try { comps = await api.components() } catch { /* ignore */ }
    let regQ: any[] = []
    try { regQ = await api.regulatoryQuestions() } catch { /* ignore */ }
    const regAns: Record<string, string> = {}
    regQ.forEach((q: any) => { regAns[q.id] = q.options[0].v })
    set({
      componentsList: comps, fitComponent: comps[0]?.key || '', projectsList: projects,
      regQuestions: regQ, regAnswers: regAns,
      archetypes: lib.archetypes, materials: lib.materials, projectId: pid,
      archetype: first.key, params: archDefaults(first), material: first.default_material,
      versions, log, currentVersionId: versions.find((v) => v.status === 'ok')?.id ?? null,
      aiEnabled,
    })
    const cv = versions.find((v) => v.status === 'ok')?.id
    if (cv != null) get().loadAnnotations(cv)
  },

  saveKey: async (key) => {
    try {
      const r = await api.setKey(key)
      set({ aiEnabled: r.enabled })
    } catch (e: any) {
      set({ error: 'Saving key failed: ' + String(e) })
    }
  },

  setPatientContact: (v) => set({ patientContact: v }),

  generatePatent: async () => {
    const { currentVersionId, patientContact } = get()
    if (currentVersionId == null) return
    set({ busyPatent: true })
    try {
      const payload = await api.makePatent(currentVersionId, patientContact)
      set({ patent: { versionId: currentVersionId, payload } })
    } catch (e: any) {
      set({ error: 'Patent generation failed: ' + String(e) })
    } finally {
      set({ busyPatent: false })
    }
  },

  checkPriorArt: async () => {
    const { currentVersionId } = get()
    if (currentVersionId == null) return
    set({ busyPriorArt: true })
    try {
      const payload = await api.priorArt(currentVersionId)
      set({ priorArt: { versionId: currentVersionId, payload } })
    } catch (e: any) {
      set({ error: 'Prior-art check failed: ' + String(e) })
    } finally {
      set({ busyPriorArt: false })
    }
  },

  setPrompt: (p) => set({ prompt: p }),

  runPrompt: async () => {
    const { projectId, prompt } = get()
    if (projectId == null || !prompt.trim()) return
    set({ building: true, error: null })
    try {
      const res = await api.prompt(projectId, prompt)
      await afterBuild(set, get, res)
    } catch (e: any) {
      set({ error: String(e) })
    } finally {
      set({ building: false })
    }
  },

  invent: async () => {
    const { projectId, prompt } = get()
    if (projectId == null || !prompt.trim()) return
    set({ building: true, error: null })
    try {
      const res = await api.invent(projectId, prompt)
      await afterBuild(set, get, res)
      if (!res.ok) set({ error: res.error || 'AI could not build that geometry — try rephrasing.' })
    } catch (e: any) {
      set({ error: 'Invent failed: ' + String(e) })
    } finally {
      set({ building: false })
    }
  },

  editByChat: async (instruction) => {
    const { projectId, currentVersionId } = get()
    if (projectId == null || currentVersionId == null || !instruction.trim()) return
    set({ building: true, error: null })
    try {
      const res = await api.edit(projectId, instruction, currentVersionId)
      await afterBuild(set, get, res)
      if (!res.ok) set({ error: res.error || 'Edit failed — try rephrasing.' })
    } catch (e: any) {
      set({ error: 'Edit failed: ' + String(e) })
    } finally {
      set({ building: false })
    }
  },

  selectArchetype: (key) => {
    const a = get().archetypes.find((x) => x.key === key)
    if (!a) return
    set({ archetype: key, params: archDefaults(a), material: a.default_material })
    get().preview()
  },

  setParam: (k, v) => set((s) => ({ params: { ...s.params, [k]: v } })),

  preview: async () => {
    const { projectId, archetype, params, material } = get()
    if (projectId == null) return
    set({ previewing: true })
    try {
      const r = await api.preview(projectId, archetype, params, material)
      if (r.ok) {
        const bytes = Uint8Array.from(atob(r.stl_b64), (c) => c.charCodeAt(0))
        const url = URL.createObjectURL(new Blob([bytes], { type: 'model/stl' }))
        const old = get().previewUrl
        set({ previewUrl: url, previewAnalysis: { geometry: r.geometry, analysis: r.analysis, dfm: r.dfm } })
        if (old) URL.revokeObjectURL(old)
      }
    } catch { /* ignore transient preview errors */ } finally {
      set({ previewing: false })
    }
  },

  setMaterial: async (key) => {
    set({ material: key })
    const { currentVersionId, versions } = get()
    const cur = versions.find((v) => v.id === currentVersionId)
    if (cur && cur.status === 'ok') {
      try {
        const analysis = await api.analysis(cur.id, key)
        set({ analysisOverride: { versionId: cur.id, analysis } })
      } catch { /* ignore */ }
    }
  },

  generate: async () => {
    const { projectId, archetype, params, material } = get()
    if (projectId == null) return
    set({ building: true, error: null })
    try {
      const res = await api.generate(projectId, archetype, params, material)
      await afterBuild(set, get, res)
    } catch (e: any) {
      set({ error: String(e) })
    } finally {
      set({ building: false })
    }
  },

  importStep: async (file) => {
    const { projectId } = get()
    if (projectId == null) return
    set({ building: true, error: null })
    try {
      const res = await api.importStep(projectId, file)
      await afterBuild(set, get, res)
    } catch (e: any) {
      set({ error: 'STEP import failed: ' + String(e) })
    } finally {
      set({ building: false })
    }
  },

  selectVersion: (id) => {
    const v = get().versions.find((x) => x.id === id)
    if (!v || v.status !== 'ok') return
    const arch = v.metrics?.archetype
    const a = get().archetypes.find((x) => x.key === arch)
    const oldUrl = get().previewUrl
    if (oldUrl) URL.revokeObjectURL(oldUrl)
    set({
      currentVersionId: id,
      analysisOverride: null, previewUrl: null, previewAnalysis: null, annotations: [],
      archetype: arch && a ? arch : get().archetype,
      params: a ? { ...a.defaults, ...(v.params || {}) } : get().params,
      material: v.metrics?.material || get().material,
    })
    get().loadAnnotations(id)
  },

  runSelftest: async (kind) => {
    const r = await api.selftest(kind)
    set((s) => ({ selftest: { ...s.selftest, [kind]: r } }))
  },
}))

async function afterBuild(set: any, get: any, res: any) {
  const pid = get().projectId
  const versions: Version[] = await api.versions(pid)
  const log = await api.log(pid)
  const v = res.version
  const oldUrl = get().previewUrl
  if (oldUrl) URL.revokeObjectURL(oldUrl)
  const patch: any = { versions, log, matched: res.matched ?? null,
                       analysisOverride: null, previewUrl: null, previewAnalysis: null }
  if (res.ok) {
    patch.currentVersionId = v.id
    patch.archetype = v.metrics?.archetype ?? get().archetype
    patch.material = v.metrics?.material ?? get().material
    const a = get().archetypes.find((x: Archetype) => x.key === patch.archetype)
    if (a) patch.params = { ...a.defaults, ...(v.params || {}) }
    patch.error = null
  } else {
    patch.error = res.crash
      ? `Build failed — ${res.crash.signal} at step “${res.crash.attributed_op}”. Try different settings.`
      : 'Build failed.'
  }
  patch.annotations = []
  set(patch)
  if (res.ok && v?.id) get().loadAnnotations(v.id)
}
