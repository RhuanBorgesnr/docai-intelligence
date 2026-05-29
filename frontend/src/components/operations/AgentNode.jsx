/**
 * AgentNode — a 3D sphere representing one agent in the operations scene.
 *
 * Colour conveys status:
 *   idle     → grey
 *   active   → green (pulsing)
 *   warning  → amber
 *   error    → red (pulsing fast)
 *
 * A floating label is rendered with Drei's <Html>.
 */
import React, { useRef, useMemo } from 'react'
import { useFrame } from '@react-three/fiber'
import { Html } from '@react-three/drei'

const STATUS_COLORS = {
  idle:    '#94a3b8',
  active:  '#22c55e',
  warning: '#f59e0b',
  error:   '#ef4444',
}

const ROLE_SCALE = {
  orchestrator: 1.0,
  agent:        0.65,
  operator:     0.65,
  gateway:      0.55,
  service:      0.55,
}

export default function AgentNode({ agent, onClick }) {
  const meshRef = useRef()
  const baseColor = STATUS_COLORS[agent.status] || STATUS_COLORS.idle
  const scale = ROLE_SCALE[agent.role] || 0.6

  // Pulsing animation for active / error
  useFrame(({ clock }) => {
    if (!meshRef.current) return
    const t = clock.getElapsedTime()
    if (agent.status === 'active') {
      meshRef.current.scale.setScalar(scale * (1 + Math.sin(t * 2) * 0.06))
    } else if (agent.status === 'error') {
      meshRef.current.scale.setScalar(scale * (1 + Math.sin(t * 6) * 0.1))
    } else {
      meshRef.current.scale.setScalar(scale)
    }
  })

  const emissive = agent.status === 'error' ? '#ff0000' : (agent.status === 'active' ? '#00ff00' : '#000000')

  return (
    <group position={agent.position}>
      <mesh
        ref={meshRef}
        onClick={(e) => { e.stopPropagation(); onClick?.(agent) }}
        castShadow
      >
        {agent.role === 'orchestrator'
          ? <dodecahedronGeometry args={[1, 0]} />
          : <sphereGeometry args={[1, 24, 24]} />
        }
        <meshStandardMaterial
          color={baseColor}
          emissive={emissive}
          emissiveIntensity={0.3}
          roughness={0.4}
          metalness={0.3}
        />
      </mesh>

      {/* Queue badge */}
      {agent.queue_size > 0 && (
        <Html position={[0.7, 0.7, 0]} center distanceFactor={8} zIndexRange={[10, 0]}>
          <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-bold text-white bg-blue-600 shadow-lg">
            {agent.queue_size}
          </span>
        </Html>
      )}

      {/* Error badge */}
      {agent.error_count > 0 && (
        <Html position={[-0.7, 0.7, 0]} center distanceFactor={8} zIndexRange={[10, 0]}>
          <span className="inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 rounded-full text-[10px] font-bold text-white bg-red-600 shadow-lg">
            {agent.error_count}
          </span>
        </Html>
      )}

      {/* Label */}
      <Html position={[0, -1.4 * scale, 0]} center distanceFactor={10} zIndexRange={[10, 0]}>
        <div className="text-center pointer-events-none select-none">
          <span className="text-[11px] font-semibold text-gray-800 bg-white/80 backdrop-blur-sm px-2 py-0.5 rounded shadow-sm whitespace-nowrap">
            {agent.label}
          </span>
        </div>
      </Html>
    </group>
  )
}
