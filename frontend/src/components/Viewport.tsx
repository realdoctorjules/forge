import { useEffect, useState } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, Grid, Bounds, GizmoHelper, GizmoViewport, Billboard, Text } from '@react-three/drei'
import { STLLoader } from 'three/examples/jsm/loaders/STLLoader.js'
import type { BufferGeometry } from 'three'

export type Pt = [number, number, number]
export type Annotation = { id: number; x: number; y: number; z: number; text: string }
export type Mode = 'orbit' | 'measure' | 'annotate'

function Model({ url, mode, onPick }: { url: string; mode: Mode; onPick: (p: Pt) => void }) {
  const [geom, setGeom] = useState<BufferGeometry | null>(null)
  useEffect(() => {
    let alive = true
    new STLLoader().load(url, (g) => {
      if (!alive) return
      g.center()
      g.computeVertexNormals()
      setGeom((prev) => { prev?.dispose(); return g })
    })
    return () => { alive = false }
  }, [url])
  if (!geom) return null
  return (
    <mesh
      geometry={geom}
      castShadow
      receiveShadow
      onClick={(e) => {
        if (mode === 'orbit') return
        e.stopPropagation()
        onPick([e.point.x, e.point.y, e.point.z])
      }}
    >
      <meshStandardMaterial color="#8b82f0" metalness={0.1} roughness={0.55} />
    </mesh>
  )
}

function Marker({ p, color, r = 2 }: { p: Pt; color: string; r?: number }) {
  return (
    <mesh position={p}>
      <sphereGeometry args={[r, 16, 16]} />
      <meshBasicMaterial color={color} />
    </mesh>
  )
}

function Pin({ p, n }: { p: Pt; n: number }) {
  return (
    <group position={p}>
      <mesh>
        <sphereGeometry args={[2.2, 16, 16]} />
        <meshBasicMaterial color="#8b82f0" />
      </mesh>
      <Billboard position={[0, 4.5, 0]}>
        <Text fontSize={4} color="#d8d4ff" anchorX="center" anchorY="middle" outlineWidth={0.3} outlineColor="#0b0b0c">
          {String(n)}
        </Text>
      </Billboard>
    </group>
  )
}

export function Viewport({ url, fitKey, mode, annotations, measureA, measureB, onPick }: {
  url: string | null
  fitKey: string | number    // changes only on version switch -> reframe (not on live drag)
  mode: Mode
  annotations: Annotation[]
  measureA: Pt | null
  measureB: Pt | null
  onPick: (p: Pt) => void
}) {
  return (
    <Canvas shadows camera={{ position: [90, 70, 90], fov: 45 }} style={{ background: '#0b0b0c' }}>
      <ambientLight intensity={0.55} />
      <directionalLight position={[60, 90, 40]} intensity={1.3} castShadow />
      <directionalLight position={[-40, 20, -30]} intensity={0.4} />
      <Grid infiniteGrid cellSize={5} sectionSize={25} cellColor="#2a2a2c"
            sectionColor="#3c3489" fadeDistance={500} fadeStrength={1.5} position={[0, -0.01, 0]} />

      {url && (
        <Bounds key={fitKey} fit clip observe margin={1.3}>
          <Model url={url} mode={mode} onPick={onPick} />
        </Bounds>
      )}

      {/* annotation pins — numbered to match the side-panel list */}
      {annotations.map((a, i) => <Pin key={a.id} p={[a.x, a.y, a.z]} n={i + 1} />)}

      {/* measurement endpoints */}
      {measureA && <Marker p={measureA} color="#ef9f27" r={1.8} />}
      {measureB && <Marker p={measureB} color="#ef9f27" r={1.8} />}

      <OrbitControls makeDefault />
      <GizmoHelper alignment="bottom-right" margin={[64, 64]}>
        <GizmoViewport axisColors={['#d85a30', '#639922', '#378add']} labelColor="#e8e8e6" />
      </GizmoHelper>
    </Canvas>
  )
}
