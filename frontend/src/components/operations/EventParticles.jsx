/**
 * EventParticles — animates small spheres traveling between agents to
 * represent recent events flowing through the system.
 *
 * Each event becomes a particle that lerps from source → target over ~2 s
 * then disappears.
 */
import React, { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import * as THREE from 'three'

const PARTICLE_LIFETIME = 2.0 // seconds
const MAX_PARTICLES = 15

export default function EventParticles({ events, agents }) {
  const posMap = useMemo(() => {
    const m = {}
    agents.forEach((a) => { m[a.id] = new THREE.Vector3(...a.position) })
    return m
  }, [agents])

  // Take the most recent N events
  const particles = useMemo(() => {
    return (events || []).slice(0, MAX_PARTICLES).map((evt, i) => ({
      id: i,
      from: posMap[evt.source] || posMap.jarvis,
      to: posMap[evt.target] || posMap.jarvis,
      offset: i * 0.35, // stagger start
    }))
  }, [events, posMap])

  return (
    <>
      {particles.map((p) => (
        <Particle key={p.id} from={p.from} to={p.to} offset={p.offset} />
      ))}
    </>
  )
}

function Particle({ from, to, offset }) {
  const ref = useRef()
  const temp = useMemo(() => new THREE.Vector3(), [])

  useFrame(({ clock }) => {
    if (!ref.current || !from || !to) return
    const t = ((clock.getElapsedTime() + offset) % PARTICLE_LIFETIME) / PARTICLE_LIFETIME
    temp.lerpVectors(from, to, t)
    ref.current.position.copy(temp)
    // Fade at edges
    const alpha = Math.sin(t * Math.PI)
    ref.current.material.opacity = alpha * 0.9
    ref.current.scale.setScalar(0.08 + alpha * 0.06)
  })

  return (
    <mesh ref={ref}>
      <sphereGeometry args={[1, 8, 8]} />
      <meshBasicMaterial color="#3b82f6" transparent depthWrite={false} />
    </mesh>
  )
}
