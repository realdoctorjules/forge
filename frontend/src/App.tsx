import { useEffect, useRef, useState } from 'react'
import { useStore } from './store'
import { Viewport } from './components/Viewport'

function Stat({ k, v, sub }: { k: string; v: string; sub?: string }) {
  return (
    <div className="stat">
      <span className="k">{k}</span>
      <span className="v">{v}{sub ? <> <small>{sub}</small></> : null}</span>
    </div>
  )
}

function paramDiff(a: any, b: any): string[] {
  const pa = a || {}, pb = b || {}
  const out: string[] = []
  for (const k of Object.keys(pb)) if (pa[k] !== pb[k]) out.push(`${k}: ${pa[k]}→${pb[k]}`)
  return out
}

export default function App() {
  const s = useStore()
  const [drag, setDrag] = useState(false)
  const [showKey, setShowKey] = useState(false)
  const [keyInput, setKeyInput] = useState('')
  const buildTimer = useRef<number | null>(null)
  const [mode, setMode] = useState<'orbit' | 'measure' | 'annotate'>('orbit')
  const [mA, setMA] = useState<[number, number, number] | null>(null)
  const [mB, setMB] = useState<[number, number, number] | null>(null)
  const [pending, setPending] = useState<[number, number, number] | null>(null)
  const [annText, setAnnText] = useState('')
  const [editVid, setEditVid] = useState<number | null>(null)
  const [editLabel, setEditLabel] = useState('')
  const [editInstr, setEditInstr] = useState('')

  const onPick = (p: [number, number, number]) => {
    if (mode === 'measure') {
      if (!mA || (mA && mB)) { setMA(p); setMB(null) } else { setMB(p) }
    } else if (mode === 'annotate') {
      setPending(p)
    }
  }

  useEffect(() => {
    s.init()
    s.runSelftest('isolation')
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  // live: re-preview shortly after a slider/material change (warm worker ~0.1s)
  const schedulePreview = () => {
    if (buildTimer.current) window.clearTimeout(buildTimer.current)
    buildTimer.current = window.setTimeout(() => s.preview(), 180)
  }

  const arch = s.archetypes.find((a) => a.key === s.archetype)
  const cur = s.versions.find((v) => v.id === s.currentVersionId) || null
  const committedUrl = cur && cur.status === 'ok' ? `/api/versions/${cur.id}/file/stl` : null
  const url = s.previewUrl || committedUrl
  const unsaved = !!s.previewAnalysis
  const geom = s.previewAnalysis ? s.previewAnalysis.geometry : cur?.metrics?.geometry
  const analysis = s.previewAnalysis ? s.previewAnalysis.analysis
    : (s.analysisOverride && s.analysisOverride.versionId === cur?.id
        ? s.analysisOverride.analysis : cur?.metrics?.analysis)
  const iso = s.selftest['isolation']
  const seg = s.selftest['segfault']
  const allow = s.selftest['allowlist']
  const patent = s.patent && s.patent.versionId === cur?.id ? s.patent.payload : null
  const priorArt = s.priorArt && s.priorArt.versionId === cur?.id ? s.priorArt.payload : null
  const views: string[] = cur?.metrics?.geometry?.svg_views || []
  const dfm: any[] = (s.previewAnalysis ? s.previewAnalysis.dfm : cur?.metrics?.dfm) || []
  const fit = s.fitResult && s.fitResult.versionId === cur?.id ? s.fitResult.result : null

  const onFile = (f: File | undefined) => { if (f) s.importStep(f) }

  return (
    <div className="app">
      <div className="header">
        <h1>Forge</h1>
        {iso && (
          <span className={`badge ${iso.sandbox_available ? 'ok' : 'warn'}`}>
            {iso.sandbox_available ? 'worker sandboxed · network denied' : 'subprocess only'}
          </span>
        )}
        <span className={`badge ${s.aiEnabled ? 'ok' : 'warn'}`} style={{ cursor: 'pointer' }}
              onClick={() => setShowKey((v) => !v)}>
          {s.aiEnabled ? 'AI: on (Claude)' : 'AI: off — add key'}
        </span>
        <div style={{ flex: 1 }} />
        <span className="badge">drafts for attorney/engineer review · not a filing</span>
      </div>

      {showKey && (
        <div className="promptbar" style={{ background: '#161618' }}>
          <input className="prompt" type="password" value={keyInput}
                 placeholder="Paste your Anthropic API key (sk-ant-…) — stored locally in forge/backend/.env, never sent anywhere but Anthropic"
                 onChange={(e) => setKeyInput(e.target.value)} />
          <button onClick={() => { s.saveKey(keyInput); setKeyInput(''); setShowKey(false) }}>
            Save key
          </button>
          <span className="note">Unlocks free-text "any device" prompts and AI-written patent prose.</span>
        </div>
      )}

      {/* PROMPT BAR */}
      <div className="promptbar">
        <input
          className="prompt"
          placeholder='Describe a device…  e.g. "a 7-compartment weekly pill organizer" or "a 60x40x25 project box"'
          value={s.prompt}
          onChange={(e) => s.setPrompt(e.target.value)}
          onKeyDown={(e) => { if (e.key === 'Enter') s.runPrompt() }}
        />
        <button onClick={() => s.runPrompt()} disabled={s.building || !s.prompt.trim()}>
          {s.building ? 'Building…' : 'Build'}
        </button>
        <button className="invent" onClick={() => s.invent()}
                disabled={s.building || !s.prompt.trim() || !s.aiEnabled}
                title={s.aiEnabled ? 'AI writes custom geometry — any rigid shape (experimental, uses credits)' : 'Add your API key to enable'}>
          ⚡ Invent
        </button>
        <label
          className={`dropzone ${drag ? 'drag' : ''}`}
          onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
          onDragLeave={() => setDrag(false)}
          onDrop={(e) => { e.preventDefault(); setDrag(false); onFile(e.dataTransfer.files?.[0]) }}
        >
          drop / pick a .STEP file
          <input type="file" accept=".step,.stp" style={{ display: 'none' }}
                 onChange={(e) => onFile(e.target.files?.[0] || undefined)} />
        </label>
        {s.matched && <span className="matched">→ matched: {s.matched.archetype}</span>}
      </div>

      {s.matched && s.matched.generated && (s.matched.summary || s.matched.printable_notes) && (
        <div className="gen-note">
          <b>⚡ AI-generated geometry.</b> {s.matched.summary}
          {s.matched.printable_notes && <> — <i>{s.matched.printable_notes}</i></>}
        </div>
      )}

      {s.matched && s.matched.fit && s.matched.fit !== 'good' && !s.matched.generated && (
        <div className="scope-warn">
          <b>{s.matched.fit === 'out_of_scope' ? '⚠ Outside Forge’s range.' : '⚠ Rough match.'}</b>{' '}
          {s.matched.fit_note || 'This is only the closest simple stand-in, not the device you described.'}
          {' '}Forge currently builds simple rigid printable parts (enclosures, trays, caps, brackets, knobs, stands, clips, hooks) — not soft, wearable, or articulated devices.
          {Array.isArray(s.matched.alternatives) && s.matched.alternatives.length > 0 && (
            <div style={{ marginTop: 10, display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
              <span>Build instead:</span>
              {s.matched.alternatives.map((a: any, i: number) => (
                <button key={i} className="secondary" onClick={() => { s.setPrompt(a.prompt); s.runPrompt() }}>
                  {a.label}
                </button>
              ))}
            </div>
          )}
        </div>
      )}

      <div className="main">
        {/* LEFT — controls */}
        <div className="panel">
          <div className="sec-title">Invention (project)</div>
          <select value={s.projectId ?? ''} onChange={(e) => s.switchProject(Number(e.target.value))}>
            {s.projectsList.map((p: any) => <option key={p.id} value={p.id}>{p.name}</option>)}
          </select>
          <div className="btnrow">
            <button className="secondary" onClick={() => {
              const n = window.prompt('Name this invention:', 'Untitled device')
              if (n !== null) s.newProject(n)
            }}>+ New</button>
            <button className="secondary" onClick={() => {
              const p = s.projectsList.find((x: any) => x.id === s.projectId)
              const n = window.prompt('Rename invention:', p?.name || '')
              if (n && s.projectId != null) s.renameProject(s.projectId, n)
            }}>Rename</button>
            <button className="secondary" onClick={() => {
              const p = s.projectsList.find((x: any) => x.id === s.projectId)
              if (s.projectId != null && window.confirm(`Delete "${p?.name}" and all its versions? This cannot be undone.`)) s.deleteProject(s.projectId)
            }}>Delete</button>
          </div>

          <div className="sec-title">Device type</div>
          <select value={s.archetype} onChange={(e) => s.selectArchetype(e.target.value)}>
            {s.archetypes.map((a) => <option key={a.key} value={a.key}>{a.label}</option>)}
          </select>

          <div className="sec-title">Dimensions &amp; shape</div>
          {arch && Object.entries(arch.params).map(([k, spec]) => (
            <div className="slider-row" key={k}>
              <label>
                {spec.label}
                <span className="val">
                  {(s.params[k] ?? spec.value).toFixed(spec.integer || spec.step >= 1 ? 0 : 1)}{spec.unit ? ` ${spec.unit}` : ''}
                </span>
              </label>
              <input type="range" min={spec.min} max={spec.max} step={spec.step}
                value={s.params[k] ?? spec.value}
                onChange={(e) => { s.setParam(k, parseFloat(e.target.value)); schedulePreview() }} />
            </div>
          ))}

          <div className="sec-title">Material</div>
          <select value={s.material} onChange={(e) => { s.setMaterial(e.target.value); schedulePreview() }}>
            {s.materials.map((m) => <option key={m.key} value={m.key}>{m.name}</option>)}
          </select>

          <div className="btnrow">
            <button onClick={() => s.generate()} disabled={s.building}>
              {s.building ? 'Saving…' : 'Save version'}
            </button>
          </div>
          <div className="note">Drag the sliders — the model and numbers update live. Click <b>Save version</b> to keep it (that enables exports, drawings, and the patent draft).</div>

          <div className="sec-title">Edit by chat (AI)</div>
          <input className="prompt" style={{ width: '100%' }}
                 placeholder='e.g. "thicker walls", "20% bigger", "add 2 compartments"'
                 value={editInstr} onChange={(e) => setEditInstr(e.target.value)}
                 onKeyDown={(e) => { if (e.key === 'Enter' && editInstr.trim()) { s.editByChat(editInstr); setEditInstr('') } }} />
          <div className="btnrow">
            <button onClick={() => { if (editInstr.trim()) { s.editByChat(editInstr); setEditInstr('') } }}
                    disabled={s.building || !s.aiEnabled || s.currentVersionId == null}
                    title={!s.aiEnabled ? 'Add your API key first' : s.currentVersionId == null ? 'Build/select a device first' : 'AI edits the current device into a new version'}>
              {s.building ? 'Editing…' : 'Apply edit'}
            </button>
          </div>
          <div className="note">Edits the current device into a new version (your prior versions stay).</div>
        </div>

        {/* CENTER — viewport */}
        <div className="center">
          {url ? (
            <Viewport url={url} fitKey={cur?.id ?? 'none'} mode={mode}
                      annotations={unsaved ? [] : s.annotations}
                      measureA={mA} measureB={mB} onPick={onPick} />
          ) : (
            <div className="empty">Type what you want to build above and press Build,<br />or drag in a .STEP file.</div>
          )}

          {url && (
            <div className="vp-tools">
              {(['orbit', 'measure', 'annotate'] as const).map((m) => (
                <button key={m} className={`secondary ${mode === m ? 'active' : ''}`}
                        onClick={() => { setMode(m); setMA(null); setMB(null); setPending(null) }}>
                  {m === 'orbit' ? 'Rotate' : m === 'measure' ? 'Measure' : 'Pin note'}
                </button>
              ))}
            </div>
          )}

          {(cur || unsaved) && (
            <div className="overlay">
              {unsaved
                ? <span style={{ color: '#ef9f27' }}>live preview · unsaved — click Save version</span>
                : <>{cur!.metrics?.name || cur!.label} · v{cur!.id}</>}
              {s.previewing && <span style={{ color: '#7a7a76' }}> · updating…</span>}
              {mode === 'measure' && <span style={{ color: '#f3c577' }}> · click two points{mA && mB ? ` = ${Math.hypot(mA[0]-mB[0],mA[1]-mB[1],mA[2]-mB[2]).toFixed(1)} mm` : ''}</span>}
              {mode === 'annotate' && !pending && <span style={{ color: '#b9b3f0' }}> · click a spot to pin a note</span>}
              {s.error && <div className="err" style={{ marginTop: 6 }}>{s.error}</div>}
            </div>
          )}

          {pending && (
            <div className="pending-ann">
              <input autoFocus value={annText} placeholder="Note for this spot (e.g. 'thicken this corner')"
                     onChange={(e) => setAnnText(e.target.value)}
                     onKeyDown={(e) => { if (e.key === 'Enter' && annText.trim()) { s.addAnnotation(pending, annText); setPending(null); setAnnText('') } }} />
              <button onClick={() => { if (annText.trim()) { s.addAnnotation(pending, annText); setPending(null); setAnnText('') } }}>Pin</button>
              <button className="secondary" onClick={() => { setPending(null); setAnnText('') }}>Cancel</button>
            </div>
          )}

          {s.building && <div className="building">Saving version…</div>}
        </div>

        {/* RIGHT — analysis */}
        <div className="panel right">
          <div className="sec-title">What it's made of</div>
          {analysis && geom ? (
            <>
              <Stat k="Dimensions (L×W×H)" v={`${geom.bbox_mm.x} × ${geom.bbox_mm.y} × ${geom.bbox_mm.z} mm`} />
              <Stat k="Weight" v={`${analysis.mass_g} g`} sub={`(${analysis.mass_g_range[0]}–${analysis.mass_g_range[1]})`} />
              <Stat k="Material" v={analysis.material} />
              <Stat k="Volume" v={`${analysis.volume_cm3} cm³`} />
              <Stat k="Components" v={`${analysis.component_count}`} />
              {analysis.print_time_h != null
                ? <Stat k="Est. print time" v={analysis.print_time_str || `${analysis.print_time_h} h`} sub={analysis.slicer_source ? '(sliced)' : `(${analysis.print_time_h_range[0]}–${analysis.print_time_h_range[1]})`} />
                : <Stat k="Made by" v={analysis.process_label || 'Machined'} />}
              <Stat k={analysis.print_time_h != null ? 'Est. cost' : 'Est. cost (stock)'} v={`$${analysis.cost_usd}`} sub={`($${analysis.cost_usd_range[0]}–$${analysis.cost_usd_range[1]})`} />
              {analysis.cost_note && <div className="note">{analysis.cost_note}</div>}
              <Stat k={analysis.process === 'machine' ? 'Solid (watertight)' : 'Watertight (printable)'} v={geom.watertight ? 'yes' : 'no'} />

              <div className="sec-title">Bill of materials</div>
              {analysis.components.map((c: any, i: number) => (
                <div className="comp" key={i}>
                  <span>{c.qty}× {c.name}<div className="meta">{c.type} · {c.material}</div></span>
                  <span>{c.mass_g != null ? `${c.mass_g} g` : ''}{c.cost_usd ? ` · $${c.cost_usd}` : ''}</span>
                </div>
              ))}
              <div className="note">{analysis.confidence}</div>

              {dfm.length > 0 && (
                <>
                  <div className="sec-title">{analysis.process === 'machine' ? 'Manufacturability (DFM)' : 'Printability (DFM)'}</div>
                  {dfm.map((d: any, i: number) => (
                    <div className="mono" key={i} style={{
                      color: d.level === 'warn' ? '#ef9f27' : d.level === 'ok' ? '#5dcaa5' : '#9a9a96',
                    }}>{d.level === 'warn' ? '⚠ ' : d.level === 'ok' ? '✓ ' : 'ℹ '}{d.msg}</div>
                  ))}
                </>
              )}

              {unsaved && <div className="note" style={{ color: '#ef9f27' }}>Live preview (unsaved). The buttons below act on the last saved version — click Save version to update exports, drawings, and the patent draft.</div>}
              {cur ? (
                <>
              <div className="sec-title">Export</div>
              <div className="btnrow">
                <a href={`/api/versions/${cur!.id}/file/stl`} download>
                  <button className="secondary">Download STL (print)</button>
                </a>
                <a href={`/api/versions/${cur!.id}/file/step`} download>
                  <button className="secondary">Download STEP (CAD)</button>
                </a>
              </div>
              <div className="btnrow">
                <a href="https://craftcloud3d.com/" target="_blank" rel="noreferrer">
                  <button className="secondary">Order a 3D print ↗</button>
                </a>
              </div>
              <div className="note">Download the STL, then upload it to a print service (e.g. Craftcloud) to order a physical print.</div>

              <div className="sec-title">Electronics fit</div>
              <select value={s.fitComponent} onChange={(e) => s.setFitComponent(e.target.value)}>
                {s.componentsList.map((c: any) => <option key={c.key} value={c.key}>{c.name}</option>)}
              </select>
              <div className="btnrow">
                <button className="secondary" onClick={() => s.checkFit()}>Check fit</button>
              </div>
              {fit && (
                <>
                  <div className="mono" style={{ color: fit.fits ? (fit.tight ? '#ef9f27' : '#5dcaa5') : '#f09595' }}>
                    {fit.fits ? (fit.tight ? '⚠ tight fit' : '✓ fits') : '✗ does not fit'} · spare {fit.min_margin_mm} mm
                    {'\n'}cavity {fit.interior_lwh.join(' × ')} mm vs part {fit.component_lwh.join(' × ')} mm
                  </div>
                  {(fit.warnings || []).map((w: string, i: number) => <div className="note" key={i}>{w}</div>)}
                </>
              )}

              {views.length > 0 && (
                <>
                  <div className="sec-title">2D technical drawings</div>
                  <div className="btnrow">
                    {views.map((view) => (
                      <a key={view} href={`/api/versions/${cur!.id}/drawing/${view}.svg`}
                         target="_blank" rel="noreferrer">
                        <button className="secondary">{view}</button>
                      </a>
                    ))}
                  </div>
                  <div className="btnrow">
                    <a href={`/api/versions/${cur!.id}/drawing-sheet.html`} target="_blank" rel="noreferrer">
                      <button>Dimensioned drawing sheet</button>
                    </a>
                  </div>
                  <div className="note">Individual views are exact line-art. The dimensioned sheet adds a title block + to-scale measured views (printable to PDF).</div>
                </>
              )}

              <div className="sec-title">Patent draft</div>
              <button onClick={() => s.checkPriorArt()} disabled={s.busyPriorArt} className="secondary">
                {s.busyPriorArt ? 'Searching…' : '1. Check prior art'}
              </button>
              {priorArt && (
                <div style={{ marginTop: 8 }}>
                  <div className="mono">{priorArt.assessment}</div>
                  {s.busyPriorArtAI && (
                    <div className="note">🔍 Searching patent databases & the web for similar art… (this runs in the background, ~1–3 min; the links below work right now)</div>
                  )}
                  {priorArt.ai_error && (
                    <div className="note">AI search unavailable ({priorArt.ai_error}). Use the links below to search yourself.</div>
                  )}
                  {(priorArt.references || []).slice(0, 6).map((r: any, i: number) => (
                    <div className="comp" key={i}>
                      <span><a href={r.url} target="_blank" rel="noreferrer">{r.title}</a>
                        <div className="meta">{r.overlap || r.why_relevant}</div></span>
                    </div>
                  ))}
                  {priorArt.links && (
                    <div className="btnrow">
                      {Object.entries(priorArt.links).map(([k, url]) => (
                        <a key={k} href={url as string} target="_blank" rel="noreferrer">
                          <button className="secondary">{k.replace('_', ' ')}</button>
                        </a>
                      ))}
                    </div>
                  )}
                  <div className="note">{priorArt.disclaimer}</div>
                </div>
              )}
              <label style={{ display: 'flex', gap: 8, fontSize: 12, alignItems: 'center', marginBottom: 8 }}>
                <input type="checkbox" checked={s.patientContact}
                       onChange={(e) => s.setPatientContact(e.target.checked)} />
                This device touches a patient or is powered near a person
              </label>
              <button onClick={() => s.generatePatent()} disabled={s.busyPatent}>
                {s.busyPatent ? 'Drafting…' : '2. Generate patent draft'}
              </button>
              {patent && (
                <>
                  <div className="note">{patent.ai_note}</div>
                  <div className="btnrow">
                    <a href={`/api/versions/${cur!.id}/patent.html`} target="_blank" rel="noreferrer">
                      <button className="secondary">Open draft</button>
                    </a>
                    <a href={`/api/versions/${cur!.id}/patent.md`} download>
                      <button className="secondary">Download (.md)</button>
                    </a>
                    <a href={`/api/versions/${cur!.id}/patent-figures.html`} target="_blank" rel="noreferrer">
                      <button className="secondary">Patent figures</button>
                    </a>
                  </div>
                  <div className="note">Patent figures: numbered FIGs, black line-art, reference numerals with leader lines (no dimensions) — a USPTO-style draft for your attorney.</div>
                  {patent.gates?.stop && <div className="mono err" style={{ marginTop: 6 }}>{patent.gates.stop}</div>}
                </>
              )}
              <div className="note">Attorney-review-ready draft — not a filing, not legal advice.</div>

              <div className="sec-title">Notes on the model ({s.annotations.length})</div>
              <div className="note">Use the <b>Pin note</b> tool above the 3D view, then click a spot to mark it.</div>
              {s.annotations.map((a: any, i: number) => (
                <div className="ann-row" key={a.id}>
                  <span><b>{i + 1}.</b> {a.text}</span>
                  <span className="x" title="delete" onClick={() => s.removeAnnotation(a.id)}>✕</span>
                </div>
              ))}
                </>
              ) : (
                <div className="note">Click Save version to enable exports, 2D drawings, notes, and the patent draft.</div>
              )}
            </>
          ) : (
            <div className="note">Drag the sliders or type a prompt to see materials, dimensions, weight, components and cost — live.</div>
          )}

          <div className="sec-title">Versions ({s.versions.length}) · nothing is ever lost</div>
          <ul className="vlist">
            {s.versions.map((v) => {
              const parent = s.versions.find((p) => p.id === v.parent_id)
              const sameKind = parent && (parent as any).part_module === (v as any).part_module
                && !v.metrics?.generated && !parent.metrics?.generated
              const changes = sameKind ? paramDiff(parent.params, v.params) : []
              return (
                <li key={v.id}
                    className={`vrow ${v.id === s.currentVersionId ? 'active' : ''} ${v.status === 'failed' ? 'failed' : ''}`}
                    onClick={() => v.status === 'ok' && editVid !== v.id && s.selectVersion(v.id)}>
                  {editVid === v.id ? (
                    <>
                      <input autoFocus value={editLabel} onClick={(e) => e.stopPropagation()}
                             onChange={(e) => setEditLabel(e.target.value)}
                             onKeyDown={(e) => { if (e.key === 'Enter') { s.renameVersion(v.id, editLabel); setEditVid(null) } }} />
                      <span className="edit" onClick={(e) => { e.stopPropagation(); s.renameVersion(v.id, editLabel); setEditVid(null) }}>save</span>
                    </>
                  ) : (
                    <>
                      <span style={{ flex: 1 }}>v{v.id} · {v.label || v.metrics?.name || v.metrics?.archetype || '—'}</span>
                      <span className={`tag ${v.status}`}>{v.status}</span>
                      {v.status === 'ok' && (
                        <span className="edit" title="rename"
                              onClick={(e) => { e.stopPropagation(); setEditVid(v.id); setEditLabel(v.label || v.metrics?.name || '') }}>✎</span>
                      )}
                      {v.metrics?.generated
                        ? <div className="diff">⚡ AI-generated geometry</div>
                        : changes.length > 0 && <div className="diff">changed: {changes.join(', ')}</div>}
                    </>
                  )}
                </li>
              )
            })}
          </ul>

          <details>
            <summary>Regulatory radar (FDA)</summary>
            <div className="note" style={{ marginTop: 8 }}>Answer about the device's intended use for preliminary FDA considerations — not a determination, not legal advice.</div>
            {s.regQuestions.map((q: any) => (
              <div key={q.id}>
                <label className="fld">{q.label}</label>
                <select value={s.regAnswers[q.id] || ''} onChange={(e) => s.setRegAnswer(q.id, e.target.value)}>
                  {q.options.map((o: any) => <option key={o.v} value={o.v}>{o.l}</option>)}
                </select>
              </div>
            ))}
            <div className="btnrow"><button onClick={() => s.assessRegulatory()}>Assess</button></div>
            {s.regResult && (
              <div style={{ marginTop: 10 }}>
                <div className="stat"><span className="k">Likely class</span><span className="v">{s.regResult.class_estimate}</span></div>
                <div className="note">{s.regResult.pathway}</div>
                {s.regResult.considerations.map((c: any, i: number) => (
                  <div className="comp" key={i}>
                    <span><b>{c.title}</b><div className="meta">{c.detail}</div>
                      {c.url && <a href={c.url} target="_blank" rel="noreferrer">FDA reference ↗</a>}</span>
                  </div>
                ))}
                <div className="btnrow">
                  {Object.entries(s.regResult.links).map(([k, url]) => (
                    <a key={k} href={url as string} target="_blank" rel="noreferrer"><button className="secondary">{k}</button></a>
                  ))}
                </div>
                <div className="note err">{s.regResult.disclaimer}</div>
              </div>
            )}
          </details>

          <details>
            <summary>Developer diagnostics</summary>
            <div className="btnrow" style={{ marginTop: 8 }}>
              <button className="secondary" onClick={() => s.runSelftest('segfault')}>Test crash isolation</button>
              <button className="secondary" onClick={() => s.runSelftest('allowlist')}>Test code allowlist</button>
            </div>
            {seg && <div className="mono" style={{ marginTop: 8 }}>{seg.interpretation}{'\n'}backend_alive: {String(seg.backend_alive)}</div>}
            {allow && <div className="mono" style={{ marginTop: 8 }}>rejected: {String(allow.rejected)}{'\n'}{(allow.issues || []).join('\n')}</div>}
            <div className="note">Inventorship log:{'\n'}{s.log.slice(-6).map((e) => `[${e.actor}] ${e.action}${e.version_id ? ` v${e.version_id}` : ''}`).join('\n')}</div>
          </details>
        </div>
      </div>

      <div className="footer">
        Forge is an R&D drafting tool. CAD, cost, weight and (later) patent outputs are estimates and drafts for human and attorney review — not engineering sign-off, manufacturing approval, or legal advice.
      </div>
    </div>
  )
}
