/**
 * OperationsScene — the main React-Three-Fiber canvas that renders the
 * agent topology as a 3D scene.
 *
 * Features:
 *   - Orbit controls (drag to rotate, scroll to zoom)
 *   - Agent nodes with colour-coded status
 *   - Edges between connected agents
 *   - Animated event particles
 *   - Click on agent → callback to parent
 */
import React, { Suspense } from 'react'
import { Canvas } from '@react-three/fiber'
import { OrbitControls, PerspectiveCamera } from '@react-three/drei'
import AgentNode from './AgentNode'
import ConnectionLines from './ConnectionLines'
import EventParticles from './EventParticles'

export default function OperationsScene({ agents, events, onAgentClick }) {
  return (
    <div className="w-full h-[520px] rounded-xl overflow-hidden bg-gradient-to-b from-slate-900 to-slate-800 border border-slate-700 shadow-xl">
      <Canvas dpr={[1, 1.5]} gl={{ antialias: true, alpha: false }}>
        <PerspectiveCamera makeDefault position={[0, 0, 10]} fov={50} />
        <OrbitControls
          enablePan={false}
          minDistance={6}
          maxDistance={18}
          maxPolarAngle={Math.PI / 1.8}
        />
        <color attach="background" args={['#0f172a']} />
        <ambientLight intensity={0.5} />
        <directionalLight position={[5, 5, 5]} intensity={0.8} />
        <pointLight position={[0, 0, 4]} intensity={0.4} color="#60a5fa" />

        <Suspense fallback={null}>
          <ConnectionLines agents={agents} />
          {agents.map((agent) => (
            <AgentNode key={agent.id} agent={agent} onClick={onAgentClick} />
          ))}
          <EventParticles events={events} agents={agents} />
        </Suspense>

        {/* Subtle grid floor */}
        <gridHelper args={[20, 20, '#1e293b', '#1e293b']} position={[0, -4, 0]} />
      </Canvas>
    </div>
  )
}
