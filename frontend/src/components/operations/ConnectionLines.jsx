/**
 * ConnectionLines — renders edges between connected agents.
 *
 * Uses Drei's <Line> for crisp rendering.
 */
import React from 'react'
import { Line } from '@react-three/drei'

export default function ConnectionLines({ agents }) {
  const posMap = {}
  agents.forEach((a) => { posMap[a.id] = a.position })

  const edges = []
  const seen = new Set()
  agents.forEach((a) => {
    (a.connections || []).forEach((target) => {
      const key = [a.id, target].sort().join('→')
      if (seen.has(key) || !posMap[target]) return
      seen.add(key)
      edges.push({ from: posMap[a.id], to: posMap[target] })
    })
  })

  return (
    <>
      {edges.map((e, i) => (
        <Line
          key={i}
          points={[e.from, e.to]}
          color="#cbd5e1"
          lineWidth={1.5}
          opacity={0.6}
          transparent
        />
      ))}
    </>
  )
}
